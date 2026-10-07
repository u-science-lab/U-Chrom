"""A/B compartments of a contact map by the cis eigenvector, and their strength by saddle analysis.

:func:`call_compartments_eig` is the eigenvector decomposition of the observed / expected map of each
chromosome (Lieberman-Aiden et al. 2009, *Science* 326:289), in the formulation of cooltools ``eigs_cis``
(Open2C, Abdennur et al. 2024, *PLoS Comput Biol* 20:e1012067; Imakaev et al. 2012, *Nat Methods* 9:999):
the balanced map, the first ``ignore_diags`` diagonals set to the expected, masked bins dropped, observed /
expected with the expected pooled over log-spaced classes of separation, clipped at a high percentile, and
the leading eigenvectors of ``O/E - 1`` (by absolute eigenvalue), each scaled by the square root of its
eigenvalue and oriented by its correlation with a phasing track (GC content, gene density, an active mark)
so that ``E1 > 0`` is the A compartment.

:func:`compartment_strength` is the saddle analysis (Nora et al. 2017, *Cell* 169:930; Flyamer et al. 2017,
*Nature* 544:110; Schwarzer et al. 2017, *Nature* 551:51; cooltools ``saddle``): the bins are grouped by
quantiles of E1 and the observed / expected contacts are averaged over every pair of groups; the strength
is ``(AA + BB) / (AB + BA)`` from the corners of that matrix.

Both work on the sparse pixels of one chromosome (:func:`uchrom.fea.band.read_band`): the eigenvectors are
found by Lanczos iteration (ARPACK) on ``O/E - 1`` applied as a sparse matrix minus a rank-one term, so
memory stays at the number of pixels, not the square of the number of bins.

The helpers shared with :func:`uchrom.strc.comp.call_compartments_hic` (the PC1 of the correlation matrix,
for uneven loci) live here too: the leading eigenpairs of a symmetric matrix, the orientation of an
eigenvector by a track, and the mapping of loci onto map bins.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from uchrom.convention import merge_tables, resolve_chroms, store_and_return

__all__ = [
    "EigCompartmentParams",
    "SaddleParams",
    "call_compartments_eig",
    "cis_eigs",
    "compartment_strength",
    "saddle_strength",
]


# ------------------------------------------------------------------ shared with hic_pc1


def _rows_at(table: pd.DataFrame, chrom: np.ndarray, pos: np.ndarray) -> np.ndarray:
    """For each ``(chrom, pos)``: the row (position in ``table``) whose ``[start, end)`` holds ``pos`` on
    that chromosome; -1 for none."""
    out = np.full(len(pos), -1, dtype=np.int64)
    tchrom = table["chrom"].astype(str).to_numpy()
    for c in np.unique(chrom):
        rows = np.flatnonzero(tchrom == c)
        if not len(rows):
            continue
        order = rows[np.argsort(table["start"].to_numpy()[rows], kind="mergesort")]
        starts = table["start"].to_numpy(np.int64)[order]
        ends = table["end"].to_numpy(np.int64)[order]
        want = np.flatnonzero(chrom == c)
        k = np.searchsorted(starts, pos[want], side="right") - 1
        ok = (k >= 0) & (pos[want] < ends[np.clip(k, 0, None)])
        out[want[ok]] = order[k[ok]]
    return out


def _loci_midpoints(bins: pd.DataFrame):
    return bins["chrom"].astype(str).to_numpy(), (bins["start"].to_numpy(np.int64) + bins["end"].to_numpy(np.int64)) // 2


def _top_eigs(M, n_eigs: int, *, dense_max: int = 256, seed: int = 0) -> Tuple[np.ndarray, np.ndarray]:
    """The ``n_eigs`` eigenpairs of a real symmetric matrix with the largest absolute eigenvalues.

    ``M`` is an ndarray (solved densely), or a sparse matrix / ``LinearOperator`` (dense below ``dense_max``
    rows, else ARPACK ``eigsh`` from a fixed start vector).  Returns ``eigvals (n_eigs,)`` sorted by
    decreasing ``|eigval|`` and ``eigvecs (n_eigs, n)`` (rows, unit norm), NaN-padded when the matrix is
    too small for ``n_eigs``.
    """
    n = M.shape[0]
    vals = np.full(n_eigs, np.nan)
    vecs = np.full((n_eigs, n), np.nan)
    if n == 0 or n_eigs <= 0:
        return vals, vecs
    if isinstance(M, np.ndarray) or n <= dense_max:
        A = M if isinstance(M, np.ndarray) else np.asarray(M @ np.eye(n))
        w, V = np.linalg.eigh(A)                            # ascending; ties in |w| go to the larger one
        order = (n - 1 - np.argsort(-np.abs(w[::-1]), kind="stable"))[: min(n_eigs, n)]
        vals[: len(order)] = w[order]
        vecs[: len(order)] = V[:, order].T
        return vals, vecs
    from scipy.sparse.linalg import eigsh

    k = min(n_eigs, n - 1)
    v0 = np.random.default_rng(seed).uniform(0.5, 1.5, n)
    w, V = eigsh(M, k=k, which="LM", v0=v0, tol=0)
    order = np.argsort(-np.abs(w), kind="stable")
    vals[:k] = w[order]
    vecs[:k] = V[:, order].T
    return vals, vecs


def _correlation(x: np.ndarray, y: np.ndarray, method: str) -> float:
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 2 or np.ptp(x[ok]) == 0 or np.ptp(y[ok]) == 0:
        return float("nan")
    if method == "pearson":
        return float(np.corrcoef(x[ok], y[ok])[0, 1])
    if method == "spearman":
        from scipy.stats import spearmanr

        return float(spearmanr(x[ok], y[ok])[0])
    raise ValueError(f"phasing method {method!r}: 'spearman' or 'pearson'")


def _orient(vec: np.ndarray, track: Optional[np.ndarray], method: str = "pearson") -> Tuple[np.ndarray, float]:
    """``vec`` flipped to correlate positively with ``track`` (NaN entries left out; unchanged when the
    correlation is undefined) and the correlation after flipping."""
    if track is None:
        return vec, float("nan")
    r = _correlation(np.asarray(vec, float), np.asarray(track, float), method)
    if np.isfinite(r) and r < 0:
        return -vec, -r
    return vec, r


# ------------------------------------------------------------------ parameters


@dataclass(frozen=True)
class EigCompartmentParams:
    """Knobs of :func:`call_compartments_eig` (defaults: cooltools ``eigs_cis``).

    ``ignore_diags``: the diagonals next to the main one that are left out (set to the expected); ``None``
    takes the value the map was balanced with (``ignore_diags`` attribute of its weights, else 2).
    ``clip_percentile``: observed / expected values above this percentile of all valid pairs are clipped
    (0 or 100: no clipping).  ``dist_bin_ratio``: the expected is the mean over classes of separation whose
    edges grow by this ratio (cooltools: 1.03); 1 = one class per diagonal.  ``phasing_method``: the
    correlation (``"spearman"`` as cooltools, or ``"pearson"``) by which each eigenvector is oriented
    against the phasing track; ``sort_by_phasing`` reorders the eigenvectors of a region by decreasing
    absolute correlation with the track (cooltools ``sort_metric``), which keeps a chromosome-arm or
    translocation eigenvector from being reported as E1.
    """

    ignore_diags: Optional[int] = None
    clip_percentile: float = 99.9
    dist_bin_ratio: float = 1.03
    phasing_method: str = "spearman"
    sort_by_phasing: bool = False


@dataclass(frozen=True)
class SaddleParams:
    """Knobs of :func:`compartment_strength` (defaults: the Open2C saddle examples).

    The bins are grouped by E1 between the quantiles ``qrange`` (or the values ``vrange``) into
    ``n_bins`` groups plus one outlier group at each end; pairs closer than ``min_diag`` diagonals (and
    farther than ``max_diag``, ``None``: no limit) are left out.  ``corner``: the fraction of bins at each
    end of the E1 ranking that make the AA / BB / AB corners of the scalar strength (0.2: the top and
    bottom 20 %, as Flyamer et al. 2017 and Nora et al. 2017).
    """

    qrange: Optional[Tuple[float, float]] = (0.025, 0.975)
    vrange: Optional[Tuple[float, float]] = None
    min_diag: int = 3
    max_diag: Optional[int] = None
    corner: float = 0.2


# ------------------------------------------------------------------ the eigen core


def _logbin_edges(n: int, ratio: Optional[float]) -> np.ndarray:
    """Edges of the classes of separation (diagonals) the expected is pooled over: 0 then log-spaced integers
    from 1 to ``n`` growing by ``ratio`` (cooltools ``numutils._logbins_numba(1, n, ratio)``); ``ratio <= 1``:
    one class per diagonal."""
    if ratio is None or ratio <= 1 or n < 2:
        return np.arange(n + 1, dtype=np.int64)
    num = int(np.log(n) / np.log(ratio))
    edges = np.unique(np.rint(10 ** np.linspace(0.0, np.log10(n), max(num, 2)))).astype(np.int64)
    return np.r_[0, edges]


def _weighted_percentile(values: np.ndarray, counts: np.ndarray, q: float) -> float:
    """``np.percentile`` (linear interpolation) of the multiset holding each ``values[k]`` ``counts[k]``
    times."""
    order = np.argsort(values, kind="stable")
    v = values[order]
    cum = np.cumsum(counts[order])
    total = int(cum[-1])
    pos = q / 100.0 * (total - 1)
    lo = int(np.floor(pos))
    hi = min(lo + 1, total - 1)
    a = v[np.searchsorted(cum, lo, side="right")]
    b = v[np.searchsorted(cum, hi, side="right")]
    t = pos - lo
    return float(a + (b - a) * t)


def _clip_threshold(pairs: np.ndarray, singles: np.ndarray, single_counts: np.ndarray, n_zero: float,
                    q: float) -> float:
    """``np.percentile(OE[valid][:, valid], q)`` without the dense matrix: the multiset holds every value of
    ``pairs`` twice (an off-diagonal pixel and its mirror), ``singles[k]`` ``single_counts[k]`` times and
    ``n_zero`` zeros (all values >= 0).  For a high percentile only the largest values are sorted (a
    partition of ``pairs``)."""
    single_counts = np.asarray(single_counts, dtype=np.int64)
    total = 2 * len(pairs) + int(single_counts.sum()) + int(round(n_zero))
    pos = q / 100.0 * (total - 1)
    r = int(np.floor(pos))
    r2 = min(r + 1, total - 1)
    need = total - r                                  # the elements of ascending rank >= r
    if 0 < need <= 2 * len(pairs):
        m = (need + 1) // 2
        top = np.partition(pairs, len(pairs) - m)[len(pairs) - m:]
        pool = np.sort(np.concatenate([top, top, np.repeat(singles, single_counts)]))[::-1]
        a, b = pool[need - 1], pool[total - 1 - r2]
        return float(a + (b - a) * (pos - r))
    values = np.r_[pairs, singles, 0.0]
    counts = np.r_[np.full(len(pairs), 2.0), single_counts.astype(float), float(max(n_zero, 0.0))]
    keep = counts > 0
    return _weighted_percentile(values[keep], counts[keep], q)


def cis_eigs(band, *, lo: int = 0, hi: Optional[int] = None, n_eigs: int = 3, ignore_diags: int = 2,
             clip_percentile: float = 99.9, dist_bin_ratio: float = 1.03) -> Tuple[np.ndarray, np.ndarray]:
    """Compartment eigenvectors of one cis region of a balanced map (cooltools ``cis_eig``, sparse).

    The region is bins ``[lo, hi)`` of ``band`` (a :func:`uchrom.fea.band.read_band` of the whole
    chromosome).  Valid bins are those with a positive balanced contact sum; the first ``ignore_diags``
    diagonals are set to 1 (so to the expected); observed / expected uses the mean over classes of
    separation growing by ``dist_bin_ratio`` and the valid pairs only (pairs without contacts count as 0);
    values above the ``clip_percentile`` of all valid pairs are clipped; the matrix ``O/E - 1`` of the valid
    bins is decomposed (Lieberman-Aiden et al. 2009; Imakaev et al. 2012; Open2C 2024).

    Returns
    -------
    eigvals : ndarray (n_eigs,)
        Sorted by decreasing absolute value (NaN when the region is too small).
    eigvecs : ndarray (n_eigs, hi - lo)
        Unit norm times ``sqrt(|eigval|)``; NaN on invalid bins.  Signs are arbitrary.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import LinearOperator

    from uchrom.fea.band import _valid_pairs

    if band.weight is None:
        raise ValueError("cis_eigs needs a balanced map (a 'weight' column)")
    hi = band.n if hi is None else int(hi)
    lo = int(lo)
    n = hi - lo
    ig = max(int(ignore_diags), 0)
    eigvals = np.full(n_eigs, np.nan)
    eigvecs = np.full((n_eigs, n), np.nan)
    if n <= 0:
        return eigvals, eigvecs
    v = band.values(True)
    if lo == 0 and hi == band.n:
        ok = np.isfinite(v) & (v != 0)
    else:
        ok = (band.i >= lo) & (band.j < hi) & np.isfinite(v) & (v != 0)
    i = (band.i[ok] - lo).astype(np.int32)
    j = (band.j[ok] - lo).astype(np.int32)
    v = v[ok]
    del ok
    off = i != j
    colsum = np.bincount(i, weights=v, minlength=n) + np.bincount(j[off], weights=v[off], minlength=n)
    del off
    valid = colsum > 0
    nv = int(valid.sum())
    if n <= ig + 3 or nv <= ig + 3:
        return eigvals, eigvecs

    # observed / expected over classes of separation (the ignored diagonals hold 1.0 on every valid pair)
    d = j - i
    npairs = _valid_pairs(valid, n - 1).astype(np.float64)               # valid pairs per diagonal 0..n-1
    if ig > 0:
        far = d >= ig
        i, j, v, d = i[far], j[far], v[far], d[far]
        del far
    sums = np.bincount(d, weights=v, minlength=n).astype(np.float64)
    sums[:ig] = npairs[:ig]
    edges = _logbin_edges(n, dist_bin_ratio)
    cls = np.searchsorted(edges, np.arange(n), side="right") - 1
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.bincount(cls, weights=sums) / np.bincount(cls, weights=npairs)
    expd = mean[cls]
    scale = np.where(np.isfinite(expd) & (expd != 0), 1.0 / np.where(expd != 0, expd, 1.0), 1.0)
    oe = v * scale[d]                                                  # O/E of the pixels kept
    del v
    ign = scale[:ig].copy()                                             # O/E of the ignored diagonals

    if clip_percentile and 0 < clip_percentile < 100:
        ign_count = npairs[:ig] * np.where(np.arange(ig) > 0, 2.0, 1.0)
        if ig > 0:                                                      # every pixel kept is off-diagonal
            pairs, singles, scount = oe, ign, ign_count
        else:
            on = d == 0
            pairs, singles, scount = oe[~on], oe[on], np.ones(int(on.sum()))
        n_zero = float(nv) * nv - 2.0 * len(pairs) - float(np.sum(scount))      # valid pairs without contacts
        thr = _clip_threshold(pairs, singles, scount, max(n_zero, 0.0), clip_percentile)
        del pairs, singles
        np.minimum(oe, thr, out=oe)
        ign = np.minimum(ign, thr)
    del d

    # O/E - 1 on the valid bins: S (sparse, symmetric) minus the all-ones matrix
    pos = (np.cumsum(valid) - 1).astype(np.int32)
    rows, cols, vals = [pos[i]], [pos[j]], [oe]
    del i, j
    for dd in range(min(ig, n)):
        k = np.flatnonzero(valid[: n - dd] & valid[dd:])
        rows.append(pos[k])
        cols.append(pos[k + dd])
        vals.append(np.full(len(k), ign[dd]))
    U = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(nv, nv))
    del rows, cols, vals, oe
    U = U.tocsr()
    diag = U.diagonal()
    UT = U.T                                                            # CSC view, no copy

    def matvec(x):
        x = np.ravel(x)
        return U @ x + UT @ x - diag * x - x.sum()

    if nv <= 256:
        M = U.toarray()
        M = M + M.T - np.diag(diag) - 1.0
    else:
        M = LinearOperator((nv, nv), matvec=matvec, rmatvec=matvec, dtype=np.float64)
    vals_, vecs_ = _top_eigs(M, n_eigs)
    with np.errstate(invalid="ignore", divide="ignore"):
        vecs_ = vecs_ / np.sqrt(np.nansum(vecs_ ** 2, axis=1))[:, None] * np.sqrt(np.abs(vals_))[:, None]
    eigvals[:] = vals_
    eigvecs[:, valid] = vecs_
    return eigvals, eigvecs


