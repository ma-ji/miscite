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
- Dataset paths are required unless you enable an API-based source:
  - `MISCITE_RETRACTIONWATCH_CSV` (Retraction Watch CSV)
  - `MISCITE_PREDATORY_CSV` (predatory venues CSV)

## Billing (optional)

Usage billing is disabled by default. To enable Stripe balance top-ups and auto-charge, set:

- `MISCITE_BILLING_ENABLED=true`
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`
- `STRIPE_SUCCESS_URL` and `STRIPE_CANCEL_URL`
- Optional tuning: `MISCITE_BILLING_COST_MULTIPLIER`, `MISCITE_BILLING_MIN_CHARGE_CENTS`,
  `MISCITE_BILLING_AUTO_CHARGE_THRESHOLD_CENTS`, `MISCITE_BILLING_AUTO_CHARGE_AMOUNT_CENTS`,
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
