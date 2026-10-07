"""Comparing 3-D structures: with each other, with imaging, with the contacts they come from.

A few ideas cover the usual checks of a reconstruction:

* **one set of loci onto another's bins** — :func:`bin_index` (the bin that holds a position),
  :func:`rebin_coords` (a structure's or a tracing experiment's coordinates averaged onto other bins, per
  trace / cell), :func:`match_spots` (the same spots in two objects);
* **an ensemble's spread** — :func:`kabsch_rmsd` (RMSD after optimal superposition), :func:`ensemble_models`,
  :func:`ensemble_agreement`;
* **distance matrices on shared bins** — :func:`distance_correlation` (two coordinate sets, per chromosome),
  :func:`compare_structures` (models against models, e.g. a reconstruction against published structures),
  :func:`compare_distances` (population statistics, e.g. a consensus structure or a population against the
  median distances of chromatin tracing);
* **the contacts** — :func:`contact_agreement` (a structure's distances against a linked Hi-C map, raw and
  observed / expected), :func:`contact_distances` (the distance between the two ends of every contact).

Bins are genomic intervals ``[start, end)``.  NucDynamics / EMber particles are ``(start, end]`` (the
particle at position ``p`` holds the contacts in ``(p - size, p]``); a reconstruction records this in
``uns[...]["particle_position"] == "end"``, and ``closed=None`` follows it.
"""

from __future__ import annotations

import itertools
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

__all__ = [
    "Comparison",
    "kabsch_rmsd",
    "distance_correlation",
    "ensemble_models",
    "ensemble_agreement",
    "bin_index",
    "rebin_coords",
    "match_spots",
    "compare_distances",
    "compare_structures",
    "contact_agreement",
    "contact_distances",
]


class Comparison(dict):
    """Result of a comparison: a dict with attribute access; :attr:`scores` holds its scalar entries (for
    a table), the other entries are arrays / tables (matrices, the shared bins)."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    @property
    def scores(self) -> Dict[str, float]:
        return {k: v for k, v in self.items() if np.isscalar(v)}


# --------------------------------------------------------------------------- superposition, ensembles

def kabsch_rmsd(a, b, *, reflection: bool = False) -> float:
    """Root-mean-square deviation of two coordinate sets of the same points after optimal superposition
    (translation + rotation, Kabsch 1976).

    Parameters
    ----------
    a, b
        (n, 3) coordinates, row ``i`` the same point in both; rows with a NaN in either are left out.
    reflection
        Allow the mirror image as well (an improper rotation) — for structures computed from contacts, which
        a structure and its mirror image satisfy equally.

    Returns
    -------
    RMSD in the units of the coordinates.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.shape != b.shape or a.ndim != 2:
        raise ValueError(f"two (n, 3) arrays of the same shape, not {a.shape} and {b.shape}")
    ok = np.isfinite(a).all(1) & np.isfinite(b).all(1)
    a, b = a[ok], b[ok]
    if not len(a):
        return float("nan")
    a = a - a.mean(0)
    b = b - b.mean(0)
    u, _, vt = np.linalg.svd(a.T @ b)
    if reflection:
        signs = (1.0, -1.0)
    else:
        signs = (float(np.sign(np.linalg.det(u @ vt))) or 1.0,)
    return min(float(np.sqrt((((a @ (u @ np.diag([1.0, 1.0, d]) @ vt)) - b) ** 2).sum(1).mean()))
               for d in signs)