# ------------------------------------------------------------------ inputs


def _ignore_diags(clr, given: Optional[int]) -> int:
    if given is not None:
        return int(given)
    try:
        with clr.open("r") as h5:
            value = h5["bins"]["weight"].attrs.get("ignore_diags", 2)
        return int(value)
    except (KeyError, OSError, TypeError, ValueError):
        return 2


def _is_fasta(x) -> bool:
    name = str(x).lower()
    return name.endswith((".fa", ".fasta", ".fna", ".fa.gz", ".fasta.gz", ".fna.gz"))


def _track_on_bins(loci: pd.DataFrame, values: np.ndarray, bins: pd.DataFrame) -> np.ndarray:
    """A track given on ``loci`` (``chrom, start, end``) on the map ``bins``: the mean over the loci whose
    midpoint falls in a bin; for a bin without any, the locus that holds the bin's midpoint (a coarser
    track)."""
    loci = loci.reset_index(drop=True).astype({"chrom": str})
    values = np.asarray(values, dtype=float)
    bins = bins.reset_index(drop=True).astype({"chrom": str})
    lchrom, lmid = _loci_midpoints(loci)
    row = _rows_at(bins, lchrom, lmid)
    ok = (row >= 0) & np.isfinite(values)
    out = np.array(pd.Series(values[ok]).groupby(row[ok]).mean().reindex(np.arange(len(bins))), dtype=float)
    missing = ~np.isfinite(out)
    if missing.any():
        bchrom, bmid = _loci_midpoints(bins.iloc[np.flatnonzero(missing)])
        back = _rows_at(loci, bchrom, bmid)
        out[np.flatnonzero(missing)[back >= 0]] = values[back[back >= 0]]
    return out


