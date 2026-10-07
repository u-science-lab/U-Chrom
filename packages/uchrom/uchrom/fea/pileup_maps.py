"""Pileups of a Hi-C map around a set of features: aggregate peak analysis (APA) of loops, on-diagonal
pileups of points (domain boundaries, peaks).

A loop that is too weak to be called in a sparse map — a cell-type pseudo-bulk, a few deep single cells —
still shows when the map is averaged over many loops: :func:`pileup` cuts a ``(2f+1) x (2f+1)`` window of
the map around every feature and aggregates observed over expected (the expected contact at each pixel's
separation): the summed observed over the summed expected of every pixel of the window (default), or the
mean of the features' observed / expected windows.  Pairs (loops ``chrom1, start1, end1,
chrom2, start2, end2``; called in bulk Hi-C, or from imaging) are centred on the pixel of their two anchors
(Rao et al. 2014, APA); points (``chrom, start, end``) on the diagonal at the point.

The scores follow Juicer APA (Rao et al. 2014; Durand et al. 2016): for pairs ``apa`` = P2LL, the centre
pixel over the mean of the lower-left corner (the ``corner x corner`` square towards the diagonal), ``p2m``
the centre over the mean of the rest of the window and ``zscore_ll`` the centre's z-score in the lower-left
corner — above 1 (P2LL) when the loops are enriched.  For points ``score`` = mean of the two on-diagonal
quadrants (upstream x upstream, downstream x downstream) over the mean of the cross quadrant (upstream x
downstream) — above 1 at insulating boundaries.

References
----------
Rao, S. S. P. et al. (2014) *Cell* 159:1665-1680 (APA).  Durand, N. C. et al. (2016) Juicer provides a
one-click system for analyzing loop-resolution Hi-C experiments. *Cell Syst.* 3:95-98.
Flyamer, I. M., Illingworth, R. S. & Bickmore, W. A. (2020) Coolpup.py: versatile pile-up analysis of Hi-C
data. *Bioinformatics* 36:2980-2985.
"""

from __future__ import annotations

from typing import Optional, Union

import numpy as np
import pandas as pd

__all__ = ["pileup", "pileup_scores"]

#: window pixels gathered per batch (bounds the working memory: ~10 arrays of this size)
WINDOW_CELLS = 2_000_000


def _feature_table(cd, features) -> pd.DataFrame:
    if isinstance(features, str):
        if hasattr(cd, "intervals") and features in cd.intervals:
            features = cd.intervals[features]
        elif hasattr(cd, "results") and features in cd.results:
            features = cd.results[features]
        else:
            raise KeyError(f"{features!r} is neither in cd.intervals nor in cd.results")
    t = pd.DataFrame(features).reset_index(drop=True)
    return t


def _kind(t: pd.DataFrame) -> str:
    if {"start1", "end1", "start2", "end2"} <= set(t.columns):
        if not ({"chrom1"} <= set(t.columns) or "chrom" in t.columns):
            raise KeyError("pair features need chrom1 (or chrom)")
        return "pair"
    if {"chrom", "start", "end"} <= set(t.columns):
        return "point"
    raise KeyError("features need chrom1, start1, end1, chrom2, start2, end2 (pairs) or chrom, start, end "
                   "(points)")


def pileup_scores(matrix: np.ndarray, *, kind: str = "pair", corner: int = 6) -> dict:
    """Scores of a pileup window (``(2f+1) x (2f+1)``, rows = first anchor, columns = second).

    ``kind="pair"``: ``apa`` (P2LL: centre / mean of the lower-left ``corner x corner`` square), ``p2m``
    (centre / mean of the other pixels), ``zscore_ll`` (centre's z-score in the lower-left square, sample
    s.d.).  ``kind="point"``: ``score`` = mean of the on-diagonal quadrants / mean of the upstream x
    downstream quadrant (centre row and column left out).  NaN pixels are left out.
    """
    M = np.asarray(matrix, dtype=np.float64)
    L = M.shape[0]
    f = L // 2
    with np.errstate(invalid="ignore", divide="ignore"):
        if kind == "pair":
            c = M[f, f]
            ll = M[L - corner:, :corner]
            rest = np.delete(M.ravel(), f * L + f)
            llv = ll[np.isfinite(ll)]
            mll = float(llv.mean()) if len(llv) else np.nan
            sll = float(llv.std(ddof=1)) if len(llv) > 1 else np.nan
            rv = rest[np.isfinite(rest)]
            return {"apa": float(c / mll), "p2m": float(c / rv.mean()) if len(rv) else np.nan,
                    "zscore_ll": float((c - mll) / sll), "center": float(c), "lower_left": mll}
        up, down = slice(0, f), slice(f + 1, L)
        within = np.r_[M[up, up].ravel(), M[down, down].ravel()]
        cross = M[up, down].ravel()
        w, x = within[np.isfinite(within)], cross[np.isfinite(cross)]
        mw = float(w.mean()) if len(w) else np.nan
        mx = float(x.mean()) if len(x) else np.nan
        return {"score": mw / mx, "within": mw, "between": mx}


