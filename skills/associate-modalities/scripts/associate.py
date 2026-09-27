"""Relate a feature to chromatin structure (or two modalities) at a stated level — the
associate-modalities skill's recipe.

    # cell level: one value per cell, confounders partialled out, within cell types
    python associate.py cell data.h5cd --x if.<MARK> --y rg [--covar nuc_volume_um3,n_spots] [--group cell_type]
    python associate.py cell data.h5cd --x atac.<GENE> --y rna.<GENE> --group cell_type
    # bin level: per genomic bin, the mean of a spot track vs the mean of a structural spot feature
    python associate.py bin data.h5cd --x <TRACK> --y <TRACK> --chrom <CHROM> --bin-size <BIN>
    # embedding: k-nearest-neighbour label purity of a 2-D / n-D embedding in cellm
    python associate.py purity data.h5cd --emb hic_umap,rna_umap --label cell_type --k 15

Per-cell values (``--x`` / ``--y``):
  a ``cells`` column (``if.<MARK>``, ``rna.<GENE>``, ``nuc_volume_um3``, …);
  ``rg`` / ``span`` — median over the cell's traces of the trace radius of gyration / end-to-end distance;
  ``rg_norm`` — the same after dividing each trace's Rg by the median Rg of its chromosome (removes
  chromosome-composition differences between cells);
  ``n_spots`` — median spots per trace;  ``track:<name>`` — mean of a per-spot track over the cell's spots.
Per-spot values for ``bin``: any ``tracks`` column, or ``dist_to_cell_center`` (distance of a spot from the
centroid of all spots of its cell).
Prints one JSON object; ``checks`` lists what the report must mention.
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd
from scipy import stats as st

MIN_N = 5


def _cell_index(cd) -> pd.Index:
    c = cd.cells
    return c["cell_id"].astype(str) if "cell_id" in c.columns else c.index.astype(str)


def _trace_frame(cd) -> pd.DataFrame:
    s = cd.spots
    df = pd.DataFrame({"trace_id": s["trace_id"].astype(str).to_numpy(), "chrom": s["chrom"].astype(str).to_numpy(),
                       "start": s["start"].to_numpy(np.int64),
                       "cell_id": s["cell_id"].astype(str).to_numpy() if "cell_id" in s.columns else "all"})
    df[["x", "y", "z"]] = np.asarray(cd.coords, dtype=float)
    return df


def per_trace(cd) -> pd.DataFrame:
    """trace_id, cell_id, chrom, n_spots, rg, span (all spots, as ``uchrom.fea.distance``)."""
    df = _trace_frame(cd)
    xyz = df[["x", "y", "z"]].to_numpy()
    cen = df.groupby("trace_id")[["x", "y", "z"]].transform("mean").to_numpy()
    df["r2"] = ((xyz - cen) ** 2).sum(1)
    df = df.sort_values(["trace_id", "start"])
    g = df.groupby("trace_id")
    t = g.agg(cell_id=("cell_id", "first"), chrom=("chrom", "first"), n_spots=("r2", "size"), ms=("r2", "mean"))
    t["rg"] = np.sqrt(t.pop("ms"))
    first, last = g[["x", "y", "z"]].first(), g[["x", "y", "z"]].last()
    t["span"] = np.linalg.norm(first.to_numpy() - last.to_numpy(), axis=1)
    t.loc[t["n_spots"] < 2, ["rg", "span"]] = np.nan
    t["rg_norm"] = t["rg"] / t.groupby("chrom")["rg"].transform("median")
    return t


def per_cell(cd, spec: str) -> pd.Series:
    """One value per cell (index = cell id) for a value spec (see module docstring)."""
    if spec in ("rg", "span", "rg_norm", "n_spots"):
        return per_trace(cd).groupby("cell_id")[spec].median().rename(spec)
    if spec.startswith("track:"):
        name = spec[len("track:"):]
        cid = cd.spots["cell_id"].astype(str).to_numpy()
        return pd.Series(pd.to_numeric(cd.tracks[name], errors="coerce").to_numpy()).groupby(cid).mean().rename(spec)
    if cd.cells is None or spec not in cd.cells.columns:
        raise KeyError(f"{spec!r} is not a cells column nor one of rg, span, rg_norm, n_spots, track:<name>")
    return pd.Series(pd.to_numeric(cd.cells[spec], errors="coerce").to_numpy(), index=_cell_index(cd), name=spec)


def _rank_resid(y: np.ndarray, Z: np.ndarray) -> np.ndarray:
    """Residuals of rank(y) on ranks of the covariates (for a partial Spearman correlation)."""
    ry = st.rankdata(y)
    X = np.column_stack([np.ones(len(y))] + [st.rankdata(z) for z in Z.T])
    beta, *_ = np.linalg.lstsq(X, ry, rcond=None)
    return ry - X @ beta


def _corr(a, b, method):
    r = st.spearmanr(a, b) if method == "spearman" else st.pearsonr(a, b)
    return float(r.statistic), float(r.pvalue)


def cell_level(cd, x: str, y: str, covariates=("nuc_volume_um3",), group: str | None = "cell_type",
               method: str = "spearman") -> dict:
    """Correlate two per-cell values across cells: overall, partial on covariates, and within groups."""
    cols = {x: per_cell(cd, x), y: per_cell(cd, y)}
    covs = [c for c in (covariates or []) if c and c not in (x, y)]
    for c in covs:
        cols[c] = per_cell(cd, c)
    df = pd.DataFrame(cols).dropna()
    if group and cd.cells is not None and group in cd.cells.columns:
        lab = pd.Series(cd.cells[group].astype(str).to_numpy(), index=_cell_index(cd))
        df["_group"] = lab.reindex(df.index).to_numpy()
    else:
        group = None
    n = len(df)
    res = {"level": "cell (one value per cell)", "x": x, "y": y, "method": method, "n_cells": n, "checks": []}
    if n < 3:
        res["checks"].append("fewer than 3 cells with both values")
        return res
    res["rho"], res["p"] = _corr(df[x], df[y], method)
    res["confounders"] = {}
    for c in covs:
        rx, _ = _corr(df[x], df[c], "spearman")
        ry, _ = _corr(df[y], df[c], "spearman")
        res["confounders"][c] = {"rho_with_x": rx, "rho_with_y": ry}
        if abs(rx) > 0.3 and abs(ry) > 0.3:
            res["checks"].append(f"{c} correlates with both {x} (rho {rx:.2f}) and {y} (rho {ry:.2f}): part of the "
                                 f"association may run through {c} — report the partial correlation")
    if covs and n > len(covs) + 3:
        Z = df[covs].to_numpy(float)
        pr = st.pearsonr(_rank_resid(df[x].to_numpy(float), Z), _rank_resid(df[y].to_numpy(float), Z))
        res["partial"] = {"controls": covs, "rho": float(pr.statistic), "p": float(pr.pvalue),
                          "method": "Spearman partial (rank residuals)"}
    if group:
        within = {}
        for g, d in df.groupby("_group"):
            if len(d) >= MIN_N and d[x].nunique() > 1 and d[y].nunique() > 1:
                r, p = _corr(d[x], d[y], method)
                within[g] = {"n": int(len(d)), "rho": r, "p": p}
            else:
                within[g] = {"n": int(len(d)), "rho": None, "note": f"< {MIN_N} cells or constant"}
        res["within_" + group] = within
        rhos = [v["rho"] for v in within.values() if v.get("rho") is not None]
        res["median_within_group_rho"] = float(np.median(rhos)) if rhos else None
        # pooled within-group: centre ranks inside each group, then correlate
        cx = df.groupby("_group")[x].rank(pct=True) - 0.5
        cy = df.groupby("_group")[y].rank(pct=True) - 0.5
        pw = st.pearsonr(cx, cy)
        res["pooled_within_group"] = {"rho": float(pw.statistic), "p": float(pw.pvalue),
                                      "method": f"Pearson of within-{group} percentile ranks"}
        gm = df.groupby("_group")[[x, y]].median()
        if len(gm) >= 3:
            res["between_group_medians_rho"] = _corr(gm[x], gm[y], "spearman")[0]
        if (abs(res["rho"]) >= 0.1 and res["p"] < 0.05
                and abs(res["pooled_within_group"]["rho"]) < 0.5 * abs(res["rho"])):
            res["checks"].append(f"the association is much weaker within {group} (pooled within rho "
                                 f"{res['pooled_within_group']['rho']:.2f} vs overall {res['rho']:.2f}): it is largely "
                                 f"driven by differences between {group}s")
    if n < 20:
        res["checks"].append(f"only {n} cells: wide uncertainty; give the p-value and avoid strong claims")
    if cd.cells is not None and "batch" in cd.cells.columns and cd.cells["batch"].nunique() <= 1:
        res["checks"].append("one batch / field of view: no biological replicate")
    return res


def spot_values(cd, name: str) -> np.ndarray:
    if name == "dist_to_cell_center":
        df = _trace_frame(cd)
        cen = df.groupby("cell_id")[["x", "y", "z"]].transform("mean").to_numpy()
        return np.linalg.norm(df[["x", "y", "z"]].to_numpy() - cen, axis=1)
    return pd.to_numeric(cd.tracks[name], errors="coerce").to_numpy(float)


def bin_level(cd, x: str, y: str, chrom: str, bin_size: float = 1e6, cells=None, method: str = "spearman",
              min_spots: int = 10) -> dict:
    """Per genomic bin (``bin_size`` bp on ``chrom``): mean of spot value x and of spot value y over all spots
    (optionally of ``cells``) in the bin; correlate across bins."""
    s = cd.spots
    mask = s["chrom"].astype(str).to_numpy() == str(chrom)
    if cells is not None:
        mask &= s["cell_id"].astype(str).isin([str(c) for c in cells]).to_numpy()
    xv, yv = spot_values(cd, x)[mask], spot_values(cd, y)[mask]
    mid = ((s["start"].to_numpy(np.int64) + s["end"].to_numpy(np.int64)) // 2)[mask]
    b = mid // int(bin_size)
    df = pd.DataFrame({"bin": b, "x": xv, "y": yv, "cell": s["cell_id"].astype(str).to_numpy()[mask]}).dropna()
    g = df.groupby("bin").agg(x=("x", "mean"), y=("y", "mean"), n_spots=("x", "size"), n_cells=("cell", "nunique"))
    g = g[g["n_spots"] >= min_spots]
    res = {"level": f"genomic bin ({int(bin_size)} bp) — per-bin means over spots of all selected cells", "x": x,
           "y": y, "chrom": chrom, "method": method, "n_bins": int(len(g)),
           "median_spots_per_bin": float(g["n_spots"].median()) if len(g) else None, "checks": []}
    if len(g) >= 3:
        res["rho"], res["p"] = _corr(g["x"], g["y"], method)
        # spot-level for contrast only: spots are not independent (same trace, same cell)
        res["spot_level_rho_for_contrast"] = _corr(df["x"], df["y"], method)[0]
        res["checks"].append("p-value across bins ignores spatial autocorrelation of neighbouring bins; treat it as "
                             "descriptive")
    if y == "dist_to_cell_center" or x == "dist_to_cell_center":
        res["checks"].append("dist_to_cell_center: larger = more peripheral (centroid of the cell's DNA spots, not "
                             "the segmented nucleus)")
    return res


def knn_purity(cd, emb: str, label: str = "cell_type", k: int = 15) -> dict:
    """Mean fraction of each cell's k nearest neighbours (self excluded, Euclidean) sharing its label."""
    from sklearn.neighbors import NearestNeighbors
    X = np.asarray(cd.cellm[emb], dtype=float)
    lab = cd.cells[label].astype(str).to_numpy()
    ok = np.isfinite(X).all(1) & pd.notna(cd.cells[label]).to_numpy()
    X, lab = X[ok], lab[ok]
    idx = NearestNeighbors(n_neighbors=k + 1).fit(X).kneighbors(X, return_distance=False)[:, 1:]
    same = (lab[idx] == lab[:, None]).mean(1)
    freq = pd.Series(lab).value_counts(normalize=True)
    per = pd.Series(same).groupby(lab).mean()
    meta = (cd.uns.get("embeddings") or {}).get(emb, {})
    return {"embedding": emb, "dims": int(X.shape[1]), "label": label, "k": k, "n_cells": int(len(X)),
            "purity": float(same.mean()), "chance_purity": float((freq ** 2).sum()),
            "per_label": per.round(4).to_dict(), "modality": meta.get("modality"), "method": meta.get("method")}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["cell", "bin", "purity"])
    ap.add_argument("data")
    ap.add_argument("--x")
    ap.add_argument("--y")
    ap.add_argument("--covar", default="nuc_volume_um3")
    ap.add_argument("--group", default="cell_type")
    ap.add_argument("--method", default="spearman", choices=["spearman", "pearson"])
    ap.add_argument("--chrom")
    ap.add_argument("--bin-size", type=float, default=1e6)
    ap.add_argument("--emb")
    ap.add_argument("--label", default="cell_type")
    ap.add_argument("--k", type=int, default=15)
    a = ap.parse_args()
    from uchrom.core import ChromData
    cd = ChromData.read(a.data)
    if a.cmd == "cell":
        covs = [c for c in a.covar.split(",") if c and (c in ("rg", "n_spots", "span", "rg_norm")
                                                      or c.startswith("track:") or c in cd.cells.columns)]
        out = cell_level(cd, a.x, a.y, covs, a.group or None, a.method)
    elif a.cmd == "bin":
        out = bin_level(cd, a.x, a.y, a.chrom, a.bin_size, method=a.method)
    else:
        out = {e: knn_purity(cd, e, a.label, a.k) for e in a.emb.split(",")}
    json.dump(out, sys.stdout, indent=1, default=float)
    print()


if __name__ == "__main__":
    main()
