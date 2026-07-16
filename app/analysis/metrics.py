"""Numeric similarity metrics — computed with numpy, not asked of the LLM.

The LLM interprets these numbers; it does not invent them. Produces:
  product_correlation  per-Siemens-product max cosine vs the startup profile
  partner_similarity   cosine of each existing partner vs the profile
  heatmap              startup chunks x Siemens products cosine matrix
"""

import numpy as np

from app.search.store import VectorStore


def _norm(m: np.ndarray) -> np.ndarray:
    return m / np.linalg.norm(m, axis=-1, keepdims=True)


def compute_metrics(store: VectorStore, profile_vec: list[float],
                    startup_group: str) -> dict:
    q = _norm(np.array(profile_vec))

    # --- per-product correlation (max over the product's chunks) ----------
    siemens = store.get_chunks(doc_type="siemens", with_vectors=True)
    products: dict[str, list[np.ndarray]] = {}
    for c in siemens:
        products.setdefault(c["title"], []).append(np.array(c["embedding"]))
    product_correlation = sorted(
        (
            {"product": title,
             "similarity": round(float(max(_norm(np.stack(vs)) @ q)), 3)}
            for title, vs in products.items()
        ),
        key=lambda d: -d["similarity"],
    )

    # --- partner similarity ------------------------------------------------
    partners = store.get_chunks(doc_type="partner", with_vectors=True)
    partner_similarity = sorted(
        (
            {"name": p["title"],
             "similarity": round(float(_norm(np.array(p["embedding"])) @ q), 3)}
            for p in partners
        ),
        key=lambda d: -d["similarity"],
    )

    # --- heatmap: startup chunks x top products ----------------------------
    chunks = store.get_chunks(doc_type="startup", group_id=startup_group,
                              with_vectors=True)[:12]
    top_products = [d["product"] for d in product_correlation[:8]]
    heatmap = {"rows": [], "cols": top_products, "values": []}
    if chunks:
        cm = _norm(np.array([c["embedding"] for c in chunks]))
        for c, row_vec in zip(chunks, cm):
            heatmap["rows"].append(
                (c["title"][:40] + f" #{c['chunk_no']}"))
            row = []
            for title in top_products:
                pv = _norm(np.stack(products[title]))
                row.append(round(float(max(pv @ row_vec)), 3))
            heatmap["values"].append(row)

    return {
        "product_correlation": product_correlation,
        "partner_similarity": partner_similarity,
        "heatmap": heatmap,
    }
