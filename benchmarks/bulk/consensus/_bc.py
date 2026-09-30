"""Shared helpers of the consensus benchmark: data locations, model / locus mapping,
loci-level distance matrices.

Everything that reads Hi-C goes through ``uchrom.recon.bulk.consensus`` (the same balancing
the method uses), so baselines and the fit-to-input metric see exactly the matrix the method saw.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BULK = HERE.parent
ROOT = BULK.parents[1]
for _p in (str(BULK), str(ROOT / "benchmarks" / "screcon"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _common import BONEV_4DN, RAO_IMR90_4DN, example_data, jdump  # noqa: E402

# _common puts benchmarks/bulk and benchmarks/screcon first; this directory's modules (score,
# imaging, ...) must win over their namesakes there
while str(HERE) in sys.path:
    sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))

#: Hi-C sources (local copy on Sherlock, else the 4DN URL with range reads)
CELLS = {
    "imr90": {"local": "rao2014_imr90/4DNFIR1JDZH7.mcool", "url": RAO_IMR90_4DN, "assembly": "GRCh38",
              "label": "Rao 2014 IMR90 in situ (4DN 4DNFIR1JDZH7)"},
    "bonev": {"local": "bonev2017_mesc/4DNFIC21MG3U.mcool", "url": BONEV_4DN, "assembly": "mm10",
              "label": "Bonev 2017 mESC (4DN 4DNFIC21MG3U)"},
}

#: imaging truth sets and the Hi-C cell type they are compared with
IMAGING = {
    "su2020_genome": {"cell": "imr90", "label": "Su 2020 IMR90 DNA-MERFISH, 1,041 loci genome-wide (cis + trans)"},
    "su2020_chr21": {"cell": "imr90", "label": "Su 2020 IMR90 chr21 tracing, 651 x 50 kb"},
    "takei2021_1mb": {"cell": "bonev", "label": "Takei 2021 mESC seqFISH+ 1 Mb, 2,460 loci genome-wide (cis + trans)"},
}


def hic_source(cell: str) -> str:
    c = CELLS[cell]
    p = example_data() / c["local"]
    return str(p) if p.exists() else c["url"]


def write_json(path, obj) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(jdump(obj))


def read_json(path):
    return json.loads(Path(path).read_text())


# --------------------------------------------------------------------------- loci mapping

def map_loci_to_bins(loci: pd.DataFrame, bins: pd.DataFrame) -> np.ndarray:
    """Index of the bin containing each locus midpoint (-1: none)."""
    out = np.full(len(loci), -1, np.int64)
    mid = ((loci["start"].to_numpy(np.int64) + loci["end"].to_numpy(np.int64)) // 2)
    lc = loci["chrom"].astype(str).to_numpy()
    b = bins.reset_index(drop=True)
    for c, sub in b.groupby(b["chrom"].astype(str), sort=False):
        k = np.flatnonzero(lc == c)
        if not len(k):
            continue
        s = sub.sort_values("start")
        st, en = s["start"].to_numpy(), s["end"].to_numpy()
        j = np.searchsorted(st, mid[k], side="right") - 1
        ok = (j >= 0) & (mid[k] < en[np.clip(j, 0, None)])
        out[k[ok]] = s.index.to_numpy()[j[ok]]
    return out


class Model:
    """A model scored against imaging: bead coordinates per bin (``coords``, NaN = none)
    or a loci-level distance matrix (``dist`` on the imaging loci; e.g. HIPPS, IGM means)."""

    def __init__(self, name: str, bins: Optional[pd.DataFrame] = None, coords: Optional[np.ndarray] = None,
                 dist: Optional[np.ndarray] = None, meta: Optional[dict] = None):
        self.name, self.bins, self.coords, self.dist, self.meta = name, bins, coords, dist, meta or {}

    def loci_coords(self, loci: pd.DataFrame):
        """(L, 3) coordinates of the imaging loci (NaN when the bin has no bead) and the bin index."""
        idx = map_loci_to_bins(loci, self.bins)
        X = np.full((len(loci), 3), np.nan)
        ok = idx >= 0
        X[ok] = self.coords[idx[ok]]
        return X, idx

    def loci_distances(self, loci: pd.DataFrame):
        """(L, L) model distances; NaN for loci without a bead and for two loci in one bin."""
        if self.dist is not None:
            return self.dist, None
        X, idx = self.loci_coords(loci)
        D = np.linalg.norm(X[:, None] - X[None], axis=2)
        same = (idx[:, None] == idx[None]) & (idx[:, None] >= 0)
        np.fill_diagonal(same, False)
        D[same] = np.nan
        return D, X


def model_from_chromdata(path, name: str, layer: Optional[str] = None) -> Model:
    from uchrom.core import ChromData

    cd = ChromData.read(str(path))
    xyz = np.asarray(cd.layers[layer] if layer else cd.coords, float)
    bins = cd.bins[["chrom", "start", "end"]].reset_index(drop=True)
    bins["chrom"] = bins["chrom"].astype(str)
    coords = np.full((len(bins), 3), np.nan)
    bid = cd.spots["bin_id"].to_numpy()
    pos = pd.Index(cd.bins.index).get_indexer(bid)
    coords[pos] = xyz
    meta = dict(cd.uns.get("consensus", {}))
    for k in ("stages", "stage_coords", "stage_beads"):
        meta.pop(k, None)
    return Model(name, bins, coords, meta=meta)


def model_from_npz(path, name: str) -> Model:
    z = np.load(path, allow_pickle=True)
    bins = pd.DataFrame({"chrom": z["chrom"].astype(str), "start": z["start"], "end": z["end"]})
    meta = json.loads(str(z["meta"])) if "meta" in z.files else {}
    return Model(name, bins, np.asarray(z["coords"], float), meta=meta)


def save_model_npz(path, bins: pd.DataFrame, coords: np.ndarray, meta: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, chrom=bins["chrom"].astype(str).to_numpy(), start=bins["start"].to_numpy(),
                        end=bins["end"].to_numpy(), coords=np.asarray(coords, np.float32), meta=jdump(meta))


def peak_rss_gb() -> float:
    import resource
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e9 if sys.platform == "darwin" else r / 1e6
