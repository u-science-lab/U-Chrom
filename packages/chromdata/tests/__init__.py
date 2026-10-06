"""Tests of chromdata (from packages/chromdata: ``pytest tests``); they never import uchrom."""

from pathlib import Path

#: the repository root (example-data/, apps/)
REPO = Path(__file__).resolve().parents[3]
