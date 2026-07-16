"""Pluggable embedding provider with a checksum-keyed SQLite cache.

Cache key = (model, sha256(text)) — identical text is never embedded twice,
across restarts and across startups. This is where most of the token savings
on re-crawls come from: unchanged pages hit the cache at zero cost.
"""

import hashlib
import json
import sqlite3

import httpx

from app.config import OLLAMA_BASE_URL, STATE_DIR, cfg
from app.llm.router import record_usage

_DB = STATE_DIR / "embed_cache.db"


def _conn():
    c = sqlite3.connect(_DB)
    c.execute("CREATE TABLE IF NOT EXISTS embeds "
              "(key TEXT PRIMARY KEY, vec TEXT)")
    return c


def _key(model: str, text: str) -> str:
    return model + ":" + hashlib.sha256(text.encode()).hexdigest()


def _embed_openai(model: str, texts: list[str]) -> list[list[float]]:
    from openai import OpenAI
    resp = OpenAI().embeddings.create(model=model, input=texts)
    record_usage(model, resp.usage.prompt_tokens, 0)
    return [d.embedding for d in resp.data]


def _embed_ollama(model: str, texts: list[str]) -> list[list[float]]:
    r = httpx.post(f"{OLLAMA_BASE_URL}/api/embed",
                   json={"model": model, "input": texts}, timeout=120)
    r.raise_for_status()
    return r.json()["embeddings"]


def embed(texts: list[str]) -> list[list[float]]:
    e = cfg()["embeddings"]
    model, provider = e["model"], e["provider"]

    out: list[list[float] | None] = [None] * len(texts)
    misses: list[int] = []
    with _conn() as c:
        for i, t in enumerate(texts):
            row = c.execute("SELECT vec FROM embeds WHERE key=?",
                            (_key(model, t),)).fetchone()
            if row:
                out[i] = json.loads(row[0])
            else:
                misses.append(i)

    if misses:
        batch = [texts[i] for i in misses]
        vecs = (_embed_openai(model, batch) if provider == "openai"
                else _embed_ollama(model, batch))
        with _conn() as c:
            for i, v in zip(misses, vecs):
                out[i] = v
                c.execute("INSERT OR REPLACE INTO embeds VALUES (?, ?)",
                          (_key(model, texts[i]), json.dumps(v)))
    return out  # type: ignore[return-value]
