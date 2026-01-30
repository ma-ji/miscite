# AGENTS.md

Repository guide for future assistants working on **miscite**.

## Project conventions
- Keep this AGENTS.md up to date; update it whenever the codebase structure, workflows, or contracts change.
- This project is in active development; do not preserve backward compatibility or add fallbacks unless explicitly requested.

## Product summary
miscite is a citation-check platform for academic manuscripts (PDF/DOCX). It parses in-text citations and bibliography entries, resolves references against metadata sources, flags issues (missing refs, retractions, predatory venues, potentially inappropriate citations), and renders a traceable report in a FastAPI + Jinja UI.

## Quickstart (dev)
- Install deps: `pip install -r requirements.txt` (optional NLI: `pip install -r requirements-optional.txt`).
- Configure env: copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`.
- Run web app: `python -m server.main` (or `make dev`).
- Run worker: `python -m server.worker` (or `make worker`).
- Combined: `bash scripts/dev.sh`.
  - Optional flags for both web/worker: `--blank-db`, `--text-backend {markitdown,docling}`, `--accelerator {cpu,gpu}`, `--debug`.

## High-level architecture
- **Web app**: `server/main.py` creates FastAPI app, mounts routes and static assets.
- **Worker**: `server/worker.py` spawns one or more worker processes; `server/miscite/worker.py` runs the job loop.
- **DB**: SQLAlchemy models in `server/miscite/models.py`, SQLite by default.
- **Storage**: uploads saved to `MISCITE_STORAGE_DIR` (default `./data/uploads`).
- **Analysis pipeline**: `server/miscite/analysis/pipeline.py` is the main orchestration.

## Repository map
- `server/main.py`: FastAPI entrypoint.
- `server/worker.py`: worker process launcher.
- `server/miscite/worker.py`: job loop, progress events, dataset auto-sync.
- `server/miscite/analysis/`: text extraction, parsing, matching, checks, deep analysis.
- `server/miscite/prompts/`: LLM prompts organized by stage (parsing/matching/checks/deep_analysis) with paired `system.txt` + `user.txt`.
- `server/miscite/prompts/registry.yaml`: prompt catalog (purpose, inputs, schema).
- `server/miscite/prompts/schemas/`: JSON Schemas for LLM prompt outputs.
- `server/miscite/sources/`: OpenAlex, Crossref, arXiv, datasets, optional APIs, sync helpers.
- `server/miscite/routes/`: auth, dashboard, billing, health endpoints.
- `server/miscite/templates/`: Jinja UI (job report page relies on report JSON shape).
- `server/miscite/templates/report_access.html`: token-based public report access form.
- `server/miscite/static/styles.css`: design system (see `DESIGN.md`).
- `kb/`: research and promptbook material (not wired into the runtime app).
- `scripts/`: helper scripts (dev runner, Zotero helper).

## Runtime data flow
1) **Upload** (`/upload`): `server/miscite/storage.py` saves PDF/DOCX and creates `Document` + `AnalysisJob` rows.
2) **Worker claims job**: `server/miscite/worker.py` updates job to RUNNING and writes `AnalysisJobEvent` progress rows.
3) **Analyze document**: `server/miscite/analysis/pipeline.py`:
   - Text extraction via Docling (`analysis/docling_extract.py`).
   - LLM parsing (OpenRouter) to get bibliography + citations (`analysis/llm_parsing.py`).
   - Resolve references in order: OpenAlex -> Crossref -> arXiv (LLM assists ambiguous matches).
   - Flag issues: missing bibliography, unresolved refs, retractions, predatory venues, inappropriate citations (LLM + optional local NLI).
   - Optional deep analysis: expands citation neighborhood via OpenAlex and suggests additions/removals (`analysis/deep_analysis.py`).
   - Report assembled + methodology markdown.
4) **UI + API**: `server/miscite/routes/dashboard.py` serves `/jobs/{id}` report page and `/api/jobs/{id}` JSON.

## Report schema contract
The report JSON returned by `analysis/pipeline.py` is rendered in `server/miscite/templates/job.html` and returned by `/api/jobs/{id}`. If you add new issue types, summary fields, or change schema, update:
- `server/miscite/templates/job.html`
- any clients reading `/api/jobs/{id}`

## Data model (SQLAlchemy)
Defined in `server/miscite/models.py`:
- `User` / `UserSession`: auth + session cookies.
- `Document`: uploaded file metadata.
- `AnalysisJob`: status, report JSON, methodology markdown, access-token hash/hint for shared report access.
- `AnalysisJobEvent`: streaming progress events for SSE.
- `BillingAccount`: Stripe subscription status.

No migrations are present; schema changes require manual DB resets or a future migration plan.

## Configuration and env
Settings live in `server/miscite/config.py` and `.env.example`. Critical env keys:
- Required: `OPENROUTER_API_KEY`.
- Storage/DB: `MISCITE_DB_URL`, `MISCITE_STORAGE_DIR`, upload limits.
- Text extraction/accelerator: `MISCITE_TEXT_EXTRACT_BACKEND`, `MISCITE_TEXT_EXTRACT_PROCESS_CONTEXT`, `MISCITE_ACCELERATOR`.
- LLM: model names and call limits (parse, match, inappropriate).
- Sources: Crossref mailto/user-agent, retraction/predatory datasets/APIs.
- Billing (optional): Stripe keys and flags.
- Ops/security: maintenance mode, load shedding, rate limits, upload scan, job reaper, access-token TTL.

If you add new env vars:
- Update `server/miscite/config.py`.
- Update `.env.example` and `README.md`.

## External integrations
- **OpenRouter**: LLM parsing, matching, and inappropriate-citation classification.
- **OpenAlex**: metadata resolution, retraction flags, deep analysis network expansion.
- **Crossref**: metadata resolution, retraction info.
- **arXiv**: metadata resolution fallback.
- **Retraction Watch**: local CSV dataset; sync via `server/sync_retractionwatch.py`.
- **Predatory lists**: local CSV or Google Sheets sync; optional custom API.
- **Stripe**: optional subscription gating in `server/miscite/routes/billing.py`.

## UI and design system
- Templates: `server/miscite/templates/`.
- CSS tokens + components documented in `DESIGN.md` and implemented in `server/miscite/static/styles.css`.

## Worker notes / footguns
- A worker must run for uploads to process; jobs stay PENDING otherwise.
- The pipeline raises errors if required datasets are missing:
  - Retraction Watch CSV must exist.
  - Predatory venue source must be enabled (CSV or API).
- LLM parsing and inappropriate checks are mandatory; missing `OPENROUTER_API_KEY` or disabled `MISCITE_ENABLE_LLM_INAPPROPRIATE` fails jobs.
- Docling is required for text extraction (`docling` package).
- Stale RUNNING jobs are reaped based on `MISCITE_JOB_STALE_SECONDS`; be mindful of long-running documents.

## Common commands
- `make dev` / `python -m server.main`: run web app.
- `make worker` / `python -m server.worker`: run worker.
- `make sync-rw` / `python -m server.sync_retractionwatch`: sync retraction dataset.
- `make sync-predatory` / `python -m server.sync_predatory`: sync predatory lists.
- `make check`: compile server modules.

## Extending the system
- New metadata sources: add client in `server/miscite/sources/` and wire into `analysis/pipeline.py`.
- New issue types: add to pipeline and update report template/summary counts.
- Parsing changes: update `analysis/llm_parsing.py` or `analysis/citation_parsing.py`.
- Deep analysis tweaks: `analysis/deep_analysis.py` (watch LLM budget and OpenAlex usage limits).

## Security notes
- Auth uses PBKDF2-SHA256 with session + CSRF cookies (`server/miscite/security.py`).
- Set `MISCITE_COOKIE_SECURE=true` for HTTPS deployments.
