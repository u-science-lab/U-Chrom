"""How accurate is an imputation?  A hold-out test on real traces."""

from __future__ import annotations

import time
from typing import Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd


class ImputationHoldout(dict):
    """Result of :func:`evaluate_imputation` (a dict with attribute access):

    - ``summary``: one column per method, rows ``median error``, ``mean error``, ``not imputed``,
      ``median neighbour distance, true`` / ``imputed`` (in the unit of ``uns['xyz_unit']``) and
      ``seconds``;
    - ``errors``: one row per hidden spot (index ``trace_id, chrom, start``), the 3-D error of each method;
    - ``n_observed``, ``n_hidden``, ``frac``, ``seed``, ``neighbour_bp``, ``unit``.
    """

    __getattr__ = dict.__getitem__


def _trace_rank(tr: pd.Series) -> np.ndarray:
    """Rank of every row's trace id in the sorted ids (ints numerically, strings lexicographically)."""
    if isinstance(tr.dtype, pd.CategoricalDtype):
        cats = tr.cat.categories.to_numpy()
        rank = np.empty(len(cats), dtype=np.int64)
        rank[np.argsort(cats, kind="stable")] = np.arange(len(cats))
        return rank[tr.cat.codes.to_numpy()]
    return pd.factorize(tr, sort=True)[0]


def _by_locus(cd) -> pd.DataFrame:
    sp = cd.spots_with_loci()
    idx = pd.MultiIndex.from_arrays([sp["trace_id"].astype(str).to_numpy(), sp["chrom"].astype(str).to_numpy(),
                                     sp["start"].to_numpy(dtype=np.int64)], names=["trace_id", "chrom", "start"])
    df = pd.DataFrame(np.asarray(cd.coords, dtype=np.float64), columns=list("xyz"), index=idx)
    return df[~df.index.duplicated()]


