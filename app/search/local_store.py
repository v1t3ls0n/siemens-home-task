"""Numpy fallback store — same interface as OpenSearchStore, zero infra.

Lets the app run on a free PaaS (no OpenSearch) and acts as the "my demo must
not die" path. Persisted as a single JSON file; fine for POC volumes.
"""

import json

import numpy as np

from app.config import STATE_DIR

_PATH = STATE_DIR / "localstore.json"


class LocalStore:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        if _PATH.exists():
            self.docs = json.loads(_PATH.read_text())

    def _save(self) -> None:
        _PATH.write_text(json.dumps(self.docs))

    def ensure_ready(self, dim: int) -> None:
        pass

    def source_checksum(self, source_url: str) -> str | None:
        for d in self.docs:
            if d["source_url"] == source_url:
                return d["checksum"]
        return None

    def touch_source(self, source_url: str, when: str) -> None:
        for d in self.docs:
            if d["source_url"] == source_url:
                d["last_checked"] = when
        self._save()

    def replace_source(self, source_url: str, chunks: list[dict]) -> None:
        self.docs = [d for d in self.docs if d["source_url"] != source_url]
        self.docs.extend(chunks)
        self._save()

    def _filtered(self, doc_type, group_id):
        return [d for d in self.docs
                if (doc_type is None or d["doc_type"] == doc_type)
                and (group_id is None or d["group_id"] == group_id)]

    def search(self, vector, doc_type=None, group_id=None, k=8) -> list[dict]:
        docs = self._filtered(doc_type, group_id)
        if not docs:
            return []
        q = np.array(vector)
        q = q / np.linalg.norm(q)
        m = np.array([d["embedding"] for d in docs])
        m = m / np.linalg.norm(m, axis=1, keepdims=True)
        sims = m @ q
        order = np.argsort(-sims)[:k]
        return [{**{k2: v for k2, v in docs[i].items() if k2 != "embedding"},
                 "score": float(sims[i])} for i in order]

    def get_chunks(self, doc_type=None, group_id=None, with_vectors=False):
        docs = self._filtered(doc_type, group_id)
        if with_vectors:
            return [dict(d) for d in docs]
        return [{k2: v for k2, v in d.items() if k2 != "embedding"}
                for d in docs]
