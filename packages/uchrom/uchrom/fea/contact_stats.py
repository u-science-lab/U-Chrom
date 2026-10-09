"""Global 3-D genome features of every cell from its contacts: the share of short- and long-range cis contacts
and their ratio, the slope of the contact-decay curve P(s), the cis fraction and the share of each chromosome's
contacts that are trans — from the contact-distance histograms of :class:`uchrom.io.ContactStats` stored on the
object (``cd.cellm["<key>.distance"]``, ``cd.uns["contact_stats"][key]``).

The short / long-range ratio is that of Guo et al. 2026 by default: contacts closer than 5 kb are left out,
short = 200 kb - 2 Mb and long = 20 - 50 Mb as fractions of the remaining cis contacts (scHiCluster's bins
51-76 and 103-114, :meth:`ContactFeatureParams.guo2026`).  A bin counts in a range when its centre (geometric
mean of its edges) lies inside; ``guo2026()`` gives the exact bins of the paper.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..convention import UNSET

__all__ = ["ContactFeatureParams", "contact_features"]


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
        The chromosomes counted (default: all of the histograms).
    """

    min_distance: float = 5_000.0
    short: Tuple[float, float] = (2.0e5, 2.0e6)
    long: Tuple[float, float] = (2.0e7, 5.0e7)
    short_bins: Optional[Tuple[int, int]] = None
    long_bins: Optional[Tuple[int, int]] = None
    bands: Sequence[Tuple[float, float]] = ((2.0e6, 1.2e7),)
    slopes: Sequence[Tuple[float, float]] = ((1.0e5, 1.0e6), (1.0e6, 1.0e7))
    chroms: Optional[Sequence[str]] = None

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
    use = np.arange(len(chroms)) if p.chroms is None else np.array([chroms.index(c) for c in p.chroms])
    if dist.ndim == 2:                                            # stored summed over the chromosomes
        if p.chroms is not None:
            raise ValueError(f"the histograms {key!r} are summed over the chromosomes: params.chroms is not available")
        h = dist[rows].astype(float)
    else:
        h = dist[rows][:, use].sum(axis=1).astype(float)         # cells x (n_edges + 1)
    # real bins 1..m: [edges[k-1], edges[k]); centre = geometric mean
    lo_e, hi_e = edges[:-1], edges[1:]
    centre = np.sqrt(lo_e * hi_e)
    real = h[:, 1:-1]
    keep = lo_e >= p.min_distance
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

    out = pd.DataFrame(index=ids[rows])
    n_cis = h.sum(axis=1)
    out["n_cis"] = n_cis
    out["n_trans"] = trans[rows].sum(axis=1) // 2
    with np.errstate(divide="ignore", invalid="ignore"):
        out["cis_fraction"] = n_cis / (n_cis + out["n_trans"].to_numpy())
    out["n_used"] = n_used
    out["frac_short"] = frac(*p.short, bins=p.short_bins)
    out["frac_long"] = frac(*p.long, bins=p.long_bins)
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
    cis_per = (np.asarray(cd.cellm[f"{key}.cis"])[rows] if f"{key}.cis" in cd.cellm
               else dist[rows].sum(axis=2))
    legs_cis = 2 * cis_per                                        # each cis contact: two legs on its chromosome
    with np.errstate(divide="ignore", invalid="ignore"):
        share = trans[rows] / (trans[rows] + legs_cis)
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
