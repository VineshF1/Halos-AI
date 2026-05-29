"""
rag_ingestion.py — Phase 1: RAG Ingestion Pipeline

Pipeline:
  1. Read urls.txt, skip already-processed URLs
  2. Scrape pages concurrently (BoundedSemaphore) with request blocking
  3. Chunk text -> embed via NVIDIA NV-Embed-v1 API -> bulk insert to PG

Usage:
    python rag_ingestion.py
"""

import json
import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

import psycopg2
import tiktoken
from asyncio import BoundedSemaphore, gather, run, sleep as aio_sleep
from concurrent.futures import ThreadPoolExecutor

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI

from config import (
    ADMIN_CONN_STR,
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    NVIDIA_EMBEDDING_MODEL,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    PLAYWRIGHT_NAV_DELAY,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("rag_ingestion")

URLS_FILE = os.path.join(os.path.dirname(__file__), "urls.txt")

# ── NVIDIA embedding client (OpenAI-compatible) ────────────────────────────

_nv_client = OpenAI(api_key=NVIDIA_API_KEY, base_url=NVIDIA_BASE_URL)
_executor = ThreadPoolExecutor(max_workers=4)


def _embed_sync(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    resp = _nv_client.embeddings.create(
        model=NVIDIA_EMBEDDING_MODEL,
        input=texts,
        encoding_format="float",
        extra_body={"input_type": "passage"},
    )
    return [e.embedding for e in resp.data]


# ── URL loading ─────────────────────────────────────────────────────────────

def load_urls() -> list[str]:
    if not os.path.exists(URLS_FILE):
        log.warning("%s not found — using fallback", URLS_FILE)
        return ["https://en.wikipedia.org/wiki/Formula_One"]
    with open(URLS_FILE, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]
    log.info("Loaded %d URLs from %s", len(urls), URLS_FILE)
    return urls


def get_completed_urls() -> set[str]:
    conn = psycopg2.connect(ADMIN_CONN_STR)
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT url FROM knowledge_chunks")
        return {row[0] for row in cur.fetchall()}
    finally:
        cur.close()
        conn.close()


# ──── Page stripping ────────────────────────────────────────────────────────

PAGE_STRIP_JS = """
() => {
    for (const s of ['script','style','noscript','svg','template','nav','footer','header','aside',
                     '.nav','.navbar','.footer','.sidebar','.menu',
                     '[role="navigation"]','[role="banner"]','[role="contentinfo"]',
                     '.toc','#toc','.infobox','.mw-jump-link','.noprint','.mw-editsection']) {
        document.querySelectorAll(s).forEach(el => el.remove());
    }
    return document.body ? document.body.innerText : '';
}
"""


async def strip_page(page: Any) -> str:
    return await page.evaluate(PAGE_STRIP_JS)


# ── Route blocking (block images, css, fonts, analytics) ───────────────────

BLOCKED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
                      ".css", ".woff", ".woff2", ".ttf", ".eot",
                      ".ico", ".mp4", ".webm", ".mp3"}

BLOCKED_KEYWORDS = {"analytics", "tracking", "beacon", "pixel", "facebook",
                    "google-analytics", "gtag"}


async def _block_route(route):
    url = route.request.url.lower()
    for ext in BLOCKED_EXTENSIONS:
        if url.endswith(ext):
            await route.abort()
            return
    for kw in BLOCKED_KEYWORDS:
        if kw in url:
            await route.abort()
            return
    await route.continue_()


# ── Scraping ───────────────────────────────────────────────────────────────

async def scrape_one(browser: Any, url: str, sem: BoundedSemaphore) -> str | None:
    async with sem:
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()
        await page.route("**/*", _block_route)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_selector("body", timeout=8000)
            await page.wait_for_timeout(1500)
            text = await strip_page(page)
            if text and len(text.strip()) >= 50:
                return text
            log.warning("  ~ Little content: %s", url)
            return None
        except PlaywrightTimeout:
            log.warning("  ~ Timeout: %s", url)
            return None
        except Exception as exc:
            log.warning("  ~ Error %s: %s", url, exc)
            return None
        finally:
            await page.close()
            await ctx.close()


# ── Chunking ───────────────────────────────────────────────────────────────

def count_tokens(text: str) -> int:
    return len(tiktoken.get_encoding("cl100k_base").encode(text))


splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
    length_function=count_tokens,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def chunk_text(text: str, url: str) -> list[dict[str, Any]]:
    chunks = []
    for idx, content in enumerate(splitter.split_text(text)):
        content = content.strip()
        if content:
            chunks.append({"url": url, "chunk_index": idx, "content": content})
    return chunks


# ── Bulk DB insert ─────────────────────────────────────────────────────────

def bulk_insert(all_chunks: list[dict[str, Any]],
                all_embeddings: list[list[float]]) -> int:
    if not all_chunks:
        return 0
    conn = psycopg2.connect(ADMIN_CONN_STR)
    try:
        cur = conn.cursor()
        from psycopg2.extras import execute_values
        total = 0
        BATCH = 100
        for i in range(0, len(all_chunks), BATCH):
            chunk_batch = all_chunks[i:i+BATCH]
            emb_batch = all_embeddings[i:i+BATCH]
            rows = []
            for c, emb in zip(chunk_batch, emb_batch):
                vec = "[" + ",".join(str(v) for v in emb) + "]"
                rows.append((c["url"], c["chunk_index"], c["content"], vec))
            execute_values(
                cur,
                "INSERT INTO knowledge_chunks (url, chunk_index, content, embedding) VALUES %s",
                rows, template="(%s, %s, %s, %s::vector)",
            )
            total += len(rows)
        conn.commit()
        log.info("Inserted %d chunks total", total)
        return total
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


# ── Per-URL processing ────────────────────────────────────────────────────

def process_one_url_batch(chunks: list[dict[str, Any]]) -> bool:
    texts = [c["content"] for c in chunks]
    embs = _embed_sync(texts)
    if len(embs) != len(texts):
        log.error("  Embedding count mismatch — skip")
        return False
    bulk_insert(chunks, embs)
    return True


# ── Main pipeline ──────────────────────────────────────────────────────────

async def run_pipeline():
    urls = load_urls()
    if not urls:
        return

    done = get_completed_urls()
    todo = [u for u in urls if u not in done]
    log.info("Completed %d/%d — remaining: %d", len(done), len(urls), len(todo))
    if not todo:
        log.info("All done.")
        return

    sem = BoundedSemaphore(5)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            # Scrape all remaining URLs concurrently
            log.info("Scraping %d URLs ...", len(todo))
            t0 = time.time()
            texts = await gather(*[scrape_one(browser, u, sem) for u in todo])
            log.info("Scraping done in %.1fs", time.time() - t0)

            # Process each URL: chunk -> embed -> insert (immediate checkpoint)
            ok_count = 0
            for idx, (url, text) in enumerate(zip(todo, texts)):
                log.info("[%d/%d] %s", idx + 1, len(todo), url)
                if not text:
                    log.warning("  Skip — no content")
                    continue
                chunks = chunk_text(text, url)
                if not chunks:
                    continue
                if process_one_url_batch(chunks):
                    ok_count += 1
                    log.info("  V %d chunks inserted", len(chunks))
                await aio_sleep(0.5)

            log.info("Processed %d/%d URLs successfully", ok_count, len(todo))

        finally:
            await browser.close()

    log.info("Pipeline complete.")


if __name__ == "__main__":
    run(run_pipeline())
