"""The data directory: ``$UCHROM_DATA``, else ``~/.cache/uchrom``."""

from __future__ import annotations

import os
from pathlib import Path

ENV = "UCHROM_DATA"


def data_dir() -> Path:
    """Where datasets are downloaded and built: ``$UCHROM_DATA``, else ``~/.cache/uchrom``.

    The layout below it is the same for every dataset (e.g. ``4DNFIHF3JCBY.csv``,
    ``stevens2017_mesc/...``, ``schicar_mop/raw/...``), so a folder of earlier downloads can simply be
    named by ``UCHROM_DATA``.
    """
    env = os.environ.get(ENV)
    return Path(env).expanduser() if env else Path.home() / ".cache" / "uchrom"