def pileup(
    cd,
    features,
    *,
    contacts=None,
    resolution: Optional[int] = None,
    chrom=None,
    flank: Optional[int] = None,
    expected: Union[bool, pd.DataFrame] = True,
    balance: bool = True,
    min_separation: Optional[int] = None,
    max_separation: Optional[int] = None,
    corner: Optional[int] = None,
    ignore_diags: int = 2,
    aggregate: str = "sum",
    key_added: Optional[str] = "pileup",
    copy: bool = False,
):
    """The average observed / expected Hi-C map around a set of features (APA; Rao et al. 2014).

    Parameters
    ----------
    cd : ChromData
        Holds the map (``cd.link_cool``) and receives the result; or the path of a ``.cool`` / ``.mcool``
        (then nothing is stored).
    features : DataFrame or str
        Pairs (``chrom1, start1, end1, chrom2, start2, end2``; e.g. loops from :func:`call_loops_hiccups`,
        :func:`call_loops_axiswise_f`, a published list) or points (``chrom, start, end``; e.g. domain
        boundaries), or a key of ``cd.intervals`` / ``cd.results``.  An anchor sits in the map bin holding its
        midpoint; pairs between chromosomes are left out.
    contacts : str, optional
        Key of the linked map (``None``: the only one) or the path of a ``.cool`` / ``.mcool``.
    resolution : int, optional
        The level of an ``.mcool``.
    chrom : str or sequence of str, optional
        Only the features on these chromosomes.
    flank : int, optional
        Half-width of the window, bp (default 10 bins, as Juicer APA).
    expected : bool or DataFrame
        ``True``: divide every pixel by the mean contact of its diagonal on its chromosome
        (:func:`uchrom.fea.band.expected_cis`, from the map itself); a DataFrame: that expected (``chrom,
        diag, balanced_avg`` — or ``count_avg`` with ``balance=False``); ``False``: the (balanced) observed.
    balance : bool
        Balanced values (cooler ``weight``); ``False`` = raw counts (a map too sparse to balance).
    min_separation, max_separation : int, optional
        Pairs whose anchors are closer / farther (bins) are left out.  Default minimum: the window stays off
        the ignored diagonals (``2 * flank_bins + ignore_diags``).
    corner : int, optional
        Side of the lower-left square of the APA score, bins (Juicer: 3 at 5 kb, else 6).
    ignore_diags : int
        Diagonals left out (NaN): the first two, as for the expected.
    aggregate : {"sum", "mean"}
        ``"sum"`` (default): per pixel, the summed observed over the summed expected of the features — the
        Poisson maximum-likelihood enrichment of the set; features weigh by their expected, so a few far-apart
        pairs (tiny expected, huge O/E) cannot dominate, and it is steadier in sparse maps.  ``"mean"``: the
        mean of the features' observed / expected windows (every feature weighs the same).
    key_added : str or None
        ``cd.results`` key (default ``"pileup"``); ``None`` does not store.
    copy : bool
        ``True`` → return a new ChromData holding the result.

    Returns
    -------
    dict (``copy=False``) or ChromData (``copy=True``)
        ``matrix`` (the mean window, ``(2f+1, 2f+1)``; rows = first anchor ± f bins, columns = second),
        ``n_pixels`` (features contributing to each pixel), ``n`` (features used), ``n_dropped``, ``kind``,
        ``resolution``, ``flank_bins``, the scores of :func:`pileup_scores` (pairs: ``apa``, ``p2m``,
        ``zscore_ll``; points: ``score``), and ``features``: the feature table with ``used``, ``center``
        (their centre pixel), ``lower_left`` (mean of their lower-left square) for pairs.

    Examples
    --------
    >>> loops = ds.fetch("rao2014_annotations")                                # doctest: +SKIP
    >>> apa = pileup(hic, published_loops, contacts="bulk_10kb")              # doctest: +SKIP
    >>> apa["apa"]                                                             # doctest: +SKIP
    """
    from uchrom.fea.band import _expected_one, read_band
    from uchrom.fea.maps import _is_chromdata, _is_cooler, map_path, open_map

    if copy and (key_added is None or not _is_chromdata(cd)):
        raise ValueError("pileup(copy=True) needs a ChromData and a key_added")
    if aggregate not in ("mean", "sum"):
        raise ValueError(f"aggregate={aggregate!r}: 'mean' or 'sum'")
    clr = cd if _is_cooler(cd) else open_map(map_path(cd, contacts) if _is_chromdata(cd) else cd,
                                             resolution=resolution)
    binsize = int(clr.binsize) if clr.binsize else None          # None: bins of uneven size (e.g. imaged loci)
    if binsize is None:
        sizes = (clr.bins()[:]["end"] - clr.bins()[:]["start"]).to_numpy()
        step = float(np.median(sizes))
    else:
        step = float(binsize)
    f = 10 if flank is None else max(1, int(round(flank / step)))
    L = 2 * f + 1
    cw = (3 if step <= 5000 else 6) if corner is None else int(corner)
    cw = min(cw, f)
    t = _feature_table(cd, features)
    kind = _kind(t)
    if kind == "pair":
        c1 = (t["chrom1"] if "chrom1" in t.columns else t["chrom"]).astype(str).to_numpy()
        c2 = (t["chrom2"] if "chrom2" in t.columns else t["chrom"]).astype(str).to_numpy()
        m1 = (t["start1"].to_numpy(np.int64) + t["end1"].to_numpy(np.int64)) // 2
        m2 = (t["start2"].to_numpy(np.int64) + t["end2"].to_numpy(np.int64)) // 2
        m1, m2 = np.minimum(m1, m2), np.maximum(m1, m2)
        ok = c1 == c2
    else:
        c1 = t["chrom"].astype(str).to_numpy()
        m1 = m2 = (t["start"].to_numpy(np.int64) + t["end"].to_numpy(np.int64)) // 2
        ok = np.ones(len(t), bool)
    names = set(map(str, clr.chromnames))
    alias = {}                                                   # "21" -> "chr21" and back (published lists)
    for c in pd.unique(c1):
        alias[c] = c if c in names else (f"chr{c}" if f"chr{c}" in names else
                                         (c[3:] if c.startswith("chr") and c[3:] in names else None))
    if chrom is not None:
        keep = {chrom} if isinstance(chrom, str) else set(map(str, chrom))
        ok &= np.array([c in keep or alias.get(c) in keep for c in c1], bool)
    mapped = np.array([alias.get(c) for c in c1], dtype=object)
    ok &= mapped != None  # noqa: E711
    # the map bin holding each anchor's midpoint (-1: none)
    b1 = np.full(len(t), -1, np.int64)
    b2 = np.full(len(t), -1, np.int64)
    for c in pd.unique(mapped[ok]):
        rows = np.flatnonzero(ok & (mapped == c))
        cb = clr.bins().fetch(c)
        starts, ends = cb["start"].to_numpy(np.int64), cb["end"].to_numpy(np.int64)
        for m, b in ((m1, b1), (m2, b2)):
            k = np.searchsorted(starts, m[rows], side="right") - 1
            inside = (k >= 0) & (m[rows] < ends[np.clip(k, 0, len(ends) - 1)])
            b[rows] = np.where(inside, k, -1)
    ok &= (b1 >= 0) & (b2 >= 0)
    if kind == "pair":
        lo_sep = 2 * f + ignore_diags if min_separation is None else int(min_separation)
        ok &= (b2 - b1) >= lo_sep
        if max_separation is not None:
            ok &= (b2 - b1) <= int(max_separation)

    total = np.zeros((L, L))
    tot_o, tot_e = np.zeros((L, L)), np.zeros((L, L))
    npix = np.zeros((L, L), np.int64)
    center = np.full(len(t), np.nan)
    lower_left = np.full(len(t), np.nan)
    used = np.zeros(len(t), bool)
    off = np.arange(-f, f + 1)
    for c in pd.unique(mapped[ok]):
        rows = np.flatnonzero(ok & (mapped == c))
        lo_c, hi_c = clr.extent(c)
        n = int(hi_c - lo_c)
        if not len(rows):
            continue
        reach = int((b2[rows] - b1[rows]).max()) + 2 * f + 1
        band = read_band(clr, chrom=c, max_dist=None if binsize is None else reach * binsize,
                         balance=balance)
        use_bal = balance and band.weight is not None
        vals = band.values(use_bal)
        if isinstance(expected, pd.DataFrame):
            ex = expected[expected["chrom"].astype(str) == c].set_index("diag")
            col = "balanced_avg" if use_bal or "count_avg" not in ex.columns else "count_avg"
            evec = ex[col].reindex(np.arange(reach + 1)).to_numpy(dtype=np.float64)
        elif expected:
            ex = _expected_one(band, use_bal)
            evec = (ex["balanced_avg"] if use_bal else ex["count_sum"] / ex["n_valid"]).to_numpy(np.float64)
            evec = np.r_[evec, np.full(max(0, reach + 1 - len(evec)), np.nan)][: reach + 1]
        else:
            evec = np.ones(reach + 1)
        evec = evec.copy()
        evec[: max(0, ignore_diags)] = np.nan
        # pixel lookup in the band (i <= j) by key i * n + j
        keys = band.i.astype(np.int64) * n + band.j.astype(np.int64)
        if len(keys) > 1 and not (keys[1:] >= keys[:-1]).all():      # cooler pixels come sorted
            order = np.argsort(keys, kind="stable")
            keys, vals = keys[order], vals[order]
        valid = band.valid if use_bal else np.ones(n, bool)
        batch = max(1, WINDOW_CELLS // (L * L))
        for s in range(0, len(rows), batch):                         # (m, L, L) windows, in batches
            rr = rows[s: s + batch]
            I, J = np.broadcast_arrays(b1[rr][:, None, None] + off[None, :, None],
                                       b2[rr][:, None, None] + off[None, None, :])
            inb = (I >= 0) & (I < n) & (J >= 0) & (J < n)
            lo, hi = np.clip(np.minimum(I, J), 0, n - 1), np.clip(np.maximum(I, J), 0, n - 1)
            v = np.zeros(I.shape)
            if len(keys):
                k = lo * n + hi
                pos = np.minimum(np.searchsorted(keys, k), len(keys) - 1)
                hit = keys[pos] == k
                v[hit] = vals[pos[hit]]
            d = hi - lo
            good = inb & valid[lo] & valid[hi] & (d <= reach)
            ev = evec[np.minimum(d, reach)]
            with np.errstate(invalid="ignore", divide="ignore"):
                win = np.where(good, v / ev, np.nan)
            fin = np.isfinite(win)
            total += np.where(fin, win, 0.0).sum(0)
            tot_o += np.where(fin, v, 0.0).sum(0)
            tot_e += np.where(fin, ev, 0.0).sum(0)
            npix += fin.sum(0)
            center[rr] = win[:, f, f]
            if kind == "pair":
                llw = win[:, L - cw:, :cw].reshape(len(rr), -1)
                cnt = np.isfinite(llw).sum(1)
                with np.errstate(invalid="ignore", divide="ignore"):
                    lower_left[rr] = np.where(cnt > 0, np.nansum(llw, 1) / np.maximum(cnt, 1), np.nan)
            used[rr] = True
    with np.errstate(invalid="ignore", divide="ignore"):
        if aggregate == "mean":
            matrix = np.where(npix > 0, total / np.maximum(npix, 1), np.nan)
        else:
            matrix = np.where((npix > 0) & (tot_e > 0), tot_o / np.where(tot_e > 0, tot_e, 1.0), np.nan)
    scores = pileup_scores(matrix, kind=kind, corner=cw)
    feats = t.assign(used=used, center=center)
    if kind == "pair":
        feats = feats.assign(lower_left=lower_left)
    result = {"matrix": matrix, "n_pixels": npix, "n": int(used.sum()), "n_dropped": int(len(t) - used.sum()),
              "kind": kind, "resolution": binsize, "flank_bins": int(f), "corner": int(cw),
              "expected": bool(expected is not False), **{k: v for k, v in scores.items()},
              "features": feats}
    if key_added is None or not _is_chromdata(cd):
        return result
    target = cd.copy() if copy else cd
    params = {"flank": flank, "expected": "table" if isinstance(expected, pd.DataFrame) else bool(expected),
              "balance": balance, "min_separation": min_separation, "max_separation": max_separation,
              "corner": corner, "ignore_diags": ignore_diags, "aggregate": aggregate}
    target.results.set(key_added, result, kind="mapping", function="uchrom.fea.pileup", params=params,
                       inputs={"contacts": str(contacts) if contacts is not None else None, "resolution": binsize,
                               "features": features if isinstance(features, str) else f"{len(t)} features",
                               "chrom": chrom})
    return target if copy else result
