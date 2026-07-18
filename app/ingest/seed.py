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

    # every data/*.md file is Siemens reference material. We split it into two
    # doc_types, both kept under group_id="siemens" so RAG retrieves either:
    #   product  the DISW product portfolio (siemens_portfolio.md) — the only
    #            material used for per-product correlation and the heatmap, so
    #            those visuals compare a startup strictly against real offerings.
    #   context  program / strategic material (siemens_dynamo.md scraped by
    #            scripts/scrape_dynamo.py, siemens_context.md) — grounds the
    #            analyst's reasoning but is NOT a product, so it is excluded
    #            from the product metrics.
    # One "## " section = one chunk source.
    for md_file in sorted(DATA_DIR.glob("*.md")):
        doc_type = "product" if md_file.stem == "siemens_portfolio" else "context"
        text = md_file.read_text(encoding="utf-8")
        for section in text.split("\n## ")[1:]:
            title, _, body = section.partition("\n")
            title = title.strip()
            source_url = f"reference://{md_file.stem}/{title}"
            written.add(source_url)
            stats[index_document(
                store, doc_type=doc_type, group_id="siemens", title=title,
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
    existing = (store.get_chunks(group_id="siemens")   # product + context
                + store.get_chunks(doc_type="partner"))
    for source_url in {c["source_url"] for c in existing} - written:
        store.replace_source(source_url, [])   # delete all chunks for it
        stats["pruned"] += 1
    return stats
