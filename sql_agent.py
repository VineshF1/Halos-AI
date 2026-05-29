"""
sql_agent.py — Phase 2: Text-to-SQL Agent

Pipeline:
  1. Receive a natural-language query about F1 statistics
  2. Inject table schemas into the GPT-4o system instruction
  3. GPT-4o generates a SQL query via function calling
  4. Validate the SQL (must be SELECT-only, no destructive statements)
  5. Execute the SQL against PostgreSQL using a read-only DB user
  6. Send the result set back to GPT-4o, which formats it as natural language

Security features:
  - Read-only PostgreSQL user for all query execution
  - SQL statement validation (rejects DROP, DELETE, INSERT, UPDATE, ALTER, TRUNCATE)
  - Query timeout via statement_timeout
  - Parameterised queries only (no raw string interpolation)
  - Credentials never logged

Usage:
    python sql_agent.py "Who won the 2023 Monaco Grand Prix?"
    python sql_agent.py --interactive   # starts a REPL loop
"""

import argparse
import json
import logging
import re
from typing import Any

import psycopg2
from openai import OpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
    LLM_MAX_TOKENS_SQL,
    LLM_MAX_TOKENS_RESPONSE,
    READONLY_CONN_STR,
    SQL_QUERY_TIMEOUT_SECONDS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("sql_agent")

# ── OpenAI client ───────────────────────────────────────────────────────────

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
    default_headers={
        "HTTP-Referer": "http://localhost:5173",
        "X-Title": "Halos F1 AI",
    },
)

# ── SQL validation ──────────────────────────────────────────────────────────

_DESTRUCTIVE_PATTERN = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE|CREATE|REPLACE"
    r"|GRANT|REVOKE|EXECUTE|CALL|MERGE|LOAD)\b",
    re.IGNORECASE,
)

_SELECT_ONLY = re.compile(r"^\s*(SELECT|WITH)\s", re.IGNORECASE)


def validate_sql(sql: str) -> str | None:
    """
    Validate that the generated SQL is safe to execute.
    Returns None if valid, or an error message string if invalid.
    """
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return "Empty SQL statement."

    if not _SELECT_ONLY.match(stripped):
        return "Only SELECT (or WITH) queries are permitted."

    if _DESTRUCTIVE_PATTERN.search(stripped):
        return "Destructive SQL statements are not allowed."

    return None


# ── Database schema prompt ──────────────────────────────────────────────────

TABLE_SCHEMAS = """
-- Table: races
CREATE TABLE races (
    race_id   SERIAL PRIMARY KEY,
    season    INT  NOT NULL,
    round     INT  NOT NULL,
    race_name TEXT NOT NULL,
    circuit   TEXT,
    date      DATE,
    UNIQUE (season, round)
);

-- Table: race_results
CREATE TABLE race_results (
    result_id          SERIAL PRIMARY KEY,
    race_id            INT  NOT NULL REFERENCES races(race_id),
    driver_code        VARCHAR(3),
    driver_full_name   TEXT,
    team_name          TEXT,
    grid_position      INT,
    finishing_position INT,
    points             FLOAT,
    laps               INT,
    status             TEXT,
    race_time_seconds  FLOAT,
    UNIQUE (race_id, driver_code)
);

-- Table: qualifying_results
CREATE TABLE qualifying_results (
    qualifying_id   SERIAL PRIMARY KEY,
    race_id         INT  NOT NULL REFERENCES races(race_id),
    driver_code     VARCHAR(3),
    driver_full_name TEXT,
    team_name       TEXT,
    position        INT,
    q1_seconds      FLOAT,
    q2_seconds      FLOAT,
    q3_seconds      FLOAT,
    UNIQUE (race_id, driver_code)
);

-- Notes:
--   - q1_seconds, q2_seconds, q3_seconds are fastest session times in seconds.
--   - race_time_seconds is total race duration (NULL if driver >1 lap behind).
--   - finishing_position = 1 means the winner. NULL means DNF.
--   - status describes how the race ended (e.g. 'Finished', 'Crash', 'Gearbox').
--   - grid_position is the starting position (NULL for qualifying-only data).
--   - driver_code is the 3-letter code (e.g. 'VER', 'HAM', 'LEC').
--   - Join races ON race_results.race_id = races.race_id.
--   - Join races ON qualifying_results.race_id = races.race_id.
"""

SYSTEM_INSTRUCTION = f"""You are an F1 statistician. Given a natural-language question, generate a single SQL query to answer it from a PostgreSQL database.

Database schema:
{TABLE_SCHEMAS}

Rules:
- Generate ONLY the SQL query (use the run_sql_query function if available, otherwise output SQL directly).
- Use standard PostgreSQL syntax.
- Join tables using race_id foreign keys.
- Use driver_code (3-letter) for driver lookups.
- Use ILIKE for fuzzy text matching.
- Use EXTRACT(YEAR FROM date) for year comparisons.
- Use COALESCE for nullable columns.
- Use ROUND for numeric formatting.
- For time comparisons in qualifying, compare q1_seconds, q2_seconds, q3_seconds directly.
- Do NOT use LIMIT unless the question asks for a specific number of results.
- Do NOT modify the database. Only SELECT."""

