"""
app.py — FastAPI backend for Halos F1 AI Chatbot

Endpoints:
  POST /api/chat  — hybrid RAG (Wikipedia trivia) + Text-to-SQL (statistics)

Architecture:
  1. Classify query as "stats" or "trivia"
  2. Stats  → sql_agent.py (DeepSeek V4 → SQL → pg read-only)
  3. Trivia → embed query → pgvector search → DeepSeek V4 answer
"""

import json
import logging
import os
import re
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel

from config import (
    ADMIN_CONN_STR,
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    NVIDIA_EMBEDDING_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
    LLM_MAX_TOKENS_RESPONSE,
    READONLY_CONN_STR,
    SQL_QUERY_TIMEOUT_SECONDS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("halos_api")

app = FastAPI(title="Halos F1 AI")
_CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,https://halos-ai.vercel.app").split(",")
_REFERER = os.getenv("HTTP_REFERER", "https://halos-ai.vercel.app")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI-compatible clients
nvidia_client = OpenAI(api_key=NVIDIA_API_KEY, base_url=NVIDIA_BASE_URL)
llm_client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL,
                    default_headers={"HTTP-Referer": _REFERER, "X-Title": "Halos F1 AI"})


# ── Schema ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = []

class ChatResponse(BaseModel):
    reply: str


# ── Query classifier ─────────────────────────────────────────────────────────

_STATS_PATTERN = re.compile(
    r"\b(win|won|winner|champion|championship|point|pole|podium|finish|fastest lap"
    r"|dnf|retire|crash|grid|qualif|season|standings|constructor|driver.*title"
    r"|race.*result|grand prix|monaco|bahrain|silverstone|spa|monza|suzuka"
    r"|record|consecutive|streak|hat trick|grand slam"
    r"|time\s+champion|world\s+champion|title|standings)\b",
    re.IGNORECASE,
)

_CHAMPIONSHIP_PATTERN = re.compile(
    r"(time\s+champion|world\s+champion|championship|title|standings|leader)",
    re.IGNORECASE,
)

def classify_query(text: str) -> str:
    stats_matches = _STATS_PATTERN.findall(text)
    is_championship = bool(_CHAMPIONSHIP_PATTERN.search(text))
    score = len(stats_matches)
    if is_championship:
        score += 1
    year_match = re.search(r"\b(19|20)\d{2}\b", text)
    if year_match:
        score += 1
    return "stats" if score >= 1 else "trivia"


# ── Embedding ────────────────────────────────────────────────────────────────

def embed_text(text: str) -> list[float]:
    resp = nvidia_client.embeddings.create(
        model=NVIDIA_EMBEDDING_MODEL,
        input=text,
        extra_body={"input_type": "query"},
    )
    return resp.data[0].embedding


# ── RAG search ───────────────────────────────────────────────────────────────

_RAG_SYSTEM = """You are an F1 expert. Answer based ONLY on the provided context. If the context lacks the answer, say so honestly. Be concise."""

def search_knowledge(query_embedding: list[float], limit: int = 5) -> list[dict[str, Any]]:
    conn = psycopg2.connect(ADMIN_CONN_STR)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT content, url, chunk_index,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM knowledge_chunks
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (query_embedding, query_embedding, limit))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

def rag_answer(question: str) -> str:
    emb = embed_text(question)
    docs = search_knowledge(emb)
    if not docs:
        return "I don't have information about that in my knowledge base."

    context = "\n\n---\n\n".join(
        f"Source: {d['url']} (chunk {d['chunk_index']})\n{d['content']}"
        for d in docs
        if d.get("content")
    )
    resp = llm_client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": _RAG_SYSTEM},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
        temperature=0.3,
        max_tokens=LLM_MAX_TOKENS_RESPONSE,
    )
    content = resp.choices[0].message.content
    return content.strip() if content else "No answer available."


# ── SQL agent integration ────────────────────────────────────────────────────