def _phasing_values(cd, phasing, bins: pd.DataFrame) -> Tuple[Optional[np.ndarray], Optional[str]]:
    """The phasing track on the map ``bins`` (all chromosomes called) and a description for provenance."""
    from uchrom.fea.maps import _is_chromdata

    if phasing is None:
        return None, None
    if isinstance(phasing, pd.DataFrame):
        missing = [c for c in ("chrom", "start", "end") if c not in phasing.columns]
        if missing:
            raise KeyError(f"a phasing DataFrame needs chrom, start, end and a value column (missing {missing})")
        others = [c for c in phasing.columns if c not in ("chrom", "start", "end")]
        col = "value" if "value" in phasing.columns else (others[0] if len(others) == 1 else None)
        if col is None:
            raise KeyError(f"a phasing DataFrame needs chrom, start, end and one value column (named 'value' when "
                           f"there are several; got {others})")
        return _track_on_bins(phasing[["chrom", "start", "end"]], phasing[col].to_numpy(dtype=float), bins), \
            f"DataFrame[{col}]"
    if isinstance(phasing, str) and _is_chromdata(cd) and phasing in cd.results:
        table = cd.results[phasing]
        if not (isinstance(table, pd.DataFrame) and {"chrom", "start", "end", "E1"} <= set(table.columns)):
            raise KeyError(f"phasing={phasing!r}: cd.results[{phasing!r}] is not a compartment table (chrom, start, "
                           f"end, E1)")
        return _track_on_bins(table[["chrom", "start", "end"]], table["E1"].to_numpy(dtype=float), bins), \
            f"results[{phasing}].E1"
    if isinstance(phasing, str) and _is_chromdata(cd) and phasing in cd.bin_tracks.columns:
        loci = cd.bins[["chrom", "start", "end"]]
        return _track_on_bins(loci, cd.bin_tracks[phasing].to_numpy(dtype=float), bins), f"bin_tracks[{phasing}]"
    if isinstance(phasing, (str, Path)) and _is_fasta(phasing) and Path(phasing).expanduser().exists():
        from uchrom.fea.sequence import compute_sequence_features

        gc = compute_sequence_features(bins[["chrom", "start", "end"]], Path(phasing).expanduser(),
                                       features=["gc_fraction"], missing="ignore")
        return gc["gc_fraction"].to_numpy(dtype=float), f"GC content of {Path(phasing).expanduser()}"
    columns = list(cd.bin_tracks.columns) if _is_chromdata(cd) else []
    raise KeyError(f"phasing={phasing!r}: not a cd.bin_tracks column ({columns}), a compartment table in cd.results, "
                   f"a FASTA file or a DataFrame")


