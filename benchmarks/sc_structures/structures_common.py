"""Shared helpers of the structure-calling benchmarks on reconstructed single-cell structures and imaging
(``benchmarks/sc_structures/structures_*.py``): structures on coarser bins, trace subsets, reference calls on
bulk Hi-C (Rao 2014, Bonev 2017), boundary / loop / compartment agreement, FISHnet in windows, timing.

Nothing here is written into the repository: outputs go to ``--out`` (default ``$UCHROM_BENCH_OUT``, else the
system temp directory).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

#: hg38 -> hg19 offset of chr21q (benchmarks/hic_structures/compartments.py: Bintu 2018 loci, UCSC liftOver)
OFFSET_HG38_TO_HG19_CHR21 = 1_372_318
#: the Bonev et al. 2017 mESC Hi-C on 4DN (mm10, balanced), read over HTTP range requests
BONEV = ("https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/"
         "2b448d99-d3fb-4bb9-a126-386ccb99a6fd/4DNFIC21MG3U.mcool")


def default_out(name: str) -> Path:
    base = os.environ.get("UCHROM_BENCH_OUT") or tempfile.gettempdir()
    return Path(base) / name


def dump(obj, path: Path) -> None:
    def conv(x):
        if isinstance(x, (np.integer,)):
            return int(x)
        if isinstance(x, (np.floating,)):
            return None if not np.isfinite(x) else float(x)
        if isinstance(x, float) and not np.isfinite(x):
            return None
        if isinstance(x, np.ndarray):
            return [conv(v) for v in x.tolist()]
        if isinstance(x, dict):
            return {str(k): conv(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [conv(v) for v in x]
        if isinstance(x, (np.bool_,)):
            return bool(x)
        return x

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(conv(obj), indent=1))


def _rss_reader():
    """A function giving this process' resident memory in bytes: psutil, else /proc (Linux), else the peak
    so far (``resource``)."""
    try:
        import psutil

        proc = psutil.Process()
        return lambda: proc.memory_info().rss
    except ImportError:
        pass
    if os.path.exists("/proc/self/statm"):
        page = os.sysconf("SC_PAGE_SIZE")

        def statm():
            with open("/proc/self/statm") as fh:
                return int(fh.read().split()[1]) * page
        return statm
    import resource
    import sys as _sys

    scale = 1 if _sys.platform == "darwin" else 1024
    return lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale


class PeakRSS:
    """Peak resident memory of this process, sampled in a thread."""

    def __init__(self, every: float = 0.2):
        self.rss, self.every, self.peak, self._stop = _rss_reader(), every, 0, threading.Event()

    def __enter__(self):
        self.peak = self.base = self.rss()
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()
        return self

    def _run(self):
        while not self._stop.wait(self.every):
            self.peak = max(self.peak, self.rss())

    def __exit__(self, *exc):
        self._stop.set()
        self.t.join()


def timed(fn, *args, repeats: int = 1, **kw):
    """``(result, {"s": best seconds, "all_s": [...], "peak_rss_gb", "load"})`` over ``repeats`` runs."""
    times, peak, out = [], 0, None
    for _ in range(repeats):
        with PeakRSS() as mem:
            t = time.perf_counter()
            out = fn(*args, **kw)
            times.append(time.perf_counter() - t)
        peak = max(peak, mem.peak)
    return out, {"s": min(times), "all_s": [round(x, 2) for x in times], "peak_rss_gb": round(peak / 1e9, 2),
                 "load_1min": round(os.getloadavg()[0], 1)}


# ------------------------------------------------------------------------------------------------ structures

def in_memory_chrom(cd, chrom: str):
    """The spots of one chromosome, in memory."""
    sub = cd.get_chrom(chrom) if hasattr(cd, "get_chrom") else cd
    return sub.to_memory() if getattr(sub, "backed", False) else sub


def coarsen(cd, resolution: int, chrom: str, *, layer: Optional[str] = None, offset: int = 0):
    """Structures (or traces) of ``chrom`` on bins of ``resolution`` bp with edges at ``offset + k *
    resolution``: per trace the mean of the particles whose midpoint each bin holds
    (:func:`uchrom.fea.rebin_coords`).  ``layer``: use that coordinate set instead of ``coords``."""
    from chromdata import ChromData
    from uchrom.fea import rebin_coords

    sub = in_memory_chrom(cd, chrom)
    loci = sub.bins[sub.bins["chrom"].astype(str) == chrom]
    lo = (int(loci["start"].min()) - offset) // resolution * resolution + offset
    hi = int(loci["end"].max())
    starts = np.arange(lo, hi, resolution, dtype=np.int64)
    ends = np.minimum(starts + resolution, hi)                  # the last bin ends with the last locus
    bins = pd.DataFrame({"chrom": chrom, "start": starts, "end": ends})
    cube, groups = rebin_coords(sub, bins, by="trace", layer=layer, closed="left")
    t, b = np.nonzero(np.isfinite(cube[..., 0]))
    spots = pd.DataFrame({"chrom": chrom, "start": starts[b], "end": ends[b],
                          "trace_id": np.asarray(groups)[t].astype(str)})
    if "cell_id" in sub.spots.columns:
        cell_of = (sub.spots[["trace_id", "cell_id"]].astype(str).drop_duplicates("trace_id")
                   .set_index("trace_id")["cell_id"])
        spots["cell_id"] = cell_of.reindex(spots["trace_id"]).to_numpy()
    uns = {k: v for k, v in sub.uns.items() if k in ("genome_assembly", "xyz_unit")}
    uns["coarsened"] = {"resolution": int(resolution), "offset": int(offset), "layer": layer}
    return ChromData(cube[t, b], spots, uns=uns)


def trace_ids(cd) -> np.ndarray:
    return np.asarray(pd.unique(cd.spots["trace_id"].astype(str)))


def subsample(cd, n: int, seed: int, *, pool: Optional[Sequence[str]] = None):
    """``n`` traces of ``cd`` drawn without replacement (seeded), or ``cd`` when it has ``n`` or fewer."""
    ids = trace_ids(cd) if pool is None else np.asarray(pool)
    if n >= len(ids):
        return cd, list(ids)
    pick = np.random.default_rng(seed).choice(ids, size=n, replace=False)
    keep = cd.spots["trace_id"].astype(str).isin(set(pick)).to_numpy()
    return cd[keep], sorted(pick)


def gc_table(bins: pd.DataFrame, fasta) -> pd.DataFrame:
    """GC content of ``bins`` (``chrom, start, end``) from a FASTA: ``chrom, start, end, value``."""
    from uchrom.fea.sequence import compute_sequence_features

    b = bins[["chrom", "start", "end"]].reset_index(drop=True).astype({"chrom": str})
    gc = compute_sequence_features(b, Path(fasta), features=["gc_fraction"], missing="ignore")
    return b.assign(value=gc["gc_fraction"].to_numpy(dtype=float))


def with_track(cd, table: pd.DataFrame, name: str = "gc"):
    """``cd`` with ``cd.bin_tracks[name]`` = the value of ``table`` (``chrom, start, end, value``) at each
    locus (the row holding its midpoint)."""
    from uchrom.fea.compare import bin_index

    loci = cd.bins
    mid = ((loci["start"].to_numpy(np.int64) + loci["end"].to_numpy(np.int64)) // 2)
    idx = bin_index(table[["chrom", "start", "end"]], loci["chrom"].astype(str).to_numpy(), mid)
    vals = np.where(idx >= 0, table["value"].to_numpy(dtype=float)[np.clip(idx, 0, None)], np.nan)
    bt = cd.bin_tracks.copy()
    bt[name] = vals
    cd.bin_tracks = bt
    return cd


# ------------------------------------------------------------------------------------------------ references

def edges_to_domains(chrom: str, edges: Iterable[int]) -> pd.DataFrame:
    """A domain table whose internal boundaries are ``edges`` (bp; the first and last edge bound the table)."""
    e = np.unique(np.asarray(list(edges), dtype=np.int64))
    return pd.DataFrame({"chrom": chrom, "start": e[:-1], "end": e[1:]})


def arrowhead(cell: str, chrom: str) -> pd.DataFrame:
    """Rao 2014 Arrowhead domains of ``cell`` (``"GM12878"`` / ``"IMR90"``) on ``chrom``."""
    import uchrom.datasets as ds
    from uchrom.io import read_juicer_domains

    folder = Path(ds.fetch("rao2014_annotations"))
    name = {"IMR90": "GSE63525_IMR90_Arrowhead_domainlist.txt.gz",
            "GM12878": "GSE63525_GM12878_primary+replicate_Arrowhead_domainlist.txt.gz"}[cell]
    path = folder / name if (folder / name).exists() else next(folder.rglob(name))
    return read_juicer_domains(path, chrom=chrom)


def hiccups(cell: str, chrom: str) -> pd.DataFrame:
    import uchrom.datasets as ds
    from uchrom.io import read_juicer_loops

    folder = Path(ds.fetch("rao2014_annotations"))
    name = {"IMR90": "GSE63525_IMR90_HiCCUPS_looplist.txt.gz",
            "GM12878": "GSE63525_GM12878_primary+replicate_HiCCUPS_looplist.txt.gz"}[cell]
    path = folder / name if (folder / name).exists() else next(folder.rglob(name))
    return read_juicer_loops(path, chrom=chrom)


def rebinned(src, res: int, out_dir: Path, tag: str, anchor: int = 0, chrom: Optional[str] = None) -> Path:
    from uchrom.fea.maps import rebin_map

    out = Path(out_dir) / f"{tag}_{res // 1000}kb{'' if not anchor else f'_at{anchor}'}.cool"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        rebin_map(str(src), resolution=res, anchor=anchor, chrom=chrom, out=str(out))
    return out


def map_references(cool5k, chrom: str, fasta, out_dir: Path, tag: str, *, comp_res: int = 100_000,
                   tad_res: int = 20_000, loop_res: Optional[int] = None) -> Dict[str, object]:
    """Map-based calls on a 5 kb map: E1 (``comp_res``, GC-phased), insulation domains (``tad_res``, default
    window), optionally HiCCUPS loops (``loop_res``)."""
    from uchrom.strc.comp.eig import call_compartments_eig
    from uchrom.strc.tad import call_tads_insulation

    out: Dict[str, object] = {}
    p = rebinned(cool5k, comp_res, out_dir, tag, chrom=chrom)
    out["e1"] = call_compartments_eig(str(p), chrom=chrom, phasing=str(fasta))
    p = rebinned(cool5k, tad_res, out_dir, tag, chrom=chrom)
    out["insulation"] = call_tads_insulation(str(p), chrom=chrom)
    out["insulation_path"] = p
    if loop_res:
        from uchrom.strc.loop import call_loops_hiccups

        p = rebinned(cool5k, loop_res, out_dir, tag, chrom=chrom)
        out["hiccups"] = call_loops_hiccups(str(p), chrom=chrom)
    return out


# ------------------------------------------------------------------------------------------------ agreement

def boundaries_vs(cd, query, references: Dict[str, pd.DataFrame], tols=(1, 2)) -> Dict[str, dict]:
    """``compare_boundaries`` both ways (precision-like: query near reference; recall-like: reference near
    query) against each reference domain table, on the loci of ``cd``; with the chance levels."""
    from uchrom.strc.tad import compare_boundaries

    out = {}
    if isinstance(query, pd.DataFrame) and query.empty:       # compare_boundaries fails on an empty table
        return {f"{name}_tol{tol}": {"n_query": 0, "n_reference": None, "precision": float("nan"),
                                     "precision_chance": float("nan"), "recall": 0.0, "recall_chance": float("nan"),
                                     "enrichment": float("nan")} for name in references for tol in tols}
    for name, ref in references.items():
        for tol in tols:
            q = compare_boundaries(cd, query, ref, tol=tol)
            r = compare_boundaries(cd, ref, query, tol=tol)
            out[f"{name}_tol{tol}"] = {"n_query": q["n_query"], "n_reference": q["n_reference"],
                                        "precision": q["fraction_near"], "precision_chance": q["chance"],
                                        "recall": r["fraction_near"], "recall_chance": r["chance"],
                                        "enrichment": q["enrichment"]}
    return out


def frequency_auc(freq: np.ndarray, positives: np.ndarray) -> float:
    """ROC AUC of a per-locus score for the loci flagged ``positives`` (ties counted half)."""
    from scipy.stats import rankdata

    freq = np.asarray(freq, dtype=float)
    pos = np.asarray(positives, dtype=bool)
    ok = np.isfinite(freq)
    f, p = freq[ok], pos[ok]
    n1, n0 = int(p.sum()), int((~p).sum())
    if not n1 or not n0:
        return float("nan")
    r = rankdata(f)
    return float((r[p].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def near_loci(cd, chrom: str, domains: pd.DataFrame, tol: int) -> np.ndarray:
    """Per locus of ``chrom`` in ``cd``: within ``tol`` loci of a boundary of ``domains``."""
    from uchrom.strc._traces import chrom_loci
    from uchrom.strc.tad import tad_boundaries

    n = len(chrom_loci(cd, chrom))
    b = tad_boundaries(cd, domains)
    idx = b.loc[b["chrom"] == chrom, "bin_index"].to_numpy()
    flag = np.zeros(n, bool)
    for k in idx:
        flag[max(0, k - tol):k + tol + 1] = True
    return flag


def loops_vs(calls: pd.DataFrame, reference: pd.DataFrame, tols=(25_000, 50_000)) -> Dict[str, dict]:
    from uchrom.strc.loop import match_loops

    out = {}
    for tol in tols:
        rec = match_loops(reference, calls, tol=tol) if len(calls) else pd.Series([False] * len(reference))
        pre = match_loops(calls, reference, tol=tol) if len(calls) else pd.Series([], dtype=bool)
        out[f"tol{tol // 1000}kb"] = {"n_calls": int(len(calls)), "n_reference": int(len(reference)),
                                      "recall": float(rec.mean()) if len(rec) else float("nan"),
                                      "precision": float(pre.mean()) if len(pre) else float("nan")}
    return out


def snap_loops(loops: pd.DataFrame, cd, chrom: str) -> pd.DataFrame:
    """Loop anchors moved to the start of the locus of ``cd`` holding each anchor's midpoint (dropped when
    none does) — for :func:`uchrom.strc.loop.score_loops` on structures."""
    from uchrom.strc._traces import chrom_loci

    loci = chrom_loci(cd, chrom)
    s, e = loci["start"].to_numpy(), loci["end"].to_numpy()

    def snap(a, b):
        m = (np.asarray(a) + np.asarray(b)) // 2
        k = np.searchsorted(s, m, side="right") - 1
        ok = (k >= 0) & (m < e[np.clip(k, 0, None)])
        return np.where(ok, s[np.clip(k, 0, None)], -1)

    t = loops.copy()
    t["start1"] = snap(loops["start1"], loops["end1"])
    t["start2"] = snap(loops["start2"], loops["end2"])
    t = t[(t["start1"] >= 0) & (t["start2"] >= 0) & (t["start1"] != t["start2"])]
    return t.assign(chrom1=chrom).reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ FISHnet

def fishnet_windows(cd, chrom: str, params, *, window: int = 100, step: int = 50, traces=None,
                    verbose: bool = False) -> pd.DataFrame:
    """FISHnet (Patel et al. 2025) on each trace in overlapping windows of ``window`` loci (start every
    ``step``): a window's boundaries are kept in its central part (``step`` loci; the first / last window keep
    their outer part too), so every locus is judged by one window.  FISHnet was made for regions of tens to
    ~150 loci; a whole chromosome of 20 kb particles (thousands of loci) does not fit its Louvain sweep.

    Returns one row per (trace, boundary): ``chrom, trace_id, bin_index`` (locus index within ``chrom`` in
    ``cd.bins``), ``start``."""
    from uchrom.strc._traces import chrom_loci, coord_cube
    from uchrom.strc.tad.fishnet import _fishnet_on_matrix, trace_seed

    cube, loci, tids = coord_cube(cd, chrom)
    if traces is not None:
        keep = np.isin(tids, np.asarray(list(traces), dtype=str))
        cube, tids = cube[keep], tids[keep]
    n = cube.shape[1]
    starts = list(range(0, max(n - window, 0) + 1, step))
    if starts[-1] + window < n:
        starts.append(n - window)
    margin = (window - step) // 2
    rows = []
    for t, tid in enumerate(tids):
        for k, a in enumerate(starts):
            b = min(a + window, n)
            X = cube[t, a:b]
            d = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(-1))
            res = _fishnet_on_matrix(d, params, trace_seed(f"{tid}:{a}"))
            lo = a if k == 0 else a + margin
            hi = b if k == len(starts) - 1 else a + margin + step
            for bnd in res["boundaries"]:
                g = a + int(bnd)
                if lo <= g < hi:
                    rows.append({"chrom": chrom, "trace_id": str(tid), "bin_index": g,
                                 "start": int(loci["start"].iat[g])})
        if verbose:
            print(f"  fishnet {chrom} trace {t + 1}/{len(tids)}", flush=True)
    return pd.DataFrame(rows, columns=["chrom", "trace_id", "bin_index", "start"])


def fishnet_frequency(bounds: pd.DataFrame, n_loci: int, traces: Sequence[str]) -> np.ndarray:
    """Per locus: the fraction of ``traces`` with a FISHnet boundary there."""
    b = bounds[bounds["trace_id"].isin(set(map(str, traces)))]
    return np.bincount(b["bin_index"].to_numpy(np.int64), minlength=n_loci)[:n_loci] / max(len(traces), 1)


def frequency_peaks(freq: np.ndarray, n: int, min_sep: int = 2) -> np.ndarray:
    """The ``n`` highest local maxima of a per-locus frequency (at least ``min_sep`` loci apart)."""
    from scipy.signal import find_peaks

    idx, _ = find_peaks(np.r_[0.0, freq, 0.0], distance=min_sep)
    idx = idx - 1
    idx = idx[np.argsort(-freq[idx], kind="stable")][:n]
    return np.sort(idx)


def peaks_to_domains(cd, chrom: str, peaks: np.ndarray) -> pd.DataFrame:
    from uchrom.strc._traces import chrom_loci

    loci = chrom_loci(cd, chrom)
    s = loci["start"].to_numpy()
    edges = np.r_[s[0], s[np.asarray(peaks, dtype=np.int64)], loci["end"].iat[-1]]
    return edges_to_domains(chrom, edges)
