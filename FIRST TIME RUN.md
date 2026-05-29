# Halos AI — Runbook
# This is the guide, If you are running this in your system for the first time.

## 1. Prerequisites

- Python 3.10+
- Node.js 20+
- PostgreSQL 15+ with pgvector

---

## 2. Python Backend Setup

```powershell
# From project root (C:\Users\LVST\Desktop\vinesh\Halos Ai)

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser engine
playwright install chromium
```

---

## 3. PostgreSQL Setup

```powershell
# Connect to PostgreSQL and set up database
psql -U postgres -c "CREATE DATABASE halos_f1;"
psql -U postgres -d halos_f1 -c "CREATE EXTENSION vector;"

# Create read-only user for SQL agent safety
psql -U postgres -d halos_f1 -c "CREATE USER halos_readonly WITH PASSWORD 'your_password_here';"
psql -U postgres -d halos_f1 -c "GRANT CONNECT ON DATABASE halos_f1 TO halos_readonly;"
psql -U postgres -d halos_f1 -c "GRANT USAGE ON SCHEMA public TO halos_readonly;"
psql -U postgres -d halos_f1 -c "GRANT SELECT ON ALL TABLES IN SCHEMA public TO halos_readonly;"
```

---

## 4. Configure Environment

Edit `.env` with your credentials:

| Variable | What to put |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key |
| `DB_HOST` | `localhost` (or your PostgreSQL host) |
| `DB_PORT` | `5432` |
| `DB_NAME` | `halos_f1` |
| `DB_USER` | `halos_app` |
| `DB_PASSWORD` | Password for halos_app user |
| `DB_USER_READONLY` | `halos_readonly` |
| `DB_PASSWORD_READONLY` | Password for halos_readonly user |

---

## 5. Create Database Tables

```powershell
python db_schema.py
```

---

## 6. Ingest Data (one-time, run in order)

```powershell
# Phase 1 — Scrape Wikipedia, chunk, embed with OpenAI, store in pgvector
python rag_ingestion.py

# Phase 2 — Ingest all F1 seasons (1950–present) into relational tables
python sql_ingestion.py

# Optional: ingest specific seasons only
python sql_ingestion.py --seasons 2023 2024
```

---

## 7. Frontend Setup

```powershell
cd frontend
npm install
cd ..
```

---

## 8. Run the App (two terminals)

### Terminal 1 — Python API Server

```powershell
.\venv\Scripts\activate
# Start your API server (e.g. FastAPI, Flask) on port 8000
# Example: python -m uvicorn api_server:app --reload --port 8000
```

### Terminal 2 — React Dev Server

```powershell
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## 9. Test the SQL Agent (CLI)

```powershell
.\venv\Scripts\activate
python sql_agent.py "Who won the 2023 Monaco Grand Prix?"
python sql_agent.py --interactive
```

---

## 10. Production Build

```powershell
cd frontend
npm run build
# Output: frontend/dist/  — serve this with any static server
```

---

## Quick Command Summary

| Step | Command |
|---|---|
| Activate venv | `.\venv\Scripts\activate` |
| Create tables | `python db_schema.py` |
| Scrape + embed | `python rag_ingestion.py` |
| Ingest F1 stats | `python sql_ingestion.py` |
| Start frontend | `cd frontend && npm run dev` |
| Test SQL agent | `python sql_agent.py "question"` |
| Build frontend | `cd frontend && npm run build` |
