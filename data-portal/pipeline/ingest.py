"""Ingest CLI: catalog YAML + .h5cd + notebook -> one DB row + artifacts.

Idempotent UPSERT. Reading the .h5cd is mandatory (abort on failure);
notebook rendering is best-effort (null the path on failure).

Usage:
    python -m pipeline.ingest pipeline/catalog/mesc_sox2_test.yaml
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from uchrom.core.cdata import ChromData

from backend.db import Base, default_db_path, make_engine, make_session
from backend.models import Dataset
from pipeline.catalog import load_catalog
from pipeline.extract import extract_stats
from pipeline.render_nb import render_notebook

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("ingest")


def ingest(yaml_path: str, db_path: str | None = None, data_dir: str | None = None) -> None:
    entry = load_catalog(yaml_path)

    # Mandatory: read ChromData (raises if unreadable -> abort, no DB write).
    cd = ChromData.read(str(entry.source_h5cd_path))
    stats = extract_stats(cd)

    data_root = Path(data_dir) if data_dir else Path(default_db_path()).parent
    nb_dir = data_root / "notebooks"
    notebook_rel = None
    if entry.notebook_path is not None:
        out_html = nb_dir / f"{entry.id}.html"
        if render_notebook(str(entry.notebook_path), str(out_html)):
            notebook_rel = f"notebooks/{entry.id}.html"
        else:
            logger.warning("notebook unavailable for %s", entry.id)

    engine = make_engine(db_path)
    Base.metadata.create_all(engine)
    Session = make_session(engine)
    with Session() as s:
        row = s.get(Dataset, entry.id)
        if row is None:
            row = Dataset(id=entry.id)
            s.add(row)
        row.title = entry.title
        row.description = entry.description
        row.organism = entry.organism
        row.assembly = entry.assembly or stats["assembly"]
        row.technology = entry.technology
        row.doi = entry.doi
        row.citation = entry.citation
        row.n_cells = stats["n_cells"]
        row.n_traces = stats["n_traces"]
        row.n_spots = stats["n_spots"]
        row.n_markers = stats["n_markers"]
        row.cell_types = stats["cell_types"]
        row.genome_coverage = stats["genome_coverage"]
        row.xyz_unit = stats["xyz_unit"]
        row.files = entry.files
        row.notebook_html_path = notebook_rel
        row.analyzer_url = entry.analyzer_url
        row.status = "published"
        s.commit()
    logger.info(
        "ingested %s: %d cells, %d traces, %d markers",
        entry.id, stats["n_cells"], stats["n_traces"], stats["n_markers"],
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest a dataset catalog YAML")
    ap.add_argument("catalog", help="path to catalog YAML")
    ap.add_argument("--db", default=None, help="SQLite path (default data/portal.db)")
    ap.add_argument("--data-dir", default=None, help="artifact output dir")
    args = ap.parse_args()
    ingest(args.catalog, db_path=args.db, data_dir=args.data_dir)


if __name__ == "__main__":
    main()