def _centromere_of(centromeres, chrom: str) -> Optional[int]:
    if centromeres is None:
        return None
    if isinstance(centromeres, pd.DataFrame):
        sub = centromeres[centromeres["chrom"].astype(str) == chrom]
        if sub.empty:
            return None
        for col in ("mid", "pos", "position"):
            if col in sub.columns:
                return int(sub[col].iloc[0])
        return int((int(sub["start"].iloc[0]) + int(sub["end"].iloc[0])) // 2)
    value = dict(centromeres).get(chrom)
    return None if value is None else int(value)


def _regions(chrom: str, starts: np.ndarray, length: int, cen: Optional[int]) -> List[Tuple[str, int, int, int, int]]:
    """``(name, lo, hi, start_bp, end_bp)`` per region of the chromosome: the whole of it, or its two arms
    (a bin goes to the arm holding its start)."""
    n = len(starts)
    if cen is None or cen <= 0 or cen >= length:
        return [(chrom, 0, n, 0, int(length))]
    k = int(np.searchsorted(starts, cen, side="left"))
    out = []
    if k > 0:
        out.append((f"{chrom}_p", 0, k, 0, int(cen)))
    if k < n:
        out.append((f"{chrom}_q", k, n, int(cen), int(length)))
    return out


def _eig_segments(table: pd.DataFrame) -> pd.DataFrame:
    """Runs of equal label within a region, broken where bins are masked: ``chrom, start, end, label,
    n_bins, E1`` (the mean E1 of the run)."""
    cols = ["chrom", "start", "end", "label", "n_bins", "E1"]
    if table.empty:
        return pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype="int64"),
                             "end": pd.Series(dtype="int64"), "label": pd.Series(dtype=str),
                             "n_bins": pd.Series(dtype="int64"), "E1": pd.Series(dtype=float)})
    frames = []
    for _, sub in table.groupby("region", sort=False, observed=True):
        sub = sub.sort_values("bin_index", kind="mergesort")
        lab = sub["compartment"].astype(str).to_numpy()
        idx = sub["bin_index"].to_numpy()
        brk = np.r_[True, (lab[1:] != lab[:-1]) | (np.diff(idx) > 1)]
        run = np.cumsum(brk) - 1
        g = sub.assign(_run=run).groupby("_run", sort=True)
        frames.append(pd.DataFrame({
            "chrom": g["chrom"].first().astype(str).to_numpy(),
            "start": g["start"].first().to_numpy(np.int64),
            "end": g["end"].last().to_numpy(np.int64),
            "label": g["compartment"].first().astype(str).to_numpy(),
            "n_bins": g.size().to_numpy(np.int64),
            "E1": g["E1"].mean().to_numpy(float),
        }))
    return pd.concat(frames, ignore_index=True)[cols]


