# Development

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m server.migrate upgrade
```

Run the web app:

```bash
python -m server.main
```

Run at least one worker (new terminal):

```bash
python -m server.worker
```

Open `http://localhost:8000`.

## Common commands

```bash
make dev
make worker
bash scripts/dev.sh
make check
make db-upgrade
make db-check
```

### Combined runner flags

`bash scripts/dev.sh` supports a few useful dev flags shared by web/worker:

- `--blank-db`
- `--text-backend {markitdown,docling}`
- `--accelerator {cpu,gpu}`
- `--debug`

## Required configuration

- `OPENROUTER_API_KEY` is required for core parsing/matching/checks.
- Default `.env.example` is Docker/PostgreSQL-oriented (`db:5432`). For non-Docker local runs,
  point `MISCITE_DB_URL` to a reachable PostgreSQL instance (or set a temporary SQLite URL for
  isolated testing).
- `MISCITE_PUBLIC_ORIGIN` should be set in production so email links include the correct domain.
- `MISCITE_SAMPLE_REPORT_URL` controls the sample report CTA link (token, `/reports/<token>`, or full URL).
- Dataset paths are required unless you enable an API-based source:
  - `MISCITE_RETRACTIONWATCH_CSV` (Retraction Watch CSV)
  - `MISCITE_PREDATORY_CSV` (predatory venues CSV)

## Matching and verification tuning (optional)

- `MISCITE_LLM_MATCH_MAX_CALLS` limits LLM disambiguation calls used for citation↔bibliography matching and metadata resolution.
- `MISCITE_PREPRINT_YEAR_GAP_MAX` (default `5`) controls how many years of gap are treated as plausible for preprint/working-paper → published matches during metadata resolution.
- API concurrency controls (rate-limit safety + throughput):
  - `MISCITE_JOB_API_MAX_PARALLEL`: per-job cap across all outbound API calls.
  - `MISCITE_SOURCE_GLOBAL_MAX_OPENROUTER`
  - `MISCITE_SOURCE_GLOBAL_MAX_OPENALEX`
  - `MISCITE_SOURCE_GLOBAL_MAX_CROSSREF`
  - `MISCITE_SOURCE_GLOBAL_MAX_PUBMED`
  - `MISCITE_SOURCE_GLOBAL_MAX_ARXIV`
  - `MISCITE_SOURCE_GLOBAL_MAX_RETRACTION_API`
  - `MISCITE_SOURCE_GLOBAL_MAX_PREDATORY_API`
  - Note: source caps are per-process and shared by all jobs running in that worker process.
- PubMed (NCBI E-utilities) request identity / rate tuning:
  - `MISCITE_NCBI_TOOL` (default `miscite`)
  - `MISCITE_NCBI_EMAIL` (defaults to `MISCITE_CROSSREF_MAILTO`)
  - `MISCITE_NCBI_API_KEY` (optional)
  - References containing `PMID` / `PMCID` are treated as strong identifiers during the PubMed stage of resolution (without changing the overall lookup order).

## Deep analysis (optional)

Deep analysis is disabled by default (`MISCITE_ENABLE_DEEP_ANALYSIS=false`). When enabled, it expands a citation neighborhood around key references and produces:

- A ranked recommendation block with top 5 global actions.
- Section-by-section recommendations (top-level only), capped at 3 actions per section.
- Each action includes a concrete edit location (`where`) and a quoted nearby text anchor (`anchor_quote`).

Key settings:

- `MISCITE_ENABLE_DEEP_ANALYSIS`
- `MISCITE_ENABLE_DEEP_ANALYSIS_LLM_KEY_SELECTION`
- `MISCITE_ENABLE_DEEP_ANALYSIS_LLM_SUGGESTIONS`
- `MISCITE_ENABLE_DEEP_ANALYSIS_LLM_STRUCTURE`
- `MISCITE_DEEP_ANALYSIS_STRUCTURE_MAX_CANDIDATES`
- `MISCITE_DEEP_ANALYSIS_REVIEWER_RECENT_YEARS`
- `MISCITE_DEEP_ANALYSIS_REVIEWER_AUTHOR_WORKS_MAX`
- `MISCITE_ENABLE_DEEP_ANALYSIS_LLM_SUBSECTION_RECOMMENDATIONS`
- `MISCITE_DEEP_ANALYSIS_SUBSECTION_MAX_SUBSECTIONS`
- `MISCITE_DEEP_ANALYSIS_SUBSECTION_GRAPH_MAX_NODES`
- `MISCITE_DEEP_ANALYSIS_SUBSECTION_GRAPH_MAX_EDGES`
- `MISCITE_DEEP_ANALYSIS_SUBSECTION_TEXT_MAX_CHARS`
- `MISCITE_DEEP_ANALYSIS_SUBSECTION_PROMPT_MAX_REFS`
- `MISCITE_DEEP_ANALYSIS_ABSTRACT_MAX_CHARS`

Notes:

- `MISCITE_DEEP_ANALYSIS_SUBSECTION_MAX_SUBSECTIONS=0` means “all top-level sections”.
- `MISCITE_DEEP_ANALYSIS_REVIEWER_RECENT_YEARS=0` disables the recency filter (keeps all years).

