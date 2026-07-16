"""Central config: env vars + config.yaml (model routing, prices, crawler)."""

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STATE_DIR = Path(os.environ.get("STATE_DIR", ROOT))  # sqlite/localstore files


@lru_cache
def cfg() -> dict:
    path = Path(os.environ.get("CONFIG_PATH", ROOT / "config.yaml"))
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