def _empty_table(n_eigs: int) -> pd.DataFrame:
    cols = {"chrom": pd.Series(dtype=str), "start": pd.Series(dtype="int64"), "end": pd.Series(dtype="int64"),
            "bin_index": pd.Series(dtype="int64"), "region": pd.Series(dtype=str),
            "compartment": pd.Series(dtype=str)}
    cols.update({f"E{k + 1}": pd.Series(dtype=float) for k in range(n_eigs)})
    return pd.DataFrame(cols)


def _contacts_label(cd, contacts, path) -> str:
    from uchrom.fea.maps import _is_chromdata, _is_linked, _map_key

    if _is_chromdata(cd) and _is_linked(cd, contacts):
        return _map_key(cd, contacts)
    return str(path)


def _open(cd, contacts, resolution):
    from uchrom.fea.maps import _is_cooler, map_path, open_map

    if _is_cooler(cd):
        return cd, str(cd.uri)
    return open_map(cd, contacts, resolution=resolution), map_path(cd, contacts)


# ------------------------------------------------------------------ the caller


def call_compartments_eig(
    cd,
    *,
    contacts: Optional[str] = None,
    chrom=None,
    resolution: Optional[int] = None,
    phasing=None,
    centromeres=None,
    n_eigs: int = 3,
    params: Optional[EigCompartmentParams] = None,
    key_added: Optional[str] = "compartments.eig",
    copy: bool = False,
):
    """A/B compartments of a contact map: the cis eigenvectors of observed / expected, per chromosome (arm).

    The eigenvector decomposition of Lieberman-Aiden et al. 2009 (*Science* 326:289) in the formulation of
    cooltools ``eigs_cis`` (Open2C, Abdennur et al. 2024, *PLoS Comput Biol* 20:e1012067): on the balanced
    map of each chromosome (or chromosome arm), bins without contacts are dropped, the first
    ``ignore_diags`` diagonals ignored, the contacts divided by their expected (mean over log-spaced classes
    of separation), clipped at the 99.9th percentile, and the leading eigenvectors of ``O/E - 1`` taken (by
    absolute eigenvalue), each scaled by the square root of its eigenvalue.  Each eigenvector is then
    flipped to correlate positively with the ``phasing`` track, so that ``E1 > 0`` is the A (active,
    GC-rich, gene-rich) compartment.  For a map whose loci are uneven (imaged segments), use
    :func:`call_compartments_hic`.

    Parameters
    ----------
    cd : ChromData, path or cooler.Cooler
        Holds the link (``cd.link_cool(path, key=...)``) and receives the result.  A path / cooler is read
        directly and nothing is stored.
    contacts : str, optional
        Key of the linked map (``None``: the only one) or the path of a ``.cool`` / ``.mcool``.  The map
        must be balanced (``rebin_map`` balances what it writes).
    chrom : str, sequence of str, or None
        ``None``: the chromosomes of ``cd`` that the map has (every map chromosome when ``cd`` has no spots).
    resolution : int, optional
        The level of an ``.mcool``.
    phasing : str, path or DataFrame, optional
        The track the eigenvectors are oriented by (higher in A): the path of a FASTA (the GC content of
        every map bin, :func:`uchrom.fea.compute_sequence_features`), the name of a ``cd.bin_tracks``
        column (gene density, an active mark), the key of a compartment table in ``cd.results`` (its
        ``E1``: e.g. cell-type maps oriented like the all-cells map), or a DataFrame with ``chrom, start,
        end`` and one value column (``value`` when it has several) — each map bin takes the mean of the loci
        whose midpoint it holds (or the locus holding its midpoint).  Without it the signs, and so which
        label is A, are arbitrary.
    centromeres : mapping or DataFrame, optional
        Centromere position per chromosome (``{chrom: bp}``, or a table with ``chrom`` and ``mid`` / ``pos``
        / ``start, end``): each arm is decomposed on its own (a bin belongs to the arm holding its start),
        which keeps the arms' contrast out of E1.
    n_eigs : int
        Eigenvectors per region (``E1 .. En``).
    params : EigCompartmentParams, optional
    key_added : str or None
        ``cd.results`` key (default ``"compartments.eig"``); ``None`` does not store.
    copy : bool
        ``True`` → return a new ChromData holding the result.

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        One row per valid map bin: ``chrom, start, end, bin_index`` (in the map, per chromosome),
        ``region`` (the chromosome, or ``<chrom>_p`` / ``<chrom>_q``), ``compartment`` (``"A"`` where
        ``E1 > 0``) and ``E1 .. En``.  When stored, also the eigenvalues per region (``region, chrom, start,
        end, eigval1 .., phasing_r1 ..``: the correlation of each eigenvector with the phasing track) as
        ``cd.results[f"{key_added}.eigvals"]``, the runs of equal label (broken at masked bins) as the
        ``segment`` table ``cd.intervals[key_added]``, and E1 on the loci of ``cd`` (the map bin holding
        each locus' midpoint) as ``cd.bin_tracks[f"{key_added}.E1"]``.
    """
    from uchrom.fea.band import read_band
    from uchrom.fea.maps import _is_chromdata

    params = params or EigCompartmentParams()
    if n_eigs < 1:
        raise ValueError("n_eigs must be at least 1")
    is_cd = _is_chromdata(cd)
    if not is_cd:
        if copy:
            raise ValueError("call_compartments_eig(copy=True) needs a ChromData")
        key_added = None
    if copy and key_added is None:
        raise ValueError("call_compartments_eig(): copy=True needs a key_added")
    clr, path = _open(cd, contacts, resolution)
    if chrom is None:
        wanted = resolve_chroms(cd, None) if is_cd and len(cd.spots) else []
        chroms = [c for c in wanted if c in clr.chromnames] or list(clr.chromnames)
    else:
        chroms = resolve_chroms(cd, chrom) if is_cd else ([chrom] if isinstance(chrom, str) else list(chrom))
    missing = [c for c in chroms if c not in clr.chromnames]
    if missing:
        raise ValueError(f"not in the map: {missing}")
    if "weight" not in clr.bins().columns:
        raise ValueError(f"{path}: the map is not balanced (no 'weight' column); balance it, e.g. "
                         f"uchrom.fea.rebin_map(cd, contacts, resolution=...)")
    ig = _ignore_diags(clr, params.ignore_diags)

    all_bins = pd.concat([clr.bins().fetch(c)[["chrom", "start", "end"]] for c in chroms], ignore_index=True)
    all_bins["chrom"] = all_bins["chrom"].astype(str)
    track_all, phasing_label = _phasing_values(cd, phasing, all_bins)
    offsets = np.r_[0, np.cumsum([int(clr.extent(c)[1] - clr.extent(c)[0]) for c in chroms])]

    frames, evals = [], []
    for ci, c in enumerate(chroms):
        band = read_band(clr, chrom=c, balance=True)
        track = None if track_all is None else track_all[offsets[ci]: offsets[ci + 1]].copy()
        if track is not None:
            track[~band.valid] = np.nan
        vecs = np.full((n_eigs, band.n), np.nan)
        for name, lo, hi, s_bp, e_bp in _regions(c, band.starts, int(clr.chromsizes[c]),
                                                 _centromere_of(centromeres, c)):
            w, V = cis_eigs(band, lo=lo, hi=hi, n_eigs=n_eigs, ignore_diags=ig,
                            clip_percentile=params.clip_percentile, dist_bin_ratio=params.dist_bin_ratio)
            r = np.full(n_eigs, np.nan)
            if track is not None:
                for k in range(n_eigs):
                    V[k], r[k] = _orient(V[k], track[lo:hi], params.phasing_method)
                if params.sort_by_phasing:
                    order = np.argsort(-np.nan_to_num(np.abs(r), nan=-1.0), kind="stable")
                    w, V, r = w[order], V[order], r[order]
            vecs[:, lo:hi] = V
            evals.append({"region": name, "chrom": c, "start": s_bp, "end": e_bp,
                          **{f"eigval{k + 1}": float(w[k]) for k in range(n_eigs)},
                          **{f"phasing_r{k + 1}": float(r[k]) for k in range(n_eigs)}})
            rows = np.arange(lo, hi)[np.isfinite(V[0])]
            if not len(rows):
                continue
            e1 = vecs[0, rows]
            ends = all_bins["end"].to_numpy(np.int64)[offsets[ci]: offsets[ci + 1]]
            frame = pd.DataFrame({"chrom": c, "start": band.starts[rows], "end": ends[rows],
                                  "bin_index": rows.astype(np.int64), "region": name,
                                  "compartment": np.where(e1 > 0, "A", "B")})
            for k in range(n_eigs):
                frame[f"E{k + 1}"] = vecs[k, rows]
            frames.append(frame)
    table = merge_tables(frames, _empty_table(n_eigs)).reset_index(drop=True)
    table = table[list(_empty_table(n_eigs).columns)]
    table["chrom"] = table["chrom"].astype(str)
    eigvals = pd.DataFrame(evals, columns=["region", "chrom", "start", "end"]
                           + [f"eigval{k + 1}" for k in range(n_eigs)]
                           + [f"phasing_r{k + 1}" for k in range(n_eigs)])
    if not is_cd or key_added is None:
        return table

    inputs = {"contacts": _contacts_label(cd, contacts, path), "contacts_path": str(path),
              "resolution": int(clr.binsize) if clr.binsize else None, "chrom": list(chroms),
              "phasing": phasing_label, "ignore_diags": ig, "n_eigs": int(n_eigs),
              "centromeres": None if centromeres is None else
              {c: _centromere_of(centromeres, c) for c in chroms if _centromere_of(centromeres, c) is not None}}
    out = store_and_return(
        cd, table, key_added=key_added, copy=copy, kind="table",
        function="uchrom.strc.comp.call_compartments_eig", params=params, inputs=inputs,
        extra=[(f"{key_added}.eigvals", eigvals, "table")],
        intervals=[(key_added, _eig_segments(table), "segment")],
    )
    target = out if copy else cd
    if len(target.bins):
        lchrom, mid = _loci_midpoints(target.bins)
        row = _rows_at(table, lchrom, mid)
        values = np.where(row >= 0, table["E1"].to_numpy()[np.clip(row, 0, None)], np.nan)
        bt = target.bin_tracks.copy()
        bt[f"{key_added}.E1"] = values
        target.bin_tracks = bt
    return out


