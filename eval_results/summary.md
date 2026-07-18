# partner-scout evaluation — 2026-07-18T17:10:39.805714+00:00

API: `http://localhost:8000` · sites: 9 · total LLM cost ≈ $0.2788 · ✅ no anomalies

| Category | Company | Fit | Partner sim | Self-sim | Cost | Flags |
|---|---|---|---|---|---|---|
| partner | Cybord | 8 | 9 | 0.813 | 0.0306 | ok |
| partner | Realtime Robotics | 8 | 9 | 0.807 | 0.0293 | ok |
| partner | Portcast | 7 | 8 | 0.828 | 0.0326 | ok |
| partner | Retrocausal | 8 | 9 | 0.84 | 0.0298 | ok |
| good | Protex AI | 8 | 6 | 0.546 | 0.033 | ok |
| good | Augury | 8 | 6 | 0.577 | 0.0343 | ok |
| weak | Viz.ai | 5 | 5 | 0.474 | 0.0322 | ok |
| weak | Notion | 6 | 4 | 0.403 | 0.0321 | ok |
| bad | Airbnb | 2 | 2 | 0.293 | 0.0249 | ok |

## Reading the table
- **partner** rows: fit and partner-sim should be high; **self-sim** is the top partner-similarity hit — an existing partner matching its own reference entry. It sits at ~0.75-0.85 (two different texts about the same company, not ~1.0) and must be a separated PEAK, well above unrelated partners (~0.3-0.5); this confirms the embedding+metric path is sound.
- **good** rows: fit high — the system rewards genuine Industry-4.0 fit.
- **weak/bad** rows: fit low — the system DISCRIMINATES, it does not just produce plausible prose for everything.
- Any ⚠ flag is a result contradicting its expected label — review the matching `eval_results/<site>.json`.
