"""Tests of u-chrom (from packages/uchrom: ``pytest tests``)."""

import os
from pathlib import Path

#: the repository root (skills/, apps/)
REPO = Path(__file__).resolve().parents[3]

#: test fixtures (small real data; their sources in fixtures/README.md)
FIXTURES = Path(__file__).resolve().parent / "fixtures"
#: downloaded / built datasets (``python -m uchrom.datasets``): ``$UCHROM_DATA``, else ``~/.cache/uchrom``
DATA_DIR = Path(os.environ["UCHROM_DATA"]).expanduser() if os.environ.get("UCHROM_DATA") else Path.home() / ".cache" / "uchrom"