## Billing (optional)

Usage billing is disabled by default. To enable Stripe balance top-ups and auto-charge, set:

- `MISCITE_BILLING_ENABLED=true`
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`
- `STRIPE_SUCCESS_URL` and `STRIPE_CANCEL_URL`
- Optional tuning: `MISCITE_BILLING_COST_MULTIPLIER`, `MISCITE_BILLING_MIN_CHARGE_CENTS`,
  `MISCITE_BILLING_AUTO_CHARGE_THRESHOLD_CENTS`, `MISCITE_BILLING_AUTO_CHARGE_AMOUNT_CENTS`,
  `MISCITE_BILLING_AUTO_CHARGE_IN_FLIGHT_TTL_SECONDS`,
  `MISCITE_OPENROUTER_PRICING_REFRESH_MINUTES`

## Optional dependencies

- Local NLI checks: `pip install -r requirements-optional.txt`

## Database migrations

- Apply pending migrations: `python -m server.migrate upgrade` (or `make db-upgrade`).
- Verify DB is at code head: `python -m server.migrate check` (or `make db-check`).
- Show DB-applied revisions: `python -m server.migrate current`.
- Show expected migration heads: `python -m server.migrate heads`.
- Create a new migration from model changes:
  `python -m server.migrate revision -m "describe change"` (or `make db-revision msg="..."`).

Runtime behavior:

- Web and worker startup now require DB revision at head and fail fast on mismatch.
- `bash scripts/dev.sh` and Docker `migrate` service automatically run migrations before app startup.
- For near zero-downtime deployments, prefer expand/contract migrations (additive change first,
  contract/drop in a later deploy after code has switched over).

## Caching

miscite caches expensive LLM + metadata lookups by default (can be disabled).

Cache layers:

- **DB cache table** (`CacheEntry`): structured JSON results (most metadata + small payloads).
- **File cache dir** (`MISCITE_CACHE_DIR`, default `./data/cache`): large text payloads (text extraction, some list-mode APIs).

Key settings:

- `MISCITE_CACHE_ENABLED`
- `MISCITE_CACHE_DIR`
- `MISCITE_CACHE_LLM_TTL_DAYS` (OpenRouter `chat_json`)
- `MISCITE_CACHE_HTTP_TTL_DAYS` (OpenAlex/Crossref/PubMed/arXiv + custom APIs)
- `MISCITE_CACHE_TEXT_TTL_DAYS` (text extraction outputs)

Debugging:

- Completed analysis reports now include `report.cache_debug` with per-namespace cache hit/miss/error counters for the current run.
- Worker logs now print a one-line cache summary per completed job (`hits` + split `json_hits`/`file_hits`, `misses`, `http_calls`, `errors`, `cache_writes` + top namespaces), visible in terminal output.
- `misses` are cache misses (not raw HTTP requests); `http_calls` counts outbound analysis HTTP requests (OpenRouter/OpenAlex/Crossref/PubMed/arXiv/custom APIs).
- Top namespaces in the terminal summary include per-namespace `jh`/`fh`/`m`/`http` counts (JSON hits, file hits, misses, outbound calls).
- To log cache HIT/MISS per cache lookup, set `MISCITE_LOG_LEVEL=DEBUG` and `MISCITE_CACHE_DEBUG_LOG_EACH=true` (very verbose).

Intentionally **not** cached: side-effectful or per-request auth flows (Mailgun email sends, Cloudflare Turnstile verification, Stripe).

## Datasets

Sample CSV schemas live in `server/miscite/datasets/`.

### Sync commands

```bash
python -m server.sync_retractionwatch
python -m server.sync_predatory
```

### Retraction Watch (`MISCITE_RETRACTIONWATCH_CSV`)

This project expects the Crossref-hosted Retraction Watch dataset CSV schema.

Required header columns (strict):

- `OriginalPaperDOI` (used for matching)
- `RetractionNature` (filtered to rows containing "retraction" by default)
- `RetractionDate`
- `Reason`
- `Record ID`
- `Title`
- `Journal`
- `Publisher`
- `URLS`
- `Paywalled`
- `Notes`

Sample: `server/miscite/datasets/retractionwatch.sample.csv`.

### Predatory venues (`MISCITE_PREDATORY_CSV`)

Required header columns:

- `name`
- `type` (journal | publisher)
- `issn`
- `source`
- `notes`

Matching is done by ISSN (exact) or by normalized journal/publisher name.

Sample: `server/miscite/datasets/predatory.sample.csv`.

#### Auto-sync (optional)

This project can auto-sync the predatory CSV from two Google Sheets (publishers + journals)
provided by predatoryjournals.org.

Enable with:

- `MISCITE_PREDATORY_SYNC_ENABLED=true`
- `MISCITE_PREDATORY_PUBLISHERS_URL=...`
- `MISCITE_PREDATORY_JOURNALS_URL=...`

## Troubleshooting

- Uploads stay `PENDING` until a worker is running.
- The worker fails jobs early if required datasets are missing.
