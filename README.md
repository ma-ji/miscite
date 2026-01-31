# miscite

Citation-check platform for academic manuscripts (PDF / DOCX) with a traceable, transparent report.

This repository contains:

- A FastAPI web app (upload + dashboard + report UI)
- A background worker (parallel, multi-process) that produces reports
- A modular analysis pipeline you can extend (more checks, new sources, better parsing)

UI uses a lightweight CSS-variables design system (light/dark) in `server/miscite/static/styles.css` (see `DESIGN.md`).

## Features

- Upload PDF or DOCX and generate a citation-check report:
  - **Missing bibliography references**: in-text citations not found in the bibliography section.
  - **Unresolved references**: bibliography items not found in metadata sources.
  - **Retracted articles**: detected via OpenAlex/Crossref retraction flags (when available), plus optional custom retraction API and/or local dataset file.
  - **Predatory journals/publishers**: detected via optional custom predatory API and/or local dataset file.
  - **Potentially inappropriate citations**:
    - Heuristic relevance between citing context and the cited work’s title/abstract (when available).
    - Optional local NLI model (GPU/CPU) to catch obvious contradictions.
    - OpenRouter LLM for conservative classification (“appropriate / inappropriate / uncertain”).
- Optional **deep literature analysis** (off by default): picks key references, expands the surrounding citation neighborhood (works cited by / citing them), and suggests additions/removals to strengthen the paper.
- Clear report transparency:
  - Lists data sources used per reference.
  - Includes methodology + limitations.
- Parallel processing via background workers (run multiple worker processes to scale).
- Optional Stripe subscription gating (feature flag via env).

## What this is / isn’t (yet)

- This is **not** a full-text paywalled citation verifier: by default it validates against *bibliographic metadata* (title/abstract/venue) + retraction/predatory sources.
- “Non-existent” means “not resolvable in the configured metadata sources” and can include:
  - incomplete bibliography formatting, missing DOI, bad OCR, or parsing errors
  - the work not indexed by a source you enabled
  - legitimate works (e.g., books/chapters) that are hard to resolve from metadata alone

## Quickstart (dev)

1) Create a virtualenv and install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Configure env:

```bash
cp .env.example .env
```

3) Set required keys in `.env`:

- `OPENROUTER_API_KEY`
- `MISCITE_MAILGUN_API_KEY`
- `MISCITE_MAILGUN_DOMAIN`
- `MISCITE_MAILGUN_SENDER`

4) Run the web app:

```bash
python -m server.main
```

5) Run at least one worker (in another terminal):

```bash
python -m server.worker
```

Then open `http://localhost:8000`.

### Developer workflow shortcuts

Use the `Makefile` for common tasks:

```bash
make dev
make worker
make sync-rw
make check
```

Or launch web + worker together:

```bash
bash scripts/dev.sh
```

## Optional dependencies

Some features require extra packages that are **not** installed by default:

- Local NLI (GPU/CPU) (`MISCITE_ENABLE_LOCAL_NLI=true`)

Install with:

```bash
pip install -r requirements-optional.txt
```

## Architecture

- Web app: `server/main.py` (FastAPI)
  - UI routes: `server/miscite/routes/`
  - Templates/static assets: `server/miscite/templates/`, `server/miscite/static/`
- Worker: `server/worker.py` + `server/miscite/worker.py`
  - Claims jobs from DB (`analysis_jobs`) and runs the analysis pipeline
- Analysis pipeline: `server/miscite/analysis/pipeline.py`
  - Text extraction: `server/miscite/analysis/text_extract.py`
  - Citation + bibliography parsing: `server/miscite/analysis/citation_parsing.py`
  - Optional local NLI: `server/miscite/analysis/local_nli.py`
- Sources:
  - Crossref metadata: `server/miscite/sources/crossref.py`
  - OpenAlex metadata/retraction flag: `server/miscite/sources/openalex.py`
  - arXiv metadata: `server/miscite/sources/arxiv.py`
  - Custom APIs: `server/miscite/sources/retraction_api.py`, `server/miscite/sources/predatory_api.py`
  - Local datasets: `server/miscite/sources/datasets.py`

