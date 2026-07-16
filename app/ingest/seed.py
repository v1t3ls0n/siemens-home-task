"""Seed the vector store with reference data: Siemens DISW portfolio chunks
and the existing-partner list. Idempotent thanks to checksum detection —
re-running only re-embeds sections whose text actually changed."""

import json

from app.config import DATA_DIR, cfg
from app.ingest.indexer import index_document
from app.search.store import VectorStore


def seed_reference_data(store: VectorStore) -> dict:
    store.ensure_ready(cfg()["embeddings"]["dim"])
    stats = {"new": 0, "updated": 0, "unchanged": 0}

    text = (DATA_DIR / "siemens_portfolio.md").read_text(encoding="utf-8")
    for section in text.split("\n## ")[1:]:
        title, _, body = section.partition("\n")
        title = title.strip()
        status = index_document(
            store, doc_type="siemens", group_id="siemens", title=title,
            source_url=f"portfolio://siemens/{title}", text=body.strip(),
        )
        stats[status] += 1

    partners = json.loads((DATA_DIR / "partners.json").read_text("utf-8"))
    for p in partners:
        status = index_document(
            store, doc_type="partner", group_id="partners", title=p["name"],
            source_url=f"partner://{p['name']}",
            text=f"{p['name']}: {p['description']}",
        )
        stats[status] += 1
    return stats
