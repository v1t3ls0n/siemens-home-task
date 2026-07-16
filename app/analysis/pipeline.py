"""End-to-end analysis pipeline + result persistence (SQLite history).

Stages:
  1. CRAWL + INDEX   deterministic; checksum decides what gets re-embedded
  2. RESEARCH        light-tier agent -> StartupProfile
  3. METRICS         numpy cosine similarities (products, partners, heatmap)
  4. ANALYSIS        heavy-tier agent -> MatchReport (structured)
"""

import json
import sqlite3
import time

from app.config import STATE_DIR, cfg
from app.ingest.crawler import crawl
from app.ingest.embeddings import embed
from app.ingest.indexer import index_startup_pages
from app.ingest.seed import seed_reference_data
from app.analysis.llm_agents import (build_analyst, build_researcher,
                                     set_research_target)
from app.analysis.metrics import compute_metrics
from app.llm.router import run_agent, usage_report
from app.search.store import get_store

_DB = STATE_DIR / "analyses.db"


def _conn():
    c = sqlite3.connect(_DB)
    c.execute("CREATE TABLE IF NOT EXISTS analyses ("
              "url TEXT PRIMARY KEY, result TEXT, created_at REAL)")
    return c


def cached_analysis(url: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT result FROM analyses WHERE url=?",
                        (url,)).fetchone()
    return json.loads(row[0]) if row else None


def list_analyses() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT url, result, created_at FROM analyses "
                         "ORDER BY created_at DESC").fetchall()
    return [{"url": u,
             "company": json.loads(r)["profile"]["company_name"],
             "score": json.loads(r)["report"]["partnership_score"],
             "created_at": t} for u, r, t in rows]


async def analyze(url: str, force: bool = False) -> dict:
    if not force:
        hit = cached_analysis(url)
        if hit:
            hit["cached"] = True
            return hit

    store = get_store()
    t0 = time.time()
    usage_before = usage_report()["total_cost_usd"]

    seed_reference_data(store)                       # idempotent (checksums)

    # 1. ingest ------------------------------------------------------------
    pages = crawl(url)
    ingest_stats = index_startup_pages(store, pages)
    group_id = ingest_stats["group_id"]

    # 2. research (light tier) ----------------------------------------------
    set_research_target(group_id)
    research = await run_agent(
        "light", build_researcher,
        f"Research the startup whose pages are indexed (site: {url}).")
    profile = research.final_output          # StartupProfile

    # 3. numeric metrics -----------------------------------------------------
    profile_vec = embed([f"{profile.summary} "
                         f"Technologies: {', '.join(profile.technologies)}"])[0]
    metrics = compute_metrics(store, profile_vec, group_id)
    siemens_hits = store.search(profile_vec, doc_type="siemens", k=6)

    # 4. analysis (heavy tier) ----------------------------------------------
    analyst_input = json.dumps({
        "startup_profile": profile.model_dump(),
        "relevant_siemens_products": [
            {"title": h["title"], "text": h["chunk"]} for h in siemens_hits],
        "existing_partner_similarity": metrics["partner_similarity"],
        "per_product_correlation": metrics["product_correlation"],
    }, ensure_ascii=False, indent=1)
    analysis = await run_agent("heavy", build_analyst, analyst_input)
    report = analysis.final_output           # MatchReport

    result = {
        "url": url,
        "profile": profile.model_dump(),
        "report": report.model_dump(),
        "metrics": metrics,
        "ingest": ingest_stats,
        "runtime_s": round(time.time() - t0, 1),
        "cost_usd": round(usage_report()["total_cost_usd"] - usage_before, 4),
        "cached": False,
    }
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO analyses VALUES (?, ?, ?)",
                  (url, json.dumps(result, ensure_ascii=False), time.time()))
    return result
