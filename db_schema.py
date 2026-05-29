"""
db_schema.py — Creates all PostgreSQL tables and indexes.

Run this ONCE (drops existing data):
    python db_schema.py
"""

import psycopg2
from config import ADMIN_CONN_STR

CREATE_EXTENSION = """CREATE EXTENSION IF NOT EXISTS vector;"""

DROP_TABLES_ORDERED = """
DROP TABLE IF EXISTS qualifying_results CASCADE;
DROP TABLE IF EXISTS race_results      CASCADE;
DROP TABLE IF EXISTS races             CASCADE;
DROP TABLE IF EXISTS knowledge_chunks  CASCADE;
"""

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id          SERIAL PRIMARY KEY,
    url         TEXT NOT NULL,
    chunk_index INT  NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(4096),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS races (
    race_id   SERIAL PRIMARY KEY,
    season    INT  NOT NULL,
    round     INT  NOT NULL,
    race_name TEXT NOT NULL,
    circuit   TEXT,
    date      DATE,
    UNIQUE (season, round)
);

CREATE TABLE IF NOT EXISTS race_results (
    result_id          SERIAL PRIMARY KEY,
    race_id            INT  NOT NULL REFERENCES races(race_id) ON DELETE CASCADE,
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

CREATE TABLE IF NOT EXISTS qualifying_results (
    qualifying_id   SERIAL PRIMARY KEY,
    race_id         INT  NOT NULL REFERENCES races(race_id) ON DELETE CASCADE,
    driver_code     VARCHAR(3),
    driver_full_name TEXT,
    team_name       TEXT,
    position        INT,
    q1_seconds      FLOAT,
    q2_seconds      FLOAT,
    q3_seconds      FLOAT,
    UNIQUE (race_id, driver_code)
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_race_results_race_id   ON race_results(race_id);
CREATE INDEX IF NOT EXISTS idx_qualifying_race_id     ON qualifying_results(race_id);
CREATE INDEX IF NOT EXISTS idx_races_season           ON races(season);
"""


def run() -> None:
    conn = psycopg2.connect(ADMIN_CONN_STR)
    conn.autocommit = True
    cur = conn.cursor()

    print("Creating pgvector extension ...")
    cur.execute(CREATE_EXTENSION)

    print("Dropping old tables ...")
    cur.execute(DROP_TABLES_ORDERED)

    print("Creating tables ...")
    cur.execute(CREATE_TABLES)

    print("Creating indexes ...")
    cur.execute(CREATE_INDEXES)

    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    run()
