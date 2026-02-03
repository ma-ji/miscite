# AGENTS.md

Repository guide for future assistants working on **miscite**.

## Project conventions

- Keep this AGENTS.md up to date; update it whenever the codebase structure, workflows, or contracts change.
- This project is in active development; do not preserve backward compatibility or add fallbacks unless explicitly requested.
- When adding or refactoring steps, split data prep from matching/analysis into separate modules or folders when appropriate (e.g., `sources/*/data.py` + `sources/*/match.py`, and thin orchestrators under `analysis/pipeline/` / `analysis/deep_analysis/`).
- Keep documentation centralized under `docs/` (avoid adding many small per-folder `README.md` files unless there's a strong reason).
- **Record major agent interactions in `kb/promptbook.md`:** when an agent prompt leads to non-trivial code/architecture changes, new workflows, or changed assumptions, append an entry with **date**, **goal**, **prompt (or summary)**, **files touched**, and **decision/rationale**. Skip trivial Q&A and typo fixes.

## Product summary

miscite is a citation-check platform for academic manuscripts (PDF/DOCX). It parses in-text citations and bibliography entries, resolves references against metadata sources, flags issues (missing refs, retractions, predatory venues, potentially inappropriate citations), and renders a traceable report in a FastAPI + Jinja UI.

## Quickstart (dev)

- Install deps: `pip install -r requirements.txt` (optional NLI: `pip install -r requirements-optional.txt`).
- Configure env: copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`.
- Run web app: `python -m server.main` (or `make dev`).
- Run worker: `python -m server.worker` (or `make worker`).
- Combined: `bash scripts/dev.sh`.
  - Optional flags for both web/worker: `--blank-db`, `--text-backend {markitdown,docling}`, `--accelerator {cpu,gpu}`, `--debug`.

## Quickstart (docker)

- Build + run (web + worker): `docker compose up -d --build`
- Dev override (bind mount + reload): `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`

## High-level architecture

- **Web app**: `server/main.py` creates FastAPI app, mounts routes and static assets.
- **Worker**: `server/worker.py` spawns one or more worker processes; `server/miscite/worker/` runs the job loop.
- **DB**: SQLAlchemy models in `server/miscite/core/models.py`, SQLite by default.
- **Storage**: uploads saved to `MISCITE_STORAGE_DIR` (default `./data/uploads`).
- **Analysis pipeline**: `server/miscite/analysis/pipeline/` is the main orchestration.

## Repository map

- `Dockerfile`: single image for web + worker.
- `docker-compose.yml`: production-ish Compose stack (web + worker + `./data` bind mount).
- `docker-compose.dev.yml`: dev override (bind mount code + reload/log level).
- `docker-compose.caddy.yml`: optional Caddy reverse proxy (automatic TLS).
- `docs/`: centralized documentation (start at `docs/README.md`).
- `deploy/`: deployment assets (`Caddyfile`, `miscite.service` with `COMPOSE_FILES` for compose overrides, `monitoring.md`).
- `server/main.py`: FastAPI entrypoint.
- `server/worker.py`: worker process launcher.
- `server/miscite/worker/`: job loop, progress events, dataset auto-sync.
- `server/miscite/core/`: shared config, db, models, cache, security, storage, middleware, email, rate limiting.
- `server/miscite/billing/`: OpenRouter pricing cache, LLM usage tracking, cost calculation, Stripe helpers, ledger updates.
- `server/miscite/web/`: Jinja template helpers + filters.
- `server/miscite/analysis/`: pipeline steps (extract/parse/checks/deep_analysis/report/shared + pipeline/).
- `server/miscite/prompts/`: LLM prompts organized by stage (parsing/matching/checks/deep_analysis) with paired `system.txt` + `user.txt`.
- `server/miscite/prompts/registry.yaml`: prompt catalog (purpose, inputs, schema).
- `server/miscite/prompts/schemas/`: JSON Schemas for LLM prompt outputs.
- `server/miscite/sources/`: OpenAlex, Crossref, arXiv, datasets, optional APIs, sync helpers (`sources/predatory/` and `sources/retraction/` split data prep vs matching).
- `server/miscite/routes/`: auth, dashboard, billing, health endpoints.
- `server/miscite/routes/seo.py`: robots.txt + sitemap.xml + favicon redirect endpoints.
- `server/miscite/core/email.py`: Mailgun email delivery helpers.
- `server/miscite/core/turnstile.py`: Cloudflare Turnstile verification helper.
- `server/miscite/templates/`: Jinja UI (job report page relies on report JSON shape).
- `server/miscite/templates/report_access.html`: token-based public report access form.
- `server/miscite/static/styles.css`: design system (see `DESIGN.md`).
- `server/miscite/static/favicon.svg`: brand favicon (referenced in `base.html`).
- `kb/`: research and promptbook material (not wired into the runtime app). Don't delete contents in `promptbook.md`.
- `deploy/monitoring.md`: deployment monitoring options.
- `scripts/`: helper scripts (dev runner, nginx install, Docker install, VPS bootstrap, backups, Zotero helper).

## Runtime data flow

1) **Upload** (`/upload`): `server/miscite/core/storage.py` saves PDF/DOCX and creates `Document` + `AnalysisJob` rows.
2) **Worker claims job**: `server/miscite/worker/` updates job to RUNNING and writes `AnalysisJobEvent` progress rows.
3) **Analyze document**: `server/miscite/analysis/pipeline/`:
   - Text extraction via Docling (`analysis/extract/docling_extract.py`).
   - LLM parsing (OpenRouter) to get bibliography + citations (`analysis/parse/llm_parsing.py`).
   - Resolve references in order: OpenAlex -> Crossref -> arXiv (LLM assists ambiguous matches).
   - Flag issues: missing bibliography, unresolved refs, retractions, predatory venues, inappropriate citations (LLM + optional local NLI).
   - Optional deep analysis: expands citation neighborhood via OpenAlex and suggests additions/removals (`analysis/deep_analysis/deep_analysis.py`).
   - Report assembled + methodology markdown.
   - On completion, the worker issues the access token, deducts LLM usage cost from balance, and emails the access token.
4) **UI + API**: `server/miscite/routes/dashboard.py` serves `/jobs/{id}` report page and `/api/jobs/{id}` JSON (owners can manage access tokens + delete reports here).

## Report schema contract

The report JSON returned by `analysis/pipeline/` is rendered in `server/miscite/templates/job.html` and returned by `/api/jobs/{id}`. If you add new issue types, summary fields, or change schema, update:

- `server/miscite/templates/job.html`
- any clients reading `/api/jobs/{id}`

## Data model (SQLAlchemy)

Defined in `server/miscite/core/models.py`:

- `User` / `UserSession`: auth + session cookies.
- `LoginCode`: short-lived email sign-in codes.
- `Document`: uploaded file metadata.
- `AnalysisJob`: status, report JSON, methodology markdown, access-token hash/hint/value + expiry for shared report access.
- `AnalysisJobEvent`: streaming progress events for SSE.
- `BillingAccount`: Stripe customer + balance + auto-charge settings.
- `BillingTransaction`: balance ledger entries (top-ups, usage charges, auto-charge).

No migrations are present; schema changes require manual DB resets or a future migration plan.

## Configuration and env

Settings live in `server/miscite/core/config.py` and `.env.example`. Critical env keys:

- Required: `OPENROUTER_API_KEY`.
- Storage/DB: `MISCITE_DB_URL`, `MISCITE_STORAGE_DIR`, upload limits.
- Text extraction/accelerator: `MISCITE_TEXT_EXTRACT_BACKEND`, `MISCITE_TEXT_EXTRACT_PROCESS_CONTEXT`, `MISCITE_ACCELERATOR`.
- LLM: model names and call limits (parse, match, inappropriate, deep analysis).
- Auth email: `MISCITE_MAILGUN_API_KEY`, `MISCITE_MAILGUN_DOMAIN`, `MISCITE_MAILGUN_SENDER`, `MISCITE_LOGIN_CODE_TTL_MINUTES`.
- Public URLs: `MISCITE_PUBLIC_ORIGIN` for absolute links in emails.
- Bot protection: `MISCITE_TURNSTILE_SITE_KEY`, `MISCITE_TURNSTILE_SECRET_KEY`.
- Sources: Crossref mailto/user-agent, retraction/predatory datasets/APIs.
- Billing (optional): Stripe keys, pricing refresh, multipliers, auto-charge thresholds.
- Ops/security: maintenance mode, load shedding, rate limits, upload scan, job reaper, access-token TTL.
- Cache (optional): `MISCITE_CACHE_*` controls for HTTP/LLM/text caching.
- Email login: Mailgun API keys + login code TTL/length.

If you add new env vars:

- Update `server/miscite/core/config.py`.
- Update `.env.example` and `docs/DEVELOPMENT.md` (and `README.md` if the quickstart needs changes).

## External integrations

- **OpenRouter**: LLM parsing, matching, and inappropriate-citation classification.
- **OpenAlex**: metadata resolution, retraction flags, deep analysis network expansion.
- **Crossref**: metadata resolution, retraction info.
- **arXiv**: metadata resolution fallback.
- **Retraction Watch**: local CSV dataset; sync via `server/sync_retractionwatch.py`.
- **Predatory lists**: local CSV or Google Sheets sync; optional custom API.
- **Stripe**: optional subscription gating in `server/miscite/routes/billing.py`.
- **Mailgun**: email-based sign-in code delivery.
- **Cloudflare Turnstile**: bot protection on login/register step.

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
- Access tokens are issued when a report completes; expiration can be adjusted or removed in the report UI (default is `MISCITE_ACCESS_TOKEN_DAYS`). Expired jobs/uploads are auto-deleted by the worker when an expiration is set.

## Common commands

- `make dev` / `python -m server.main`: run web app.
- `make worker` / `python -m server.worker`: run worker.
- `make sync-rw` / `python -m server.sync_retractionwatch`: sync retraction dataset.
- `make sync-predatory` / `python -m server.sync_predatory`: sync predatory lists.
- `bash scripts/install-nginx.sh`: install nginx and enable service.
- `docker compose up -d --build`: run web + worker in Docker.
- `docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build`: run with Caddy reverse proxy.
- `bash scripts/backup-data.sh`: stop services and backup `./data` (excludes `./data/cache`).
- `bash scripts/restore-data.sh ./backups/<file>.tar.gz --force`: restore `./data` from a backup archive.
- `bash scripts/install-docker-ubuntu.sh`: install Docker Engine + Compose plugin on Ubuntu.
- `DOMAIN=miscite.review bash scripts/bootstrap-vps-ubuntu.sh`: one-shot VPS bootstrap (Docker + Caddy + systemd).
- `make check`: compile server modules.

## Extending the system

- New metadata sources: add client in `server/miscite/sources/` and wire into `analysis/pipeline/`.
- New issue types: add to pipeline and update report template/summary counts.
- Parsing changes: update `analysis/parse/llm_parsing.py` or `analysis/parse/citation_parsing.py`.
- Deep analysis tweaks: `analysis/deep_analysis/deep_analysis.py` (watch LLM budget and OpenAlex usage limits).

## Security notes

- Auth uses email login codes + session + CSRF cookies (`server/miscite/core/security.py`).
- Set `MISCITE_COOKIE_SECURE=true` for HTTPS deployments.
