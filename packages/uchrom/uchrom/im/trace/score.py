"""How well called fibres reproduce a reference assignment of the same detections."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def _spots(x) -> pd.DataFrame:
    if isinstance(x, pd.DataFrame):
        return x
    sp = x.spots_with_loci() if hasattr(x, "spots_with_loci") else x.spots
    return sp


def _scores(df: pd.DataFrame) -> pd.Series:
    from sklearn.metrics import adjusted_rand_score

    on = df[df["fibre"].notna()]
    purity = on.groupby("fibre")["label"].agg(lambda s: s.value_counts().iloc[0] / len(s))
    ari = [adjusted_rand_score(g["label"], g["fibre"].fillna("none"))
           for _, g in df.groupby(["cell", "chrom"]) if g["label"].nunique() > 1]
    return pd.Series({"assigned": df["fibre"].notna().mean(), "purity": purity.mean(),
                      "median ARI": np.median(ari) if ari else np.nan, "n_spots": float(len(df)),
                      "n_fibres": float(on["fibre"].nunique())})


def score_alignment(cd, reference, *, label: Optional[str] = None, per: Optional[str] = None):
    """Compare the fibres of an alignment with a reference assignment of the same detections.

    The detections are matched by ``spot_id`` (which :func:`align_spots` carries through).  Scored are the
    reference spots with a label (missing or negative labels — e.g. ``labelID == -1``, rejected by the
    upstream pipeline — are left out) in the (cell, chromosome) groups the alignment processed (its
    ``results['ploidy']``; so a reference may hold more chromosomes or cells than were aligned):

    * ``assigned`` — fraction of them placed on some fibre;
    * ``purity`` — per fibre, the fraction of its spots from its majority reference label, averaged over
      the fibres;
    * ``median ARI`` — per (cell, chromosome) with more than one reference label, the adjusted Rand index
      between fibres and labels (spots on no fibre form one extra group); the median over those;
    * ``n_spots``, ``n_fibres`` — the scored spots and the fibres they fall on.

    Parameters
    ----------
    cd : ChromData
        The alignment (:func:`align_spots`): ``spot_id`` and ``trace_id`` (the fibre) per spot.
    reference : ChromData or DataFrame
        The detections with ``spot_id``, ``cell_id``, ``chrom`` and the reference label.
    label : str, optional
        The reference spot column with the assignment (e.g. ``"label"``, the upstream homolog call);
        default ``trace_id`` (a traced reference).  Labels are compared within (cell, chromosome).
    per : ``None`` or ``"chrom"``
        One set of scores, or one row per chromosome.

    Returns
    -------
    Series (or DataFrame with one row per chromosome, ``per="chrom"``)
    """
    if per not in (None, "chrom"):
        raise ValueError("per must be None or 'chrom'")
    called = cd.spots
    if "spot_id" not in called.columns:
        raise ValueError("score_alignment: the alignment has no spot_id (pass detections with spot_id)")
    ref = _spots(reference)
    col = label or "trace_id"
    for c in ("spot_id", "cell_id", "chrom", col):
        if c not in ref.columns:
            raise ValueError(f"score_alignment: the reference has no column {c!r}")
    fibre = pd.Series(called["trace_id"].astype(str).to_numpy(), index=called["spot_id"].to_numpy())
    if fibre.index.has_duplicates:
        raise ValueError("score_alignment: a spot_id is on two fibres")
    lab = ref[col]
    keep = np.array(lab.notna().to_numpy(), dtype=bool)
    if pd.api.types.is_numeric_dtype(lab):
        keep = keep & (lab.fillna(-1) >= 0).to_numpy()
    df = pd.DataFrame({"cell": ref["cell_id"].astype(str).to_numpy(), "chrom": ref["chrom"].astype(str).to_numpy(),
                       "fibre": fibre.reindex(ref["spot_id"].to_numpy()).to_numpy(),
                       "label": lab.to_numpy()})
    if "ploidy" in getattr(cd, "results", {}):         # only the (cell, chromosome) groups that were aligned
        done = cd.results["ploidy"]
        done = pd.MultiIndex.from_arrays([done["cell_id"].astype(str), done["chrom"].astype(str)])
        keep = keep & pd.MultiIndex.from_arrays([df["cell"], df["chrom"]]).isin(done)
    df = df[keep]
    if per is None:
        return _scores(df)
    return pd.DataFrame({c: _scores(g) for c, g in df.groupby("chrom", sort=False)}).T


__all__ = ["score_alignment"]
