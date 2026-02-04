# Development

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
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
```

### Combined runner flags

`bash scripts/dev.sh` supports a few useful dev flags shared by web/worker:

- `--blank-db`
- `--text-backend {markitdown,docling}`
- `--accelerator {cpu,gpu}`
- `--debug`

## Required configuration

- `OPENROUTER_API_KEY` is required for core parsing/matching/checks.
- `MISCITE_PUBLIC_ORIGIN` should be set in production so email links include the correct domain.
- `MISCITE_SAMPLE_REPORT_URL` controls the sample report CTA link (token, `/reports/<token>`, or full URL).
- Dataset paths are required unless you enable an API-based source:
  - `MISCITE_RETRACTIONWATCH_CSV` (Retraction Watch CSV)
  - `MISCITE_PREDATORY_CSV` (predatory venues CSV)

## Matching and verification tuning (optional)

- `MISCITE_LLM_MATCH_MAX_CALLS` limits LLM disambiguation calls used for citation↔bibliography matching and metadata resolution.
- `MISCITE_PREPRINT_YEAR_GAP_MAX` (default `5`) controls how many years of gap are treated as plausible for preprint/working-paper → published matches during metadata resolution.
- PubMed (NCBI E-utilities) request identity / rate tuning:
  - `MISCITE_NCBI_TOOL` (default `miscite`)
  - `MISCITE_NCBI_EMAIL` (defaults to `MISCITE_CROSSREF_MAILTO`)
  - `MISCITE_NCBI_API_KEY` (optional)
  - References containing `PMID` / `PMCID` are treated as strong identifiers during the PubMed stage of resolution (without changing the overall lookup order).

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
