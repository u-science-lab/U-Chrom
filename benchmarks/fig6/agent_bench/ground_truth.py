"""Reference answers for the Fig 6e agent benchmark (questions.yaml), computed with scripted uchrom analyses.

    python benchmarks/fig6/agent_bench/ground_truth.py --data-root <example-data dir> [--only A1,C1,…]

Writes ``answers.json``: question id → {"values": {...}, "notes": "..."}.  Each function below is named in
questions.yaml (`truth:`).  Statistics follow the benchmark's conventions: the cell is the unit for
cell-level comparisons (per-cell median over traces), Mann–Whitney two-sided, Spearman for association.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

from uchrom.core import ChromData
from uchrom.fea.distance import radius_of_gyration

HERE = Path(__file__).resolve().parent
DATA = {"takei": "takei2025_fov0/takei2025_fov0.chromdata.zarr", "schicar": "schicar_mop/schicar_mop.chromdata.zarr",
        "sim": "sim_cell1/sim_cell1.cdz"}
_CACHE: dict = {}


def load(root: Path, key: str) -> ChromData:
    if key not in _CACHE:
        _CACHE[key] = ChromData.read(str(root / DATA[key]))
    return _CACHE[key]


def spots_df(cd: ChromData) -> pd.DataFrame:
    df = cd.spots.copy()
    df[["x", "y", "z"]] = np.asarray(cd.coords, float)
    return df


def cell_rg(cd: ChromData) -> pd.Series:
    """Median trace Rg per cell (all chromosomes)."""
    df = spots_df(cd)
    rg = radius_of_gyration(df)
    cell = df.groupby("trace_id", observed=True)["cell_id"].first().astype(str)
    return pd.Series(rg.to_numpy(), index=cell.reindex(rg.index).to_numpy()).groupby(level=0).median()


def ids(cd):
    return cd.cells.index.astype(str)


# ------------------------------------------------------------------ A
def counts(root):
    cd = load(root, "takei")
    return {"n_cells": int(cd.n_cells), "n_traces": int(cd.n_traces), "n_spots": int(cd.n_spots)}


def n_if_channels(root):
    cd = load(root, "takei")
    cols = [c for c in cd.cells.columns if c.startswith("if.")]
    return {"n": len(cols), "channels": cols}


def scool_cells(root):
    import cooler
    cd = load(root, "schicar")
    link = cd.uns["linked_scool"]["per_cell"]
    path = root / "schicar_mop" / link["path"]
    cells = cooler.fileops.list_scool_cells(str(path))
    c = cooler.Cooler(f"{path}::{cells[0]}")
    return {"n_cells": len(cells), "resolution_bp": int(c.binsize), "n_cells_in_table": int(cd.n_cells)}


# ------------------------------------------------------------------ B
def dist_at_1mb(root, chrom="chr15"):
    cd = load(root, "takei")
    df = spots_df(cd)
    df = df[df["chrom"].astype(str) == chrom]
    out = []
    for _, t in df.groupby("trace_id", observed=True):
        if len(t) < 2:
            continue
        mid = ((t["start"] + t["end"]) / 2).to_numpy()
        xyz = t[["x", "y", "z"]].to_numpy()
        sep = np.abs(mid[:, None] - mid[None])
        i, j = np.nonzero(np.triu((sep >= 0.9e6) & (sep <= 1.1e6), 1))
        if len(i):
            out.append(np.linalg.norm(xyz[i] - xyz[j], axis=1))
    d = np.concatenate(out)
    d = d[np.isfinite(d)]
    return {"median_um": float(np.median(d)), "n_pairs": int(len(d))}


def rg_by_chrom(root):
    cd = load(root, "takei")
    df = spots_df(cd)
    rg = radius_of_gyration(df)
    chrom = df.groupby("trace_id", observed=True)["chrom"].first().astype(str)
    med = pd.Series(rg.to_numpy(), index=chrom.reindex(rg.index).to_numpy()).groupby(level=0).median()
    return {"top_chrom": str(med.idxmax()), "top_median": float(med.max()),
            "by_chrom": {k: round(float(v), 3) for k, v in med.sort_values(ascending=False).items()}}


# ------------------------------------------------------------------ C
def _compare(a: pd.Series, b: pd.Series):
    u = st.mannwhitneyu(a, b, alternative="two-sided")
    return {"median_a": float(a.median()), "median_b": float(b.median()), "n_a": int(len(a)), "n_b": int(len(b)),
            "p": float(u.pvalue), "rank_biserial": float(2 * u.statistic / (len(a) * len(b)) - 1)}


def rg_bergmann_vs_granule(root):
    cd = load(root, "takei")
    r = cell_rg(cd)
    ct = pd.Series(cd.cells["cell_type"].astype(str).to_numpy(), index=ids(cd))
    res = _compare(r[ct[ct == "Bergmann"].index], r[ct[ct == "Granule"].index])
    both = r[ct[ct.isin(["Bergmann", "Granule"])].index]
    vol = pd.Series(cd.cells["nuc_volume_um3"].to_numpy(), index=ids(cd))[both.index]
    res["rho_rg_nuclear_volume"] = float(st.spearmanr(both, vol).statistic)
    return res


def rg_purkinje_vs_granule(root):
    cd = load(root, "takei")
    r = cell_rg(cd)
    ct = pd.Series(cd.cells["cell_type"].astype(str).to_numpy(), index=ids(cd))
    res = _compare(r[ct[ct == "Purkinje"].index], r[ct[ct == "Granule"].index])
    # what a trace-level (pseudo-replicated) test would claim
    df = spots_df(cd)
    rg = radius_of_gyration(df)
    cell = df.groupby("trace_id", observed=True)["cell_id"].first().astype(str).reindex(rg.index)
    cty = cell.map(ct)
    res["trace_level_p"] = float(st.mannwhitneyu(rg[cty == "Purkinje"], rg[cty == "Granule"]).pvalue)
    return res


def top_if_bergmann(root):
    cd = load(root, "takei")
    c = cd.cells
    sel = c["cell_type"].astype(str) == "Bergmann"
    rows = []
    for col in [x for x in c.columns if x.startswith("if.")]:
        a, b = c.loc[sel, col].dropna(), c.loc[~sel, col].dropna()
        rows.append((col, st.mannwhitneyu(a, b).pvalue, a.median(), b.median()))
    r = pd.DataFrame(rows, columns=["mark", "p", "med_bergmann", "med_other"]).sort_values("p")
    r["q"] = np.minimum(1, r["p"] * len(r) / np.arange(1, len(r) + 1))
    top = r.iloc[0]
    return {"mark": top["mark"].replace("if.", ""), "p": float(top["p"]), "q": float(top["q"]),
            "n_significant_q05": int((r["q"] < 0.05).sum())}


# ------------------------------------------------------------------ D
def h3k9me3_vs_rg_cells(root):
    cd = load(root, "takei")
    r = cell_rg(cd)
    c = cd.cells.set_axis(ids(cd))
    x = c.loc[r.index, "if.H3K9me3"]
    v = c.loc[r.index, "nuc_volume_um3"]
    rho = st.spearmanr(x, r)
    # partial Spearman given nuclear volume (ranks, residuals)
    R = pd.DataFrame({"x": x.rank(), "y": r.rank(), "v": v.rank()})
    res = lambda a: a - np.polyval(np.polyfit(R["v"], a, 1), R["v"])
    partial = st.pearsonr(res(R["x"]), res(R["y"])).statistic
    return {"rho": float(rho.statistic), "p": float(rho.pvalue), "n_cells": int(len(r)),
            "partial_rho_given_nuclear_volume": float(partial)}


def contacts_vs_rna(root):
    cd = load(root, "schicar")
    c = cd.cells
    rho = st.spearmanr(c["n_contacts_hic"], c["n_counts_rna"])
    within = []
    for t, g in c.groupby(c["cell_type"].astype(str)):
        if len(g) >= 30:
            within.append((t, len(g), st.spearmanr(g["n_contacts_hic"], g["n_counts_rna"]).statistic))
    w = pd.DataFrame(within, columns=["type", "n", "rho"])
    return {"rho": float(rho.statistic), "p": float(rho.pvalue), "n_cells": int(len(c)),
            "median_within_type_rho": float(w["rho"].median()), "n_types": int(len(w))}


FUNCS = {f.__name__: f for f in [counts, n_if_channels, scool_cells, dist_at_1mb, rg_by_chrom,
                                 rg_bergmann_vs_granule, rg_purkinje_vs_granule, top_if_bergmann,
                                 h3k9me3_vs_rg_cells, contacts_vs_rna]}


# ================================================================== helpers for the remaining questions
L23 = ("L23IT.1", "L23IT.2", "L23IT.3")      # scHiCAR L2/3 IT subtypes, pooled for "L2/3 IT neurons"
OLIGO = "Oligo"


def cell_type(cd) -> pd.Series:
    return pd.Series(cd.cells["cell_type"].astype(str).to_numpy(), index=ids(cd))


def cell_col(cd, col) -> pd.Series:
    return pd.Series(cd.cells[col].to_numpy(), index=ids(cd))


def trace_cells(df) -> pd.Series:
    return df.groupby("trace_id", observed=True)["cell_id"].first().astype(str)


def per_cell_median_rg(df) -> pd.Series:
    """Per-cell median of per-trace Rg (uchrom.fea.distance.radius_of_gyration) for a spots+xyz frame."""
    rg = radius_of_gyration(df)
    return rg.groupby(trace_cells(df).reindex(rg.index).to_numpy()).median()


def spearman(a, b):
    r = st.spearmanr(a, b, nan_policy="omit")
    return float(r.statistic), float(r.pvalue)


def loglog_slope(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = (x > 0) & (y > 0) & np.isfinite(x) & np.isfinite(y)
    return float(np.polyfit(np.log10(x[ok]), np.log10(y[ok]), 1)[0]), int(ok.sum())


def cis_matrix(clr, chrom):
    return np.asarray(clr.matrix(balance=False).fetch(chrom), float)


def ps_curve(m, dmin, dmax):
    """Mean raw count per diagonal offset d (bins), d in [dmin, dmax]; also returns d."""
    d = np.arange(dmin, dmax + 1)
    return d, np.array([np.diagonal(m, k).mean() for k in d])


def coarsen(m, f):
    n = m.shape[0] // f * f
    extra = m.shape[0] - n
    if extra:     # pad a partial last bin
        m = np.pad(m, ((0, f - extra), (0, f - extra)))
        n = m.shape[0]
    return m.reshape(n // f, f, n // f, f).sum(axis=(1, 3))


def schicar_path(root, rel):
    return root / "schicar_mop" / rel


def binned_chrom(cd, chrom, bin_bp=1_000_000):
    """Coarse-grain one chromosome: per trace, mean xyz of its spots inside each ``bin_bp`` bin → ChromData."""
    df = spots_df(cd)
    df = df[df["chrom"].astype(str) == chrom].copy()
    df["b"] = ((df["start"] + df["end"]) // 2) // bin_bp
    g = df.groupby(["trace_id", "b"], observed=True).agg(x=("x", "mean"), y=("y", "mean"), z=("z", "mean"),
                                                          cell_id=("cell_id", "first"), n=("x", "size")).reset_index()
    spots = pd.DataFrame({"chrom": chrom, "start": (g["b"] * bin_bp).astype(np.int64),
                          "end": ((g["b"] + 1) * bin_bp).astype(np.int64),
                          "trace_id": g["trace_id"].astype(str), "cell_id": g["cell_id"].astype(str)})
    return ChromData(coords=g[["x", "y", "z"]].to_numpy(float), spots=spots), df


# ------------------------------------------------------------------ A (remaining)
def largest_cell_type(root):
    cd = load(root, "takei")
    vc = cd.cells["cell_type"].astype(str).value_counts()
    return {"cell_type": str(vc.index[0]), "n": int(vc.iloc[0]), "counts": {k: int(v) for k, v in vc.items()}}


def top_chrom(root):
    cd = load(root, "takei")
    vc = cd.spots["chrom"].astype(str).value_counts()
    return {"chrom": str(vc.index[0]), "n_spots": int(vc.iloc[0]), "runner_up": [str(vc.index[1]), int(vc.iloc[1])]}


def schicar_top_type(root):
    import h5py
    cd = load(root, "schicar")
    c = cd.cells
    vc = c["cell_type"].astype(str).value_counts()
    top = str(vc.index[0])
    sel = c["cell_type"].astype(str) == top
    # cross-check: contacts actually stored in the linked per-cell .scool (1 Mb, symmetric-upper, all chroms)
    path = schicar_path(root, cd.uns["linked_scool"]["per_cell"]["path"])
    with h5py.File(path, "r") as f:
        scool_sum = pd.Series({k: int(f["cells"][k].attrs["sum"]) for k in c.index[sel].astype(str)})
    return {"cell_type": top, "n": int(vc.iloc[0]), "median_contacts": float(c.loc[sel, "n_contacts_hic"].median()),
            "median_scool_pixel_sum": float(scool_sum.median()),
            "note": "median_contacts = cells['n_contacts_hic'] (per-cell Hi-C contact count stored with the cell "
                    "metadata); the per-cell .scool pixel sums (1 Mb, all chromosomes) are given for context "
                    "and differ because the .scool keeps only binned cis+trans contacts on the 21 chromosomes."}


def bond_length(root):
    cd = load(root, "sim")
    df = spots_df(cd)
    df = df[df["chrom"].astype(str) == "chr1"].sort_values("start")
    xyz = df[["x", "y", "z"]].to_numpy()
    d = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
    return {"median": float(np.median(d)), "unit": str(cd.uns.get("xyz_unit")), "n_particles": int(len(df)),
            "particle_bp": float(np.median(df["end"] - df["start"])), "mean": float(d.mean())}


def units(root):
    cd = load(root, "takei")
    return {"xyz_unit": str(cd.uns["xyz_unit"]), "genome_assembly": str(cd.uns["genome_assembly"])}


# ------------------------------------------------------------------ B (remaining)
def _pair_table(df, lo, hi):
    """All within-trace spot pairs with bin-midpoint separation in [lo, hi] bp → (sep, dist)."""
    seps, dists = [], []
    for _, t in df.groupby("trace_id", observed=True):
        mid = ((t["start"] + t["end"]) / 2).to_numpy()
        xyz = t[["x", "y", "z"]].to_numpy()
        i, j = np.triu_indices(len(t), 1)
        s = np.abs(mid[i] - mid[j])
        k = (s >= lo) & (s <= hi)
        seps.append(s[k])
        dists.append(np.linalg.norm(xyz[i[k]] - xyz[j[k]], axis=1))
    return np.concatenate(seps), np.concatenate(dists)


def scaling_exponent(root, chrom="chr15", n_bins=20):
    cd = load(root, "takei")
    df = spots_df(cd)
    df = df[df["chrom"].astype(str) == chrom]
    s, d = _pair_table(df, 1e6, 20e6)
    out = {}
    for nb in sorted({n_bins, 10, 40}):
        edges = np.logspace(6, np.log10(20e6), nb + 1)
        k = np.clip(np.digitize(s, edges) - 1, 0, nb - 1)
        xs = [np.median(s[k == b]) for b in range(nb)]
        ys = [np.median(d[k == b]) for b in range(nb)]
        out[nb] = loglog_slope(xs, ys)[0]
    return {"exponent": out[n_bins], "n_pairs": int(len(s)),
            "exponent_10_bins": out[10], "exponent_40_bins": out[40],
            "method": f"all within-trace spot pairs on {chrom} (all traces), separation = bin-midpoint difference in "
                      f"[1, 20] Mb; {n_bins} log-spaced separation bins; median 3-D distance and median separation "
                      "per bin; OLS of log10(distance) on log10(separation)"}


def ps_slope(root, chrom="chr1"):
    import cooler
    clr = cooler.Cooler(str(root / "sim_cell1" / "cell1_contacts.mcool") + "::/resolutions/1000000")
    m = cis_matrix(clr, chrom)
    d, p = ps_curve(m, 2, 20)
    slope, n = loglog_slope(d * 1e6, p)
    return {"slope": slope, "n_offsets_used": n, "resolution_bp": int(clr.binsize),
            "method": "sim_cell1/cell1_contacts.mcool::/resolutions/1000000, raw counts; P(s) = mean count on "
                      "diagonal offset d = 2..20 bins (2-20 Mb) of the chr1 cis map; OLS log10 P vs log10 s"}


def contacts_vs_distance(root, chrom="chr1"):
    import cooler
    cd = load(root, "sim")
    clr = cooler.Cooler(str(root / "sim_cell1" / "cell1_contacts.mcool") + "::/resolutions/1000000")
    m = cis_matrix(clr, chrom)
    df = spots_df(cd)
    df = df[df["chrom"].astype(str) == chrom]
    b = (((df["start"] + df["end"]) // 2) // clr.binsize).to_numpy()
    cen = df[["x", "y", "z"]].groupby(b).mean()
    idx = cen.index.to_numpy()
    xyz = cen.to_numpy()
    i, j = np.triu_indices(len(idx), 1)
    cnt = m[idx[i], idx[j]]
    dist = np.linalg.norm(xyz[i] - xyz[j], axis=1)
    k = cnt > 0
    rho, p = spearman(cnt[k], dist[k])
    rho_all, _ = spearman(cnt, dist)
    return {"rho": rho, "p": p, "n_pairs": int(k.sum()), "rho_all_pairs_incl_zero": rho_all,
            "method": "chr1 particles grouped into the mcool's 1 Mb bins (by particle midpoint); 3-D distance "
                      "between bin centroids; Spearman(count, distance) over off-diagonal bin pairs with count > 0"}


def long_range_fraction(root, chrom="chr1"):
    import cooler
    path = schicar_path(root, "contacts_all.mcool")
    out = {}
    for res in (1_000_000, 250_000):
        clr = cooler.Cooler(f"{path}::/resolutions/{res}")
        m = np.triu(cis_matrix(clr, chrom))
        dd = np.subtract.outer(np.arange(len(m)), np.arange(len(m))) * -1   # j - i
        out[res] = float(m[dd * res > 10e6].sum() / m.sum()), float(m.sum())
    return {"fraction": out[1_000_000][0], "fraction_250kb": out[250_000][0],
            "total_chr1_contacts": out[1_000_000][1],
            "method": "linked all-cell pseudo-bulk contacts_all.mcool (uns['linked_cool']['all_cells']), 1 Mb, raw "
                      "counts, chr1 cis upper triangle incl. diagonal; fraction of counts with bin separation "
                      "> 10 Mb (i.e. >= 11 bins); 250 kb value for context. The .scool was not summed."}


def tads_arcfish(root, chrom="chr15"):
    from uchrom.strc.tad import TADCallerParams, call_tads_by_pval
    cd = load(root, "takei")
    cdb, df = binned_chrom(cd, chrom)
    n_bins_native = int(df["start"].nunique())
    res = {}
    for w in (1e5, 4e6):
        t = call_tads_by_pval(cdb, chrom=chrom, params=TADCallerParams(window_bp=w), device="cpu", key_added=None)
        res[w] = t
    t = res[4e6]
    lvl1 = t[t["level"] == 1] if len(t) else t
    return {"n_domains": int(len(lvl1)), "n_boundaries": max(int(len(lvl1)) - 1, 0),
            "n_domains_default_window_1e5": int((res[1e5]["level"] == 1).sum()) if len(res[1e5]) else 0,
            "domains_level1": [[int(a), int(b)] for a, b in zip(lvl1.get("start", []), lvl1.get("end", []))],
            "method": "uchrom.strc.tad.call_tads_by_pval(cd_chr15_1Mb, 'chr15', TADCallerParams(window_bp=4e6), "
                      "device='cpu'); all other params default (fdr_cutoff=0.1, hierarchical, max_levels=4, "
                      "k_sigma=4, frac=0.1); n_domains = level-1 (finest) partition",
            "note": f"ILL-POSED as worded: at native 25 kb chr15 has {n_bins_native} bins and only ~3 traces per bin; "
                    "the caller's (3, n_traces, B, B) tensor would need >10 GB per copy and most bin pairs have <2 "
                    "co-observations. Closest faithful version: each trace's spots averaged per 1 Mb bin, and the "
                    "boundary window scaled to 4 bins (the default 100 kb window = 4 bins at 25 kb); the literal "
                    "default window (100 kb) on 1 Mb bins yields no candidate boundaries."}


def compartments_h3k27ac(root, chrom="chr15"):
    from uchrom.strc.comp import call_compartments_axes_pc
    cd = load(root, "takei")
    cdb, df = binned_chrom(cd, chrom)
    comp = call_compartments_axes_pc(cdb, chrom=chrom, device="cpu", key_added=None)
    tr = cd.spot_tracks.loc[df.index, "H3K27ac"]
    k27 = tr.groupby(df["b"].to_numpy()).mean()
    comp["H3K27ac"] = k27.reindex((comp["start"] // 1_000_000).to_numpy()).to_numpy()
    by = comp.groupby("compartment")["H3K27ac"].mean()
    active = str(by.idxmax())
    frac = float((comp["compartment"] == active).mean())
    a, b = comp.loc[comp["compartment"] == active, "H3K27ac"], comp.loc[comp["compartment"] != active, "H3K27ac"]
    return {"fraction": frac, "n_bins": int(len(comp)), "caller_label_of_high_H3K27ac": active,
            "caller_label_agrees_with_H3K27ac": active == "A",
            "mean_H3K27ac_by_caller_label": {k: float(v) for k, v in by.items()},
            "mwu_p_H3K27ac_between_compartments": float(st.mannwhitneyu(a, b).pvalue),
            "method": "uchrom.strc.comp.call_compartments_axes_pc(cd_chr15_1Mb, 'chr15', device='cpu') with default "
                      "CompartmentCallerParams; per-bin mean of the per-spot H3K27ac track; the cluster with higher "
                      "mean H3K27ac is A",
            "note": "caller run on 1 Mb bins (each trace's spots averaged per bin): the native 25 kb chr15 (3,829 "
                    "bins, ~3 traces/bin) is infeasible in memory and too sparse. The caller's own A/B label is a "
                    "compaction convention; A is re-assigned here by H3K27ac."}


# ------------------------------------------------------------------ C (remaining)
def h3k9me3_granule_vs_bergmann(root):
    cd = load(root, "takei")
    ct, x = cell_type(cd), cell_col(cd, "if.H3K9me3")
    r = _compare(x[ct == "Granule"], x[ct == "Bergmann"])
    r["group_a"], r["group_b"] = "Granule", "Bergmann"
    r["direction"] = "granule higher" if r["median_a"] > r["median_b"] else "granule lower"
    return r


def nucvol_bergmann_vs_granule(root):
    cd = load(root, "takei")
    ct, x = cell_type(cd), cell_col(cd, "nuc_volume_um3")
    r = _compare(x[ct == "Bergmann"], x[ct == "Granule"])
    r["group_a"], r["group_b"], r["unit"] = "Bergmann", "Granule", "um^3"
    r["direction"] = "Bergmann larger" if r["median_a"] > r["median_b"] else "Bergmann smaller"
    return r


def contacts_oligo_vs_l23(root):
    cd = load(root, "schicar")
    ct, x = cell_type(cd), cell_col(cd, "n_contacts_hic")
    r = _compare(x[ct == OLIGO], x[ct.isin(L23)])
    r["group_a"], r["group_b"] = OLIGO, "+".join(L23) + " (pooled)"
    r["per_subtype_median"] = {t: float(x[ct == t].median()) for t in L23}
    r["direction"] = "Oligo more" if r["median_a"] > r["median_b"] else "Oligo fewer"
    return r


def ps_oligo_vs_l23(root, chrom="chr1"):
    import cooler
    lc = load(root, "schicar").uns["linked_cool"]

    def slope(keys, res_factor=1):
        m = sum(cis_matrix(cooler.Cooler(str(schicar_path(root, lc[k]["path"]))), chrom) for k in keys)
        bs = cooler.Cooler(str(schicar_path(root, lc[keys[0]]["path"]))).binsize
        if res_factor > 1:
            m = coarsen(m, res_factor)
            bs *= res_factor
        m_u = np.triu(m)
        d, p = ps_curve(m, int(1e6 // bs), int(10e6 // bs))
        p = p / m_u.sum()                       # depth-normalised: fraction of chr1 cis contacts
        return loglog_slope(d * bs, p)[0], float(m_u.sum()), int(bs)

    a, b = slope(["type_Oligo"]), slope([f"type_{t.replace('.', '_')}" for t in L23])
    a1, b1 = slope(["type_Oligo"], 2), slope([f"type_{t.replace('.', '_')}" for t in L23], 2)
    return {"slope_a": a[0], "slope_b": b[0], "group_a": OLIGO, "group_b": "L23IT.1+2+3 (summed cools)",
            "chr1_cis_contacts_a": a[1], "chr1_cis_contacts_b": b[1], "resolution_bp": a[2],
            "slope_a_1Mb": a1[0], "slope_b_1Mb": b1[0],
            "method": "linked per-type pseudo-bulk cools (uns['linked_cool'], native 500 kb, raw counts); L2/3 IT = "
                      "sum of the three L23IT subtype cools; P(s) = mean count per diagonal offset / total chr1 cis "
                      "contacts (depth-normalised), s = 1-10 Mb (offsets 2..20); OLS log10 P vs log10 s"}


def rg_size_adjusted(root, chrom="chr15"):
    cd = load(root, "takei")
    df = spots_df(cd)
    rg = per_cell_median_rg(df[df["chrom"].astype(str) == chrom])
    ct, vol = cell_type(cd), cell_col(cd, "nuc_volume_um3")
    adj = rg / vol.reindex(rg.index) ** (1 / 3)
    g, p = ct.reindex(rg.index) == "Granule", ct.reindex(rg.index) == "Purkinje"
    raw, sz = _compare(rg[g], rg[p]), _compare(adj[g], adj[p])
    return {"group_a": "Granule", "group_b": "Purkinje",
            "median_rg_a": raw["median_a"], "median_rg_b": raw["median_b"], "p_raw": raw["p"],
            "rank_biserial_raw": raw["rank_biserial"],
            "median_adj_a": sz["median_a"], "median_adj_b": sz["median_b"], "p_adjusted": sz["p"],
            "rank_biserial_adjusted": sz["rank_biserial"], "n_a": raw["n_a"], "n_b": raw["n_b"],
            "median_nuc_volume_a": float(vol[ct == "Granule"].median()),
            "median_nuc_volume_b": float(vol[ct == "Purkinje"].median()),
            "method": f"{chrom} traces only; per-cell median trace Rg; size adjustment = Rg / nuc_volume_um3^(1/3) "
                      "(Rg in units of nuclear radius scale); Mann-Whitney two-sided; n_b = 3 is too few"}


def selection_vs_rest(root):
    cd = load(root, "takei")
    sel_ids = ["1_0_34", "1_0_61", "1_0_95", "1_0_119", "1_0_217", "1_0_269", "1_0_270", "1_0_272"]
    c = cd.cells.set_axis(ids(cd))
    sel = c.index.isin(sel_ids)
    types = c.loc[sel, "cell_type"].astype(str).value_counts()
    rows = []
    for col in [x for x in c.columns if x.startswith("if.")] + ["nuc_volume_um3"]:
        a, b = c.loc[sel, col].dropna(), c.loc[~sel, col].dropna()
        u = st.mannwhitneyu(a, b)
        rows.append((col, u.pvalue, a.median(), b.median(), 2 * u.statistic / (len(a) * len(b)) - 1))
    r = pd.DataFrame(rows, columns=["field", "p", "med_sel", "med_rest", "r"]).sort_values("p")
    r["q"] = np.minimum.accumulate((r["p"] * len(r) / np.arange(1, len(r) + 1))[::-1])[::-1].clip(upper=1)
    top = r.iloc[0]
    return {"identity_bergmann": f"all {int(types.get('Bergmann', 0))}/{int(sel.sum())} selected cells are Bergmann "
                                 f"glia (= every Bergmann cell in the FOV: {int((c['cell_type'] == 'Bergmann').sum())})",
            "top_mark_sox2": top["field"].replace("if.", ""), "top_p": float(top["p"]), "top_q": float(top["q"]),
            "top_rank_biserial": float(top["r"]), "n_sel": int(sel.sum()), "n_rest": int((~sel).sum()),
            "selected_types": {k: int(v) for k, v in types.items()},
            "top5": [[f, float(q), float(rr)] for f, q, rr in r[["field", "q", "r"]].head(5).to_numpy()],
            "n_significant_q05": int((r["q"] < 0.05).sum()),
            "method": "cell-level Mann-Whitney (selected vs other 39 cells) on each if.* field + nuclear volume, "
                      "BH-FDR across 49 fields"}


def rna_counts_top(root):
    cd = load(root, "schicar")
    ct, x = cell_type(cd), cell_col(cd, "n_counts_rna")
    med = x.groupby(ct).median().sort_values(ascending=False)
    t1, t2 = med.index[0], med.index[1]
    r = _compare(x[ct == t1], x[ct == t2])
    pooled = x.groupby(ct.replace({t: "L23IT" for t in L23})).median().sort_values(ascending=False)
    return {"cell_type": str(t1), "runner_up": str(t2), **r,
            "top5_medians": {k: float(v) for k, v in med.head(5).items()},
            "top_with_L23IT_pooled": str(pooled.index[0]),
            "method": "per-cell n_counts_rna; rank types by median; Mann-Whitney two-sided top vs runner-up"}


# ------------------------------------------------------------------ D (remaining)
def laminb1_vs_radial_spots(root):
    cd = load(root, "takei")
    t = cd.spot_tracks
    rho, p = spearman(t["LaminB1"], t["n_rad_score"])
    df = spots_df(cd)
    cen = df.groupby("cell_id", observed=True)[["x", "y", "z"]].transform("mean").to_numpy()
    dcen = np.linalg.norm(df[["x", "y", "z"]].to_numpy() - cen, axis=1)
    rho_per, _ = spearman(t["LaminB1"], t["n_per_dist(um)"])
    within = [spearman(g["LaminB1"], g["n_rad_score"])[0] for _, g in t.groupby(cd.spots["cell_id"].to_numpy())]
    return {"rho": rho, "p": p, "n_spots": int(len(t)),
            "rho_laminb1_vs_distance_to_periphery_um": rho_per,
            "median_within_cell_rho": float(np.median(within)),
            "n_rad_score_meaning": "larger = more peripheral (Spearman with distance from the cell's spot centroid "
                                   f"= {spearman(t['n_rad_score'], dcen)[0]:.2f}; with n_per_dist(um) = "
                                   f"{spearman(t['n_rad_score'], t['n_per_dist(um)'])[0]:.2f})",
            "direction": "higher LaminB1 -> more peripheral" if rho > 0 else "higher LaminB1 -> more central",
            "method": "spot level, all 383,674 spots: Spearman(tracks.LaminB1, tracks.n_rad_score)"}


def h3k27ac_vs_radial_bins(root, chrom="chr15"):
    cd = load(root, "takei")
    m = (cd.spots["chrom"].astype(str) == chrom).to_numpy()
    s, t = cd.spots[m], cd.spot_tracks[m]
    b = (((s["start"] + s["end"]) // 2) // 1_000_000).to_numpy()
    g = t[["H3K27ac", "n_rad_score"]].groupby(b).mean()
    rho, p = spearman(g["H3K27ac"], g["n_rad_score"])
    return {"rho": rho, "p": p, "n_bins": int(len(g)),
            "direction": "more H3K27ac -> more central" if rho < 0 else "more H3K27ac -> more peripheral",
            "method": "bin level: chr15 spots of all cells grouped into 1 Mb bins; per-bin mean H3K27ac and mean "
                      "n_rad_score (larger = more peripheral); Spearman across bins. rho < 0 means more central."}


def nucvol_vs_rg(root):
    cd = load(root, "takei")
    r = cell_rg(cd)
    v = cell_col(cd, "nuc_volume_um3").reindex(r.index)
    rho, p = spearman(v, r)
    lr = st.linregress(v, r)
    return {"rho": rho, "p": p, "n_cells": int(len(r)), "slope_um_per_um3": float(lr.slope),
            "intercept_um": float(lr.intercept), "pearson_r": float(lr.rvalue),
            "method": "cell level: per-cell median trace Rg (all chromosomes) vs nuc_volume_um3; Spearman; OLS slope"}


def knn_purity(root, k=15):
    from sklearn.neighbors import NearestNeighbors
    cd = load(root, "schicar")
    ct = cd.cells["cell_type"].astype(str).to_numpy()
    ct_pool = np.where(np.isin(ct, L23), "L23IT", ct)

    def purity(key, labels):
        X = np.asarray(cd.cellm[key], float)
        nn = NearestNeighbors(n_neighbors=k + 1).fit(X)
        _, idx = nn.kneighbors(X)
        nb = np.array([row[row != i][:k] for i, row in enumerate(idx)])
        return float((labels[nb] == labels[:, None]).mean())

    return {"purity_hic": purity("hic_umap", ct), "purity_rna": purity("rna_umap", ct),
            "purity_hic_L23IT_pooled": purity("hic_umap", ct_pool),
            "purity_rna_L23IT_pooled": purity("rna_umap", ct_pool), "n_cells": int(len(ct)),
            "n_types": int(len(set(ct))),
            "method": f"cellm['hic_umap'] / cellm['rna_umap']; {k} nearest neighbours (Euclidean, self excluded); "
                      "purity = mean fraction of neighbours with the same cells['cell_type'] (22 labels as given)"}


def mobp_atac_rna(root):
    cd = load(root, "schicar")
    c = cd.cells
    rho, p = spearman(c["atac.Mobp"], c["rna.Mobp"])
    within = {}
    for t, g in c.groupby(c["cell_type"].astype(str)):
        if len(g) >= 30:
            within[t] = spearman(g["atac.Mobp"], g["rna.Mobp"])[0]
    w = pd.Series(within)
    return {"rho_all": rho, "p": p, "n_cells": int(len(c)), "median_within_type_rho": float(w.median()),
            "n_types": int(len(w)), "n_types_defined": int(w.notna().sum()),
            "rho_oligo": float(within.get(OLIGO, np.nan)),
            "within_type": {k: (round(float(v), 3) if np.isfinite(v) else None) for k, v in within.items()},
            "method": "cell level Spearman(atac.Mobp, rna.Mobp); within each cell type with >= 30 cells; median of "
                      "the defined within-type rhos (NaN where a type has constant values)"}


def sox2_rg_within_bergmann(root):
    cd = load(root, "takei")
    r = cell_rg(cd)
    ct = cell_type(cd).reindex(r.index)
    rb = r[ct == "Bergmann"]
    x = cell_col(cd, "if.SOX2").reindex(rb.index)
    rho, p = spearman(x, rb)
    return {"rho": rho, "p": p, "n_cells": int(len(rb)),
            "method": "Bergmann cells only; per-cell if.SOX2 vs per-cell median trace Rg; Spearman (n = 8)"}


# ------------------------------------------------------------------ E
def alleles_per_chrom(root):
    cd = load(root, "takei")
    s = cd.spots
    tr = s.groupby("trace_id", observed=True)[["cell_id", "chrom"]].first().astype(str)
    allele = tr.index.astype(str).str.extract(r"_a(-?\d+)$")[0].astype(int).to_numpy()
    n = tr.groupby(["cell_id", "chrom"]).size()
    dist = n.value_counts().sort_index()
    trc = cd.traces
    return {"frac_cell_chrom_gt2": float((n > 2).mean()), "n_cell_chrom_pairs": int(len(n)),
            "distribution": {int(k): int(v) for k, v in dist.items()}, "max": int(n.max()),
            "n_traces": int(len(tr)), "allele_suffix_counts": {int(k): int(v) for k, v in
                                                               pd.Series(allele).value_counts().sort_index().items()},
            "n_unassigned_traces_in_data": int((allele == -1).sum()),
            "allele_col_used": str(cd.uns.get("allele_col")), "keep_unclustered": str(cd.uns.get("keep_unclustered")),
            "traces_table_minus1": {c: int((trc[c] == -1).sum()) for c in trc.columns},
            "note": "trace ids come from uns['allele_col'] (dbscan_ldp_nbr_allele); unassigned (-1) spots were "
                    "dropped at load (keep_unclustered=False), so no trace has suffix a-1. The traces table's "
                    "dbscan_allele / dbscan_ldp_allele are alternative allele calls; their -1 counts are how many "
                    "of these traces those methods would leave unassigned."}


def duplicated_loci(root):
    cd = load(root, "takei")
    s = cd.spots
    dup = s.duplicated(["trace_id", "chrom", "start"], keep=False)
    per = dup.groupby(s["trace_id"].to_numpy()).any()
    extra = s.duplicated(["trace_id", "chrom", "start"])
    return {"frac_traces_with_duplicates": float(per.mean()), "n_traces_with_duplicates": int(per.sum()),
            "n_traces": int(len(per)), "n_duplicate_spots": int(extra.sum()),
            "frac_spots_duplicate": float(extra.mean()),
            "method": "a trace has duplicates if any (chrom, start) occurs more than once in it"}


def spots_per_trace_by_type(root):
    cd = load(root, "takei")
    s = cd.spots
    n = s.groupby("trace_id", observed=True).size()
    cell = s.groupby("trace_id", observed=True)["cell_id"].first().astype(str)
    ct = cell_type(cd)
    per_cell = n.groupby(cell.reindex(n.index).to_numpy()).median()
    pc_type = ct.reindex(per_cell.index)
    by_type = per_cell.groupby(pc_type).median()
    pooled = n.groupby(ct.reindex(cell.reindex(n.index)).to_numpy()).median()
    g, p = per_cell[pc_type == "Granule"], per_cell[pc_type == "Purkinje"]
    rg = cell_rg(cd).reindex(per_cell.index)
    return {"median_granule": float(g.median()), "median_purkinje": float(p.median()),
            "by_type_cell_level": {k: float(v) for k, v in by_type.items()},
            "by_type_trace_pooled": {k: float(v) for k, v in pooled.items()},
            "kruskal_p_across_types": float(st.kruskal(*[per_cell[pc_type == t] for t in by_type.index]).pvalue),
            "rho_cell_spots_vs_rg": spearman(per_cell, rg)[0],
            "method": "spots per trace; per-cell median over its traces, then median over cells of each type "
                      "(trace-pooled medians given for context); Kruskal-Wallis across types on per-cell medians; "
                      "Spearman across cells between median spots/trace and median trace Rg"}


def pseudobulk_oligo_check(root, chrom="chr1"):
    import cooler
    cd = load(root, "schicar")
    path = schicar_path(root, cd.uns["linked_scool"]["per_cell"]["path"])
    cells = ids(cd)[cd.cells["cell_type"].astype(str).to_numpy() == OLIGO]
    names = {c.split("/")[-1] for c in cooler.fileops.list_scool_cells(str(path))}
    m = None
    for c in cells:
        if c not in names:
            continue
        x = cis_matrix(cooler.Cooler(f"{path}::/cells/{c}"), chrom)
        m = x if m is None else m + x
    prov = cooler.Cooler(str(schicar_path(root, cd.uns["linked_cool"]["type_Oligo"]["path"])))
    pm = cis_matrix(prov, chrom)
    f = 1_000_000 // prov.binsize
    pm1 = coarsen(pm, f)
    n = min(len(m), len(pm1))
    iu = np.triu_indices(n)
    a, b = m[:n, :n][iu], pm1[:n, :n][iu]
    return {"total_contacts_chr1": float(np.triu(m).sum()), "provided_total_chr1": float(np.triu(pm).sum()),
            "ratio_provided_over_sum": float(np.triu(pm).sum() / np.triu(m).sum()),
            "pearson_r_pixels": float(st.pearsonr(a, b).statistic),
            "pearson_r_log1p_pixels": float(st.pearsonr(np.log1p(a), np.log1p(b)).statistic),
            "n_cells_summed": int(sum(c in names for c in cells)), "provided_resolution_bp": int(prov.binsize),
            "n_bins_1Mb": int(n),
            "method": f"sum of chr1 1 Mb raw matrices of all Oligo cells in the linked .scool; totals = upper "
                      f"triangle incl. diagonal (each contact once); provided contacts_Oligo.cool is "
                      f"{prov.binsize // 1000} kb and was coarsened x{f} to 1 Mb before the pixel Pearson r"}


def rg_equal_spots(root, n_loci=150, n_draws=20, seed=0):
    cd = load(root, "takei")
    df = spots_df(cd)
    df["_loc"] = df["chrom"].astype(str) + ":" + df["start"].astype(str)
    nloc = df.groupby("trace_id", observed=True)["_loc"].nunique()
    keep = nloc.index[nloc >= n_loci]
    df = df[df["trace_id"].isin(keep)]
    # canonical row order, so the random draws do not depend on how the store orders its rows
    df = df.assign(_t=df["trace_id"].astype(str)).sort_values(["_t", "chrom", "start", "x", "y", "z"], kind="mergesort")
    df = df.drop(columns="_t").reset_index(drop=True)
    ct = cell_type(cd)
    rng = np.random.default_rng(seed)
    rgs, meds = [], []
    for _ in range(n_draws):
        d = df.assign(_r=rng.random(len(df))).sort_values("_r")
        d = d.drop_duplicates(["trace_id", "_loc"])                   # one random spot per distinct locus
        d = d[d.groupby("trace_id", observed=True).cumcount() < n_loci]   # n_loci random distinct loci
        rg = radius_of_gyration(d)
        rgs.append(rg)
        pc = rg.groupby(trace_cells(d).reindex(rg.index).to_numpy()).median()
        t = ct.reindex(pc.index)
        meds.append((pc[t == "Bergmann"].median(), pc[t == "Granule"].median()))
    rg_mean = pd.concat(rgs, axis=1).mean(axis=1)                    # per-trace Rg averaged over draws
    pc = rg_mean.groupby(trace_cells(df).reindex(rg_mean.index).to_numpy()).median()
    t = ct.reindex(pc.index)
    r = _compare(pc[t == "Bergmann"], pc[t == "Granule"])
    meds = np.array(meds)
    full = cell_rg(cd)
    tf = ct.reindex(full.index)
    r.update({"group_a": "Bergmann", "group_b": "Granule", "n_loci": n_loci, "n_draws": n_draws, "seed": seed,
              "n_traces_kept": int(len(keep)), "n_traces_total": int(len(nloc)),
              "sd_over_draws_median_a": float(meds[:, 0].std()), "sd_over_draws_median_b": float(meds[:, 1].std()),
              "unequalised_median_a": float(full[tf == "Bergmann"].median()),
              "unequalised_median_b": float(full[tf == "Granule"].median()),
              "method": f"traces with >= {n_loci} distinct loci kept; per draw: one random spot per distinct locus, "
                        f"then {n_loci} random loci per trace; uchrom radius_of_gyration; per-trace Rg averaged over "
                        f"{n_draws} draws (numpy default_rng({seed})); per-cell median; Mann-Whitney two-sided",
              "note": f"{n_draws} draws; group medians vary across single draws by the sd_over_draws_* values"})
    return r


def embeddings_inventory(root):
    cd = load(root, "schicar")
    meta = cd.uns.get("embeddings", {})
    inv = {k: {"shape": list(np.shape(v)), "modality": str(meta.get(k, {}).get("modality", "?")),
               "method": str(meta.get(k, {}).get("method", "?")), "label": str(meta.get(k, {}).get("label", "?"))}
           for k, v in cd.cellm.items()}
    hic = [k for k, v in inv.items() if v["modality"] == "Hi-C"]
    return {"n_embeddings": len(inv), "hic_based": hic, "inventory": inv,
            "recommended": "hic_pca (scHiCluster PCA of the 1 Mb scHi-C maps) for analysis; hic_umap/hic_tsne "
                           "for display",
            "modalities": sorted({v["modality"] for v in inv.values()})}


FUNCS.update({f.__name__: f for f in [
    largest_cell_type, top_chrom, schicar_top_type, bond_length, units, scaling_exponent, ps_slope,
    contacts_vs_distance, long_range_fraction, tads_arcfish, compartments_h3k27ac, h3k9me3_granule_vs_bergmann,
    nucvol_bergmann_vs_granule, contacts_oligo_vs_l23, ps_oligo_vs_l23, rg_size_adjusted, selection_vs_rest,
    rna_counts_top, laminb1_vs_radial_spots, h3k27ac_vs_radial_bins, nucvol_vs_rg, knn_purity, mobp_atac_rna,
    sox2_rg_within_bergmann, alleles_per_chrom, duplicated_loci, spots_per_trace_by_type, pseudobulk_oligo_check,
    rg_equal_spots, embeddings_inventory]})


def main():
    import yaml
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--out", type=Path, default=HERE / "answers.json")
    a = ap.parse_args()
    qs = yaml.safe_load((HERE / "questions.yaml").read_text())["questions"]
    only = set(filter(None, a.only.split(",")))
    out = json.loads(a.out.read_text()) if a.out.exists() else {}
    for q in qs:
        if only and q["id"] not in only:
            continue
        f = FUNCS.get(q["truth"])
        if f is None:
            print(f"{q['id']}: {q['truth']} not implemented yet")
            continue
        out[q["id"]] = {"values": f(a.data_root), "truth": q["truth"]}
        print(q["id"], json.dumps(out[q["id"]]["values"], default=str)[:300])
    a.out.write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
