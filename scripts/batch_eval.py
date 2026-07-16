"""Batch evaluation harness for partner-scout.

Runs a labelled set of startup URLs through the live /api/analyze endpoint and
produces (1) per-site JSON logs, (2) a summary CSV + Markdown table, and
(3) an anomaly report that flags results contradicting the expected label —
so a reviewer can verify the system DISCRIMINATES (good candidates score high,
out-of-domain sites score low) rather than just returning plausible prose.

The labelled set lives in scripts/eval_set.json. Categories and what they
assert:

  partner  an existing Dynamo partner. Sanity check: because the partner is
           already in the reference list, analysing it should yield a
           near-1.0 self-similarity to itself, and a high similarity score.
  good     a strong non-listed candidate (Industry 4.0 / industrial AI).
           Expect partnership_score high.
  weak     real tech but outside Siemens' domain (e.g. healthcare AI).
           Expect a middling-to-low fit — tests the domain boundary.
  bad      clearly out of domain (consumer apps). Expect a low fit —
           the core discrimination test.

Usage:
  # app must be running (docker compose up)
  python -m scripts.batch_eval                        # default set, no force
  python -m scripts.batch_eval --force                # bypass caches
  python -m scripts.batch_eval --api http://host:8000 --set my_set.json
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "eval_results"

# Expected score bands per category: (fit_min, fit_max, sim_min, sim_max).
# None = unconstrained. Used only to FLAG anomalies for review, not to pass/fail.
BANDS = {
    "partner": {"fit": (6, 10), "sim": (7, 10)},
    "good":    {"fit": (6, 10), "sim": (4, 10)},
    "weak":    {"fit": (1, 5),  "sim": (1, 7)},
    "bad":     {"fit": (1, 4),  "sim": (1, 6)},
}


def slug(url: str) -> str:
    return (url.replace("https://", "").replace("http://", "")
            .replace("/", "_").strip("_") or "site")


def analyze(api: str, url: str, force: bool) -> dict:
    r = httpx.post(f"{api}/api/analyze", json={"url": url, "force": force},
                   timeout=600)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}: {r.text[:400]}"}
    return r.json()


def self_similarity(result: dict) -> float | None:
    """For a partner analysed against a list that contains it, the top
    partner-similarity entry should be ~1.0 (the startup matching its own
    reference entry). Returns the max partner similarity, or None."""
    sims = result.get("metrics", {}).get("partner_similarity", [])
    return max((p["similarity"] for p in sims), default=None)


def check_anomalies(cat: str, res: dict) -> list[str]:
    flags = []
    if "error" in res:
        return [f"ERROR: {res['error']}"]

    rep = res.get("report", {})
    fit = rep.get("partnership_score")
    sim = rep.get("partner_similarity_score")
    band = BANDS.get(cat, {})

    if fit is not None and "fit" in band:
        lo, hi = band["fit"]
        if not (lo <= fit <= hi):
            flags.append(f"fit {fit} outside expected {lo}-{hi} for '{cat}'")
    if sim is not None and "sim" in band:
        lo, hi = band["sim"]
        if not (lo <= sim <= hi):
            flags.append(f"partner-similarity {sim} outside expected {lo}-{hi}")

    # partner self-match sanity: an existing partner should match itself ~1.0
    if cat == "partner":
        top = self_similarity(res)
        if top is None:
            flags.append("no partner_similarity metrics produced")
        elif top < 0.85:
            flags.append(f"self-similarity only {top} (<0.85) — "
                         "embedding/metric path may be broken")

    # structural sanity
    prof = res.get("profile", {})
    if not prof.get("evidence_urls"):
        flags.append("no evidence_urls — profile not grounded in pages")
    if len(rep.get("dimensions", [])) != 5:
        flags.append(f"expected 5 dimensions, got {len(rep.get('dimensions', []))}")
    if res.get("runtime_s", 0) > 180:
        flags.append(f"slow: {res['runtime_s']}s")
    return flags


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--set", default=str(Path(__file__).parent / "eval_set.json"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    sites = json.loads(Path(args.set).read_text("utf-8"))
    OUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()

    rows, total_cost, any_flag = [], 0.0, False
    for i, site in enumerate(sites, 1):
        url, cat = site["url"], site["category"]
        print(f"[{i}/{len(sites)}] {cat:8} {url}")
        t0 = time.time()
        res = analyze(args.api, url, args.force)
        res["_eval"] = {"category": cat, "note": site.get("note", ""),
                        "wall_s": round(time.time() - t0, 1)}
        (OUT_DIR / f"{slug(url)}.json").write_text(
            json.dumps(res, indent=2, ensure_ascii=False), "utf-8")

        flags = check_anomalies(cat, res)
        any_flag = any_flag or bool(flags)
        total_cost += res.get("cost_usd", 0) or 0
        rep = res.get("report", {})
        rows.append({
            "url": url, "category": cat,
            "company": res.get("profile", {}).get("company_name", "—"),
            "fit": rep.get("partnership_score", "—"),
            "sim": rep.get("partner_similarity_score", "—"),
            "self_sim": self_similarity(res) if "error" not in res else "—",
            "cost": res.get("cost_usd", "—"),
            "cached": res.get("cached", False),
            "flags": flags,
        })
        for f in flags:
            print(f"    ⚠ {f}")

    # --- write summary.csv + summary.md ------------------------------------
    import csv
    with open(OUT_DIR / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["url", "category", "company", "fit", "partner_sim",
                    "self_sim", "cost_usd", "cached", "flags"])
        for r in rows:
            w.writerow([r["url"], r["category"], r["company"], r["fit"],
                        r["sim"], r["self_sim"], r["cost"], r["cached"],
                        " | ".join(r["flags"])])

    md = [f"# partner-scout evaluation — {ts}", "",
          f"API: `{args.api}` · sites: {len(sites)} · "
          f"total LLM cost ≈ ${round(total_cost, 4)} · "
          f"{'⚠ anomalies present' if any_flag else '✅ no anomalies'}", "",
          "| Category | Company | Fit | Partner sim | Self-sim | Cost | Flags |",
          "|---|---|---|---|---|---|---|"]
    order = {"partner": 0, "good": 1, "weak": 2, "bad": 3}
    for r in sorted(rows, key=lambda x: order.get(x["category"], 9)):
        md.append(f"| {r['category']} | {r['company']} | {r['fit']} | "
                  f"{r['sim']} | {r['self_sim']} | {r['cost']} | "
                  f"{'⚠ ' + '; '.join(r['flags']) if r['flags'] else 'ok'} |")
    md += ["", "## Reading the table",
           "- **partner** rows: fit and partner-sim should be high; "
           "**self-sim ≈ 1.0** confirms the embedding+metric path is sound.",
           "- **good** rows: fit high — the system rewards genuine Industry-4.0 fit.",
           "- **weak/bad** rows: fit low — the system DISCRIMINATES, it does "
           "not just produce plausible prose for everything.",
           "- Any ⚠ flag is a result contradicting its expected label — review "
           f"the matching `eval_results/<site>.json`."]
    (OUT_DIR / "summary.md").write_text("\n".join(md) + "\n", "utf-8")

    print(f"\nWrote {OUT_DIR}/summary.md, summary.csv, and per-site JSON.")
    print(f"Total LLM cost ≈ ${round(total_cost, 4)}. "
          f"{'ANOMALIES present — review flags.' if any_flag else 'No anomalies.'}")
    sys.exit(1 if any_flag else 0)


if __name__ == "__main__":
    main()