## Configuration

Copy `.env.example` to `.env` and edit. Key settings:

### Core

- `MISCITE_DB_URL` (default: `sqlite:///./data/miscite.db`)
- `MISCITE_STORAGE_DIR` (default: `./data/uploads`)
- `MISCITE_MAX_UPLOAD_MB` (default: `50`)
- `MISCITE_MAX_BODY_MB` (default: `55`)
- `MISCITE_MAX_UNPACKED_MB` (default: `250`)
- `MISCITE_SESSION_DAYS` (default: `14`)
- `MISCITE_LOGIN_CODE_TTL_MINUTES` (default: `15`)
- `MISCITE_LOGIN_CODE_LENGTH` (default: `6`)
- `MISCITE_MAILGUN_API_KEY`
- `MISCITE_MAILGUN_DOMAIN`
- `MISCITE_MAILGUN_SENDER`
- `MISCITE_MAILGUN_BASE_URL` (default: `https://api.mailgun.net/v3`)
- `MISCITE_TURNSTILE_SITE_KEY`
- `MISCITE_TURNSTILE_SECRET_KEY`
- `MISCITE_TURNSTILE_VERIFY_URL` (default: `https://challenges.cloudflare.com/turnstile/v0/siteverify`)
- `MISCITE_LOG_LEVEL` (default: `INFO`)
- `MISCITE_API_TIMEOUT_SECONDS` (default: `20`)
- `MISCITE_CACHE_ENABLED` (default: `true`) – enables local caching for HTTP + LLM calls
- `MISCITE_CACHE_DIR` (default: `./data/cache`) – on-disk cache directory
- `MISCITE_CACHE_LLM_TTL_DAYS` (default: `30`) – TTL for cached OpenRouter JSON results
- `MISCITE_CACHE_HTTP_TTL_DAYS` (default: `30`) – TTL baseline for cached metadata HTTP responses
- `MISCITE_CACHE_TEXT_TTL_DAYS` (default: `30`) – TTL for cached extracted text
- `MISCITE_TEXT_EXTRACT_BACKEND` (default: `markitdown`, options: `markitdown|docling`)
- `MISCITE_TEXT_EXTRACT_TIMEOUT_SECONDS` (default: `120`)
- `MISCITE_TEXT_EXTRACT_SUBPROCESS` (default: `true`)
- `MISCITE_TEXT_EXTRACT_PROCESS_CONTEXT` (default: `auto`, options: `auto|fork|spawn`)
- `MISCITE_ACCELERATOR` (default: `cpu`, options: `cpu|gpu`)
- `MISCITE_COOKIE_SECURE` (default: `false`)
- `MISCITE_TRUST_PROXY` (default: `false`)
- `MISCITE_RELOAD` (default: `false`) – enables autoreload for `python -m server.main`

Notes:
- `markitdown` supports multiple file types; use `docling` if you prefer its PDF/DOCX pipeline.
- `MISCITE_TEXT_EXTRACT_PROCESS_CONTEXT=auto` chooses `fork` on Linux and `spawn` on macOS/Windows.
- If you see `Text extraction timed out`, try increasing `MISCITE_TEXT_EXTRACT_TIMEOUT_SECONDS` (Docling on CPU can be slow) or set `MISCITE_TEXT_EXTRACT_PROCESS_CONTEXT=spawn`.
- `gpu` uses CUDA via torch (local NLI only).

Config values are validated at startup; out-of-range values raise errors. Key bounds:

- `MISCITE_API_TIMEOUT_SECONDS`: 2–120
- `MISCITE_WORKER_POLL_SECONDS`: 0.1–10
- `MISCITE_LLM_MAX_CALLS`: 1–200
- `MISCITE_LLM_MATCH_MAX_CALLS`: 0–200
- LLM parse sizes: 1,000–500,000 chars (refs/citations)

### Ops controls (maintenance, load shedding, tokens)

