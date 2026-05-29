"""
sql_ingestion.py — Phase 2: FastF1 native API → PostgreSQL ingestion

Pipeline:
  1. Get race schedule via FastF1 event schedule API
  2. Load all race + qualifying sessions in parallel via ThreadPoolExecutor
  3. Extract results from session.results DataFrame
  4. Bulk-insert into races, race_results, qualifying_results tables

Usage:
    python sql_ingestion.py
    python sql_ingestion.py --seasons 2021 2022 2023
"""

import argparse
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

import fastf1
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from config import ADMIN_CONN_STR, FASTF1_CACHE_DIR, FASTF1_SEASON_DELAY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("sql_ingestion")

os.makedirs(FASTF1_CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(FASTF1_CACHE_DIR)


def get_seasons_to_process(args_seasons: list[int] | None) -> list[int]:
    current_year = datetime.now().year
    if args_seasons:
        return sorted(set(args_seasons))
    return list(range(1950, current_year + 1))


def timedelta_to_seconds(td: Any) -> float | None:
    if td is None:
        return None
    if isinstance(td, pd.Timedelta) and pd.notna(td):
        return td.total_seconds()
    if isinstance(td, timedelta):
        return td.total_seconds()
    return None


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ── Database operations ─────────────────────────────────────────────────────

def upsert_races(races_rows: list[dict[str, Any]]) -> dict[tuple[int, int], int]:
    if not races_rows:
        return {}
    conn = psycopg2.connect(ADMIN_CONN_STR)
    try:
        cur = conn.cursor()
        values = [
            (r["season"], r["round"], r["race_name"], r.get("circuit"), r.get("date"))
            for r in races_rows
        ]
        fetched = execute_values(
            cur,
            """
            INSERT INTO races (season, round, race_name, circuit, date)
            VALUES %s
            ON CONFLICT (season, round) DO UPDATE
                SET race_name = EXCLUDED.race_name,
                    circuit    = EXCLUDED.circuit,
                    date       = EXCLUDED.date
            RETURNING race_id, season, round
            """,
            values,
            template="(%s, %s, %s, %s, %s::date)",
            fetch=True,
        )
        conn.commit()
        mapping: dict[tuple[int, int], int] = {}
        for row in fetched:
            mapping[(int(row[1]), int(row[2]))] = int(row[0])
        log.info("Upserted %d races", len(fetched))
        return mapping
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def bulk_insert_results(
    table: str,
    rows: list[dict[str, Any]],
    conflict_cols: list[str],
    insert_cols: list[str],
) -> int:
    if not rows:
        return 0
    # Deduplicate rows by conflict key to avoid ON CONFLICT DO UPDATE cardinality violation
    seen: set[tuple] = set()
    deduped: list[tuple] = []
    for r in rows:
        key = tuple(r[c] for c in conflict_cols)
        if key not in seen:
            seen.add(key)
            deduped.append(tuple(r[c] for c in insert_cols))
    if not deduped:
        return 0
    conn = psycopg2.connect(ADMIN_CONN_STR)
    try:
        cur = conn.cursor()
        placeholders = ", ".join(insert_cols)
        conflict_str = ", ".join(conflict_cols)
        update_str = ", ".join(f"{c} = EXCLUDED.{c}" for c in insert_cols if c not in conflict_cols)
        sql = f"""
            INSERT INTO {table} ({placeholders})
            VALUES %s
            ON CONFLICT ({conflict_str}) DO UPDATE SET {update_str}
        """
        execute_values(cur, sql, deduped)
        conn.commit()
        return len(deduped)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


# ── FastF1 native session loading ───────────────────────────────────────────

def _load_session(season: int, round_no: int, session_type: str) -> pd.DataFrame | None:
    try:
        session = fastf1.get_session(season, round_no, session_type)
        session.load(laps=False, telemetry=False, weather=False, messages=False)
        return session.results
    except Exception as exc:
        log.warning("  \u26a0 Failed to load %s %d R%d: %s", session_type, season, round_no, exc)
        return None


def extract_race_results(
    season: int, round_no: int, race_id: int
) -> list[dict[str, Any]] | None:
    df = _load_session(season, round_no, "R")
    if df is None or df.empty:
        return None
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        rows.append({
            "race_id": race_id,
            "driver_code": str(r.get("Abbreviation", "")),
            "driver_full_name": str(r.get("FullName", "")),
            "team_name": str(r.get("TeamName", "")),
            "grid_position": _safe_int(r.get("GridPosition")),
            "finishing_position": _safe_int(r.get("Position")),
            "points": float(r.get("Points", 0) or 0),
            "laps": _safe_int(r.get("Laps")),
            "status": str(r.get("Status", "")),
            "race_time_seconds": timedelta_to_seconds(r.get("Time")),
        })
    return rows


def extract_qualifying_results(
    season: int, round_no: int, race_id: int
) -> list[dict[str, Any]] | None:
    df = _load_session(season, round_no, "Q")
    if df is None or df.empty:
        return None
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        rows.append({
            "race_id": race_id,
            "driver_code": str(r.get("Abbreviation", "")),
            "driver_full_name": str(r.get("FullName", "")),
            "team_name": str(r.get("TeamName", "")),
            "position": _safe_int(r.get("Position")),
            "q1_seconds": timedelta_to_seconds(r.get("Q1")),
            "q2_seconds": timedelta_to_seconds(r.get("Q2")),
            "q3_seconds": timedelta_to_seconds(r.get("Q3")),
        })
    return rows


# ── Season processing ───────────────────────────────────────────────────────

def process_season(season: int) -> dict[str, int]:
    counts: dict[str, int] = {"races": 0, "race_results": 0, "qualifying_results": 0}
    log.info("\u2500" * 50)
    log.info("Processing season %d", season)

    # ── 1. Race schedule ────────────────────────────────────────────────
    try:
        schedule = fastf1.get_event_schedule(season)
    except Exception as exc:
        log.error("  \u2717 Failed to get schedule for %d: %s", season, exc)
        return counts

    race_events = schedule[~schedule["EventFormat"].isin(["testing"])].copy()
    if race_events.empty:
        race_events = schedule

    races_rows: list[dict[str, Any]] = []
    for _, ev in race_events.iterrows():
        try:
            round_no = int(ev["RoundNumber"])
            race_name = str(ev.get("EventName", "")).strip()
            circuit = str(ev.get("Location", "")).strip()
            date_val = ev.get("EventDate")
            date_str = date_val.strftime("%Y-%m-%d") if date_val is not None and hasattr(date_val, "strftime") else None
            races_rows.append({
                "season": season,
                "round": round_no,
                "race_name": race_name or f"Round {round_no}",
                "circuit": circuit,
                "date": date_str,
            })
        except (ValueError, KeyError) as exc:
            log.warning("  \u26a0 Skipping event row: %s", exc)

    if not races_rows:
        log.warning("  \u26a0 No races found for season %d", season)
        return counts

    races_map = upsert_races(races_rows)
    counts["races"] = len(races_map)

    # ── 2. Parallel: load all race + quali sessions ──────────────────────
    race_tasks: list[tuple[int, int, int]] = []
    quali_tasks: list[tuple[int, int, int]] = []
    for row in races_rows:
        round_no = row["round"]
        race_id = races_map.get((season, round_no))
        if race_id is None:
            continue
        race_tasks.append((season, round_no, race_id))
        quali_tasks.append((season, round_no, race_id))

    def load_race(t: tuple[int, int, int]) -> list[dict[str, Any]] | None:
        s, r, rid = t
        return extract_race_results(s, r, rid)

    def load_quali(t: tuple[int, int, int]) -> list[dict[str, Any]] | None:
        s, r, rid = t
        return extract_qualifying_results(s, r, rid)

    all_results: list[list[dict[str, Any]]] = []
    all_qualis: list[list[dict[str, Any]]] = []

    with ThreadPoolExecutor(max_workers=8) as pool:
        race_futs = {pool.submit(load_race, t): t for t in race_tasks}
        quali_futs = {pool.submit(load_quali, t): t for t in quali_tasks}

        for fut in as_completed(race_futs):
            result = fut.result()
            if result:
                all_results.append(result)

        for fut in as_completed(quali_futs):
            result = fut.result()
            if result:
                all_qualis.append(result)

    # ── 3. Bulk insert all results ───────────────────────────────────────
    if all_results:
        flat_results = [row for batch in all_results for row in batch]
        if flat_results:
            counts["race_results"] = bulk_insert_results(
                table="race_results",
                rows=flat_results,
                conflict_cols=["race_id", "driver_code"],
                insert_cols=[
                    "race_id", "driver_code", "driver_full_name", "team_name",
                    "grid_position", "finishing_position", "points", "laps",
                    "status", "race_time_seconds",
                ],
            )

    if all_qualis:
        flat_qualis = [row for batch in all_qualis for row in batch]
        if flat_qualis:
            counts["qualifying_results"] = bulk_insert_results(
                table="qualifying_results",
                rows=flat_qualis,
                conflict_cols=["race_id", "driver_code"],
                insert_cols=[
                    "race_id", "driver_code", "driver_full_name", "team_name",
                    "position", "q1_seconds", "q2_seconds", "q3_seconds",
                ],
            )

    log.info(
        "  Season %d done \u2014 races=%d, race_results=%d, qualifying=%d",
        season,
        counts["races"],
        counts["race_results"],
        counts["qualifying_results"],
    )
    return counts


# ── Main ────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest F1 race and qualifying data from FastF1 into PostgreSQL."
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        help="Specific seasons to process (default: all 1950\u2013present)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seasons = get_seasons_to_process(args.seasons)

    total_counts: dict[str, int] = {"races": 0, "race_results": 0, "qualifying_results": 0}

    for season in seasons:
        counts = process_season(season)
        for k in total_counts:
            total_counts[k] += counts.get(k, 0)
        time.sleep(FASTF1_SEASON_DELAY)

    log.info("=" * 50)
    log.info("Ingestion complete \u2014 totals: %s", total_counts)


if __name__ == "__main__":
    main()
