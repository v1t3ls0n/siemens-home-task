"""Vector-store abstraction.

Primary backend: OpenSearch (real kNN index, hybrid-search capable).
Fallback backend: a small numpy store — same interface — so the app can run
(and be deployed to a free host) without an OpenSearch cluster.

Document model (one record per CHUNK):
  id           deterministic: sha1(source_url)#<chunk_no>
  doc_type     startup | siemens | partner
  group_id     startup domain / "siemens" / "partners"
  title        page or product or partner name
  source_url   provenance
  chunk        the text
  checksum     sha256 of the FULL source document (freshness detection)
  fetched_at   ISO timestamp of last content change
  last_checked ISO timestamp of last crawl visit
  embedding    vector
"""

from typing import Protocol


class VectorStore(Protocol):
    def ensure_ready(self, dim: int) -> None: ...
    def source_checksum(self, source_url: str) -> str | None: ...
    def touch_source(self, source_url: str, when: str) -> None: ...
    def replace_source(self, source_url: str, chunks: list[dict]) -> None: ...
    def search(self, vector: list[float], doc_type: str | None,
               group_id: str | None, k: int) -> list[dict]: ...
    def get_chunks(self, doc_type: str | None = None,
                   group_id: str | None = None,
                   with_vectors: bool = False) -> list[dict]: ...


def get_store() -> VectorStore:
    import os
    from app.config import cfg
    # SEARCH_BACKEND env var overrides config.yaml — lets a PaaS deploy pick the
    # numpy 'local' backend (no OpenSearch service needed) without editing files.
    backend = os.environ.get("SEARCH_BACKEND") or cfg()["search"]["backend"]
    if backend == "opensearch":
        from app.search.opensearch_store import OpenSearchStore
        return OpenSearchStore()
    from app.search.local_store import LocalStore
    return LocalStore()
