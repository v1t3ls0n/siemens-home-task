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


def normalize_url(url: str) -> str:
    """Accept bare domains ('cybord.ai') as well as full URLs. Prepend https://
    when no scheme is given so a reviewer typing just the domain still works."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


async def analyze_events(url: str, force: bool = False):
    """Run the pipeline as an async generator, yielding real progress events
    so the UI can show what the agent is actually doing (cache hit vs crawl,
    which stage, which model tier). The terminal event is {stage:'done',
    result:{...}}; errors surface as {stage:'error', message:...}. `analyze()`
    below drains this to a plain result for the POST API and the batch eval."""
    url = normalize_url(url)
    yield {"stage": "start", "message": f"Analyzing {url}"}

    if not force:
        hit = cached_analysis(url)
        if hit:
            hit["cached"] = True
            yield {"stage": "cache", "message": "Found a cached analysis — "
                   "returning it instantly (no crawl, no LLM cost)"}
            yield {"stage": "done", "result": hit}
            return

    store = get_store()
    t0 = time.time()
    usage_before = usage_report()["total_cost_usd"]

    yield {"stage": "seed", "message": "Preparing Siemens reference data "
           "(re-embedding only what changed)"}
    seed_reference_data(store)                        # idempotent (checksums)

    # 1. ingest ------------------------------------------------------------
    yield {"stage": "crawl", "message": f"Crawling {url} — fetching product "
           "and about pages"}
    pages = crawl(url)
    yield {"stage": "crawled", "message": f"Read {len(pages)} page(s); "
           "chunking and embedding"}
    ingest_stats = index_startup_pages(store, pages)
    yield {"stage": "indexed", "message": "Indexed "
           f"({ingest_stats['new']} new, {ingest_stats['updated']} updated, "
           f"{ingest_stats['unchanged']} unchanged)"}
    group_id = ingest_stats["group_id"]

    # 2. research (light tier) ----------------------------------------------
    yield {"stage": "research", "message": "Research agent reading the pages "
           "to build a product profile (fast model)"}
    set_research_target(group_id)
    research = await run_agent(
        "light", build_researcher,
        f"Research the startup whose pages are indexed (site: {url}).")
    profile = research.final_output          # StartupProfile
    yield {"stage": "profiled", "message": f"Profiled: {profile.company_name}"}

    # 3. numeric metrics -----------------------------------------------------
    yield {"stage": "metrics", "message": "Computing cosine similarity vs the "
           "Siemens portfolio and existing partners"}
    profile_vec = embed([f"{profile.summary} "
                         f"Technologies: {', '.join(profile.technologies)}"])[0]
    metrics = compute_metrics(store, profile_vec, group_id)
    siemens_hits = store.search(profile_vec, doc_type="siemens", k=6)

    # 4. analysis (heavy tier) ----------------------------------------------
    yield {"stage": "analyze", "message": "Analyst agent scoring the "
           "partnership fit and writing justifications (frontier model)"}
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
    yield {"stage": "done", "result": result}


async def analyze(url: str, force: bool = False) -> dict:
    """Plain result (used by the POST API and the batch eval)."""
    result = None
    async for ev in analyze_events(url, force):
        if ev["stage"] == "done":
            result = ev["result"]
    return result
