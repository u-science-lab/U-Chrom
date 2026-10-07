"""Bulk Hi-C datasets as ``ChromData``: the map stays a ``.cool`` and is linked (``cd.link_cool``)."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from ._loaders import Loader, register


def _no_spots() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                         [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str)]})


def _bulk(cool: Path, out: Path, *, key: str, label: str, source: str):
    """A ``ChromData`` without spots holding one linked bulk map (relative to the store's folder)."""
    import cooler
    from chromdata import ChromData

    clr = cooler.Cooler(str(cool))
    assembly = clr.info.get("genome-assembly")
    cd = ChromData(np.zeros((0, 3)), _no_spots(), uns={"genome_assembly": assembly, "source": source})
    rel = os.path.relpath(Path(cool).resolve(), Path(out).parent.resolve())
    cd.link_cool(rel, key=key, label=label, genome_assembly=assembly, bin_size=int(clr.binsize),
                 n_bins=int(clr.info["nbins"]), n_contacts=int(clr.info["sum"]),
                 chroms=[str(c) for c in clr.chromnames], normalization="none (observed counts, unbalanced)")
    return cd


def build_rao2014_imr90_chr21(root: Path, out: Path):
    """Rao et al. 2014 in situ Hi-C of IMR90 (GEO GSE63525, MAPQ > 0 combined map), chromosome 21 at 5 kb on
    hg19, raw counts — sliced once from the GEO ``.hic`` over HTTP (``fetch("rao2014_imr90_chr21")``) and
    linked under the key ``bulk``."""
    from . import fetch

    cool = fetch("rao2014_imr90_chr21", root=root)
    return _bulk(cool, out, key="bulk", label="Rao 2014 IMR90 in situ Hi-C, chr21, 5 kb",
                 source="Rao et al. 2014, Cell 159:1665 (in situ Hi-C, IMR90, GEO GSE63525, combined map MAPQ > 0); "
                        "chr21 at 5 kb, hg19, raw counts")


register(Loader(
    name="rao2014_imr90_chr21", build=build_rao2014_imr90_chr21,
    store="rao2014_imr90/rao2014_imr90_chr21.chromdata.zarr", sources=("rao2014_imr90_chr21",),
    description="Rao 2014 IMR90 in situ Hi-C, chr21 at 5 kb (hg19, raw counts): the map linked as 'bulk'"))
