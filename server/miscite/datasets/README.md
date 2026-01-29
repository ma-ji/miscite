# Dataset schemas

This folder contains **sample CSV schemas** for local datasets used by `miscite`.

## Retraction Watch (`MISCITE_RETRACTIONWATCH_CSV`)

This project expects the **Crossref-hosted Retraction Watch dataset CSV** schema.

Required header columns (strict):

- `OriginalPaperDOI` (used for matching)
- `RetractionNature` (filtered to rows containing “retraction” by default)
- `RetractionDate`
- `Reason`
- `Record ID`
- `Title`
- `Journal`
- `Publisher`
- `URLS`
- `Paywalled`
- `Notes`

See `server/miscite/datasets/retractionwatch.sample.csv`.

## Predatory venues (`MISCITE_PREDATORY_CSV`)

Required header columns:

- `name`
- `type` (journal | publisher)
- `issn`
- `source`
- `notes`

Matching is done by ISSN (exact) or by normalized journal/publisher name.

See `server/miscite/datasets/predatory.sample.csv`.

### Auto-sync sources

This project can auto-sync the predatory CSV from two Google Sheets (publishers + journals) provided by predatoryjournals.org.
Enable with:

- `MISCITE_PREDATORY_SYNC_ENABLED=true`
- `MISCITE_PREDATORY_PUBLISHERS_URL=...`
- `MISCITE_PREDATORY_JOURNALS_URL=...`

See root `README.md` for details.
