"""FastAPI entry point."""

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.analysis.pipeline import analyze, list_analyses
from app.auth import require_auth
from app.llm.router import usage_report
from app.models import AnalyzeRequest

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="partner-scout")

_INDEX = (Path(__file__).parent / "web" / "index.html").read_text("utf-8")


@app.get("/", response_class=HTMLResponse)
def index(_: None = Depends(require_auth)) -> str:
    return _INDEX


@app.post("/api/analyze")
async def api_analyze(req: AnalyzeRequest, _: None = Depends(require_auth)):
    try:
        return await analyze(req.url.strip(), force=req.force)
    except Exception as e:
        logging.exception("analysis failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analyses")
def api_analyses(_: None = Depends(require_auth)):
    """History of analyzed startups (from SQLite)."""
    return list_analyses()


@app.get("/api/usage")
def api_usage(_: None = Depends(require_auth)):
    """Token + cost report per model, since process start."""
    return usage_report()


@app.get("/api/health")
def health():
    """Unauthenticated — used by the platform's health check."""
    return {"ok": True}
