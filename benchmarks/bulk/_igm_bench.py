"""Helpers of the IGM engine benchmarks (numpy + h5py + uchrom_nucdyn only, so they
run in the Sherlock ``venv-main`` that has no U-Chrom install).

* :func:`fetch_igm_demo` — the IGM demo input ``WTC11_HiC_2Mb.hcs`` (GPL-3 repository
  alberlab/igm; downloaded on demand into a cache directory, never committed);
* :func:`read_hcs` — an alabtools ``.hcs`` contact-probability file (HDF5: ``index/*``,
  upper-triangular CSR ``matrix/{data,indices,indptr,diagonal}``) as bins + COO;
* :func:`read_hss` — an IGM ``.hss`` population (``coordinates`` (N, S, 3), ``index/*``);
* :func:`contact_probability` — population contact probability with IGM's contact
  definition (mean over same-copy combinations intra, all combinations inter: the
  quantity the A-step fits).
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

IGM_COMMIT = "edbb33135260443b8b41eb09d7ca4c37b19e330d"
IGM_DEMO_URL = f"https://raw.githubusercontent.com/alberlab/igm/{IGM_COMMIT}/demo/WTC11_HiC_2Mb.hcs"
IGM_DEMO_BYTES = 3_908_025

#: IGM demo configuration (demo/config_file.json at edbb331) as native parameters
DEMO_PARAMS = dict(
    occupancy=0.4, nucleus_shape="sphere", nucleus_radius=5500.0, init_radius=7000.0,
    contact_range=2.0, evfactor=1.0, contact_kspring=1.0, polymer_kspring=1.0, nucleus_kspring=1.0,
    polymer_bonds_style="simple",
    intra_sigma_list=[1.0, 0.2, 0.1, 0.05, 0.02, 0.01], inter_sigma_list=[1.0, 0.2, 0.1, 0.05, 0.02, 0.01],
    min_iterations=5, force_last_iteration=True, force_minimum_iterations_hic_cutoff=0.0, max_iterations=10,
    violation_tolerance=0.05, max_violations=0.01, timestep=0.25, max_velocity=1000.0,
    cg_etol=1e-4, cg_ftol=1e-6, cg_max_iter=500, cg_max_eval=500,
    stages=[dict(mdsteps=5000, tstart=5000.0, tstop=500.0, evfactor=0.5, envelope_factor=1.2),
            dict(mdsteps=15000, tstart=500.0, tstop=50.0, evfactor=1.0, envelope_factor=1.0),
            dict(mdsteps=15000, tstart=50.0, tstop=1.0, evfactor=1.0, envelope_factor=1.0),
            dict(mdsteps=10000, tstart=1.0, tstop=0.0, evfactor=1.0, envelope_factor=1.0)],
    relax=dict(mdsteps=500, temperature=1.0, max_velocity=10.0),
)
DEMO_PLOIDY = "male"


def cache_dir() -> Path:
    d = Path(os.environ.get("UCHROM_IGM_CACHE", Path.home() / ".cache" / "uchrom" / "igm"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch_igm_demo(dest: Optional[Path] = None) -> Path:
    """Download the IGM demo ``.hcs`` once (GPL-3 data file: kept out of the repo)."""
    dest = Path(dest) if dest else cache_dir() / "WTC11_HiC_2Mb.hcs"
    if dest.exists() and dest.stat().st_size == IGM_DEMO_BYTES:
        return dest
    tmp = dest.with_suffix(".part")
    urllib.request.urlretrieve(IGM_DEMO_URL, tmp)
    if tmp.stat().st_size != IGM_DEMO_BYTES:
        raise RuntimeError(f"unexpected size of {IGM_DEMO_URL}: {tmp.stat().st_size}")
    tmp.rename(dest)
    return dest


def _s(x) -> str:
    return x.decode() if isinstance(x, bytes) else str(x)


def read_hcs(path) -> Dict[str, np.ndarray]:
    """Bins (chrom, start, end) and the strict upper triangle (i < j, v > 0) as COO."""
    import h5py

    with h5py.File(path, "r") as f:
        chrom = np.array([_s(c) for c in f["index/chromstr"][:]])
        start = f["index/start"][:].astype(np.int64)
        end = f["index/end"][:].astype(np.int64)
        data = f["matrix/data"][:].astype(np.float64)
        indices = f["matrix/indices"][:].astype(np.int64)
        indptr = f["matrix/indptr"][:].astype(np.int64)
    rows = np.repeat(np.arange(len(indptr) - 1), np.diff(indptr))
    i, j = np.minimum(rows, indices), np.maximum(rows, indices)
    keep = (i != j) & (data > 0)
    i, j, v = i[keep], j[keep], data[keep]
    # symmetric storage would list pairs twice: keep one
    key = i * len(chrom) + j
    _, first = np.unique(key, return_index=True)
    return {"chrom": chrom, "start": start, "end": end, "i": i[first], "j": j[first], "v": v[first]}


def read_hss(path) -> Dict[str, np.ndarray]:
    """IGM population: coordinates (S, N, 3) float32 and the bead index."""
    import h5py

    with h5py.File(path, "r") as f:
        crd = f["coordinates"][:]                    # (N, S, 3), bead-major
        if "index/chromstr" in f:
            chrom = np.array([_s(c) for c in f["index/chromstr"][:]])
        else:
            names = np.array([_s(c) for c in f["genome/chroms"][:]])
            chrom = names[f["index/chrom"][:]]
        out = {"coords": np.ascontiguousarray(np.transpose(crd, (1, 0, 2))).astype(np.float32),
               "chrom": chrom,
               "start": f["index/start"][:].astype(np.int64),
               "end": f["index/end"][:].astype(np.int64),
               "copy": f["index/copy"][:].astype(np.int64),
               "radii": f["radii"][:].astype(np.float64)}
    return out


def contact_probability(coords: np.ndarray, bead_bin: np.ndarray, bead_copy: np.ndarray, radii: np.ndarray,
                        bin_chrom: np.ndarray, i: np.ndarray, j: np.ndarray, contact_range: float = 2.0,
                        chunk: int = 4000) -> np.ndarray:
    """Mean over structures and copy combinations of [d <= contact_range (r_i + r_j)]."""
    nb = len(bin_chrom)
    ncopy = int(bead_copy.max()) + 1
    idx = np.full((nb, ncopy), -1, dtype=np.int64)
    idx[bead_bin, bead_copy] = np.arange(len(bead_bin))
    rbin = np.zeros(nb)
    rbin[bead_bin[bead_copy == 0]] = radii[bead_copy == 0]
    out = np.zeros(len(i))
    X = np.asarray(coords, dtype=np.float32)
    for a in range(0, len(i), chunk):
        ii, jj = i[a:a + chunk], j[a:a + chunk]
        rc2 = (contact_range * (rbin[ii] + rbin[jj])) ** 2
        intra = bin_chrom[ii] == bin_chrom[jj]
        hit = np.zeros(len(ii))
        tot = np.zeros(len(ii))
        for c1 in range(ncopy):
            for c2 in range(ncopy):
                bi, bj = idx[ii, c1], idx[jj, c2]
                use = (bi >= 0) & (bj >= 0) & ((c1 == c2) | ~intra)
                if not use.any():
                    continue
                d = X[:, bi[use]] - X[:, bj[use]]
                d2 = np.einsum("snk,snk->sn", d, d)
                hit[use] += (d2 <= rc2[use][None, :]).sum(0)
                tot[use] += X.shape[0]
        out[a:a + chunk] = hit / np.maximum(tot, 1)
    return out


def fit_summary(inp: np.ndarray, out: np.ndarray, intra: np.ndarray, sigma: float = 0.01) -> Dict[str, float]:
    """Pearson / mean |diff| of input vs population probabilities (as igm/report/hic.py splits them)."""
    res = {}
    for name, m in (("all", np.ones_like(intra)), ("intra", intra), ("inter", ~intra)):
        for tag, sel in (("restrained", m & (inp >= sigma)), ("unrestrained", m & (inp < sigma))):
            if sel.sum() > 2:
                res[f"pearson_{name}_{tag}"] = float(np.corrcoef(inp[sel], out[sel])[0, 1])
                res[f"mae_{name}_{tag}"] = float(np.abs(inp[sel] - out[sel]).mean())
                res[f"n_{name}_{tag}"] = int(sel.sum())
    return res


def md5(path) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()
