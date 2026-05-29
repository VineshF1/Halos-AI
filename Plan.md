# Halos AI — Formula 1 Hybrid Chatbot

## Overview

Hybrid AI chatbot for Formula 1 that routes queries through two pipelines:
- **RAG (Retrieval-Augmented Generation)** — for trivia, history, rules, and unstructured facts
- **Text-to-SQL** — for statistics, standings, race results, and numerical data

A classifier in `app.py` decides which pipeline to use based on the query.

---

## Tech Stack

### Frontend
| Tool | Purpose |
|---|---|
| **React 18** | UI framework |
| **TypeScript** | Type safety |
| **Vite 6** | Bundler & dev server |
| **Tailwind CSS 3** | Utility-first styling |
| **Framer Motion** | Falling pattern animation |
| **shadcn/ui** | Component architecture (cn utility) |

### Backend
| Tool | Purpose |
|---|---|
| **Python 3.10+** | Runtime |
| **FastAPI** | REST API server |
| **Uvicorn** | ASGI server |
| **OpenAI SDK** | LLM calls (DeepSeek V4 via OpenRouter / NVIDIA Nvidia NV-Embed-v1) |
| **LangChain Text Splitters** | Document chunking |
| **Playwright** | Web scraping (Wikipedia, FIA PDFs, news) |
| **FastF1** | Structured F1 data (lap times, standings, results) |
| **psycopg2** | PostgreSQL driver |

### Database
| Tool | Purpose |
|---|---|
| **PostgreSQL 15+** | Primary database |
| **pgvector** | Vector similarity search (for RAG embeddings) |

---

## Architecture

```
┌─────────────┐     POST /api/chat     ┌──────────────────┐
│  React/Vite  │ ◄──────────────────► │  FastAPI (app.py) │
│  localhost:   │                      │  localhost:8000   │
│  5173         │                      │                  │
└─────────────┘                      └────────┬─────────┘
                                              │
                              ┌───────────────┴───────────────┐
                              │         Query Classifier       │
                              │   (keyword + regex matching)   │
                              └───────┬───────────────┬───────┘
                                      │               │
                              ┌───────┴───────┐ ┌─────┴──────────┐
                              │   RAG Path    │ │  Text-to-SQL   │
                              │  (trivia)     │ │  (stats)       │
                              └───────┬───────┘ └───────┬────────┘
                                      │                  │
                              ┌───────┴───────┐  ┌──────┴─────────┐
                              │  Embed query   │  │  LLM → SQL     │
                              │  pgvector      │  │  Execute SQL   │
                              │  top-k         │  │  Format answer │
                              │  LLM answer    │  │                │
                              └───────┬───────┘  └──────┬─────────┘
                                      │                  │
                              ┌───────┴──────────────────┴───────┐
                              │       PostgreSQL (pgvector)       │
                              │  ┌──────────┐  ┌───────────────┐  │
                              │  │ embeddings │  │  F1 stats     │  │
                              │  │ (pgvector) │  │  (relational) │  │
                              │  └──────────┘  └───────────────┘  │
                              └────────────────────────────────────┘
```

### RAG Pipeline Flow

```
Wikipedia URLs ──► Playwright scrape ──► clean text
                                              │
                                              ▼
                                    LangChain text splitter
                                    (chunk: 1000, overlap: 200)
                                              │
                                              ▼
                                    NVIDIA NV-Embed-v1
                                    (OpenAI-compatible API)
                                              │
                                              ▼
                                    pgvector (cosine search)
                                              │
                                              ▼
                                    Top-k chunks + query
                                    ──► DeepSeek V4 (OpenRouter)
                                              │
                                              ▼
                                    Final answer
```

### Text-to-SQL Pipeline Flow

```
FastF1 package ──► Download season data ──► Ingest into relational tables
                                                    │
                                                    ▼
User query ──► DeepSeek V4 generates SQL ──► Execute on read-only PostgreSQL
                                                    │
                                                    ▼
                                    Format result ──► Natural language answer
```

---

## Project Structure

```
Halos Ai/
├── app.py                  # FastAPI server + query routing
├── config.py               # Environment config
├── db_schema.py            # PostgreSQL schema setup
├── rag_ingestion.py        # Web scrape → chunk → embed → pgvector
├── sql_ingestion.py        # FastF1 → relational tables
├── sql_agent.py            # Text-to-SQL agent (LLM → SQL → result)
├── requirements.txt        # Python dependencies
├── urls.txt                # Wikipedia URLs for RAG ingestion
├── .gitignore
├── fastf1_cache/           # FastF1 API cache (28 MB)
├── venv/                   # Python virtual environment
│
└── frontend/
    ├── index.html
    ├── package.json
    ├── tailwind.config.js
    ├── vite.config.ts
    ├── tsconfig.json
    ├── public/
    │   └── logo.png        # F1 logo (user-managed)
    └── src/
        ├── main.tsx         # Entry point
        ├── App.tsx          # Root component
        ├── index.css        # Tailwind + CSS variables
        ├── types.ts         # TypeScript interfaces
        ├── api.ts           # Backend API client
        ├── lib/utils.ts     # cn() utility
        └── components/
            ├── ChatInterface.tsx    # Main chat layout + background
            ├── ChatMessage.tsx      # Message bubble component
            ├── ChatInput.tsx        # Input form + send button
            ├── TypingIndicator.tsx   # Loading animation
            ├── WelcomeScreen.tsx    # Landing greeting
            └── ui/
                └── falling-pattern.tsx  # Animated background
```

---

## What We Built

### Frontend
- **Chat interface** with pitch-black theme and animated falling particle background
- **Message bubbles** with chat-app style (user right-aligned, AI left-aligned)
- **Welcome screen** with Oswald display font and decorative red accents
- **Typing indicator** for loading state
- **Responsive layout** — works on desktop and mobile

### Backend
- **FastAPI server** with CORS, single `/api/chat` endpoint
- **Query classifier** — detects if question is about stats or trivia
- **RAG pipeline** — Playwright scrapes Wikipedia → LangChain chunks → NVIDIA embeddings → pgvector search → DeepSeek V4 answers
- **Text-to-SQL pipeline** — DeepSeek V4 generates SQL → executes on read-only PostgreSQL → formats results
- **SQL agent safety** — uses read-only database user, query timeouts

### Database
- **pgvector** for 4096-dimension embedding similarity search
- **Relational tables** for structured F1 data (seasons, races, results, drivers, constructors, lap times, pit stops)
- **Read-only user** for SQL agent to prevent writes

### Data Ingestion (one-time)
- Scraped 68 Wikipedia URLs for F1 knowledge base
- Ingested 76 years of F1 data (1950–2026) via FastF1
- Embedded all chunks into pgvector for semantic search