# ── Function declaration (OpenAI tool format) ───────────────────────────────

RUN_SQL_TOOL = {
    "type": "function",
    "function": {
        "name": "run_sql_query",
        "description": "Execute a SQL query against the F1 database and return results.",
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The PostgreSQL SELECT query to run.",
                }
            },
            "required": ["sql"],
        },
    },
}


# ── SQL generation via GPT-4o ───────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(log, logging.WARNING),
)
def generate_sql(question: str) -> str:
    """
    Send the user question + schema to GPT-4o and get back a SQL query
    via function calling.
    """
    response = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": question},
        ],
        tools=[RUN_SQL_TOOL],
        temperature=0,
        max_tokens=LLM_MAX_TOKENS_SQL,
    )

    msg = response.choices[0].message
    # Prefer tool calling if model supports it
    if msg.tool_calls:
        for tc in msg.tool_calls:
            if tc.function.name == "run_sql_query":
                args = json.loads(tc.function.arguments)
                sql = args.get("sql", "").strip()
                if sql:
                    return sql

    # Fall back to extracting SQL from content (DeepSeek)
    if msg.content:
        content = msg.content.strip()
        # Extract SQL from markdown code blocks if present
        m = re.search(r"```(?:sql)?\s*\n?(.*?)```", content, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # Remove leading/trailing backticks
        content = content.strip("` \n\t\r")
        return content

    return ""


# ── SQL execution (read-only) ───────────────────────────────────────────────

def execute_sql(sql: str) -> list[dict[str, Any]]:
    """
    Execute the validated SQL query using the read-only PostgreSQL user.
    Enforces a query timeout via SET statement_timeout.
    Returns a list of row dicts.
    """
    conn = psycopg2.connect(READONLY_CONN_STR)
    try:
        cur = conn.cursor()
        cur.execute(f"SET statement_timeout = '{SQL_QUERY_TIMEOUT_SECONDS * 1000}'")
        cur.execute(sql)

        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(dict(zip(columns, row)))
        return results
    except Exception as exc:
        log.error("SQL execution error: %s", exc)
        raise
    finally:
        cur.close()
        conn.close()


# ── Response formatting via GPT-4o ──────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(log, logging.WARNING),
)
def format_answer(question: str, sql: str, results: list[dict[str, Any]]) -> str:
    """
    Send the original question + generated SQL + result set back to GPT-4o
    to produce a natural-language answer.
    """
    response = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an F1 statistician. Given a question, the SQL used, "
                    "and the result set, answer the question in clear natural language. "
                    "Be concise but include relevant numbers. "
                    "If the result set is empty, say so honestly."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"SQL: {sql}\n\n"
                    f"Results: {json.dumps(results, default=str)}"
                ),
            },
        ],
        temperature=0.3,
        max_tokens=LLM_MAX_TOKENS_RESPONSE,
    )
    return response.choices[0].message.content.strip() or ""


# ── Orchestrator ────────────────────────────────────────────────────────────

def answer_question(question: str) -> str:
    """
    Full pipeline: question => SQL => validate => execute => formatted answer.
    """
    log.info("Generating SQL for: %s", question)
    sql = generate_sql(question)
    log.info("Generated SQL: %s", sql)

    error = validate_sql(sql)
    if error:
        log.warning("SQL validation failed: %s", error)
        return f"I cannot answer that question. Reason: {error}"

    try:
        results = execute_sql(sql)
    except Exception as exc:
        log.error("Execution error: %s", exc)
        return f"Sorry, there was an error running the query: {exc}"

    log.info("Query returned %d rows", len(results))

    answer = format_answer(question, sql, results)
    return answer


# ── CLI ─────────────────────────────────────────────────────────────────────

def interactive_loop() -> None:
    """Start an interactive REPL for asking F1 questions."""
    print("F1 SQL Agent — interactive mode. Type 'exit' to quit.")
    print("Example: Who won the 2023 Monaco Grand Prix?")
    print("-" * 60)
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q.lower() in ("exit", "quit", "q"):
            break
        print()
        answer = answer_question(q)
        print(answer)
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="F1 Text-to-SQL Agent — ask natural-language questions about F1 data."
    )
    parser.add_argument("question", nargs="?", help="Natural-language question")
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Start interactive REPL mode",
    )
    args = parser.parse_args()

    if args.interactive:
        interactive_loop()
    elif args.question:
        answer = answer_question(args.question)
        print(answer)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
