"""Central config: env vars + config.yaml (model routing, prices, crawler)."""

import logging
import os
import tempfile
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def _resolve_state_dir() -> Path:
    """Directory for SQLite caches + the local vector store.

    Prefer $STATE_DIR (point it at a mounted volume in the cloud so caches
    persist). Create it if missing and verify it's writable; if not — e.g.
    STATE_DIR=/data was set but no volume is mounted — fall back to a temp
    dir so the app still runs (caches just don't persist) instead of crashing
    with 'unable to open database file'.
    """
    candidate = Path(os.environ.get("STATE_DIR", ROOT))
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".write_test"
        probe.touch()
        probe.unlink()
        return candidate
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "partner-scout"
        fallback.mkdir(parents=True, exist_ok=True)
        logging.warning("STATE_DIR %s not writable — falling back to %s "
                        "(caches will not persist)", candidate, fallback)
        return fallback


STATE_DIR = _resolve_state_dir()


@lru_cache
def cfg() -> dict:
    path = Path(os.environ.get("CONFIG_PATH", ROOT / "config.yaml"))
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
