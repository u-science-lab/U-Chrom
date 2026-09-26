"""Locate the example datasets under ``example-data/``.

``example-data/`` holds one folder per dataset (catalog:
``example-data/README.md``).  Code that needs an example file goes
through :func:`example_path` instead of hard-coding the layout::

    from uchrom.datasets import example_path

    pairs = example_path("stevens2017_mesc", "cell1.pairs")

The root is ``$UCHROM_EXAMPLE_DATA`` when set, else the ``example-data/``
folder of the source checkout this package was imported from (editable
install), else ``./example-data``.  Nothing here checks that a file
exists; large datasets are fetched with ``example-data/download_data.py``
or built with ``example-data/<dataset>/build.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["DATASETS", "ENV_VAR", "example_data_dir", "example_path"]

ENV_VAR = "UCHROM_EXAMPLE_DATA"

#: dataset folder -> one-line description (mirrors example-data/README.md).
DATASETS: dict[str, str] = {
    "takei2021_mesc": "Takei 2021 mESC DNA seqFISH+: 4DN FOF-CT core / cell / RNA tables + Zenodo raw spots",
    "takei2025_fov0": "Takei 2025 cerebellum rep 1 FOV 0, first 47 cells, with 59 IF tracks (built)",
    "takei2025_cerebellum": "Takei 2025 cerebellum DNA seqFISH+ rep 1, all FOVs (Zenodo 7693825, built)",
    "bintu2018_imr90": "Bintu 2018 IMR90 chr21:18.6-20.6 Mb chromatin tracing (+ PyHiM ECSV)",
    "mesc_sox2": "Huang 2021 mESC Sox2 locus, 5 cells, with / without imputation",
    "stevens2017_mesc": "Stevens 2017 single-cell Hi-C read pairs (mESC)",
    "imr90_hic": "Rao 2014 IMR90 in situ Hi-C, chr21 at 30 kb (.cool)",
    "schicar_mop": "scHiCAR mouse brain (GSE305439) + MERFISH MOp atlas (built)",
    "h1esc_hff_scihic": "Kim 2020 sci-Hi-C H1Esc + HFF mix, 500 kb (downloaded)",
    "liu2025_mop": "Liu 2025 mouse MOp DNA-MERFISH, 4DN FOF-CT (downloaded, built)",
    "sim_cell1": "NucDynamics single-cell structure of stevens2017_mesc/cell1.pairs + its contacts",
    "gm12878_hic": "Rao 2014 GM12878 in situ combined Hi-C (.hic, ~40 GB, manual download)",
    "generated": "tutorial / benchmark outputs (safe to delete)",
}


def _checkout_example_data() -> Path | None:
    """``example-data/`` of the source checkout ``uchrom`` lives in, if any."""
    here = Path(__file__).resolve().parent
    for p in here.parents:
        cand = p / "example-data"
        if cand.is_dir():
            return cand
    return None


def example_data_dir() -> Path:
    """Root of the example datasets.

    ``$UCHROM_EXAMPLE_DATA`` if set, else ``<repo>/example-data`` found by
    walking up from the installed ``uchrom`` package (editable install),
    else ``./example-data``.
    """
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env).expanduser()
    found = _checkout_example_data()
    if found is not None:
        return found
    return Path("example-data")


def example_path(dataset: str, *parts: str) -> Path:
    """``example_data_dir() / dataset / Path(*parts)``; no existence check.

    ``dataset`` must be one of :data:`DATASETS` (the catalogued folders).
    """
    if dataset not in DATASETS:
        known = "\n".join(f"  {k:22s} {v}" for k, v in DATASETS.items())
        raise ValueError(
            f"unknown example dataset {dataset!r}; catalogued folders "
            f"(example-data/README.md):\n{known}"
        )
    return example_data_dir().joinpath(dataset, *parts)
