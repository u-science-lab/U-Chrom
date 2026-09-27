"""Compare a statistic between two groups of cells — the compare-groups skill's recipe.

The unit of replication is the **cell**: per-trace (or per-spot) values are first summarised per
cell (median), and the test compares cells.  Traces of one cell are not independent; testing them
as if they were inflates n and makes almost any difference "significant".

    python compare_groups.py data.h5cd --a 1_0_34,1_0_61,... --b field:cell_type=Granule --stat rg
    python compare_groups.py data.h5cd --a field:cell_type=Bergmann --b rest --stat rg --equalize 100
    python compare_groups.py data.h5cd --a 1_0_34,1_0_61,... --b rest --scan if.     # every if.* column, BH-FDR
    # or from Python:  from compare_groups import compare, scan; compare(cd, a, b, stat="rg")

Groups: comma-separated cell ids, ``field:<column>=<value>`` / ``field:<column>!=<value>`` (cells column),
``all``, or ``rest`` (for b: every cell not in a).
Stats: ``rg`` (radius of gyration per trace), ``span`` (end-to-end distance per trace), ``n_spots`` (spots
per trace), or any numeric ``cells`` column (e.g. ``nuc_volume_um3``, ``if.H3K9me3``) — then there is one
value per cell.  ``equalize=k`` recomputes ``rg``/``span`` on k randomly drawn loci per trace (traces with
fewer are dropped; averaged over draws), so groups with different detection are compared at equal loci.
``scan`` compares many cells columns at once with Benjamini–Hochberg FDR, plus categorical composition.
Prints one JSON object; ``checks`` lists everything a report must mention.
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd
from scipy import stats as st

MIN_CELLS = 5


def _all_ids(cd) -> list:
    cells = cd.cells
    if cells is not None and len(cells):
        return list(cells.index.astype(str) if "cell_id" not in cells else cells["cell_id"].astype(str))
    return list(cd.spots["cell_id"].astype(str).unique())


def resolve_group(cd, spec, other=None) -> list:
    """Cell ids of a group spec (list of ids, 'a,b,c', 'field:<col>=<value>', 'field:<col>!=<value>',
    'all', or 'rest' = every cell not in ``other``)."""
    if isinstance(spec, str) and spec in ("all", "rest"):
        excl = set(resolve_group(cd, other)) if spec == "rest" and other is not None else set()
        return [c for c in _all_ids(cd) if c not in excl]
    if isinstance(spec, str) and spec.startswith("field:"):
        body = spec[len("field:"):]
        neg = "!=" in body
        col, val = body.split("!=" if neg else "=", 1)
        cells = cd.cells
        ids = cells.index.astype(str) if "cell_id" not in cells else cells["cell_id"].astype(str)
        hit = cells[col].astype(str).to_numpy() == val
        return list(ids[~hit if neg else hit])
    if isinstance(spec, str):
        spec = [s for s in spec.split(",") if s]
    return [str(c) for c in spec]


def _equalized(df: pd.DataFrame, stat: str, k: int, draws: int, seed: int) -> pd.Series:
    """Per trace: mean over ``draws`` random subsets of k loci of Rg (or span); traces with < k loci dropped."""
    rng = np.random.default_rng(seed)
    out = {}
    for tid, t in df.groupby("trace_id", observed=True):
        if len(t) < k:
            continue
        t = t.sort_values("start")
        xyz = t[["x", "y", "z"]].to_numpy()
        vals = []
        for _ in range(draws):
            idx = np.sort(rng.choice(len(t), size=k, replace=False))
            p = xyz[idx]
            if stat == "rg":
                vals.append(np.sqrt(((p - p.mean(0)) ** 2).sum(1).mean()))
            else:
                vals.append(np.linalg.norm(p[-1] - p[0]))
        out[tid] = float(np.mean(vals))
    return pd.Series(out, dtype=float)


def per_trace(cd, stat: str, equalize: int | None = None, draws: int = 20, seed: int = 0) -> pd.DataFrame:
    """One row per trace: cell_id, value."""
    from uchrom.fea.distance import radius_of_gyration
    df = cd.to_dataframe()
    if equalize and stat in ("rg", "span"):
        v = _equalized(df, stat, int(equalize), draws, seed)
    elif stat == "n_spots":
        v = df.groupby("trace_id", observed=True).size().astype(float)
    elif stat == "rg":
        v = radius_of_gyration(df)
    elif stat == "span":
        g = df.sort_values("start").groupby("trace_id", observed=True)
        v = g.apply(lambda t: float(np.linalg.norm(t[["x", "y", "z"]].iloc[-1].to_numpy()
                                                    - t[["x", "y", "z"]].iloc[0].to_numpy())), include_groups=False)
    else:
        raise ValueError(f"unknown per-trace stat {stat!r}")
    cell = df.groupby("trace_id", observed=True)["cell_id"].first().astype(str)
    return pd.DataFrame({"cell_id": cell.reindex(v.index).to_numpy(), "value": v.to_numpy()}).dropna()


TRACE_STATS = ("rg", "span", "n_spots")


def per_cell(cd, stat: str, cells: list, equalize: int | None = None) -> pd.Series:
    """One value per cell (median over its traces, or the cells column)."""
    if stat in TRACE_STATS:
        sub = cd.get_cells(cells)
        t = per_trace(sub, stat, equalize)
        return t.groupby("cell_id")["value"].median()
    col = cd.cells
    ids = col.index.astype(str) if "cell_id" not in col else col["cell_id"].astype(str)
    s = pd.Series(pd.to_numeric(col[stat], errors="coerce").to_numpy(), index=ids)
    return s.reindex([str(c) for c in cells]).dropna()


def compare(cd, a, b, stat: str = "rg", confounder: str | None = "nuc_volume_um3",
            equalize: int | None = None) -> dict:
    a_ids = resolve_group(cd, a)
    b_ids = resolve_group(cd, b, other=a_ids)
    overlap = sorted(set(a_ids) & set(b_ids))
    va, vb = per_cell(cd, stat, a_ids, equalize), per_cell(cd, stat, b_ids, equalize)
    res = {"stat": stat, "unit": "cell (median over its traces)" if stat in TRACE_STATS else "cell",
           "a": {"n_cells": int(len(va)), "median": float(np.median(va)) if len(va) else None},
           "b": {"n_cells": int(len(vb)), "median": float(np.median(vb)) if len(vb) else None},
           "checks": []}
    if stat in ("rg", "span"):
        res["value_unit"] = str(cd.uns.get("xyz_unit", "unknown (no uns['xyz_unit'])"))
    if equalize:
        res["equalized_loci_per_trace"] = int(equalize)
        res["checks"].append(f"{stat} recomputed on {int(equalize)} random loci per trace (mean of 20 draws); traces "
                             "with fewer loci dropped — report the equalized medians next to the raw ones")
    if stat in TRACE_STATS:
        ta, tb = (per_trace(cd.get_cells(a_ids), stat, equalize), per_trace(cd.get_cells(b_ids), stat, equalize))
        res["a"]["n_traces"], res["b"]["n_traces"] = int(len(ta)), int(len(tb))
        res["a"]["median_over_traces"] = float(ta["value"].median()) if len(ta) else None
        res["b"]["median_over_traces"] = float(tb["value"].median()) if len(tb) else None
    if overlap:
        res["checks"].append(f"groups overlap in {len(overlap)} cells; compare disjoint groups")
    if min(len(va), len(vb)) < MIN_CELLS:
        res["checks"].append(f"fewer than {MIN_CELLS} cells in a group (a: {len(va)}, b: {len(vb)}); "
                             "report as exploratory, no p-value claims")
    if len(va) >= 2 and len(vb) >= 2:
        u = st.mannwhitneyu(va, vb, alternative="two-sided")
        res["test"] = {"name": "Mann–Whitney U on per-cell values", "U": float(u.statistic), "p": float(u.pvalue)}
        # rank-biserial r = 2U/(n_a n_b) - 1: +1 when every a cell exceeds every b cell
        res["effect"] = {"rank_biserial": float(2 * u.statistic / (len(va) * len(vb)) - 1),
                         "median_ratio": float(np.median(va) / np.median(vb)) if np.median(vb) else None}
    if confounder and confounder in cd.cells.columns and confounder != stat:
        both = pd.concat([va, vb])
        conf = per_cell(cd, confounder, list(both.index))
        common = both.index.intersection(conf.index)
        if len(common) >= 5:
            rho = st.spearmanr(both[common], conf[common])
            res["confounder"] = {"field": confounder, "spearman_rho": float(rho.statistic), "p": float(rho.pvalue)}
            if abs(rho.statistic) > 0.5:
                res["checks"].append(f"{stat} tracks {confounder} across cells (rho {rho.statistic:.2f}); "
                                     "the difference may reflect nuclear size, not the group")
    if stat in ("rg", "span") and not equalize:
        na, nb = per_cell(cd, "n_spots", a_ids), per_cell(cd, "n_spots", b_ids)
        if len(na) and len(nb):
            ma, mb = float(np.median(na)), float(np.median(nb))
            res["spots_per_trace"] = {"a_median_of_cells": ma, "b_median_of_cells": mb}
            if max(ma, mb) > 1.3 * min(ma, mb):
                res["checks"].append(f"spots per trace differ (median per cell {ma:.0f} vs {mb:.0f}); {stat} depends "
                                     f"on how many loci are detected — rerun with equalize=k (k ≈ the smaller "
                                     "group's lower quartile of spots per trace) and report both")
    for col in ("fov", "field_of_view", "batch", "replicate", "sample"):
        if col in cd.cells.columns:
            vals = cd.cells.loc[cd.cells.index.astype(str).isin(set(a_ids) | set(b_ids)), col]
            if vals.nunique() <= 1:
                res["checks"].append(f"all cells share one {col} ({vals.iloc[0] if len(vals) else '?'}); "
                                     "no replicate — say so")
                break
    return res


def _bh(p):
    p = np.asarray(p, float)
    n = len(p)
    o = np.argsort(p)
    q = p[o] * n / (np.arange(n) + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty(n)
    out[o] = np.clip(q, 0, 1)
    return out


def scan(cd, a, b, columns="", top: int = 10) -> dict:
    """Compare every numeric cells column (starting with ``columns``, a prefix like 'if.'; or a list) between
    groups, per cell, Mann–Whitney + rank-biserial, BH-FDR across columns; plus categorical composition."""
    a_ids = resolve_group(cd, a)
    b_ids = resolve_group(cd, b, other=a_ids)
    cells = cd.cells
    ids = cells.index.astype(str) if "cell_id" not in cells else cells["cell_id"].astype(str)
    ia, ib = ids.isin(a_ids), ids.isin(b_ids)
    if isinstance(columns, str):
        cols = [c for c in cells.columns if str(c).startswith(columns)]
    else:
        cols = list(columns)
    rows = []
    for c in cols:
        x = pd.to_numeric(cells[c], errors="coerce")
        if x.notna().sum() < 4:
            continue
        va, vb = x[ia].dropna(), x[ib].dropna()
        if len(va) < 2 or len(vb) < 2 or (va.nunique() == 1 and vb.nunique() == 1 and va.iloc[0] == vb.iloc[0]):
            continue
        u = st.mannwhitneyu(va, vb, alternative="two-sided")
        rows.append({"field": str(c), "median_a": float(va.median()), "median_b": float(vb.median()),
                     "rank_biserial": float(2 * u.statistic / (len(va) * len(vb)) - 1), "p": float(u.pvalue)})
    df = pd.DataFrame(rows)
    res = {"unit": "cell", "n_a": int(ia.sum()), "n_b": int(ib.sum()), "n_fields_tested": int(len(df)),
           "correction": "Benjamini–Hochberg FDR across all fields tested", "checks": []}
    if len(df):
        df["q"] = _bh(df["p"].to_numpy())
        # most significant first; ties (common with small n) broken by the larger effect
        df = df.iloc[np.lexsort((-df["rank_biserial"].abs().to_numpy(), df["p"].to_numpy()))].reset_index(drop=True)
        res["top"] = df.head(top).to_dict("records")
        res["n_q_below_0.05"] = int((df["q"] < 0.05).sum())
        if not (df["q"] < 0.05).any():
            res["checks"].append("no field passes FDR 0.05: report the top fields as candidates only")
    comp = {}
    for c in cells.columns:
        if (cells[c].dtype == object or str(cells[c].dtype) in ("category", "str", "string")) and 1 < cells[c].nunique() <= 30:
            ca, cb = cells.loc[ia, c].astype(str).value_counts(), cells.loc[ib, c].astype(str).value_counts()
            comp[str(c)] = {"a": ca.to_dict(), "b": cb.to_dict()}
            top_a = ca.index[0] if len(ca) else None
            if top_a is not None:
                tab = [[int(ca.get(top_a, 0)), int(ca.sum() - ca.get(top_a, 0))],
                       [int(cb.get(top_a, 0)), int(cb.sum() - cb.get(top_a, 0))]]
                comp[str(c)]["enrichment"] = {"value": top_a, "frac_a": tab[0][0] / max(1, sum(tab[0])),
                                              "frac_b": tab[1][0] / max(1, sum(tab[1])),
                                              "fisher_p": float(st.fisher_exact(tab)[1])}
    res["composition"] = comp
    if min(ia.sum(), ib.sum()) < MIN_CELLS:
        res["checks"].append(f"fewer than {MIN_CELLS} cells in a group: exploratory")
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("data")
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--stat", default="rg")
    ap.add_argument("--confounder", default="nuc_volume_um3")
    ap.add_argument("--equalize", type=int, default=None, help="recompute rg/span on k random loci per trace")
    ap.add_argument("--scan", default=None, help="compare every cells column with this prefix ('' = all), BH-FDR")
    a = ap.parse_args()
    from uchrom.core import ChromData
    cd = ChromData.read(a.data)
    out = (scan(cd, a.a, a.b, a.scan) if a.scan is not None
           else compare(cd, a.a, a.b, a.stat, a.confounder, a.equalize))
    json.dump(out, sys.stdout, indent=1, default=float)
    print()


if __name__ == "__main__":
    main()