def evaluate_imputation(
    cd,
    methods: Sequence[str] = ("linear", "cubic", "snapfish"),
    *,
    frac: float = 0.1,
    seed: int = 0,
    neighbour_bp: Optional[int] = None,
    trace_ids: Optional[Iterable] = None,
    cells: Optional[Iterable] = None,
    method_kwargs: Optional[Mapping[str, Mapping]] = None,
    key_added: Optional[str] = "imputation.holdout",
) -> ImputationHoldout:
    """Hide observed spots, impute them with each method and compare with the truth.

    The observed spots (one per trace and locus) are put in a canonical order — trace (ids sorted:
    integers numerically, strings lexicographically), chromosome, start — so that the hidden set does
    not depend on how the rows are stored; ``frac`` of them are drawn with ``numpy.random.default_rng(seed)``
    and removed (absent rows), every method of :func:`impute_coordinates` fills them back in, and the
    result is compared with the hidden truth:

    * **error** — the 3-D distance between the imputed and the true position;
    * **neighbour distance** — imputation should also keep the local chain geometry: the distances from
      each hidden locus to the observed (not hidden) loci of its trace within ``neighbour_bp``, from the
      true and from the imputed position (medians over all such pairs).

    Parameters
    ----------
    cd : ChromData
        Traces with real coordinates (spots with NaN coordinates are never hidden; they stay missing).
    methods : sequence of str
        Methods of :func:`impute_coordinates` (``"linear"``, ``"cubic"``, ``"snapfish"``).
    frac : float
        Fraction of the observed spots to hide.
    seed : int
        Seed of the random draw.
    neighbour_bp : int, optional
        Genomic window of the neighbour distances; default three times the median bin size.
    trace_ids, cells : optional
        Evaluate on these traces / cells only (the calling convention's selection).
    method_kwargs : dict, optional
        Keyword arguments per method, e.g. ``{"snapfish": {"max_iter": 50, "n_jobs": 4}}``
        (SnapFISH-IMPUTE runs with ``verbose=False`` unless given).
    key_added : str or None
        ``cd.results`` key of the summary table (``None``: not stored).

    Returns
    -------
    ImputationHoldout
        ``summary`` (metrics x methods), ``errors`` (per hidden spot and method) and the settings.

    Examples
    --------
    >>> res = evaluate_imputation(cd, trace_ids=cd.spots["trace_id"].cat.categories[:300],
    ...                           method_kwargs={"snapfish": {"n_jobs": 4}})
    >>> res.summary.round(1)
    """
    from uchrom.convention import select_spots

    from . import impute_coordinates

    if not 0 < frac < 1:
        raise ValueError("frac must be in (0, 1)")
    sub = select_spots(cd, trace_ids=trace_ids, cells=cells)
    sp = sub.spots_with_loci()
    xyz = np.asarray(sub.coords, dtype=np.float64)
    observed = np.isfinite(xyz).all(axis=1)
    chrom = sp["chrom"].astype(str).to_numpy()
    start = sp["start"].to_numpy(dtype=np.int64)
    order = np.lexsort((start, pd.factorize(chrom, sort=True)[0], _trace_rank(sp["trace_id"])))
    order = order[observed[order]]
    tid = sp["trace_id"].astype(str).to_numpy()
    first = ~pd.DataFrame({"t": tid[order], "c": chrom[order], "s": start[order]}).duplicated().to_numpy()
    rows = order[first]                                   # observed spots, one per (trace, locus)
    n_hide = int(np.floor(len(rows) * frac + 1e-9))
    if n_hide < 1:
        raise ValueError(f"frac={frac} of {len(rows)} observed spots hides nothing")
    hide = rows[np.random.default_rng(seed).choice(len(rows), size=n_hide, replace=False)]
    keep = np.ones(sub.n_spots, dtype=bool)
    keep[hide] = False
    masked = sub[np.flatnonzero(keep)]

    unit = str(sub.uns.get("xyz_unit", "")) or "units"
    if neighbour_bp is None:
        neighbour_bp = int(3 * np.median(sub.bins["end"].to_numpy() - sub.bins["start"].to_numpy()))
    truth_idx = pd.MultiIndex.from_arrays([tid[hide], chrom[hide], start[hide]],
                                          names=["trace_id", "chrom", "start"])
    truth = xyz[hide]
    # observed, not hidden neighbours of every hidden spot within neighbour_bp
    hidden_keys = set(zip(tid[hide], chrom[hide], start[hide]))
    pool = pd.DataFrame({"trace_id": tid[rows], "chrom": chrom[rows], "start": start[rows],
                         "qx": xyz[rows, 0], "qy": xyz[rows, 1], "qz": xyz[rows, 2]})
    pool = pool[[k not in hidden_keys for k in zip(pool["trace_id"], pool["chrom"], pool["start"])]]
    hid = pd.DataFrame({"trace_id": tid[hide], "chrom": chrom[hide], "s": start[hide], "k": np.arange(len(hide))})
    pairs = hid.merge(pool, on=["trace_id", "chrom"])
    gap = (pairs["start"] - pairs["s"]).abs()
    pairs = pairs[(gap > 0) & (gap <= neighbour_bp)]
    q = pairs[["qx", "qy", "qz"]].to_numpy()
    k = pairs["k"].to_numpy()
    near_true = np.linalg.norm(q - truth[k], axis=1)

    kwargs = {m: dict(v) for m, v in (method_kwargs or {}).items()}
    kwargs.setdefault("snapfish", {}).setdefault("verbose", False)
    summary, errors = {}, {}
    for method in methods:
        t0 = time.perf_counter()
        imputed = impute_coordinates(masked, method=method, **kwargs.get(method, {}))
        secs = time.perf_counter() - t0
        est = _by_locus(imputed).reindex(truth_idx).to_numpy()
        err = np.linalg.norm(est - truth, axis=1)
        near_imp = np.linalg.norm(q - est[k], axis=1)
        errors[method] = err
        summary[method] = {
            f"median error ({unit})": float(np.nanmedian(err)),
            f"mean error ({unit})": float(np.nanmean(err)),
            "not imputed": int(np.isnan(err).sum()),
            f"median neighbour distance, true ({unit})": float(np.median(near_true)),
            f"median neighbour distance, imputed ({unit})": float(np.nanmedian(near_imp)),
            "seconds": secs,
        }
    summary = pd.DataFrame(summary)
    errors = pd.DataFrame(errors, index=truth_idx)
    if key_added is not None:
        cd.results.set(key_added, summary, kind="table", function="uchrom.im.impute.evaluate_imputation",
                       params={"methods": list(methods), "frac": frac, "seed": seed, "neighbour_bp": neighbour_bp,
                               "method_kwargs": kwargs},
                       inputs={"n_traces": int(sub.n_traces), "n_observed": int(len(rows)), "n_hidden": int(n_hide)})
    return ImputationHoldout(summary=summary, errors=errors, n_observed=int(len(rows)), n_hidden=int(n_hide),
                             frac=frac, seed=seed, neighbour_bp=int(neighbour_bp), unit=unit)


__all__ = ["evaluate_imputation", "ImputationHoldout"]
