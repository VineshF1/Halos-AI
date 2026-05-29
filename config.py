import os
from dotenv import load_dotenv

load_dotenv()

# ── PostgreSQL — admin ──────────────────────────────────────────────────────
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "halos_f1")
DB_USER = os.getenv("DB_USER", "halos_app")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL:
    ADMIN_CONN_STR = DATABASE_URL
else:
    ADMIN_CONN_STR = (
        f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME} "
        f"user={DB_USER} password={DB_PASSWORD}"
    )

# ── PostgreSQL — read-only (SQL agent safety) ──────────────────────────────
READONLY_URL = os.getenv("READONLY_URL", "")
if READONLY_URL:
    READONLY_CONN_STR = READONLY_URL
else:
    DB_USER_READONLY = os.getenv("DB_USER_READONLY", "halos_readonly")
    DB_PASSWORD_READONLY = os.getenv("DB_PASSWORD_READONLY", "")
    READONLY_CONN_STR = (
        f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME} "
        f"user={DB_USER_READONLY} password={DB_PASSWORD_READONLY}"
    )

# ── NVIDIA NV-Embed-v1 (OpenAI-compatible API) ──────────────────────────────
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_EMBEDDING_MODEL = "nvidia/nv-embed-v1"

# ── OpenRouter (DeepSeek V4 for SQL agent) ────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LLM_MAX_TOKENS_SQL = 500
LLM_MAX_TOKENS_RESPONSE = 1000

# ── RAG chunking ────────────────────────────────────────────────────────────
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

# ── Rate limiting ───────────────────────────────────────────────────────────
PLAYWRIGHT_NAV_DELAY = float(os.getenv("PLAYWRIGHT_NAV_DELAY", "0.5"))
FASTF1_SEASON_DELAY = float(os.getenv("FASTF1_SEASON_DELAY", "0.5"))
SQL_QUERY_TIMEOUT_SECONDS = int(os.getenv("SQL_QUERY_TIMEOUT_SECONDS", "10"))

# ── FastF1 cache ────────────────────────────────────────────────────────────
FASTF1_CACHE_DIR = os.path.join(os.path.dirname(__file__), "fastf1_cache")