- `MISCITE_MAINTENANCE_MODE` (default: `false`) – disables uploads/rotations/billing writes, keeps read-only access
- `MISCITE_MAINTENANCE_MESSAGE` – banner text shown in the UI
- `MISCITE_LOAD_SHED_MODE` (default: `false`) – disables deep analysis and clamps LLM call budgets
- `MISCITE_ACCESS_TOKEN_DAYS` (default: `7`) – report access tokens expire after this many days (reports are deleted after expiry)
- `MISCITE_EXPOSE_SENSITIVE_REPORT_FIELDS` (default: `false`) – expose full data source details + configuration snapshots in `/api/jobs/{id}`

### Rate limiting

- `MISCITE_RATE_LIMIT_ENABLED` (default: `true`)
- `MISCITE_RATE_LIMIT_WINDOW_SECONDS` (default: `60`)
- `MISCITE_RATE_LIMIT_LOGIN_REQUEST`, `MISCITE_RATE_LIMIT_LOGIN_VERIFY`, `MISCITE_RATE_LIMIT_UPLOAD`
- `MISCITE_RATE_LIMIT_REPORT_ACCESS`, `MISCITE_RATE_LIMIT_EVENTS`, `MISCITE_RATE_LIMIT_STREAM`, `MISCITE_RATE_LIMIT_API`

### Job health

- `MISCITE_JOB_STALE_SECONDS` (default: `3600`)
- `MISCITE_JOB_STALE_ACTION` (default: `fail`, options: `fail|requeue`)
- `MISCITE_JOB_MAX_ATTEMPTS` (default: `2`)
- `MISCITE_JOB_REAP_INTERVAL_SECONDS` (default: `60`)

### Upload scanning (optional)

- `MISCITE_UPLOAD_SCAN_ENABLED` (default: `false`)
- `MISCITE_UPLOAD_SCAN_COMMAND` (example: `clamdscan --no-summary {path}`)
- `MISCITE_UPLOAD_SCAN_TIMEOUT_SECONDS` (default: `45`)

### Parallelism

- `MISCITE_WORKER_PROCESSES` (default: `1`) – worker subprocesses inside one `python -m server.worker`
- `MISCITE_WORKER_POLL_SECONDS` (default: `1.5`) – DB polling interval

### CLI overrides

`python -m server.main` and `python -m server.worker` accept:

- `--blank-db` – use a blank sqlite DB at `./data/miscite-blank.db`
- `--text-backend {markitdown,docling}`
- `--accelerator {cpu,gpu}`
- `--debug` – enable verbose logging (`MISCITE_LOG_LEVEL=DEBUG`)

### Metadata (OpenAlex/Crossref/arXiv)

- `MISCITE_CROSSREF_MAILTO` – recommended by Crossref for polite usage
- `MISCITE_CROSSREF_USER_AGENT` – recommended to include contact info

### Retracted papers (sources)

The pipeline aggregates *signals*; strong sources (Retraction Watch / custom API) are treated as high-confidence.
Single-source metadata flags (e.g., OpenAlex/Crossref only) are still flagged, but marked for review.

- OpenAlex/Crossref: metadata resolution with retraction flags when present
- Local dataset (optional): `MISCITE_RETRACTIONWATCH_CSV`
- Custom API (optional):
  - `MISCITE_RETRACTION_API_ENABLED=true`
  - `MISCITE_RETRACTION_API_URL=https://…`
  - `MISCITE_RETRACTION_API_MODE=lookup|list`
  - `MISCITE_RETRACTION_API_TOKEN=…` (optional)

### Predatory journals/publishers (sources)

The pipeline aggregates *signals*; exact ISSN/name matches or multiple sources are high-confidence.
Fuzzy name matches are still flagged, but marked for review.

- Local dataset (optional): `MISCITE_PREDATORY_CSV` (columns: `name,type,issn,source,notes`)
- Auto-sync (optional): Google Sheets lists via `MISCITE_PREDATORY_SYNC_ENABLED=true`
- Custom API (optional):
  - `MISCITE_PREDATORY_API_ENABLED=true`
  - `MISCITE_PREDATORY_API_URL=https://…`
  - `MISCITE_PREDATORY_API_MODE=lookup|list`
  - `MISCITE_PREDATORY_API_TOKEN=…` (optional)

### LLM (required)

Used for:

- parsing citations + bibliography into structured records
- classifying potentially inappropriate citations

