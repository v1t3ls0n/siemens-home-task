# partner-scout pro

A production-shaped web application that evaluates a startup as a potential
**technology partner for Siemens Digital Industries Software**, from public
sources only.

Give it a startup URL → it crawls and indexes the site (with change
detection), an LLM agent builds a product profile, numeric embedding metrics
measure where the offering correlates with the Siemens portfolio and with
existing partners, and a second agent produces scored, justified analysis —
rendered with radar/bar charts and a correlation heatmap.

## Feature highlights

- **Multi-provider LLM layer with cost routing** — OpenAI (Responses API via
  the OpenAI Agents SDK, automatic prompt caching), Anthropic, and **local
  models via Ollama**, all behind one router. Pipeline stages request a
  *tier* (`light` for extraction, `heavy` for final scoring); `config.yaml`
  maps tiers to models with **fallback chains** across providers.
- **Real vector database: OpenSearch** — kNN (HNSW, cosine) index. Every
  stored document carries `checksum` (SHA-256), `fetched_at` (last content
  change) and `last_checked` — a re-crawl re-embeds **only what changed**.
- **Cost controls at every layer** — tier routing, embedding cache keyed by
  content hash, analysis result cache, OpenAI prompt caching, optional
  all-local mode (Ollama models + Ollama embeddings = $0 per analysis).
  `/api/usage` reports tokens + estimated USD per model.
- **Numeric, visual match evidence** — per-product cosine correlation,
  per-partner cosine similarity, and a chunk×product heatmap showing *where*
  in the startup's content the overlap with which Siemens product lives.
- **All optional task items** — partner comparison, 1-10 similarity rank with
  justification, and a cloud deployment path.

## Quick start (docker)

```bash
cp .env.example .env         # put your OPENAI_API_KEY (minimum)
docker compose up --build    # OpenSearch + app
# open http://localhost:8000
```

Local dev without docker (needs a running OpenSearch, or set
`search.backend: local` in config.yaml to skip it):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
uvicorn app.main:app --reload
```

Fully local / zero-cost mode: `docker compose --profile local up`, then
`ollama pull qwen2.5:7b && ollama pull nomic-embed-text`, and in config.yaml
set the tiers to `ollama:qwen2.5:7b` and embeddings to
`provider: ollama, model: nomic-embed-text, dim: 768`.

## Architecture

```
 browser ──> FastAPI (app/main.py) ──> analysis pipeline (app/analysis/pipeline.py)
                                          │
   1. INGEST   crawler (polite, bounded) ─┤  deterministic, reproducible
               chunker → embeddings ──────┤  embed cache: sha256(content)
               indexer → OpenSearch ──────┤  checksum + fetched_at + last_checked
                                          │  unchanged page = no re-embed, no cost
   2. RESEARCH researcher agent (LIGHT tier)
               tools: list_startup_pages / read_page (reads the INDEX)
               → StartupProfile (structured, pydantic)
                                          │
   3. METRICS  numpy cosine: per-product correlation, partner similarity,
               chunk×product heatmap  — numbers, not vibes
                                          │
   4. ANALYZE  analyst agent (HEAVY tier)
               profile + retrieved chunks + metrics → MatchReport
               (5 fit dimensions, 1-10 scores, justifications)
                                          │
               SQLite history + /api/usage cost report → charts in the UI
```

### Model routing (`config.yaml`)

| Tier | Used for | Default | Fallbacks |
|---|---|---|---|
| light | page reading, profile extraction | `openai:gpt-5-mini` | anthropic haiku → local qwen |
| heavy | comparison, scoring, justification | `openai:gpt-5.1` | anthropic sonnet → gpt-5-mini |

Fallbacks fire on provider errors/rate limits, so one provider outage
degrades quality gracefully instead of failing the request.

## Design decisions (for the follow-up discussion)

1. **Ingestion is deterministic; only analysis is model-driven.** The crawler
   decides *what exists*, the agent decides *what it means*. Reproducible,
   debuggable, and the index is a persistent asset (each re-run gets cheaper).
2. **Tier routing, not one model.** Reading web pages doesn't need a frontier
   model; scoring a partnership does. Splitting the pipeline by required
   capability is the single biggest LLM cost lever.
3. **Checksums + timestamps on every document.** "Has the site changed since
   we looked?" is answerable in O(1); unchanged content costs zero tokens on
   re-crawl. `fetched_at` vs `last_checked` distinguishes "content changed"
   from "we visited".
4. **Numbers before narrative.** Cosine similarities (per product, per
   partner, per chunk) are computed with numpy and *given to* the analyst
   agent as evidence. The 1-10 ranks are LLM judgment grounded in metrics —
   and the UI shows the raw numbers so a human can audit the reasoning.
5. **Structured outputs end-to-end.** Both agents return pydantic models
   (`output_type=`), so there is no JSON-parsing failure mode.
6. **Pluggable store.** `VectorStore` protocol with OpenSearch (primary) and
   a numpy fallback — the app still runs and demos without infrastructure,
   and free-tier cloud hosts without OpenSearch remain viable.
7. **Public sources only** — research prompt forbids outside knowledge and
   requires `evidence_urls`; reference data files cite public materials.

## Deployment (optional task item)

- **Simplest**: any VM (e.g. Oracle Cloud free tier) → `docker compose up`.
- **Free PaaS** (Render/Railway, no OpenSearch): set `search.backend: local`
  in config.yaml, deploy the Dockerfile, add `OPENAI_API_KEY`. Same app, the
  store interface swaps the backend.
- **Managed OpenSearch**: point `OPENSEARCH_URL` at any hosted cluster
  (e.g. Aiven free trial / AWS OpenSearch) and deploy the app anywhere.

## API

| Endpoint | Description |
|---|---|
| `POST /api/analyze {url, force}` | Full pipeline; `force` re-crawls + re-analyzes |
| `GET /api/analyses` | History of analyzed startups |
| `GET /api/usage` | Tokens + estimated cost per model |
| `GET /api/health` | Liveness |

## Known limits (honest POC boundaries)

- JS-only sites yield thin text (no headless browser — a deliberate scope cut).
- The Siemens portfolio / partner list are curated snapshots in `data/`;
  a production version would ingest siemens.com and the partner directory
  through the same checksum-aware pipeline (the mechanism already supports it).
- Local models must support tool calling (qwen2.5, llama3.1 do).