# ------------------------------------------------------------------ saddle


def saddle_strength(S: np.ndarray, C: np.ndarray) -> np.ndarray:
    """Compartment strength for every corner extent ``k`` of a saddle (cooltools ``saddle_strength``):
    ``(AA + BB) / (AB + BA)`` with the sums and counts of the ``k x k`` corners pooled; index 0 is NaN."""
    S = np.asarray(S, float)
    C = np.asarray(C, float)
    n = S.shape[0]
    if S.shape != (n, n) or C.shape != (n, n):
        raise ValueError("saddle sums and counts must be square and of the same shape")
    out = np.full(n, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        for k in range(1, n):
            intra = (np.nansum(S[:k, :k]) + np.nansum(S[n - k:, n - k:])) / \
                    (np.nansum(C[:k, :k]) + np.nansum(C[n - k:, n - k:]))
            inter = (np.nansum(S[:k, n - k:]) + np.nansum(S[n - k:, :k])) / \
                    (np.nansum(C[:k, n - k:]) + np.nansum(C[n - k:, :k]))
            out[k] = intra / inter
    return out


def _compartment_track(cd, compartments, column: str) -> pd.DataFrame:
    if isinstance(compartments, pd.DataFrame):
        table = compartments
    else:
        if not hasattr(cd, "results") or compartments not in cd.results:
            raise KeyError(f"compartments={compartments!r} is not a key of cd.results; call "
                           f"call_compartments_eig first or pass a table")
        table = pd.DataFrame(cd.results[compartments])
    need = [c for c in ("chrom", "start", "end", column) if c not in table.columns]
    if need:
        raise KeyError(f"the compartment table lacks {need} (columns: {list(table.columns)})")
    return table.reset_index(drop=True).astype({"chrom": str})


def _pair_counts(groups: np.ndarray, G: int, diagonals: np.ndarray) -> np.ndarray:
    """Ordered pairs (i, j) with ``|i - j|`` in ``diagonals`` per pair of groups (``groups < 0``: none)."""
    n = len(groups)
    C = np.zeros(G * G)
    for d in diagonals:
        d = int(d)
        if d >= n:
            continue
        a, b = groups[: n - d], groups[d:]
        k = (a >= 0) & (b >= 0)
        C += np.bincount(a[k] * G + b[k], minlength=G * G)
        if d > 0:
            C += np.bincount(b[k] * G + a[k], minlength=G * G)
    return C.reshape(G, G)


def compartment_strength(
    cd,
    *,
    contacts: Optional[str] = None,
    compartments: Union[str, pd.DataFrame] = "compartments.eig",
    track: str = "E1",
    chrom=None,
    resolution: Optional[int] = None,
    n_bins: int = 38,
    params: Optional[SaddleParams] = None,
    key_added: Optional[str] = "compartment_strength.saddle",
    copy: bool = False,
):
    """Compartment strength by saddle analysis: observed / expected contacts averaged over pairs of E1
    quantile groups, and ``(AA + BB) / (AB + BA)`` from its corners.

    Following Nora et al. 2017 (*Cell* 169:930), Flyamer et al. 2017 (*Nature* 544:110), Schwarzer et al.
    2017 (*Nature* 551:51) and cooltools ``saddle`` / ``saddle_strength`` (Open2C 2024): the valid bins of
    the chromosomes are pooled and split by the quantiles of ``track`` into ``n_bins`` groups (plus an
    outlier group at each end); every cis pair of valid bins at least ``min_diag`` diagonals apart adds its
    observed / expected (balanced contacts over the mean of their diagonal, :func:`uchrom.fea.expected_cis`;
    pairs without contacts add 0) to the cell of its two groups.  The saddle is the mean per cell; the
    strength the pooled mean of the AA and BB corners over that of the AB and BA corners, for every corner
    size (``strength_curve``) and for the top / bottom ``corner`` fraction of bins (``strength``).

    Parameters
    ----------
    cd : ChromData, path or cooler.Cooler
        Holds the map link and the compartment call; a path / cooler (with ``compartments`` a DataFrame) is
        read directly and nothing is stored.
    contacts : str, optional
        Key of the linked map (``None``: the only one) or a path; balanced.
    compartments : str or DataFrame
        The compartment call: a ``cd.results`` key (default ``"compartments.eig"``) or a table with ``chrom,
        start, end`` and ``track``.  Each map bin takes the value of the call's bin holding its midpoint.
    track : str
        Column of ``compartments`` to group by (``E1``; higher = A).
    chrom : str, sequence of str, or None
        Chromosomes to pool (default: those of the call that the map has).
    resolution : int, optional
        The level of an ``.mcool``.
    n_bins : int
        Quantile groups between ``params.qrange`` (cooltools / Open2C examples: 38 groups of 2.5 %).
    params : SaddleParams, optional
    key_added : str or None
        ``cd.results`` key (a mapping); ``None`` does not store.
    copy : bool
        ``True`` → return a new ChromData holding the result.

    Returns
    -------
    dict (``copy=False``) or ChromData (``copy=True``)
        ``saddle`` (``(n_bins + 2) x (n_bins + 2)`` mean observed / expected, outlier groups first and
        last), ``sum`` and ``count`` (as cooltools: over both triangles, symmetrised), ``edges`` (the
        ``track`` values at the group edges), ``group_size`` (bins per group), ``strength_curve`` (by
        corner size ``k``; index 0 NaN), ``corner_groups`` (the ``k`` of ``strength``), ``strength``,
        ``AA``, ``BB``, ``AB`` (mean observed / expected in the corners), ``chrom``.
    """
    from uchrom.fea.band import band_observed_over_expected, expected_cis, read_band
    from uchrom.fea.maps import _is_chromdata

    params = params or SaddleParams()
    if n_bins < 1:
        raise ValueError("n_bins must be at least 1")
    if (params.qrange is None) == (params.vrange is None):
        raise ValueError("SaddleParams: give exactly one of qrange and vrange")
    is_cd = _is_chromdata(cd)
    if not is_cd:
        if copy:
            raise ValueError("compartment_strength(copy=True) needs a ChromData")
        key_added = None
    if copy and key_added is None:
        raise ValueError("compartment_strength(): copy=True needs a key_added")
    table = _compartment_track(cd, compartments, track)
    clr, path = _open(cd, contacts, resolution)
    if "weight" not in clr.bins().columns:
        raise ValueError(f"{path}: the map is not balanced (no 'weight' column)")
    if chrom is None:
        present = list(pd.unique(table["chrom"]))
        chroms = [c for c in clr.chromnames if c in present]
    else:
        chroms = [chrom] if isinstance(chrom, str) else [str(c) for c in chrom]
    missing = [c for c in chroms if c not in clr.chromnames]
    if missing:
        raise ValueError(f"not in the map: {missing}")
    if not chroms:
        raise ValueError("no chromosome of the compartment call is in the map")
    max_dist = None if params.max_diag is None else int(params.max_diag) * int(clr.binsize)

    bands, values = [], []
    for c in chroms:
        band = read_band(clr, chrom=c, max_dist=max_dist, balance=True)
        bins = pd.DataFrame({"chrom": c, "start": band.starts, "end": band.starts + band.binsize})
        bchrom, bmid = _loci_midpoints(bins)
        row = _rows_at(table, bchrom, bmid)
        val = np.where(row >= 0, table[track].to_numpy(dtype=float)[np.clip(row, 0, None)], np.nan)
        val[~band.valid] = np.nan
        bands.append(band)
        values.append(val)
    pooled = np.concatenate(values)
    finite = pooled[np.isfinite(pooled)]
    if len(finite) < 2:
        raise ValueError("fewer than two valid bins with a compartment value")
    if params.qrange is not None:
        qlo, qhi = params.qrange
        if not 0.0 <= qlo <= qhi <= 1.0:
            raise ValueError("qrange must satisfy 0 <= low <= high <= 1")
        edges = np.nanpercentile(finite, np.linspace(qlo, qhi, n_bins + 1) * 100)
    else:
        vlo, vhi = params.vrange
        if vlo > vhi:
            raise ValueError("vrange must satisfy low <= high")
        edges = np.linspace(vlo, vhi, n_bins + 1)
    G = n_bins + 2

    S = np.zeros((G, G))
    C = np.zeros((G, G))
    for band, val in zip(bands, values):
        g = np.where(np.isfinite(val), np.digitize(np.nan_to_num(val), edges, right=False), -1).astype(np.int64)
        exp = expected_cis(None, bands=[band])
        avg = exp["balanced_avg"].to_numpy()
        oe = band_observed_over_expected(band, exp)
        d = band.diag
        top = band.max_diag if params.max_diag is None else int(params.max_diag)
        sel = (d >= params.min_diag) & (d <= top) & np.isfinite(oe)
        gi, gj = g[band.i[sel]], g[band.j[sel]]
        k = (gi >= 0) & (gj >= 0)
        gi, gj, w, dd = gi[k], gj[k], oe[sel][k], d[sel][k]
        S += np.bincount(gi * G + gj, weights=w, minlength=G * G).reshape(G, G)
        off = dd > 0
        S += np.bincount(gj[off] * G + gi[off], weights=w[off], minlength=G * G).reshape(G, G)
        # pairs counted: both bins valid, the expected of their diagonal finite and non-zero
        n = band.n
        allowed = np.zeros(n, bool)
        D = min(len(avg), n)
        allowed[:D] = np.isfinite(avg[:D]) & (avg[:D] != 0)
        allowed[: max(params.min_diag, 0)] = False
        allowed[top + 1:] = False
        gv = np.where(band.valid, g, -1)
        if (~allowed).sum() <= allowed.sum():
            nk = np.bincount(gv[gv >= 0], minlength=G).astype(float)
            C += np.outer(nk, nk) - _pair_counts(gv, G, np.flatnonzero(~allowed))
        else:
            C += _pair_counts(gv, G, np.flatnonzero(allowed))
    S = S + S.T
    C = C + C.T
    with np.errstate(invalid="ignore", divide="ignore"):
        saddle = S / C
    curve = saddle_strength(S, C)
    group_size = np.bincount(np.concatenate([np.where(np.isfinite(v), np.digitize(np.nan_to_num(v), edges), -1)
                                             for v in values]) + 1, minlength=G + 1)[1:]
    low = np.cumsum(group_size) / max(group_size.sum(), 1)              # fraction of bins in groups < k + 1
    kc = int(np.argmin(np.abs(low[: G - 1] - params.corner))) + 1
    kc = max(1, min(kc, G // 2))
    s_aa, c_aa = np.nansum(S[G - kc:, G - kc:]), np.nansum(C[G - kc:, G - kc:])
    s_bb, c_bb = np.nansum(S[:kc, :kc]), np.nansum(C[:kc, :kc])
    s_ab = np.nansum(S[:kc, G - kc:]) + np.nansum(S[G - kc:, :kc])
    c_ab = np.nansum(C[:kc, G - kc:]) + np.nansum(C[G - kc:, :kc])
    with np.errstate(invalid="ignore", divide="ignore"):
        result: Dict[str, object] = {
            "saddle": saddle, "sum": S, "count": C, "edges": np.asarray(edges, float),
            "group_size": group_size.astype(np.int64), "strength_curve": curve, "corner_groups": int(kc),
            "strength": float(curve[kc]), "AA": float(s_aa / c_aa), "BB": float(s_bb / c_bb),
            "AB": float(s_ab / c_ab), "chrom": list(chroms),
        }
    if key_added is None:
        return result
    inputs = {"contacts": _contacts_label(cd, contacts, path), "contacts_path": str(path), "compartments":
              compartments if isinstance(compartments, str) else "DataFrame", "track": track,
              "chrom": list(chroms), "n_bins": int(n_bins),
              "resolution": int(clr.binsize) if clr.binsize else None}
    return store_and_return(cd, result, key_added=key_added, copy=copy, kind="mapping",
                            function="uchrom.strc.comp.compartment_strength", params=params, inputs=inputs)
