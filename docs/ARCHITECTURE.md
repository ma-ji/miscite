# Architecture

miscite is a FastAPI + Jinja web app with a background worker that runs a multi-step
analysis pipeline over uploaded PDF/DOCX documents.

## High-level components

- Web app entrypoint: `server/main.py`
- Worker launcher: `server/worker.py`
- Job loop: `server/miscite/worker/`
- Core infrastructure (config/db/models/security/storage/etc): `server/miscite/core/`
- Analysis pipeline (extract/parse/resolve/checks/deep_analysis/report): `server/miscite/analysis/`
- External metadata + datasets (OpenAlex/Crossref/PubMed/arXiv + local CSVs): `server/miscite/sources/`
- Prompts + JSON Schemas for LLM stages: `server/miscite/prompts/`
- UI templates + assets: `server/miscite/templates/`, `server/miscite/static/`

## Worker

The worker is responsible for:

- Claiming queued jobs and managing status transitions.
- Running `analysis.pipeline.analyze_document` and persisting report JSON + methodology.
- Emitting progress events for SSE.
- Issuing access tokens after completion and triggering delivery via email (when configured).
- Ensuring required datasets are present (retraction/predatory).

## Routes

FastAPI routes live under `server/miscite/routes/`:

- `auth.py`: email login + session management.
- `dashboard.py`: uploads, job status, report UI + API.
- `billing.py`: Stripe billing endpoints (feature-flagged).
- `health.py`: liveness/readiness probes.
- `seo.py`: robots.txt + sitemap + favicon redirect.

## LLM prompts

Prompt files live under `server/miscite/prompts/`:

- `registry.yaml`: prompt catalog and schema references.
- Stage folders (e.g. `parsing/`, `matching/`, `checks/`, `deep_analysis/`): paired `system.txt` + `user.txt`.
- `schemas/`: JSON Schemas for structured LLM outputs.

## Runtime flow

1) Upload route stores the file and creates `Document` + `AnalysisJob` rows.
2) A worker claims the job and emits progress events.
3) The worker runs the analysis pipeline and persists report JSON + methodology markdown.
4) On completion, the worker issues the access token and emails it to the user.
5) The UI renders the report; `/api/jobs/{id}` returns the report JSON.

## Analysis pipeline

Orchestrator: `server/miscite/analysis/pipeline/__init__.py` (`analyze_document(...)`).

Stages:

- Extract: `server/miscite/analysis/extract/` (Docling/MarkItDown backends)
- Parse: `server/miscite/analysis/parse/` (heuristics + OpenRouter-assisted parsing)
- Match: `server/miscite/analysis/match/` (in-text citations ↔ bibliography linking + ambiguity tracking)
- Resolve: `server/miscite/analysis/pipeline/resolve.py` (OpenAlex -> Crossref -> PubMed -> arXiv)
- Checks: `server/miscite/analysis/checks/` (retraction, predatory, inappropriate, missing refs)
- Deep analysis (optional): `server/miscite/analysis/deep_analysis/`
- Report assembly: `server/miscite/analysis/report/`

### Key modules

- Extract:
  - `server/miscite/analysis/extract/text_extract.py`: extraction orchestration (subprocess/timeouts)
  - `server/miscite/analysis/extract/docling_extract.py`: Docling backend
  - `server/miscite/analysis/extract/markitdown_extract.py`: MarkItDown backend
- Parse:
  - `server/miscite/analysis/parse/citation_parsing.py`: heuristic parsing/normalization helpers
  - `server/miscite/analysis/parse/llm_parsing.py`: OpenRouter-assisted parsing
- Match:
  - `server/miscite/analysis/match/index.py`: reference indexing + normalization for fast lookup
  - `server/miscite/analysis/match/match.py`: citation→reference matching + confidence/ambiguity
- Checks:
  - `server/miscite/analysis/checks/local_nli.py`: optional local NLI model
  - `server/miscite/analysis/checks/inappropriate.py`: heuristic + NLI + LLM inappropriate-citation checks
  - `server/miscite/analysis/checks/reference_flags.py`: missing refs, unresolved refs, retractions, predatory venues
- Deep analysis:
  - `server/miscite/analysis/deep_analysis/deep_analysis.py`: orchestrator (`run_deep_analysis`)
  - `server/miscite/analysis/deep_analysis/prep.py`: data prep
  - `server/miscite/analysis/deep_analysis/network.py`: network metrics
  - `server/miscite/analysis/deep_analysis/references.py`: OpenAlex metadata summarization/formatting
  - `server/miscite/analysis/deep_analysis/suggestions.py`: LLM/heuristic suggestions
  - `server/miscite/analysis/deep_analysis/types.py`: shared types
- Report:
  - `server/miscite/analysis/report/methodology.py`: methodology markdown embedded in reports

### Key settings

- Text extraction backend: `MISCITE_TEXT_EXTRACT_BACKEND` (`docling` or `markitdown`)
- Text extraction process context: `MISCITE_TEXT_EXTRACT_PROCESS_CONTEXT`
- Deep analysis: `MISCITE_ENABLE_DEEP_ANALYSIS`

## Data prep vs matching/analysis separation

When practical, keep "data loading/prep/indexing" separate from "matching/analysis":

- Predatory venues:
  - Data prep: `server/miscite/sources/predatory/data.py`
  - Matching: `server/miscite/sources/predatory/match.py`
- Retraction Watch:
  - Data prep: `server/miscite/sources/retraction/data.py`
  - Matching: `server/miscite/sources/retraction/match.py`

## Metadata sources + datasets

Source clients and dataset helpers live under `server/miscite/sources/`:

- Metadata clients: `openalex.py`, `crossref.py`, `pubmed.py`, `arxiv.py`
- Optional custom APIs: `retraction_api.py`, `predatory_api.py`
- Dataset sync helpers: `retractionwatch_sync.py`, `predatory_sync.py`
- Shared HTTP retry/backoff: `http.py`

## Report schema contract

The report JSON returned by `analysis/pipeline/` is:

- Rendered by `server/miscite/templates/job.html`
- Returned by `/api/jobs/{id}`

If you add new issue types or change schema/summary fields, update the template and any
API consumers.
