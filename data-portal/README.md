# U-Chrom Data Portal

Analysis-ready chromatin 3D structure dataset portal. Distributes ChromData
(`.h5cd`) datasets with embedded reproduction notebooks. See the design spec at
`../docs/superpowers/specs/2026-06-10-uchrom-web-portal-design.md`.

## Architecture

- `pipeline/` — offline CLI: `.h5cd` + notebook → SQLite row + static HTML
- `backend/` — read-only FastAPI REST over the SQLite DB (no `.h5cd` at runtime)
- `frontend/` — Next.js SSR list + detail pages

Data files are externally hosted (Zenodo); the portal stores only metadata and
pre-rendered notebooks. The portal is parallel to the U-Chrom `webapp` (an
interactive analysis tool); the two integrate only via the `.h5cd` format and an
"open in Analyzer" link.

## Setup

Python (uses the repo venv at `../../../.venv`):

```bash
/Volumes/sandisk/Coding/U-Chrom/.venv/bin/pip install -r requirements.txt
```

## Ingest a dataset

```bash
python -m pipeline.ingest pipeline/catalog/<dataset>.yaml
```

This reads the `.h5cd` named in the catalog, extracts display statistics,
renders the notebook to HTML, and UPSERTs one row into `data/portal.db`. It is
idempotent — re-running updates the existing row.

## Run

```bash
# backend (serves /api/* on :8000)
python -m uvicorn backend.main:app --port 8000
# frontend (separate shell)
cd frontend && npm install && npm run dev
```

Visit http://localhost:3000.

## Tests

```bash
python -m pytest tests/ -v
```

## Adding a dataset

1. Write a catalog YAML in `pipeline/catalog/` (see `mesc_sox2_test.yaml`).
   Paths in `source_h5cd` / `notebook` are relative to the YAML file's own
   directory.
2. Fill `files[].url` with the external (Zenodo) download links.
3. Run `python -m pipeline.ingest pipeline/catalog/<id>.yaml`.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/datasets?organism=&technology=&q=` | List published datasets (summary) |
| `GET /api/datasets/{id}` | Full dataset metadata |
| `GET /api/datasets/{id}/notebook` | Rendered notebook HTML |
| `GET /api/facets` | Distinct organism/technology values |
| `GET /api/health` | Liveness + dataset count |
