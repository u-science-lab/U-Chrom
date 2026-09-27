"""Structure statistics and callers at the right resolution — the call-structures skill's recipe.

Tracing data (3-D coordinates in a ChromData):

    python structures.py dist-at data.h5cd --chrom <CHROM> --sep <SEP> [--tol 0.1]
    python structures.py scaling  data.h5cd --chrom <CHROM>            # distance vs separation + exponent
    python structures.py rg       data.h5cd                          # radius of gyration per chromosome
    python structures.py coverage data.h5cd --chrom <CHROM>            # detection per bin size -> resolution
    python structures.py tads     data.h5cd --chrom <CHROM> [--bin-size auto|native|<BIN>] [--window-bins 4]
    python structures.py comps    data.h5cd --chrom <CHROM> [--bin-size auto]

Contact maps (.cool / .mcool / .scool, e.g. ``uns['linked_cool']``):

    python structures.py ps data.h5cd --cool <key> --res <BIN> --chrom <CHROM> --smin <S_MIN> --smax <S_MAX>
    python structures.py ps data.h5cd --cool <key_A>,<key_B> --chrom <CHROM> ...     # summed pseudo-bulk
    python structures.py ps map.mcool::/resolutions/<BIN> --chrom <CHROM> ...     # a file directly

Every command prints one JSON object with the numbers, the n behind them, and ``checks``.
Statistics use every spot, like ``uchrom.fea``; binning for the callers averages spots per (trace, bin).
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd

MIN_TRACES = 20          # below this, population structure calls are exploratory
AUTO_BIN_SIZES = (25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000, 2_000_000)
MIN_DETECTED = 0.5       # auto resolution: median trace must observe at least this fraction of bins


# ------------------------------------------------------------------ tracing: tables and binning
def trace_table(cd, chrom=None, dedup: bool = False) -> pd.DataFrame:
    """chrom, start, end, mid, x, y, z, trace_id, cell_id; ``dedup`` averages duplicate (trace, locus) spots.

    Statistics keep every spot (the ``uchrom.fea`` convention); binning for the callers always dedups."""
    s = cd.spots
    df = pd.DataFrame({"chrom": s["chrom"].astype(str).to_numpy(), "start": s["start"].to_numpy(np.int64),
                       "end": s["end"].to_numpy(np.int64), "trace_id": s["trace_id"].astype(str).to_numpy(),
                       "cell_id": (s["cell_id"].astype(str).to_numpy() if "cell_id" in s.columns else "all")})
    df[["x", "y", "z"]] = np.asarray(cd.coords, dtype=float)
    if chrom is not None:
        df = df[df["chrom"] == str(chrom)]
    df = df.dropna(subset=["x", "y", "z"])
    if dedup:
        df = df.groupby(["trace_id", "chrom", "start", "end"], as_index=False, observed=True).agg(
            x=("x", "mean"), y=("y", "mean"), z=("z", "mean"), cell_id=("cell_id", "first"))
    df["mid"] = (df["start"] + df["end"]) // 2
    return df.sort_values(["trace_id", "start"]).reset_index(drop=True)


def bin_traces(cd, chrom: str, bin_size: int):
    """New ChromData for one chromosome with coordinates averaged per (trace, bin of ``bin_size`` bp)."""
    from uchrom import ChromData
    df = trace_table(cd, chrom, dedup=True)
    df["bin"] = (df["mid"] // int(bin_size)).astype(np.int64)
    g = df.groupby(["trace_id", "bin"], as_index=False).agg(x=("x", "mean"), y=("y", "mean"), z=("z", "mean"),
                                                            cell_id=("cell_id", "first"))
    spots = pd.DataFrame({"chrom": chrom, "start": g["bin"] * int(bin_size), "end": (g["bin"] + 1) * int(bin_size),
                          "trace_id": g["trace_id"], "cell_id": g["cell_id"]})
    return ChromData(g[["x", "y", "z"]].to_numpy(), spots, uns=dict(cd.uns))


def native_bin_size(cd, chrom: str) -> int:
    df = trace_table(cd, chrom, dedup=False)
    u = np.sort(df["start"].unique())
    return int(np.median(np.diff(u))) if len(u) > 1 else int((df["end"] - df["start"]).median())


def coverage(cd, chrom: str, bin_sizes=AUTO_BIN_SIZES) -> pd.DataFrame:
    """Per bin size: n bins, median fraction of bins a trace observes, median traces per bin pair."""
    df = trace_table(cd, chrom)
    lo, hi = df["mid"].min(), df["mid"].max()
    nat = native_bin_size(cd, chrom)
    rows = []
    for bs in sorted({nat, *[b for b in bin_sizes if b >= nat]}):
        b = df["mid"] // bs
        n_bins = int(hi // bs - lo // bs + 1)
        per_trace = b.groupby(df["trace_id"]).nunique()
        frac = per_trace / n_bins
        rows.append({"bin_size": int(bs), "n_bins": n_bins, "median_detected_frac": float(frac.median()),
                     # expected traces covering a bin pair if detection were independent
                     "median_traces_per_pair": float((frac ** 2).sum())})
    return pd.DataFrame(rows)


def choose_bin_size(cd, chrom: str, min_detected: float = MIN_DETECTED) -> int:
    """Finest bin size at which the median trace observes >= ``min_detected`` of the bins."""
    cov = coverage(cd, chrom)
    ok = cov[cov["median_detected_frac"] >= min_detected]
    return int(ok["bin_size"].iloc[0] if len(ok) else cov["bin_size"].iloc[-1])


# ------------------------------------------------------------------ tracing: statistics
def _pairs_at(mid: np.ndarray, lo: float, hi: float):
    """Index pairs (i < j) with lo <= mid[j] - mid[i] <= hi (mid sorted)."""
    j_lo = np.searchsorted(mid, mid + lo, side="left")
    j_hi = np.searchsorted(mid, mid + hi, side="right")
    cnt = np.maximum(j_hi - j_lo, 0)
    i = np.repeat(np.arange(len(mid)), cnt)
    j = np.concatenate([np.arange(a, b) for a, b in zip(j_lo, j_hi) if b > a]) if cnt.sum() else np.array([], int)
    return i, j


def distance_at_separation(cd, chrom: str, sep: float, tol: float = 0.1) -> dict:
    """3-D distance between loci whose genomic separation is sep·(1±tol), all traces pooled."""
    df = trace_table(cd, chrom)
    lo, hi = sep * (1 - tol), sep * (1 + tol)
    d_all, per_trace = [], {}
    for tid, t in df.groupby("trace_id", sort=False):
        i, j = _pairs_at(t["mid"].to_numpy(), lo, hi)
        if len(i):
            xyz = t[["x", "y", "z"]].to_numpy()
            d = np.linalg.norm(xyz[i] - xyz[j], axis=1)
            d_all.append(d)
            per_trace[tid] = (np.median(d), t["cell_id"].iloc[0])
    d = np.concatenate(d_all) if d_all else np.array([])
    pt = pd.DataFrame(per_trace, index=["med", "cell"]).T
    per_cell = pt.groupby("cell")["med"].median() if len(pt) else pd.Series(dtype=float)
    return {"chrom": chrom, "sep_bp": sep, "window_bp": [lo, hi], "unit": cd.uns.get("xyz_unit", "unknown"),
            "median_over_pairs": float(np.median(d)) if len(d) else None, "mean_over_pairs": float(d.mean()) if len(d) else None,
            "n_pairs": int(len(d)), "n_traces": int(len(pt)), "n_cells": int(len(per_cell)),
            "median_of_per_cell_medians": float(per_cell.median()) if len(per_cell) else None}


def scaling(cd, chrom: str, smin: float | None = None, smax: float | None = None, n: int = 20) -> dict:
    """Median distance vs genomic separation (log bins) and the power-law exponent d ~ s^alpha."""
    df = trace_table(cd, chrom)
    nat = native_bin_size(cd, chrom)
    span = df["mid"].max() - df["mid"].min()
    smin, smax = smin or 2 * nat, smax or span / 2
    edges = np.geomspace(smin, smax, n + 1)
    sums = [[] for _ in range(n)]
    for _, t in df.groupby("trace_id", sort=False):
        m, xyz = t["mid"].to_numpy(), t[["x", "y", "z"]].to_numpy()
        i, j = _pairs_at(m, edges[0], edges[-1])
        if not len(i):
            continue
        k = np.clip(np.searchsorted(edges, m[j] - m[i], side="right") - 1, 0, n - 1)
        d = np.linalg.norm(xyz[i] - xyz[j], axis=1)
        for b in np.unique(k):
            sums[b].append(d[k == b])
    s_mid = np.sqrt(edges[:-1] * edges[1:])
    med = np.array([np.median(np.concatenate(x)) if x else np.nan for x in sums])
    cnt = np.array([sum(len(y) for y in x) for x in sums])
    ok = np.isfinite(med) & (med > 0)
    alpha, c = np.polyfit(np.log10(s_mid[ok]), np.log10(med[ok]), 1) if ok.sum() >= 3 else (np.nan, np.nan)
    return {"chrom": chrom, "unit": cd.uns.get("xyz_unit", "unknown"), "range_bp": [float(smin), float(smax)],
            "exponent_alpha": float(alpha), "fit": "OLS of log10 median distance on log10 separation",
            "curve": [{"s_bp": float(a), "median_distance": float(b), "n_pairs": int(k)}
                      for a, b, k in zip(s_mid, med, cnt)]}


def rg_table(cd, min_spots: int = 3) -> pd.DataFrame:
    """One row per trace: trace_id, cell_id, chrom, n_loci, rg (duplicates averaged)."""
    df = trace_table(cd)
    xyz = df[["x", "y", "z"]].to_numpy()
    cen = df.groupby("trace_id")[["x", "y", "z"]].transform("mean").to_numpy()
    df["r2"] = ((xyz - cen) ** 2).sum(1)
    t = df.groupby("trace_id").agg(cell_id=("cell_id", "first"), chrom=("chrom", "first"), n_loci=("r2", "size"),
                                   ms=("r2", "mean"))
    t["rg"] = np.sqrt(t.pop("ms"))
    return t[t["n_loci"] >= min_spots].reset_index()


def rg_by_chrom(cd) -> dict:
    t = rg_table(cd)
    per_cell = t.groupby(["chrom", "cell_id"])["rg"].median()
    out = {}
    for c, g in t.groupby("chrom"):
        out[c] = {"median_over_traces": float(g["rg"].median()), "n_traces": int(len(g)),
                  "median_of_per_cell_medians": float(per_cell[c].median()), "n_cells": int(len(per_cell[c])),
                  "median_n_loci": float(g["n_loci"].median())}
    top = max(out, key=lambda c: out[c]["median_over_traces"])
    return {"unit": cd.uns.get("xyz_unit", "unknown"), "per_chrom": out, "largest_median_over_traces": top,
            "note": "Rg grows with chromosome length and with the genomic spread of detected loci; "
                    "compare chromosomes/groups at matched loci if that matters"}


# ------------------------------------------------------------------ tracing: callers
def _prepare(cd, chrom, bin_size):
    nat = native_bin_size(cd, chrom)
    if bin_size in (None, "auto"):
        bs = choose_bin_size(cd, chrom)
    elif bin_size == "native":
        bs = nat
    else:
        bs = int(float(bin_size))
    sub = bin_traces(cd, chrom, bs)          # always dedups; at native size it only averages duplicates
    cov = coverage(sub, chrom, bin_sizes=(bs,)).iloc[0].to_dict()
    return sub, int(nat), int(bs), cov


def call_tads(cd, chrom: str, bin_size="auto", window_bins: float = 4, fdr: float = 0.1, device: str = "auto") -> dict:
    """ArcFISH F-test TADs (``uchrom.strc.tad.call_tads_by_pval``) with window = window_bins × bin size."""
    from uchrom.strc.tad import TADCallerParams, call_tads_by_pval
    sub, nat, bs, cov = _prepare(cd, chrom, bin_size)
    params = TADCallerParams(window_bp=float(window_bins * bs), fdr_cutoff=fdr)
    tads = call_tads_by_pval(sub, chrom=chrom, params=params, device=device, store=False)
    lvl1 = tads[tads["level"] == 1] if len(tads) else tads
    res = {"chrom": chrom, "caller": "uchrom.strc.tad.call_tads_by_pval", "native_bin_bp": nat, "bin_size_bp": bs,
           "window_bp": params.window_bp, "fdr_cutoff": fdr, "n_traces": int(sub.n_traces),
           "coverage": cov, "n_domains_level1": int(len(lvl1)),
           "n_domains_per_level": tads.groupby("level").size().astype(int).to_dict() if len(tads) else {},
           "median_domain_bp": float((lvl1["end"] - lvl1["start"]).median()) if len(lvl1) else None,
           "domains_level1": lvl1[["start", "end", "fdr"]].to_dict("records"), "checks": []}
    _caller_checks(res, sub, nat, bs, cov)
    return res


def call_compartments(cd, chrom: str, bin_size="auto", device: str = "auto") -> dict:
    """A/B compartments (``uchrom.strc.comp.call_compartments_axes_pc``) on binned traces."""
    from uchrom.strc.comp import call_compartments_axes_pc
    sub, nat, bs, cov = _prepare(cd, chrom, bin_size)
    comp = call_compartments_axes_pc(sub, chrom=chrom, device=device)
    lab = comp["compartment"].astype(str).to_numpy()
    n_seg = int(1 + (lab[1:] != lab[:-1]).sum()) if len(lab) else 0
    res = {"chrom": chrom, "caller": "uchrom.strc.comp.call_compartments_axes_pc", "native_bin_bp": nat,
           "bin_size_bp": bs, "n_traces": int(sub.n_traces), "coverage": cov,
           "n_bins": int(len(comp)), "frac_A": float((lab == "A").mean()) if len(lab) else None, "n_segments": n_seg,
           "compartments": comp[["start", "end", "compartment", "pc2"]].to_dict("records"),
           "checks": ["A/B orientation is a convention (compact cluster = A); check against gene density or an "
                      "active histone-mark track before calling a bin 'active'"]}
    _caller_checks(res, sub, nat, bs, cov)
    return res


def _caller_checks(res, sub, nat, bs, cov):
    if sub.n_traces < MIN_TRACES:
        res["checks"].append(f"only {sub.n_traces} traces (< {MIN_TRACES}): calls are exploratory")
    if cov["median_detected_frac"] < MIN_DETECTED:
        res["checks"].append(f"median trace observes {cov['median_detected_frac']:.0%} of bins at {bs} bp: too sparse "
                             "for this resolution — bin coarser")
    if bs != nat:
        res["checks"].append(f"traces binned from {nat} bp loci to {bs} bp (coordinates averaged per trace and bin); "
                             "report both and that the caller window scales with the bin size")


# ------------------------------------------------------------------ contact maps: P(s)
def open_cooler(spec: str, cd=None, res: float | None = None):
    """A cooler from a ``uns['linked_cool'|'linked_scool']`` key or a path/URI; ``res`` picks an mcool level."""
    import cooler
    path = spec
    if cd is not None:
        for fam in ("linked_cool", "linked_scool"):
            rec = (cd.uns.get(fam) or {}).get(spec)
            if rec:
                path = str(cd.resolve_link_path(rec["path"]))
    if "::" not in path and path.endswith(".mcool"):
        levels = [int(u.rsplit("/", 1)[1]) for u in cooler.fileops.list_coolers(path)]
        r = int(float(res)) if res else min(levels)
        if r not in levels:
            raise ValueError(f"{path} has resolutions {levels}, not {r}")
        path = f"{path}::/resolutions/{r}"
    return cooler.Cooler(path)


def _chrom_matrix(clr, chrom):
    return np.asarray(clr.matrix(balance=False, sparse=True).fetch(chrom).toarray(), dtype=float)


def contact_ps(coolers, chrom: str, smin: float, smax: float, normalize: bool = True) -> dict:
    """P(s) on raw counts: per diagonal, mean contacts per bin pair; summed over ``coolers`` (pseudo-bulk);
    normalised by the total cis contacts of ``chrom`` (depth).  Slope = OLS of log10 P on log10 s over
    diagonals with smin <= s <= smax."""
    if not isinstance(coolers, (list, tuple)):
        coolers = [coolers]
    bs = {int(c.binsize) for c in coolers}
    if len(bs) != 1:
        raise ValueError(f"coolers have different bin sizes {bs}; coarsen first")
    bs = bs.pop()
    M = sum(_chrom_matrix(c, chrom) for c in coolers)
    M = np.triu(M)                                   # cooler returns the symmetric matrix
    total = float(M.sum())
    n = M.shape[0]
    k = np.arange(int(np.ceil(smin / bs)), int(np.floor(smax / bs)) + 1)
    k = k[(k >= 1) & (k < n)]
    p = np.array([np.diagonal(M, int(kk)).mean() for kk in k])
    if normalize:
        p = p / total
    s = k * bs
    ok = p > 0
    slope, icpt = np.polyfit(np.log10(s[ok]), np.log10(p[ok]), 1) if ok.sum() >= 3 else (np.nan, np.nan)
    res = {"chrom": chrom, "bin_size_bp": bs, "range_bp": [float(smin), float(smax)], "n_diagonals": int(ok.sum()),
           "total_cis_contacts": total, "n_maps_summed": len(coolers), "slope": float(slope), "intercept": float(icpt),
           "normalisation": "mean raw count per diagonal / total cis contacts of the chromosome" if normalize
           else "mean raw count per diagonal (not depth-normalised)",
           "fit": "OLS of log10 P(s) on log10 s, one point per diagonal",
           "ps": [{"s_bp": int(a), "p": float(b)} for a, b in zip(s, p)], "checks": []}
    if ok.sum() < 5:
        res["checks"].append("fewer than 5 diagonals in the fit range: slope is unstable — widen the range or use a "
                             "finer resolution")
    if total < 1e4:
        res["checks"].append(f"only {total:.0f} cis contacts: single-cell maps are sparse; pool cells (pseudo-bulk) "
                             "or report as noisy")
    return res


def compare_ps(groups: dict, chrom, smin, smax) -> dict:
    """P(s) slope per group; ``groups`` maps a name to a list of coolers (summed as pseudo-bulk)."""
    out = {g: contact_ps(c, chrom, smin, smax) for g, c in groups.items()}
    names = list(out)
    res = {"per_group": {g: {k: v for k, v in r.items() if k != "ps"} for g, r in out.items()}}
    if len(names) == 2:
        res["slope_difference"] = out[names[0]]["slope"] - out[names[1]]["slope"]
    res["checks"] = ["pseudo-bulk P(s) has no cell-level replication: no p-value from one map per group; for a test, "
                     "compute per-cell slopes (scool) and compare cells (compare-groups)"]
    return res


# ------------------------------------------------------------------ CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["dist-at", "scaling", "rg", "coverage", "tads", "comps", "ps"])
    ap.add_argument("data")
    ap.add_argument("--chrom")
    ap.add_argument("--sep", type=float)
    ap.add_argument("--tol", type=float, default=0.1)
    ap.add_argument("--bin-size", default="auto")
    ap.add_argument("--window-bins", type=float, default=4)
    ap.add_argument("--fdr", type=float, default=0.1)
    ap.add_argument("--cool", help="comma-separated linked_cool / linked_scool keys summed as one map")
    ap.add_argument("--cells", help="with a linked_scool key: comma-separated cell names to sum")
    ap.add_argument("--res", type=float)
    ap.add_argument("--smin", type=float)
    ap.add_argument("--smax", type=float)
    a = ap.parse_args()
    from uchrom.core import ChromData
    if a.cmd == "ps":
        cd = ChromData.read(a.data) if a.data.endswith(".h5cd") else None
        if cd is None:
            clrs = [open_cooler(a.data, res=a.res)]
        elif a.cells:
            import cooler
            key = a.cool or next(iter(cd.uns.get("linked_scool", {})))
            p = cd.resolve_link_path(cd.uns["linked_scool"][key]["path"])
            clrs = [cooler.Cooler(f"{p}::/cells/{c}") for c in a.cells.split(",")]
        else:
            clrs = [open_cooler(k, cd, a.res) for k in a.cool.split(",")]
        out = contact_ps(clrs, a.chrom, a.smin, a.smax)
    else:
        cd = ChromData.read(a.data)
        if a.cmd == "dist-at":
            out = distance_at_separation(cd, a.chrom, a.sep, a.tol)
        elif a.cmd == "scaling":
            out = scaling(cd, a.chrom, a.smin, a.smax)
        elif a.cmd == "rg":
            out = rg_by_chrom(cd)
        elif a.cmd == "coverage":
            out = coverage(cd, a.chrom).to_dict("records")
        elif a.cmd == "tads":
            out = call_tads(cd, a.chrom, a.bin_size, a.window_bins, a.fdr)
        else:
            out = call_compartments(cd, a.chrom, a.bin_size)
    json.dump(out, sys.stdout, indent=1, default=float)
    print()


if __name__ == "__main__":
    main()
