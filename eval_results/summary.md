# partner-scout evaluation — 2026-07-18T17:24:42.188396+00:00

API: `http://localhost:8000` · sites: 9 · total LLM cost ≈ $0.267 · ✅ no anomalies

| Category | Company | Fit | Partner sim | Self-sim | Cost | Flags |
|---|---|---|---|---|---|---|
| partner | Cybord | 8 | 8 | 0.823 | 0.0296 | ok |
| partner | Realtime Robotics | 8 | 9 | 0.839 | 0.0263 | ok |
| partner | Portcast | 7 | 8 | 0.827 | 0.0313 | ok |
| partner | Retrocausal | 8 | 8 | 0.841 | 0.0291 | ok |
| good | Protex AI | 8 | 6 | 0.558 | 0.0323 | ok |
| good | Augury | 8 | 7 | 0.584 | 0.0339 | ok |
| weak | Viz.ai | 4 | 5 | 0.479 | 0.0308 | ok |
| weak | Notion | 6 | 4 | 0.392 | 0.0295 | ok |
| bad | Airbnb | 2 | 2 | 0.299 | 0.0242 | ok |

## Reading the table
- **partner** rows: fit and partner-sim should be high; **self-sim** is the top partner-similarity hit — an existing partner matching its own reference entry. It sits at ~0.75-0.85 (two different texts about the same company, not ~1.0) and must be a separated PEAK, well above unrelated partners (~0.3-0.5); this confirms the embedding+metric path is sound.
- **good** rows: fit high — the system rewards genuine Industry-4.0 fit.
- **weak/bad** rows: fit low — the system DISCRIMINATES, it does not just produce plausible prose for everything.
- Any ⚠ flag is a result contradicting its expected label — review the matching `eval_results/<site>.json`.