_DESTRUCTIVE_PATTERN = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE|CREATE|REPLACE"
    r"|GRANT|REVOKE|EXECUTE|CALL|MERGE|LOAD)\b", re.IGNORECASE)

_SQL_SYSTEM = f"""You are an F1 statistician. Given a question, generate a PostgreSQL SELECT query.

Tables:
- races(race_id, season, round, race_name, circuit, date)
- race_results(result_id, race_id, driver_code, driver_full_name, team_name, grid_position, finishing_position, points, laps, status, race_time_seconds)
- qualifying_results(qualifying_id, race_id, driver_code, driver_full_name, team_name, position, q1_seconds, q2_seconds, q3_seconds)

Rules:
- Output ONLY the SQL query, no explanation.
- Join using race_id.
- Use ILIKE for fuzzy text.
- finishing_position=1 = winner.
- driver_code is 3-letter (VER, HAM, LEC).
- Do NOT use LIMIT unless asked."""

def _validate_sql(sql: str) -> str | None:
    s = sql.strip().rstrip(";").strip()
    if not s:
        return "Empty SQL."
    if not re.match(r"^\s*(SELECT|WITH)\s", s, re.IGNORECASE):
        return "Only SELECT permitted."
    if _DESTRUCTIVE_PATTERN.search(s):
        return "Destructive SQL not allowed."
    return None

def sql_answer(question: str) -> str:
    # Generate SQL
    resp = llm_client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": _SQL_SYSTEM},
            {"role": "user", "content": question},
        ],
        temperature=0,
        max_tokens=500,
    )
    sql = resp.choices[0].message.content.strip()
    m = re.search(r"```(?:sql)?\s*\n?(.*?)```", sql, re.DOTALL | re.IGNORECASE)
    if m:
        sql = m.group(1).strip()
    sql = sql.strip("` \n\t\r")

    err = _validate_sql(sql)
    if err:
        return f"Could not generate a valid query: {err}"

    # Execute
    conn = psycopg2.connect(READONLY_CONN_STR)
    try:
        cur = conn.cursor()
        cur.execute(f"SET statement_timeout = '{SQL_QUERY_TIMEOUT_SECONDS * 1000}'")
        cur.execute(sql)
        cols = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchall()
        results = [dict(zip(cols, r)) for r in rows]
    except Exception as exc:
        return f"Query error: {exc}"
    finally:
        cur.close()
        conn.close()

    # Format answer
    resp2 = llm_client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": "You are an F1 statistician. Answer concisely from the data."},
            {"role": "user", "content": f"Question: {question}\nSQL: {sql}\nResults: {json.dumps(results, default=str)}"},
        ],
        temperature=0.3,
        max_tokens=LLM_MAX_TOKENS_RESPONSE,
    )
    content = resp2.choices[0].message.content
    return content.strip() if content else "No answer available."


# ── Chat endpoint ────────────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        query_type = classify_query(req.message)
        log.info("Query type=%s | message=%s", query_type, req.message[:80])

        if query_type == "stats":
            reply = sql_answer(req.message)
            # If SQL returned nothing useful, fall back to RAG
            if not reply or "no results" in reply.lower() or "no data" in reply.lower():
                log.info("SQL returned empty, falling back to RAG")
                reply = rag_answer(req.message)
        else:
            reply = rag_answer(req.message)

        return ChatResponse(reply=reply)
    except Exception as exc:
        log.error("Chat error: %s", exc, exc_info=True)
        err_str = str(exc).lower()
        if any(kw in err_str for kw in ["could not translate host", "connection refused", "could not connect", "name or service not known"]):
            detail = "Database unavailable — Supabase may be paused. Go to supabase.com/dashboard to unpause it, then refresh."
        else:
            detail = str(exc)
        raise HTTPException(status_code=500, detail=detail)


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "Halos F1 AI", "status": "running"}

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
