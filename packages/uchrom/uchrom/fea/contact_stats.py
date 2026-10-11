"""Global 3-D genome features of every cell from its contacts: the share of short- and long-range cis contacts
and their ratio, the slope of the contact-decay curve P(s), the cis fraction and the share of each chromosome's
contacts that are trans — from the contact-distance histograms of :class:`uchrom.io.ContactStats` stored on the
object (``cd.cellm["<key>.distance"]``, ``cd.uns["contact_stats"][key]``).

The short / long-range ratio is that of Guo et al. 2026 by default: contacts closer than 5 kb are left out,
short = 200 kb - 2 Mb and long = 20 - 50 Mb as fractions of the remaining cis contacts (scHiCluster's bins
51-76 and 103-114, :meth:`ContactFeatureParams.guo2026`).  A bin counts in a range when its centre (geometric
mean of its edges) lies inside; ``guo2026()`` gives the exact bins of the paper.

Pooled over the chromosomes (the default, as the papers compute them), the features also depend on which
chromosomes the contacts come from: long-range contacts exist only on long chromosomes, and the cis fraction on
how many chromosomes there are.  In an aneuploid tissue (a tumour's clones) a gain of small chromosomes raises a
cell's short / long ratio without any change of folding.  ``per_chromosome=True`` computes every feature on each
chromosome's own histogram and averages them over a fixed set of chromosomes with equal weights, so a gain or loss
of whole chromosomes leaves them unchanged (a gain of part of a chromosome still shifts that chromosome's
distances).

:func:`chromosome_dosage` reads the same statistics as a copy-number profile: each chromosome's share of a cell's
contact legs, relative to the cells' median share.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..convention import UNSET

__all__ = ["ContactFeatureParams", "chromosome_dosage", "contact_features"]


@dataclass
class ContactFeatureParams:
    """Ranges (bp) of the contact features.

    Attributes
    ----------
    min_distance
        Cis contacts closer than this are left out of every fraction (undigested / self-ligated fragments).
    short, long
        The short- and long-range ranges of ``short_long_ratio``; ``short_bins`` / ``long_bins`` (half-open
        index ranges into the histogram's distance bins, scHiCluster numbering) override them.
    bands
        More ranges reported as fractions of the cis contacts (``frac_<lo>_<hi>``), e.g. the mitotic band
        2-12 Mb of Nagano et al. 2017.
    slopes
        Ranges over which the slope of log10 P(s) on log10 s is fitted (contacts per bp of distance).
    chroms
        The chromosomes counted (default: all of the histograms; with ``per_chromosome``, those whose pooled
        histogram over all cells has at least half the genome-wide share of long-range contacts -- the
        chromosomes long enough for the long range).
    per_chromosome
        Each feature computed per chromosome and averaged over ``chroms`` with equal weights (needs the
        histograms per chromosome, ``ContactStats.write(per_chromosome=True)``); ``n_cis`` / ``n_trans`` /
        ``n_used`` stay totals and ``trans_share.<chrom>`` per chromosome.
    """

    min_distance: float = 5_000.0
    short: Tuple[float, float] = (2.0e5, 2.0e6)
    long: Tuple[float, float] = (2.0e7, 5.0e7)
    short_bins: Optional[Tuple[int, int]] = None
    long_bins: Optional[Tuple[int, int]] = None
    bands: Sequence[Tuple[float, float]] = ((2.0e6, 1.2e7),)
    slopes: Sequence[Tuple[float, float]] = ((1.0e5, 1.0e6), (1.0e6, 1.0e7))
    chroms: Optional[Sequence[str]] = None
    per_chromosome: bool = False

    @classmethod
    def guo2026(cls, **kw) -> "ContactFeatureParams":
        """The short / long ranges of Guo et al. 2026 (``Spatial-Hi-C-RNA``, MouseBrain/02_short_long_contact_ratio):
        scHiCluster bins 51-76 (207 kb - 1.97 Mb) and 103-114 (18.8 - 53.1 Mb), contacts < 5 kb removed."""
        return cls(short_bins=(51, 77), long_bins=(103, 115), **kw)


def _label(lo: float, hi: float) -> str:
    def f(v):
        return f"{v / 1e6:g}M" if v >= 1e6 else f"{v / 1e3:g}k"
    return f"{f(lo)}_{f(hi)}"


def contact_features(cd, *, key: str = "contacts", cells=None, params: Optional[ContactFeatureParams] = None,
                     key_added=UNSET, copy: bool = False):
    """Per-cell contact features from the stored contact-distance histograms.

    Parameters
    ----------
    cd
        A ``ChromData`` with ``ContactStats.write(cd, key=key)``.
    key
        The histograms' key.
    cells
        Only these cells (default all).
    params
        :class:`ContactFeatureParams` (default: Guo et al. 2026's ranges by bin centre).
    key_added
        Prefix of the ``cd.cells`` columns written (default ``key``; None: nothing written) — e.g.
        ``contacts.short_long_ratio``; the table is also ``cd.results["<key_added>.features"]``.

    Returns
    -------
    DataFrame
        Indexed by cell id: ``n_cis`` (all distances), ``n_trans``, ``cis_fraction``, ``n_used`` (cis at
        >= ``min_distance``), ``frac_short``, ``frac_long``, ``short_long_ratio``, ``frac_<band>``,
        ``ps_slope_<range>``, ``trans_share.<chrom>`` (each chromosome's trans legs over all its legs).
    """
    from ..convention import store_and_return

    p = params or ContactFeatureParams()
    rec = cd.uns.get("contact_stats", {}).get(key)
    if rec is None or f"{key}.distance" not in cd.cellm:
        raise KeyError(f"no contact statistics {key!r}: run ContactStats.write(cd, key={key!r}) first")
    edges = np.asarray(rec["edges"], float)
    chroms = list(rec["chroms"])
    ids = pd.Index([str(c) for c in cd._cell_ids_axis()], name="cell_id")
    dist = np.asarray(cd.cellm[f"{key}.distance"])
    trans = np.asarray(cd.cellm[f"{key}.trans"])
    rows = np.arange(len(ids))
    if cells is not None:
        rows = ids.get_indexer([str(c) for c in cells])
        if (rows < 0).any():
            raise KeyError("cells not in cd.cells")
    if dist.ndim == 2 and (p.chroms is not None or p.per_chromosome):  # stored summed over the chromosomes
        raise ValueError(f"the histograms {key!r} are summed over the chromosomes: params.chroms / per_chromosome "
                         "need them per chromosome (ContactStats.write(per_chromosome=True))")
    lo_e, hi_e = edges[:-1], edges[1:]
    centre = np.sqrt(lo_e * hi_e)                                 # real bins 1..m: [edges[k-1], edges[k])
    keep = lo_e >= p.min_distance
    trans_rows = trans[rows]
    cis_per = (np.asarray(cd.cellm[f"{key}.cis"])[rows] if f"{key}.cis" in cd.cellm
               else dist[rows].sum(axis=2))
    out = pd.DataFrame(index=ids[rows])
    if dist.ndim == 2:
        h = dist[rows].astype(float)
        feats = _features(h, centre, lo_e, hi_e, keep, p)
    else:
        if p.chroms is not None:
            use = [chroms.index(c) for c in p.chroms]
        elif p.per_chromosome:
            use = _long_enough(dist[rows], centre, keep, p)
        else:
            use = list(range(len(chroms)))
        h = dist[rows][:, use].sum(axis=1).astype(float)          # cells x (n_edges + 1)
        feats = _features(h, centre, lo_e, hi_e, keep, p)
        if p.per_chromosome:
            per = [_features(dist[rows][:, i].astype(float), centre, lo_e, hi_e, keep, p) for i in use]
            for k in feats:
                if k in ("n_used",):
                    continue
                with np.errstate(invalid="ignore"):
                    feats[k] = np.nanmean(np.column_stack([f[k] for f in per]), axis=1)
            legs = 2 * cis_per[:, use]
            with np.errstate(divide="ignore", invalid="ignore"):
                cf = legs / (legs + trans_rows[:, use])           # each chromosome's legs that are cis
            out_cis = np.nanmean(cf, axis=1)
    n_cis = h.sum(axis=1)
    out["n_cis"] = n_cis
    out["n_trans"] = trans_rows.sum(axis=1) // 2
    with np.errstate(divide="ignore", invalid="ignore"):
        out["cis_fraction"] = n_cis / (n_cis + out["n_trans"].to_numpy())
    if p.per_chromosome:
        out["cis_fraction"] = out_cis
    for k, v in feats.items():
        out[k] = v
    if p.per_chromosome:
        out.attrs["chroms"] = [chroms[i] for i in use]
    legs_cis = 2 * cis_per                                        # each cis contact: two legs on its chromosome
    with np.errstate(divide="ignore", invalid="ignore"):
        share = trans_rows / (trans_rows + legs_cis)
    for i, c in enumerate(chroms):
        out[f"trans_share.{c}"] = share[:, i]
    if key_added is UNSET:
        key_added = key
    if key_added is None:
        return out
    target = cd.copy() if copy else cd
    cells_df = target.cells.copy()
    pos = pd.Index([str(c) for c in target._cell_ids_axis()]).get_indexer(out.index)
    for col in out.columns:
        values = np.full(len(cells_df), np.nan)
        values[pos] = out[col].to_numpy(float)
        cells_df[f"{key_added}.{col}"] = values
    target.cells = cells_df
    store_and_return(target, out.reset_index(), key_added=f"{key_added}.features", copy=False, kind="table",
                     function="uchrom.fea.contact_features", params=asdict(p),
                     inputs={"contact_stats": key, "n_cells": int(len(out)), "source": rec.get("source"),
                             "filter": rec.get("filter")})
    return target if copy else out


def chromosome_dosage(cd, *, key: str = "contacts", cells=None, groupby: Optional[str] = None,
                      exclude: Sequence[str] = ("chrY",), n_pcs: int = 0, key_added=UNSET, copy: bool = False):
    """Per-cell copy-number profile from the contacts: log2 of each chromosome's share of the cell's contact legs
    over the cells' median share.

    A cis contact puts two legs on its chromosome, a trans contact one on each of its two.  A chromosome present in
    three copies instead of two carries about 1.5 times the legs, so the log2 share over the median is about the
    log2 of its copies over the typical cell's: a coverage profile at the resolution of whole chromosomes, as a
    copy-number caller reads from sequencing depth.  It is a proxy.  It is relative to the median cell, so a gain
    that every cell carries does not show.  The shares sum to one, so a gain lowers the other chromosomes a little.
    And anything else that changes how many contacts a chromosome gives shifts it too.

    Parameters
    ----------
    cd
        A ``ChromData`` with ``ContactStats.write(cd, key=key)``.
    key
        The contact statistics' key.
    cells
        Only these cells (default all); the median is taken over them.
    groupby
        A ``cd.cells`` column (section, sample): the median of each group is its cells' reference.
    exclude
        Chromosomes left out of the shares (default chrY: a few contacts or none).
    n_pcs
        Also the first ``n_pcs`` principal components of the profiles (each chromosome z-scored over the cells,
        missing values at 0; signs arbitrary): the axes along which the cells' profiles differ most.  A tumour clone
        changes several chromosomes at once, so one component can carry its whole pattern; as covariates they
        stand for copy number in a spatial test (:func:`uchrom.spatial.spatially_variable`).
    key_added
        Where to store (default ``"<key>.dosage"``; None: nothing stored): ``cd.cellm[key_added]`` (n_cells,
        n_chroms; NaN for cells left out), ``cd.cellm["<key_added>.pcs"]`` and the table
        ``cd.results[key_added]``.

    Returns
    -------
    DataFrame
        Indexed by cell id (in the order of ``cells``): one column per chromosome, then ``PC1`` ... with
        ``n_pcs``.  A cell without contacts, or a chromosome without legs in a cell, is NaN.
        ``attrs["pc_variance"]``: the share of the z-scored profiles' variance of each component.
    """
    from ..convention import store_and_return

    rec = cd.uns.get("contact_stats", {}).get(key)
    if rec is None or f"{key}.trans" not in cd.cellm:
        raise KeyError(f"no contact statistics {key!r}: run ContactStats.write(cd, key={key!r}) first")
    chroms = list(rec["chroms"])
    ids = pd.Index([str(c) for c in cd._cell_ids_axis()], name="cell_id")
    rows = np.arange(len(ids))
    if cells is not None:
        rows = ids.get_indexer([str(c) for c in cells])
        if (rows < 0).any():
            raise KeyError("cells not in cd.cells")
    if f"{key}.cis" in cd.cellm:
        cis = np.asarray(cd.cellm[f"{key}.cis"])[rows]
    else:
        dist = np.asarray(cd.cellm[f"{key}.distance"])
        if dist.ndim != 3:
            raise ValueError(f"the statistics {key!r} have no cis counts per chromosome")
        cis = dist[rows].sum(axis=2)
    use = [i for i, c in enumerate(chroms) if c not in set(exclude)]
    legs = (2 * cis + np.asarray(cd.cellm[f"{key}.trans"])[rows])[:, use].astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        share = legs / legs.sum(axis=1, keepdims=True)           # NaN for a cell without legs
    groups = (np.zeros(len(rows), int) if groupby is None
              else pd.factorize(cd.cells[groupby].to_numpy()[rows])[0])
    prof = np.full_like(share, np.nan)
    for gi in np.unique(groups[groups >= 0]):                    # a cell without a group stays NaN
        m = groups == gi
        if np.isfinite(share[m]).any():
            with np.errstate(divide="ignore", invalid="ignore"):
                prof[m] = np.log2(share[m] / np.nanmedian(share[m], axis=0))
    prof[~np.isfinite(prof)] = np.nan
    out = pd.DataFrame(prof, index=ids[rows], columns=[chroms[i] for i in use])
    pc_var = []
    if n_pcs:
        with np.errstate(divide="ignore", invalid="ignore"):
            Z = (prof - np.nanmean(prof, axis=0)) / np.nanstd(prof, axis=0, ddof=1)
        Z[~np.isfinite(Z)] = 0.0
        u, sv, _ = np.linalg.svd(Z, full_matrices=False)
        k = min(n_pcs, len(sv))
        for j in range(k):
            out[f"PC{j + 1}"] = u[:, j] * sv[j]
        pc_var = (sv ** 2 / max((sv ** 2).sum(), 1e-300))[:k].tolist()
    out.attrs["pc_variance"] = pc_var
    if key_added is UNSET:
        key_added = f"{key}.dosage"
    if key_added is None:
        return out
    target = cd.copy() if copy else cd

    def on_cells(values: np.ndarray) -> np.ndarray:
        arr = np.full((len(ids), values.shape[1]), np.nan)
        arr[rows] = values
        return arr

    target.cellm[key_added] = on_cells(prof)
    if n_pcs:
        target.cellm[f"{key_added}.pcs"] = on_cells(out[[f"PC{j + 1}" for j in range(len(pc_var))]].to_numpy())
    store_and_return(target, out.reset_index(), key_added=key_added, copy=False, kind="table",
                     function="uchrom.fea.chromosome_dosage",
                     params={"exclude": list(exclude), "groupby": groupby, "n_pcs": int(n_pcs)},
                     inputs={"contact_stats": key, "chroms": list(out.columns[:len(use)]), "n_cells": int(len(out)),
                             "pc_variance": pc_var, "source": rec.get("source"), "filter": rec.get("filter")})
    return target if copy else out


def _features(h: np.ndarray, centre, lo_e, hi_e, keep, p: ContactFeatureParams) -> dict:
    """The distance features of histograms h (cells x (n_edges + 1)): n_used, the fractions, the ratio, the bands,
    the slopes."""
    real = h[:, 1:-1]
    n_used = real[:, keep].sum(axis=1)

    def frac(lo, hi, bins=None):
        if bins is not None:
            sel = np.zeros(len(centre), bool)
            sel[bins[0]:bins[1]] = True
        else:
            sel = (centre >= lo) & (centre < hi)
        sel &= keep
        with np.errstate(divide="ignore", invalid="ignore"):
            return real[:, sel].sum(axis=1) / n_used

    out = {"n_used": n_used, "frac_short": frac(*p.short, bins=p.short_bins),
           "frac_long": frac(*p.long, bins=p.long_bins)}
    with np.errstate(divide="ignore", invalid="ignore"):
        out["short_long_ratio"] = out["frac_short"] / out["frac_long"]
    for lo, hi in p.bands:
        out[f"frac_{_label(lo, hi)}"] = frac(lo, hi)
    width = hi_e - lo_e
    for lo, hi in p.slopes:
        sel = (centre >= lo) & (centre < hi) & keep
        x = np.log10(centre[sel])
        with np.errstate(divide="ignore", invalid="ignore"):
            yv = np.log10(real[:, sel] / width[sel])
        out[f"ps_slope_{_label(lo, hi)}"] = _slopes(x, yv)
    return out


def _long_enough(dist: np.ndarray, centre, keep, p: ContactFeatureParams) -> list:
    """The chromosomes whose histogram summed over all cells has at least half the genome-wide share of
    long-range contacts (the long range fits on them)."""
    pooled = dist.sum(axis=0)[:, 1:-1].astype(float)              # chroms x bins
    if p.long_bins is not None:
        sel = np.zeros(len(centre), bool)
        sel[p.long_bins[0]:p.long_bins[1]] = True
    else:
        sel = (centre >= p.long[0]) & (centre < p.long[1])
    sel &= keep
    used = pooled[:, keep].sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        share = pooled[:, sel].sum(axis=1) / used
    genome = pooled[:, sel].sum() / max(pooled[:, keep].sum(), 1)
    return [i for i in range(len(share)) if np.isfinite(share[i]) and share[i] >= 0.5 * genome]


def _slopes(x: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Least-squares slope of each row of Y on x, over the finite values (NaN with fewer than 3)."""
    out = np.full(Y.shape[0], np.nan)
    ok = np.isfinite(Y)
    for i in range(Y.shape[0]):
        m = ok[i]
        if m.sum() >= 3:
            xm = x[m] - x[m].mean()
            out[i] = (xm * (Y[i, m] - Y[i, m].mean())).sum() / (xm ** 2).sum()
    return out
