# Halos AI — Formula 1 Chatbot 🏎️

Talk to an AI about anything Formula 1. Ask about race winners, championship standings, history, rules, or driver stats — the bot automatically picks the right data source.

## How It Works

```
You ask a question
        │
        ▼
  Classifier decides:
  "stats" or "trivia"
        │
    ┌───┴───┐
    ▼       ▼
  SQL    RAG (vector
  query  search on
         Wikipedia)
    │       │
    └───┬───┘
        ▼
    Natural language answer
```

- **Trivia questions** (history, rules, explanations) → search Wikipedia chunks stored in a vector database → answer with LLM
- **Stats questions** (standings, winners, lap times) → LLM writes SQL → runs on a read-only database → formats the result

## Tech Stack

**Frontend:** React, TypeScript, Vite, Tailwind CSS, Framer Motion  
**Backend:** Python, FastAPI, DeepSeek V4 (via OpenRouter), NVIDIA NV-Embed-v1  
**Database:** PostgreSQL + pgvector  
**Data:** Playwright (web scraping), FastF1 (racing stats)

## Features

- Pitch-black UI with animated falling particle background
- Hybrid RAG + Text-to-SQL for accurate answers
- Read-only SQL agent (safe by design)
- 6 years of F1 data (2021–2026)
