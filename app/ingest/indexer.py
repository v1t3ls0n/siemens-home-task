"""Indexing with freshness detection.

For every source document we store checksum (sha256 of the full text) and two
timestamps: fetched_at (last CONTENT CHANGE) and last_checked (last crawl).
On re-crawl:
  same checksum   -> touch last_checked only (no re-embedding, no cost)
  changed/missing -> re-chunk, re-embed, replace the source's chunks
"""

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.ingest.chunker import chunk_text
from app.ingest.embeddings import embed
from app.search.store import VectorStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def index_document(store: VectorStore, *, doc_type: str, group_id: str,
                   title: str, source_url: str, text: str) -> str:
    """Returns 'unchanged' | 'updated' | 'new'."""
    checksum = hashlib.sha256(text.encode()).hexdigest()
    existing = store.source_checksum(source_url)
    if existing == checksum:
        store.touch_source(source_url, _now())
        return "unchanged"

    chunks = chunk_text(text)
    vectors = embed(chunks)
    now = _now()
    store.replace_source(source_url, [
        {
            "doc_type": doc_type, "group_id": group_id, "title": title,
            "source_url": source_url, "chunk": c, "chunk_no": i,
            "checksum": checksum, "fetched_at": now, "last_checked": now,
            "embedding": v,
        }
        for i, (c, v) in enumerate(zip(chunks, vectors))
    ])
    return "updated" if existing else "new"


def index_startup_pages(store: VectorStore, pages: list[dict]) -> dict:
    group_id = urlparse(pages[0]["url"]).netloc
    stats = {"new": 0, "updated": 0, "unchanged": 0}
    for p in pages:
        status = index_document(
            store, doc_type="startup", group_id=group_id,
            title=p["title"], source_url=p["url"], text=p["text"],
        )
        stats[status] += 1
    return {"group_id": group_id, **stats}
