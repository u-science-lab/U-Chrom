"""Shared pieces of the scA/B validation scripts (``benchmarks/sc_structures/scab_*.py``).

* :func:`cpg_track`: the CpG frequency (Dip-C ``cpg.sh``) of every bin of a genome at a resolution, from the
  registered UCSC whole-genome FASTA (``mm10_genome``, ``hg19_genome``, ``hg38_genome``), computed once and
  cached as Parquet under ``--out`` or ``$SCAB_CACHE`` (75-90 s per genome and bin size: the FASTA is read in
  Python).
* :func:`separation`: how well a cells x features matrix separates labelled cell types — PCA (20 PCs, as Tan
  et al. 2021), kNN classification accuracy (5-fold, k = 10), kNN purity, ARI / NMI of Ward clusters (Tan et al.
  2021: hierarchical clustering of the first 20 PCs) and of k-means, with as many clusters as types.
* :class:`PeakRSS`: peak resident memory of the process, sampled in a thread.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Dict, Mapping, Optional

import numpy as np
import pandas as pd


def rss() -> int:
    """Resident memory of this process (bytes): psutil, else ``/proc/self/statm`` (Linux)."""
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except ImportError:
        with open("/proc/self/statm") as fh:
            return int(fh.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")


class PeakRSS:
    """Peak resident memory of this process, sampled in a thread."""

    def __init__(self, every: float = 0.1):
        self.every, self.peak, self._stop = every, 0, threading.Event()

    def __enter__(self):
        self.base = self.peak = rss()
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()
        return self

    def _run(self):
        while not self._stop.wait(self.every):
            self.peak = max(self.peak, rss())

    def __exit__(self, *exc):
        self._stop.set()
        self.t.join()


def load_average() -> str:
    one, five, fifteen = os.getloadavg()
    return f"{one:.1f} / {five:.1f} / {fifteen:.1f} (1 / 5 / 15 min, {os.cpu_count()} CPUs)"


def cpg_track(genome: str, chromsizes: Mapping[str, int], resolution: int, cache: Path,
              feature: str = "cpg_frequency") -> pd.DataFrame:
    """``chrom, start, end, value``: ``feature`` of every bin of ``chromsizes`` at ``resolution`` from the
    registered FASTA ``<genome>_genome`` (fetched once), cached in ``cache``."""
    import uchrom.datasets as ds
    from uchrom.fea.sequence import compute_sequence_features
    from uchrom.io.pairs_maps import genome_bins

    cache = Path(os.environ.get("SCAB_CACHE") or cache)          # shared by the jobs on a cluster
    cache.mkdir(parents=True, exist_ok=True)
    tag = f"{genome}_{feature}_{resolution}_{len(chromsizes)}chroms.parquet"
    path = cache / tag
    bins = genome_bins(dict(chromsizes), resolution)[["chrom", "start", "end"]]
    if path.exists():
        t = pd.read_parquet(path)
        if len(t) == len(bins) and (t["start"].to_numpy() == bins["start"].to_numpy()).all():
            return t
    fasta = ds.fetch(f"{genome}_genome")
    t0 = time.perf_counter()
    f = compute_sequence_features(bins, fasta, features=[feature], missing="ignore")
    print(f"[cpg] {genome} {feature} at {resolution:,} bp: {len(bins):,} bins in {time.perf_counter() - t0:.0f} s",
          flush=True)
    t = f[["chrom", "start", "end"]].assign(value=f[feature].to_numpy(dtype=float))
    t["chrom"] = t["chrom"].astype(str)
    t.to_parquet(path)
    return t


def fill_columns(x: np.ndarray, min_finite: float = 0.0) -> np.ndarray:
    """NaN entries replaced by their column's mean; columns finite in under ``min_finite`` of the rows (or in
    none) dropped."""
    x = np.asarray(x, dtype=np.float64)
    frac = np.isfinite(x).mean(axis=0)
    keep = (frac > 0) & (frac >= min_finite)
    x = x[:, keep]
    mean = np.nanmean(x, axis=0)
    out = np.where(np.isfinite(x), x, mean[None, :])
    return out


def pcs(x: np.ndarray, n: int = 20, scale: bool = False, seed: int = 0) -> np.ndarray:
    from sklearn.decomposition import PCA

    x = np.asarray(x, dtype=np.float64)
    x = x - x.mean(axis=0)
    if scale:
        sd = x.std(axis=0)
        x = x / np.where(sd > 0, sd, 1.0)
    n = int(min(n, x.shape[0] - 1, x.shape[1]))
    return PCA(n, random_state=seed, svd_solver="randomized" if min(x.shape) > 500 else "full").fit_transform(x)


def separation(emb: np.ndarray, labels, *, k: int = 10, seed: int = 0, ward_max: int = 20000) -> Dict[str, float]:
    """kNN accuracy (5-fold, stratified), kNN purity, ARI / NMI of Ward and k-means clusters (n = types)."""
    from sklearn.cluster import AgglomerativeClustering, KMeans
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.neighbors import KNeighborsClassifier

    from uchrom.emb.metrics import cluster_agreement, knn_purity

    x = np.asarray(emb, dtype=np.float64)
    y = np.asarray(labels).astype(str)
    ok = np.isfinite(x).all(axis=1)
    x, y = x[ok], y[ok]
    n_types = len(np.unique(y))
    folds = min(5, int(pd.Series(y).value_counts().min()))
    out: Dict[str, float] = {"n_cells": int(len(y)), "n_types": int(n_types)}
    if folds >= 2:
        pred = cross_val_predict(KNeighborsClassifier(n_neighbors=k), x, y,
                                 cv=StratifiedKFold(folds, shuffle=True, random_state=seed))
        out["knn_accuracy"] = float((pred == y).mean())
        per = pd.Series(pred == y).groupby(y).mean()
        out["knn_balanced_accuracy"] = float(per.mean())
    out["knn_purity"] = knn_purity(x, y, k=k)
    km = KMeans(n_types, n_init=10, random_state=seed).fit_predict(x)
    out.update({f"kmeans_{a}": b for a, b in cluster_agreement(km, y).items()})
    if len(y) <= ward_max:
        hw = AgglomerativeClustering(n_types, linkage="ward").fit_predict(x)
        out.update({f"ward_{a}": b for a, b in cluster_agreement(hw, y).items()})
    return out


def pearson(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return float("nan")
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


def spearman(a, b) -> float:
    from scipy.stats import spearmanr

    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return float("nan")
    return float(spearmanr(a[ok], b[ok])[0])


def partial_r(a, b, c) -> float:
    """Pearson correlation of ``a`` and ``b`` with ``c`` regressed out of both."""
    a, b, c = (np.asarray(v, float) for v in (a, b, c))
    ok = np.isfinite(a) & np.isfinite(b) & np.isfinite(c)
    if ok.sum() < 4:
        return float("nan")
    a, b, c = a[ok], b[ok], c[ok]
    X = np.c_[np.ones_like(c), c]
    ra = a - X @ np.linalg.lstsq(X, a, rcond=None)[0]
    rb = b - X @ np.linalg.lstsq(X, b, rcond=None)[0]
    return float(np.corrcoef(ra, rb)[0, 1])


def thin_scool(src: str, out: Path, n_contacts: int, seed: int = 0, cells: Optional[list] = None) -> pd.Series:
    """Write ``out``: the cells of the ``.scool`` ``src`` binomially thinned to about ``n_contacts`` contacts
    each (cells with fewer are left out); returns the contacts kept per cell."""
    import cooler

    rng = np.random.default_rng(seed)
    names = cooler.fileops.list_scool_cells(src)
    bins = cooler.Cooler(f"{src}::{names[0]}").bins()[["chrom", "start", "end"]][:]
    maps, kept = {}, {}
    for path in names:
        name = path.rsplit("/", 1)[-1]
        if cells is not None and name not in cells:
            continue
        px = cooler.Cooler(f"{src}::{path}").pixels()[:]
        total = int(px["count"].sum())
        if total < n_contacts:
            continue
        c = rng.binomial(px["count"].to_numpy(np.int64), n_contacts / total)
        sel = c > 0
        maps[name] = pd.DataFrame({"bin1_id": px["bin1_id"].to_numpy()[sel], "bin2_id": px["bin2_id"].to_numpy()[sel],
                                   "count": c[sel].astype(np.int32)})
        kept[name] = int(c.sum())
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    cooler.create_scool(str(out), bins, maps, ordered=True)
    return pd.Series(kept)