- `OPENROUTER_API_KEY`
- `MISCITE_LLM_MODEL` (default: `google/gemini-3-flash-preview`)
- `MISCITE_ENABLE_LLM_INAPPROPRIATE` (default: `true`)
- `MISCITE_LLM_MAX_CALLS` (default: `25`) – caps per-document LLM calls

#### LLM models per task

You can use different LLM models for different tasks:

- `MISCITE_LLM_MODEL`: inappropriate-citation classification
- `MISCITE_LLM_PARSE_MODEL`: citation/bibliography parsing
- `MISCITE_LLM_MATCH_MODEL`: OpenAlex/Crossref/arXiv match disambiguation
- `MISCITE_LLM_DEEP_ANALYSIS_MODEL`: deep-analysis key-reference selection + recommendation drafting

### Deep analysis (optional)

Off by default (can be expensive):

- `MISCITE_ENABLE_DEEP_ANALYSIS=true`

#### LLM parsing

The worker uses an LLM to extract structured records for:

- bibliography entries (CSL-JSON + DOI/year/author fields)
- in-text citations (normalized numeric and author–year locators)

Regex is only used for deterministic, lightweight steps (e.g., DOI normalization). If a bibliography heading isn't detected, the LLM will attempt to extract the References section directly.

Settings:

- `MISCITE_LLM_PARSE_MODEL` (default: `MISCITE_LLM_MODEL`)
- `MISCITE_LLM_MATCH_MODEL` (default: `MISCITE_LLM_MODEL`)
- `MISCITE_LLM_MATCH_MAX_CALLS` (default: `50`) – caps per-document LLM calls used for match disambiguation
- `MISCITE_LLM_BIB_PARSE_MAX_CHARS`, `MISCITE_LLM_BIB_PARSE_MAX_REFS`
- `MISCITE_LLM_CITATION_PARSE_MAX_CHARS`, `MISCITE_LLM_CITATION_PARSE_MAX_LINES`, `MISCITE_LLM_CITATION_PARSE_MAX_CANDIDATE_CHARS`

#### Reference linking (OpenAlex → Crossref → arXiv)

For each bibliography entry, the pipeline attempts to link it to a metadata record, in order:

1) OpenAlex (DOI first; otherwise search by title + first author + year)
2) Crossref (DOI first; otherwise search by title + first author + year)
3) arXiv (ID/DOI first; otherwise search by title + first author + year)

For ambiguous (“fussy”) results, the LLM is used to conservatively choose a candidate (or return null). Resolution stops after the first matching source.

### Local NLI (optional GPU/CPU)

Used to catch obvious contradictions/entailments between the citing sentence and the cited abstract.

- `MISCITE_ENABLE_LOCAL_NLI=true`
- `MISCITE_LOCAL_NLI_MODEL` (default: `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`)

Notes:

- Requires installing `torch` + `transformers` yourself (not in `requirements.txt`).
- Does not fall back automatically on CUDA OOM (fail fast).

## Parallelism + GPU/CPU

- Run multiple worker processes by setting `MISCITE_WORKER_PROCESSES` (or run multiple `python -m server.worker` instances).
- Local NLI supports GPU or CPU.
- If you plan to handle many concurrent uploads:
  - prefer multiple workers rather than one giant process
  - keep per-document inference bounded (`MISCITE_LLM_MAX_CALLS`)

## Performance notes

- Local CSV datasets are cached in-memory per worker and only reloaded when the file timestamp changes.
- API clients reuse HTTP sessions to reduce connection overhead in long-running workers.

## Datasets

You can run with APIs only, datasets only, or both.

Local dataset files (CSV):

- **Retraction Watch**: `MISCITE_RETRACTIONWATCH_CSV`
- **Predatory journals/publishers**: `MISCITE_PREDATORY_CSV` (columns: `name,type,issn,source,notes`)

Sample schemas are provided in `server/miscite/datasets/`.

### Retraction Watch auto-sync (recommended)

Crossref hosts the Retraction Watch dataset in a public GitLab repository. This project can sync it locally in two ways:

