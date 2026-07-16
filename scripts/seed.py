"""Seed the vector store with the Siemens portfolio + partner list.
Run once after bringing OpenSearch up:  python -m scripts.seed
(The app also seeds on demand; this just lets you do it explicitly.)"""

from app.ingest.seed import seed_reference_data
from app.search.store import get_store

if __name__ == "__main__":
    stats = seed_reference_data(get_store())
    print("seeded:", stats)
