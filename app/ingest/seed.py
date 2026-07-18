"""Seed the vector store with reference data: Siemens DISW portfolio chunks
and the existing-partner list. Idempotent thanks to checksum detection —
re-running only re-embeds sections whose text actually changed."""

import json

from app.config import DATA_DIR, cfg
from app.ingest.indexer import index_document
from app.search.store import VectorStore


def seed_reference_data(store: VectorStore) -> dict:
    store.ensure_ready(cfg()["embeddings"]["dim"])
    stats = {"new": 0, "updated": 0, "unchanged": 0, "pruned": 0}
    written: set[str] = set()   # source_urls present in the current data files

    # every data/*.md file is Siemens reference material: the DISW product
    # portfolio, plus scraped pages (e.g. siemens_dynamo.md from
    # scripts/scrape_dynamo.py). One "## " section = one chunk source.
    for md_file in sorted(DATA_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        for section in text.split("\n## ")[1:]:
            title, _, body = section.partition("\n")
            title = title.strip()
            source_url = f"reference://{md_file.stem}/{title}"
            written.add(source_url)
            stats[index_document(
                store, doc_type="siemens", group_id="siemens", title=title,
                source_url=source_url, text=body.strip())] += 1

    partners = json.loads((DATA_DIR / "partners.json").read_text("utf-8"))
    for p in partners:
        source_url = f"partner://{p['name']}"
        written.add(source_url)
        stats[index_document(
            store, doc_type="partner", group_id="partners", title=p["name"],
            source_url=source_url,
            text=f"{p['name']}: {p['description']}")] += 1

    # Self-healing prune: drop any reference doc (siemens/partner) whose source
    # is no longer in the data files — e.g. a partner removed from
    # partners.json. Without this, seeding only adds/updates, so stale entries
    # (like the old 'Why join Dynamo?' bullets) would linger in a persisted
    # index until the volume is wiped.
    existing = (store.get_chunks(doc_type="siemens")
                + store.get_chunks(doc_type="partner"))
    for source_url in {c["source_url"] for c in existing} - written:
        store.replace_source(source_url, [])   # delete all chunks for it
        stats["pruned"] += 1
    return stats