1) **Worker auto-sync** (simple):
   - Set `MISCITE_RW_SYNC_ENABLED=true`
   - The worker syncs the dataset (git by default) and re-checks hourly, only downloading when stale.

2) **External scheduler** (most robust):
   - Run `python -m server.sync_retractionwatch` on a schedule (cron / systemd timer / Kubernetes CronJob).

Example cron (daily at 02:15):

```cron
15 2 * * * cd /path/to/miscite && /path/to/venv/bin/python -m server.sync_retractionwatch >> data/rw_sync.log 2>&1
```

### Predatory lists auto-sync (Google Sheets)

Two public Google Sheets from predatoryjournals.org (“The List”) are supported for predatory publishers and journals. Enable:

- `MISCITE_PREDATORY_SYNC_ENABLED=true`
- `MISCITE_PREDATORY_SYNC_INTERVAL_HOURS=24`
- `MISCITE_PREDATORY_PUBLISHERS_URL=...`
- `MISCITE_PREDATORY_JOURNALS_URL=...`

Manual sync:

```bash
python -m server.sync_predatory
```

## Optional APIs (retractions / predatory lists)

If you have access to organization-specific list APIs, you can enable lookups.

### Retraction API contract (custom)

The worker calls:

- `GET <MISCITE_RETRACTION_API_URL>?doi=<doi>`

Supported response shapes:

- `{"match": true, "record": {...}}`
- `{"records": [{...}, ...]}`
- `[{...}, ...]`

### Predatory API contract (custom)

The worker calls:

- `GET <MISCITE_PREDATORY_API_URL>?issn=<issn>&journal=<journal>&publisher=<publisher>`

Supported response shapes:

- `{"match": true, "record": {...}}`
- `{"records": [{...}, ...]}`
- `[{...}, ...]`

Modes:

- `lookup`: query per reference (recommended)
- `list`: fetch full list once and match locally (only if the dataset is small enough)

## Methodology (high level)

This implementation is inspired by the multi-stage, evidence-first approach described in:
`kb/BibAgent-An-Agentic-Framework-for-Traceable-Miscitation-Detection-in-Scientific-Literature/Preprint-PDF.md`.

In short:

1) Parse manuscript into citing contexts + bibliography items.
2) Resolve references (DOI/title) via bibliographic metadata sources.
3) Flag objective issues (missing refs, retractions, predatory venues).
4) For “inappropriate” citations, compare the citing context to retrieved metadata (title/abstract) and optionally use an LLM to produce a traceable rationale.

See the generated report’s “Methodology” section for detailed, per-run transparency.

## Billing (Stripe)

Billing is **off by default**. To enable subscription gating:

- `MISCITE_BILLING_ENABLED=true`
- `STRIPE_SECRET_KEY=...`
- `STRIPE_PRICE_ID=...`
- `STRIPE_WEBHOOK_SECRET=...` (recommended)

Endpoints:

- Checkout: `/billing/checkout`
- Customer portal: `/billing/portal`
- Webhook: `/billing/webhook`

If billing is enabled, uploads require an active/trialing subscription.

## Security notes

- Passwords are stored as PBKDF2-SHA256 (salted).
- Auth uses an HTTPOnly session cookie plus a separate CSRF cookie for POST actions.
- For production, set `MISCITE_COOKIE_SECURE=true` and serve behind HTTPS.
- Consider enabling upload scanning (e.g., ClamAV) in production.

## Health endpoints

- `/healthz` – liveness (always `ok` if process is up)
- `/readyz` – readiness (checks DB, datasets, and required API keys)

## Extending the platform

Common extension points:

- Add new source clients in `server/miscite/sources/` and include them in `server/miscite/analysis/pipeline.py`.
- Add new issue types by appending to `issues` in the pipeline (keeps report schema stable).
- Improve parsing:
  - PDF text extraction quality varies widely; `markitdown[all]` improves coverage across formats.
  - Citation formats vary; update `server/miscite/analysis/citation_parsing.py` for your domain.

## Zotero helper (separate)

`zotero2kb.py` is a helper script to export Zotero attachments into Markdown via `zotero_files2md`.
It is currently **not wired into** the web app, but can be used to build a local knowledge base to support future retrieval-based checks.