def distance_correlation(a, b, *, groups=None, min_size: int = 10) -> float:
    """Pearson correlation of the pairwise distances of two coordinate sets of the same points — the median
    over groups (e.g. chromosomes) of the correlation within each group.

    Parameters
    ----------
    a, b
        (n, 3) coordinates, row ``i`` the same point in both.
    groups
        A label per row (e.g. the chromosome); ``None``: one group.  Only distances within a group count.
    min_size
        Groups with fewer points are left out.

    Returns
    -------
    The median correlation (NaN when no group is large enough).
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    labels = np.zeros(len(a), dtype=np.int64) if groups is None else np.asarray(groups)
    rs = []
    for g in np.unique(labels):
        i = np.flatnonzero(labels == g)
        if len(i) < min_size:
            continue
        iu = np.triu_indices(len(i), 1)
        da = np.linalg.norm(a[i, None] - a[None, i], axis=-1)[iu]
        db = np.linalg.norm(b[i, None] - b[None, i], axis=-1)[iu]
        ok = np.isfinite(da) & np.isfinite(db)
        rs.append(np.corrcoef(da[ok], db[ok])[0, 1])
    return float(np.median(rs)) if rs else float("nan")


def _model_number(name: str) -> Optional[int]:
    head, _, tail = str(name).rpartition("_")
    return int(tail) if head == "model" and tail.isdigit() else None


def ensemble_models(cd) -> List[np.ndarray]:
    """The models of a structure ensemble, each (n_spots, 3) in spot order: the layers ``model_<k>`` in the
    order of ``k``, preceded by ``coords`` unless it is one of them (a reconstruction keeps model 0 in
    ``coords`` and every model as a layer; a published ensemble may keep model 1 in ``coords`` and models
    2-10 as layers).  Without such layers: ``[coords]``."""
    coords = np.asarray(cd.coords, dtype=np.float64)
    names = sorted((n for n in cd.layers if _model_number(n) is not None), key=_model_number)
    models = [np.asarray(cd.layers[n], dtype=np.float64) for n in names]
    if not any(np.array_equal(coords, m, equal_nan=True) for m in models):
        models.insert(0, coords)
    return models


def ensemble_agreement(cd, *, n_by_chrom: Optional[int] = 4, min_particles: int = 10,
                       reflection: bool = False) -> Comparison:
    """How much the models of an ensemble (:func:`ensemble_models`) agree.

    Parameters
    ----------
    cd
        One structure ensemble (e.g. ``reconstruct_nucdyn`` / ``reconstruct_ember`` output, or one cell of
        published structures).
    n_by_chrom
        The per-chromosome measures use the pairs of the first ``n_by_chrom`` models (``None``: all; each
        pair costs a distance matrix per chromosome).
    min_particles
        Chromosomes (traces) with fewer particles are left out of the per-chromosome measures.
    reflection
        Allow mirror images in the superposition (see :func:`kabsch_rmsd`).

    Returns
    -------
    Comparison
        ``rmsd`` (n_models x n_models, genome-wide RMSD after superposition), ``rmsd_mean`` (mean over the
        pairs), ``rmsd_per_chrom`` (median over model pairs and chromosomes of the RMSD of one chromosome
        superposed alone), ``distance_r`` (median over model pairs of :func:`distance_correlation` by
        chromosome), ``n_models``.  Per chromosome means per trace (a chromosome copy).
    """
    models = ensemble_models(cd)
    n = len(models)
    rmsd = np.zeros((n, n))
    for i, j in itertools.combinations(range(n), 2):
        rmsd[i, j] = rmsd[j, i] = kabsch_rmsd(models[i], models[j], reflection=reflection)
    groups = cd.spots["trace_id"].astype(str).to_numpy()
    sub = n if n_by_chrom is None else min(int(n_by_chrom), n)
    pairs = list(itertools.combinations(range(sub), 2))
    r = [distance_correlation(models[i], models[j], groups=groups, min_size=min_particles) for i, j in pairs]
    big = [g for g in np.unique(groups) if (groups == g).sum() >= min_particles]
    per = [kabsch_rmsd(models[i][groups == g], models[j][groups == g], reflection=reflection)
           for i, j in pairs for g in big]
    iu = np.triu_indices(n, 1)
    return Comparison(rmsd_mean=float(rmsd[iu].mean()) if n > 1 else float("nan"),
                      rmsd_per_chrom=float(np.median(per)) if per else float("nan"),
                      distance_r=float(np.median(r)) if r else float("nan"),
                      n_models=n, rmsd=rmsd)


# --------------------------------------------------------------------------- loci onto other bins

def _closed_for(cd, closed: Optional[str]) -> str:
    """``closed`` or, for ``None``, the particle convention a reconstruction recorded (``"left"`` for anything
    else, e.g. a table of bins)."""
    if closed is not None:
        if closed not in ("left", "right"):
            raise ValueError("closed must be 'left' ([start, end)) or 'right' ((start, end])")
        return closed
    for value in (getattr(cd, "uns", None) or {}).values():
        if isinstance(value, dict) and value.get("particle_position") == "end":
            return "right"
    return "left"


def _bins_frame(bins) -> pd.DataFrame:
    if hasattr(bins, "spots_with_loci"):          # a ChromData: its bins
        bins = bins.bins
    b = pd.DataFrame({"chrom": np.asarray(bins["chrom"]).astype(str),
                      "start": np.asarray(bins["start"], dtype=np.int64),
                      "end": np.asarray(bins["end"], dtype=np.int64)})
    return b


def bin_index(bins, chrom, pos, *, closed: str = "left") -> np.ndarray:
    """The row of ``bins`` (0 .. len(bins) - 1) whose interval holds each position; -1 when none does.

    Parameters
    ----------
    bins
        A table with ``chrom``, ``start``, ``end`` (or a ``ChromData``: its ``bins``); intervals of one
        chromosome must not overlap; gaps are allowed.
    chrom, pos
        A chromosome and a position (bp) per query (arrays of the same length, or a scalar chromosome).
    closed
        ``"left"``: ``[start, end)`` (genomic bins); ``"right"``: ``(start, end]`` (NucDynamics particles).
    """
    b = _bins_frame(bins)
    pos = np.asarray(pos, dtype=np.int64)
    chrom = np.full(len(pos), str(chrom), dtype=object) if np.isscalar(chrom) else np.asarray(chrom).astype(str)
    if closed not in ("left", "right"):
        raise ValueError("closed must be 'left' or 'right'")
    out = np.full(len(pos), -1, dtype=np.int64)
    bchrom = b["chrom"].to_numpy()
    for c in np.unique(chrom):
        rows = np.flatnonzero(bchrom == c)
        if not len(rows):
            continue
        rows = rows[np.argsort(b["start"].to_numpy()[rows], kind="stable")]
        starts, ends = b["start"].to_numpy()[rows], b["end"].to_numpy()[rows]
        q = np.flatnonzero(chrom == c)
        p = pos[q]
        if closed == "left":
            k = np.searchsorted(starts, p, side="right") - 1
            ok = k >= 0
            ok[ok] &= p[ok] < ends[k[ok]]
        else:
            k = np.searchsorted(ends, p, side="left")
            ok = k < len(rows)
            ok[ok] &= starts[k[ok]] < p[ok]
        out[q[ok]] = rows[k[ok]]
    return out


def _spot_positions(cd, position: str) -> Tuple[np.ndarray, np.ndarray]:
    loci = cd.spots_with_loci()
    start, end = loci["start"].to_numpy(np.int64), loci["end"].to_numpy(np.int64)
    if position == "mid":
        p = (start + end) // 2
    elif position == "start":
        p = start
    elif position == "end":
        p = end
    else:
        raise ValueError("position must be 'mid', 'start' or 'end'")
    return loci["chrom"].astype(str).to_numpy(), p


def rebin_coords(cd, bins, *, by: Optional[str] = "trace", position: str = "mid", closed: Optional[str] = None,
                 layer: Optional[str] = None) -> Tuple[np.ndarray, np.ndarray]:
    """The coordinates of ``cd`` averaged onto other bins, one row per trace (or cell).

    Every spot goes to the bin of ``bins`` that holds its ``position`` (the midpoint, start or end of its
    locus); the spots of one trace in one bin are averaged.

    Parameters
    ----------
    cd
        Spots with coordinates (chromatin tracing, a structure, a population).
    bins
        Target bins (``chrom``, ``start``, ``end``; or a ``ChromData``: its bins).
    by
        ``"trace"``, ``"cell"`` or ``None`` (all spots together).
    position
        ``"mid"`` (default), ``"start"`` or ``"end"`` of a spot's locus.
    closed
        Target intervals ``"left"`` = ``[start, end)``, ``"right"`` = ``(start, end]``; ``None``: ``"left"``
        unless ``bins`` is a reconstruction with NucDynamics particles.
    layer
        Use this layer instead of ``coords``.

    Returns
    -------
    cube : ndarray (n_groups, len(bins), 3)
        NaN where a group has no spot in a bin.
    groups : ndarray
        The trace (cell) id of every row (order of first appearance).
    """
    target = _bins_frame(bins)
    closed = _closed_for(bins, closed)
    chrom, p = _spot_positions(cd, position)
    idx = bin_index(target, chrom, p, closed=closed)
    xyz = np.asarray(cd.coords if layer is None else cd.layers[layer], dtype=np.float64)
    if by is None:
        codes, groups = np.zeros(len(idx), dtype=np.int64), np.array(["all"], dtype=object)
    else:
        col = {"trace": "trace_id", "cell": "cell_id"}.get(by, by)
        codes, groups = pd.factorize(cd.spots[col].astype(str).to_numpy())
    ok = (idx >= 0) & np.isfinite(xyz).all(1)
    nb = len(target)
    key = codes[ok] * nb + idx[ok]
    size = len(groups) * nb
    n = np.bincount(key, minlength=size).astype(np.float64)
    cube = np.full((size, 3), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        for a in range(3):
            cube[:, a] = np.bincount(key, weights=xyz[ok, a], minlength=size) / n
    return cube.reshape(len(groups), nb, 3), np.asarray(groups)


def match_spots(a, b, on=None) -> Tuple[np.ndarray, np.ndarray]:
    """Rows of the same spots in two objects (e.g. before and after a round trip through a store, which
    sorts the spots).

    Parameters
    ----------
    a, b
        ``ChromData`` objects.
    on
        Spot column(s) that identify a spot; default ``"spot_id"`` when both have it, else the cell, trace
        and locus (``cell_id``, ``trace_id``, ``chrom``, ``start``, ``end``, those present in both).

    Returns
    -------
    (ia, ib)
        Row positions such that ``a`` row ``ia[k]`` and ``b`` row ``ib[k]`` are the same spot, sorted by the
        key; spots of only one object are left out.
    """
    la, lb = a.spots_with_loci(), b.spots_with_loci()
    if on is None:
        if "spot_id" in la.columns and "spot_id" in lb.columns:
            on = ["spot_id"]
        else:
            on = [c for c in ("cell_id", "trace_id", "chrom", "start", "end") if c in la.columns and c in lb.columns]
    on = [on] if isinstance(on, str) else list(on)

    def keyed(loci, name):
        df = pd.DataFrame({c: (loci[c].astype(str) if isinstance(loci[c].dtype, pd.CategoricalDtype)
                               else loci[c]).to_numpy() for c in on})
        if df.duplicated().any():
            raise ValueError(f"{on} does not identify the spots of {name} (duplicates)")
        return df.assign(**{f"_row_{name}": np.arange(len(df))})

    m = keyed(la, "a").merge(keyed(lb, "b"), on=on, how="inner").sort_values(on, kind="stable")
    return m["_row_a"].to_numpy(), m["_row_b"].to_numpy()


# --------------------------------------------------------------------------- distance matrices

def _pairwise_stat(cube: np.ndarray, stat: str, budget: int = 10_000_000) -> np.ndarray:
    """Per-group pairwise distances of a (groups, bins, 3) cube reduced over the groups."""
    n = cube.shape[1]
    if stat not in ("median", "mean"):
        raise ValueError("stat must be 'median' or 'mean'")
    if cube.shape[0] == 1:
        x = cube[0]
        return np.linalg.norm(x[:, None] - x[None], axis=-1)
    out = np.full((n, n), np.nan)
    rows = max(1, int(budget // max(cube.shape[0] * n * 3, 1)))     # bins per block: ~budget floats
    import warnings

    with warnings.catch_warnings():                       # all-NaN pairs (not observed in any group)
        warnings.simplefilter("ignore", RuntimeWarning)
        for lo in range(0, n, rows):
            d = np.linalg.norm(cube[:, lo:lo + rows, None] - cube[:, None], axis=-1)
            out[lo:lo + rows] = np.nanmedian(d, axis=0) if stat == "median" else np.nanmean(d, axis=0)
    return out


def compare_distances(cd, ref, *, bins=None, stat: str = "median", by: str = "trace", position: str = "mid",
                      closed: Optional[str] = None) -> Comparison:
    """Distance statistics of two objects on shared bins — a structure (or a population of structures)
    against chromatin tracing, typically.

    Both are averaged onto the same bins (:func:`rebin_coords`, per trace), the pairwise distances of every
    trace are reduced to one matrix per object (median over traces; a single structure is its own
    distance matrix), and the two matrices are compared over the bin pairs both observe.

    Parameters
    ----------
    cd
        The model: a structure, a population (one trace per chromosome copy), or any traced data.
    ref
        The reference, e.g. chromatin tracing (distances in nm).
    bins
        The shared grid (default: the bins of ``cd``).
    stat
        ``"median"`` or ``"mean"`` over traces.
    by
        Group spots by ``"trace"`` (default) or ``"cell"``.
    position, closed
        How spots are put onto the grid (see :func:`rebin_coords`).

    Returns
    -------
    Comparison
        ``pearson`` (Pearson r of the two matrices over the shared pairs), ``rel_error`` (mean of
        ``|s * d_cd - d_ref| / d_ref`` after rescaling ``cd`` by the least-squares factor ``s`` of that error,
        GEM-FISH's error measure), ``scale`` (``s``: units of ``ref`` per unit of ``cd``), ``ratio`` (median of
        ``d_cd / d_ref``), ``n_bins``, ``n_pairs``; ``bins`` (the shared bins: rows of the grid, with their
        positions in it as the index), ``model`` and ``reference`` (the two matrices on them).
    """
    from scipy.stats import pearsonr

    target = cd if bins is None else bins
    grid = _bins_frame(target)
    closed = _closed_for(target, closed)
    A, _ = rebin_coords(cd, grid, by=by, position=position, closed=closed)
    B, _ = rebin_coords(ref, grid, by=by, position=position, closed=closed)
    shared = np.flatnonzero(np.isfinite(A).all(-1).any(0) & np.isfinite(B).all(-1).any(0))
    if len(shared) < 2:
        raise ValueError(f"{len(shared)} bin(s) shared by the two objects: nothing to compare")
    Dm = _pairwise_stat(A[:, shared], stat)
    Dr = _pairwise_stat(B[:, shared], stat)
    iu = np.triu_indices(len(shared), 1)
    m, f = Dm[iu], Dr[iu]
    ok = np.isfinite(m) & np.isfinite(f) & (f > 0)
    m, f = m[ok], f[ok]
    q = m / f
    s = float(q.sum() / (q ** 2).sum())
    return Comparison(pearson=float(pearsonr(f, m)[0]), rel_error=float(np.mean(np.abs(s * m - f) / f)),
                      scale=s, ratio=float(np.median(q)), n_bins=int(len(shared)), n_pairs=int(ok.sum()),
                      bins=grid.iloc[shared], model=Dm, reference=Dr)


def compare_structures(cd, ref, *, n_models: Optional[int] = None, ref_models: Optional[int] = None,
                       position: str = "mid", closed: Optional[str] = None, min_particles: int = 10) -> Comparison:
    """Two structure ensembles of one cell compared model by model — e.g. a reconstruction against the
    published structures of the same cell, or two solvers.

    The particles of ``ref`` are averaged onto the particles of ``cd`` (a particle of ``ref`` goes to the
    particle of ``cd`` whose interval holds its ``position``); then, for every model of ``cd`` and every
    model of ``ref``, :func:`distance_correlation` by chromosome over the particles of ``cd`` that received
    one.

    Parameters
    ----------
    cd
        One structure (ensemble) with one particle per bin (haploid; e.g. one cell).
    ref
        The other one (any particles; e.g. ``ds.load("stevens2017_mesc").get_cell("Cell_1")``).
    n_models, ref_models
        Use the first models of each ensemble (:func:`ensemble_models`; ``None``: all).
    position
        The position of a ``ref`` particle: ``"mid"``, ``"start"`` or ``"end"`` of its locus.
    closed
        The intervals of ``cd``'s particles (``None``: as the reconstruction recorded, see the module).
    min_particles
        Chromosomes with fewer matched particles are left out.

    Returns
    -------
    Comparison
        ``distance_r`` (mean over the model pairs of the median correlation by chromosome), ``n_particles``
        (particles of ``cd`` matched), ``r`` (n_models x ref_models).
    """
    if cd.spots["bin_id"].duplicated().any():
        raise ValueError("cd has several spots per bin (cells or chromosome copies): pass one haploid structure")
    loci = cd.spots_with_loci()
    grid = loci[["chrom", "start", "end"]]
    closed = _closed_for(cd, closed)
    ours = ensemble_models(cd)[:n_models]
    theirs = ensemble_models(ref)[:ref_models]
    chrom, p = _spot_positions(ref, position)
    idx = bin_index(grid, chrom, p, closed=closed)
    ok = idx >= 0
    rows = np.unique(idx[ok])
    grp = pd.Index(rows).get_indexer(idx[ok])
    count = np.bincount(grp, minlength=len(rows))[:, None]
    avg = [np.stack([np.bincount(grp, weights=X[ok, a], minlength=len(rows)) for a in range(3)], 1) / count
           for X in theirs]
    groups = loci["chrom"].astype(str).to_numpy()[rows]
    r = np.array([[distance_correlation(m[rows], x, groups=groups, min_size=min_particles) for x in avg]
                  for m in ours])
    return Comparison(distance_r=float(np.mean(r)), n_particles=int(len(rows)), r=r)


# --------------------------------------------------------------------------- contacts

def contact_agreement(cd, hic, *, contacts: Optional[str] = None, chrom=None, resolution: Optional[int] = None,
                      balance: bool = True, max_separation: Optional[float] = None,
                      closed: Optional[str] = None) -> Comparison:
    """How well a structure reproduces a contact map: Spearman correlation of the contact frequency and
    ``1 / distance`` over the bin pairs, raw and after removing the distance decay (both sides divided by
    their mean at each genomic separation — in bins of the map, so bins the structure lacks leave gaps —
    :func:`~uchrom.fea.maps.observed_over_expected`).

    Parameters
    ----------
    cd
        A structure (or a population: median distance over its traces).
    hic
        A ``ChromData`` with the map linked (may be ``cd`` itself), or the path of a ``.cool`` / ``.mcool``.
    contacts
        Key of the linked map (``None``: the only one).
    chrom
        Chromosome(s) (default: those of ``cd``); pairs of different chromosomes are not compared.
    resolution, balance
        The map level (an ``.mcool``) and whether to use balanced values (see
        :func:`~uchrom.fea.maps.contact_matrix`).
    max_separation
        Only pairs at most this far apart (bp, bin starts).
    closed
        How the particles of ``cd`` are put onto the map's bins (by the midpoint of their locus).

    Returns
    -------
    Comparison
        ``spearman`` (pairs with contacts), ``spearman_oe``, ``n_pairs``.
    """
    from scipy.stats import spearmanr

    from .maps import contact_matrix, observed_over_expected

    chroms = [str(c) for c in pd.unique(cd.spots_with_loci()["chrom"].astype(str))] if chrom is None else (
        [chrom] if isinstance(chrom, str) else list(chrom))
    raw_h, raw_d, oe_h, oe_d = [], [], [], []
    for c in chroms:
        mbins, H = contact_matrix(hic, contacts, chrom=c, resolution=resolution, balance=balance)
        cube, _ = rebin_coords(cd, mbins, by="trace", closed="left" if closed is None else closed)
        rows = np.flatnonzero(np.isfinite(cube).all(-1).any(0))
        if len(rows) < 2:
            continue
        D = _pairwise_stat(cube[:, rows], "median")
        Hm = H[np.ix_(rows, rows)]
        starts = mbins["start"].to_numpy(np.float64)[rows]
        iu = np.triu_indices(len(rows), 1)
        sel = np.ones(len(iu[0]), dtype=bool)
        if max_separation is not None:
            sel = np.abs(starts[iu[0]] - starts[iu[1]]) <= max_separation
        h, d = Hm[iu], D[iu]
        ok = sel & (h > 0) & np.isfinite(d) & (d > 0)
        raw_h.append(h[ok])
        raw_d.append(1.0 / d[ok])
        Hoe = observed_over_expected(Hm, positions=rows)[iu]       # separation in bins of the map
        Doe = observed_over_expected(D, positions=rows)[iu]
        ok = sel & np.isfinite(Hoe) & (Hoe > 0) & np.isfinite(Doe)
        oe_h.append(Hoe[ok])
        oe_d.append(1.0 / Doe[ok])
    if not raw_h:
        raise ValueError("the structure has no two bins on the map")
    h, d = np.concatenate(raw_h), np.concatenate(raw_d)
    return Comparison(spearman=float(spearmanr(h, d)[0]),
                      spearman_oe=float(spearmanr(np.concatenate(oe_h), np.concatenate(oe_d))[0]),
                      n_pairs=int(len(h)))


def contact_distances(cd, contacts, *, layer: Optional[str] = None, closed: Optional[str] = None) -> np.ndarray:
    """The distance, in a structure, between the two ends of every contact.

    Each end goes to the particle whose interval holds its position.

    Parameters
    ----------
    cd
        One structure with one particle per bin (haploid; e.g. ``reconstruct_ember`` output).
    contacts
        A table / dict with ``chrom_a``, ``pos_a``, ``chrom_b``, ``pos_b`` (e.g.
        ``uchrom.recon.sc.nucdyn.load_contacts(path)``).
    layer
        A model layer instead of ``coords`` (model 0).
    closed
        The particles' intervals (``None``: as the reconstruction recorded; NucDynamics: ``(start, end]``).

    Returns
    -------
    ndarray, one distance per contact — NaN where an end has no particle or both ends fall into the same
    particle (no restraint between two particles).
    """
    if cd.spots["bin_id"].duplicated().any():
        raise ValueError("cd has several spots per bin (cells or chromosome copies): pass one haploid structure")
    loci = cd.spots_with_loci()
    grid = loci[["chrom", "start", "end"]]
    closed = _closed_for(cd, closed)
    xyz = np.asarray(cd.coords if layer is None else cd.layers[layer], dtype=np.float64)
    ia = bin_index(grid, np.asarray(contacts["chrom_a"]).astype(str), contacts["pos_a"], closed=closed)
    ib = bin_index(grid, np.asarray(contacts["chrom_b"]).astype(str), contacts["pos_b"], closed=closed)
    out = np.full(len(ia), np.nan)
    ok = (ia >= 0) & (ib >= 0) & (ia != ib)
    out[ok] = np.linalg.norm(xyz[ia[ok]] - xyz[ib[ok]], axis=1)
    return out
