"""Compare a statistic between two groups of cells — the compare-groups skill's recipe.

The unit of replication is the **cell**: per-trace (or per-spot) values are first summarised per
cell (median), and the test compares cells.  Traces of one cell are not independent; testing them
as if they were inflates n and makes almost any difference "significant".

    python compare_groups.py data.h5cd --a 1_0_34,1_0_61,... --b field:cell_type=Granule --stat rg
    # or from Python:  from compare_groups import compare; compare(cd, a, b, stat="rg")

Groups: comma-separated cell ids, or ``field:<column>=<value>`` (a value of a cells column).
Stats: ``rg`` (radius of gyration per trace), ``span`` (end-to-end distance per trace), or any
numeric ``cells`` column (e.g. ``nuc_volume_um3``, ``if.H3K9me3``) — then there is one value per cell.
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


def resolve_group(cd, spec) -> list:
    """Cell ids of a group spec (list of ids, 'a,b,c', or 'field:<col>=<value>')."""
    if isinstance(spec, str) and spec.startswith("field:"):
        col, val = spec[len("field:"):].split("=", 1)
        cells = cd.cells
        ids = cells.index.astype(str) if "cell_id" not in cells else cells["cell_id"].astype(str)
        return list(ids[cells[col].astype(str).to_numpy() == val])
    if isinstance(spec, str):
        spec = [s for s in spec.split(",") if s]
    return [str(c) for c in spec]


def per_trace(cd, stat: str) -> pd.DataFrame:
    """One row per trace: cell_id, value."""
    from uchrom.fea.distance import radius_of_gyration
    df = cd.to_dataframe()
    if stat == "rg":
        v = radius_of_gyration(df)
    elif stat == "span":
        g = df.sort_values("start").groupby("trace_id", observed=True)
        v = g.apply(lambda t: float(np.linalg.norm(t[["x", "y", "z"]].iloc[-1].to_numpy()
                                                    - t[["x", "y", "z"]].iloc[0].to_numpy())), include_groups=False)
    else:
        raise ValueError(f"unknown per-trace stat {stat!r}")
    cell = df.groupby("trace_id", observed=True)["cell_id"].first().astype(str)
    return pd.DataFrame({"cell_id": cell.reindex(v.index).to_numpy(), "value": v.to_numpy()}).dropna()


def per_cell(cd, stat: str, cells: list) -> pd.Series:
    """One value per cell (median over its traces, or the cells column)."""
    sub = cd.get_cells(cells)
    if stat in ("rg", "span"):
        t = per_trace(sub, stat)
        return t.groupby("cell_id")["value"].median()
    col = cd.cells
    ids = col.index.astype(str) if "cell_id" not in col else col["cell_id"].astype(str)
    s = pd.Series(pd.to_numeric(col[stat], errors="coerce").to_numpy(), index=ids)
    return s.reindex([str(c) for c in cells]).dropna()


def compare(cd, a, b, stat: str = "rg", confounder: str | None = "nuc_volume_um3") -> dict:
    a_ids, b_ids = resolve_group(cd, a), resolve_group(cd, b)
    overlap = sorted(set(a_ids) & set(b_ids))
    va, vb = per_cell(cd, stat, a_ids), per_cell(cd, stat, b_ids)
    res = {"stat": stat, "unit": "cell (median over its traces)" if stat in ("rg", "span") else "cell",
           "a": {"n_cells": int(len(va)), "median": float(np.median(va)) if len(va) else None},
           "b": {"n_cells": int(len(vb)), "median": float(np.median(vb)) if len(vb) else None},
           "checks": []}
    if stat in ("rg", "span"):
        ta, tb = per_trace(cd.get_cells(a_ids), stat), per_trace(cd.get_cells(b_ids), stat)
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
    for col in ("fov", "field_of_view", "batch", "replicate", "sample"):
        if col in cd.cells.columns:
            vals = cd.cells.loc[cd.cells.index.astype(str).isin(set(a_ids) | set(b_ids)), col]
            if vals.nunique() <= 1:
                res["checks"].append(f"all cells share one {col} ({vals.iloc[0] if len(vals) else '?'}); "
                                     "no replicate — say so")
                break
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("data")
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--stat", default="rg")
    ap.add_argument("--confounder", default="nuc_volume_um3")
    a = ap.parse_args()
    from uchrom.core import ChromData
    json.dump(compare(ChromData.read(a.data), a.a, a.b, a.stat, a.confounder), sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
