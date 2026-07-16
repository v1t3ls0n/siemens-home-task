# partner-scout evaluation — 2026-07-16T22:30:12.339751+00:00

API: `http://localhost:8000` · sites: 9 · total LLM cost ≈ $0.1683 · ✅ no anomalies

| Category | Company | Fit | Partner sim | Self-sim | Cost | Flags |
|---|---|---|---|---|---|---|
| partner | Cybord | 8 | 8 | 0.8 | 0.0243 | ok |
| partner | Realtime Robotics | 9 | 9 | 0.791 | 0.0185 | ok |
| partner | Portcast | 7 | 7 | 0.815 | 0.0192 | ok |
| partner | Retrocausal | 9 | 9 | 0.819 | 0.0234 | ok |
| good | Protex AI | 8 | 7 | 0.562 | 0.019 | ok |
| good | Augury | 7 | 7 | 0.589 | 0.0183 | ok |
| weak | Viz.ai | 3 | 4 | 0.481 | 0.0171 | ok |
| weak | Notion | 5 | 4 | 0.397 | 0.0151 | ok |
| bad | Airbnb | 2 | 2 | 0.318 | 0.0134 | ok |

## Reading the table
- **partner** rows: fit and partner-sim should be high; **self-sim ≈ 1.0** confirms the embedding+metric path is sound.
- **good** rows: fit high — the system rewards genuine Industry-4.0 fit.
- **weak/bad** rows: fit low — the system DISCRIMINATES, it does not just produce plausible prose for everything.
- Any ⚠ flag is a result contradicting its expected label — review the matching `eval_results/<site>.json`.
