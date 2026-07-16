"""Agent definitions (OpenAI Agents SDK).

Researcher (light tier): reads the already-indexed startup pages via tools
and produces a StartupProfile. It decides which pages matter — but it reads
from OUR index, not the live web: ingestion is deterministic and reproducible,
analysis is model-driven.

Analyst (heavy tier): no tools; gets the profile + retrieved Siemens chunks +
the numeric metrics, returns a MatchReport. Structured outputs on both
(`output_type=` pydantic models) — no JSON parsing by hand.
"""

from agents import Agent, function_tool

from app.models import MatchReport, StartupProfile
from app.search.store import get_store

_current_group: dict = {"group_id": None}   # set by pipeline before each run


def set_research_target(group_id: str) -> None:
    _current_group["group_id"] = group_id


@function_tool
def list_startup_pages() -> str:
    """List the crawled pages of the startup being researched (title + URL)."""
    store = get_store()
    chunks = store.get_chunks(doc_type="startup",
                              group_id=_current_group["group_id"])
    pages = {c["source_url"]: c["title"] for c in chunks}
    return "\n".join(f"- {t} | {u}" for u, t in pages.items()) or "no pages"


@function_tool
def read_page(source_url: str) -> str:
    """Read the full text of one crawled page by its URL."""
    store = get_store()
    chunks = [c for c in store.get_chunks(doc_type="startup",
                                          group_id=_current_group["group_id"])
              if c["source_url"] == source_url]
    chunks.sort(key=lambda c: c["chunk_no"])
    return "\n".join(c["chunk"] for c in chunks) or f"no page at {source_url}"


def build_researcher(model) -> Agent:
    return Agent(
        name="researcher",
        model=model,
        instructions=(
            "You research a startup from its crawled website pages. "
            "Use list_startup_pages, then read the pages needed to understand "
            "the MAIN product offering. Base every claim ONLY on page content "
            "— no outside knowledge. Cite the pages you used in evidence_urls."
        ),
        tools=[list_startup_pages, read_page],
        output_type=StartupProfile,
    )


def build_analyst(model) -> Agent:
    return Agent(
        name="analyst",
        model=model,
        instructions=(
            "You evaluate startups as potential technology partners for "
            "Siemens Digital Industries Software (DISW). You receive: the "
            "startup profile, the most relevant Siemens products (retrieved), "
            "existing partners with NUMERIC cosine similarities, and a "
            "per-product correlation table. Ground your scores in this "
            "material; treat the numeric similarities as evidence to "
            "interpret, not to contradict. partnership_score: 10 = perfect "
            "complement, clear integration path into Siemens Xcelerator, "
            "shared customers; 1 = irrelevant or purely competitive. Return "
            "exactly five dimensions: technology_overlap, market_fit, "
            "integration_potential, competitive_risk, maturity_signals."
        ),
        output_type=MatchReport,
    )
