# miscite

Citation-check platform for academic manuscripts (PDF/DOCX) with traceable, transparent reports.

## What it does

- Parses in-text citations + bibliography entries.
- Resolves references against OpenAlex/Crossref/arXiv.
- Flags missing refs, retractions, predatory venues, and potentially inappropriate citations.
- Optionally runs deep literature analysis for suggested additions/removals.

## Quickstart (dev)

```bash
pip install -r requirements.txt
cp .env.example .env
python -m server.migrate upgrade
python -m server.main
python -m server.worker
```

For detailed setup, architecture, and deployment docs, see:

- `docs/README.md`
- `AGENTS.md` (repo conventions for assistants/contributors)
- `DESIGN.md` (UI design system notes)
