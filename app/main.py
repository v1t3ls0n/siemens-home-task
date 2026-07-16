"""FastAPI entry point."""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.analysis.pipeline import analyze, list_analyses
from app.llm.router import usage_report
from app.models import AnalyzeRequest

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="partner-scout pro")

_INDEX = (Path(__file__).parent / "web" / "index.html").read_text("utf-8")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX


@app.post("/api/analyze")
async def api_analyze(req: AnalyzeRequest):
    try:
        return await analyze(req.url.strip(), force=req.force)
    except Exception as e:
        logging.exception("analysis failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analyses")
def api_analyses():
    """History of analyzed startups (from SQLite)."""
    return list_analyses()


@app.get("/api/usage")
def api_usage():
    """Token + cost report per model, since process start."""
    return usage_report()


@app.get("/api/health")
def health():
    return {"ok": True}
