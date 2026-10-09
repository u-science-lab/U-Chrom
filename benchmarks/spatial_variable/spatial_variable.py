"""spatial_variable: which 3-D genome features of spatial Hi-C spots vary in space, and which vary beyond what the
spots' transcriptomes explain (the analysis behind the Brief Communication's Fig. 2, u-chrom-paper
``manuscripts/nmeth-bc``).

Global level (this script, stages ``features`` … ``summary``): per spot, the short / long-range contact ratio
(Guo et al. 2026's definition), distance bands, P(s) slopes, cis fraction and the trans share of each
chromosome, from per-spot contact-distance histograms (``uchrom.io.ContactStats``, one pass over each sample's
.pairs on Sherlock: ``apps/atlas/recipes/spatial_hicrna/sherlock/contact_stats.sbatch``).  Each feature is
tested per section with Moran's I (8 adjacent spots) and SPARK-X, raw and adjusted for depth and for the spot's
RNA (principal components), and its region means are compared with the paper's statement (cortex, CA and DG
above white matter and choroid plexus).

    python benchmarks/spatial_variable/spatial_variable.py --stats $OAK/uchrom/spatial_3dgenome --stages all

Inputs: the atlas store ``hicrna_mouse_brain`` (``uchrom.datasets.load``: cells, positions, the linked spot RNA)
and ``<stats>/<sample>/<sample>.contact_stats_{q30,all}.npz``.  Outputs: the cache (``--out``), the headline
numbers ``benchmarks/spatial_variable/results/global_features.json`` (``benchmarks/_record.py``) and the figure
data ``spatial_variable.{json,npz}`` in the paper repository.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

DATASET = "hicrna_mouse_brain"
SECTIONS = ["mouse_brain_r1", "mouse_brain_r2"]
MIN_CONTACTS = 50_000                      # spot QC of benchmarks/spatial_composition (pitfall 3)
FILTERS = ["q30", "all"]

# Region marker sets (spot RNA, log1p CP10k, mean over the set): the anatomical regions of a coronal section
# through the dorsal hippocampus that Guo et al. 2026 compare.
REGION_MARKERS = {
    "white_matter": ["Mbp", "Plp1", "Mobp", "Mog", "Cldn11", "Mal", "Trf"],
    "choroid_plexus": ["Ttr", "Kl", "Folr1", "Clic6"],
    "DG": ["Prox1", "C1ql2", "Dsp", "Pdzd2"],
    "CA": ["Wfs1", "Fibcd1", "Pou3f1", "Spink8", "Nov"],
    "cortex": ["Satb2", "Stx1a", "Cux2", "Rorb", "Fezf2", "Tbr1"],
    "thalamus": ["Tcf7l2", "Prkcd", "Slc17a6", "Plekhg1"],
}
GUO_ORDER = {"high": ["cortex", "CA", "DG"], "low": ["white_matter", "choroid_plexus"]}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def load_store():
    import uchrom.datasets as ds

    return ds.load(DATASET)


# ------------------------------------------------------------------------------------------------------------
# stage features: per-spot contact features of every section, both filters
# ------------------------------------------------------------------------------------------------------------
def stage_features(stats_root: Path, out: Path):
    from uchrom.fea import ContactFeatureParams, contact_features
    from uchrom.io import ContactStats

    cd = load_store()
    frames = []
    for filt in FILTERS:
        work = _cells_only(cd)
        merged = None
        for sec in SECTIONS:
            st = ContactStats.load(stats_root / sec / f"{sec}.contact_stats_{filt}.npz")
            st.cells = np.asarray([f"{sec}:{b}" for b in st.cells], dtype=object)
            merged = st if merged is None else _concat(merged, st)
        merged.write(work, key="contacts", source=f"{stats_root}/<section>/<section>.contact_stats_{filt}.npz")
        for name, params in (("guo", ContactFeatureParams.guo2026()), ("bycentre", ContactFeatureParams())):
            f = contact_features(work, params=params, key_added=None)
            f.columns = [f"{c}" if name == "guo" else f"{c}@centre" for c in f.columns]
            f = f[[c for c in f.columns if name == "guo" or c.startswith(("frac_short", "frac_long",
                                                                            "short_long"))]]
            f.columns = [f"{filt}.{c}" for c in f.columns]
            frames.append(f)
        # orientation QC: inward / outward share of the contacts below 1 kb and between 1 and 5 kb
        o = work.cellm["contacts.orientation"].astype(float)
        edges = np.asarray(work.uns["contact_stats"]["contacts"]["edges"])
        hi = np.r_[edges, np.inf]                                # upper edge of each histogram column
        short = hi <= 1_000
        mid = (hi > 1_000) & (hi <= 5_000)
        tot_s, tot_m = o[:, :, short].sum((1, 2)), o[:, :, mid].sum((1, 2))
        with np.errstate(divide="ignore", invalid="ignore"):
            frames.append(pd.DataFrame({f"{filt}.inward_lt1k": o[:, 1, short].sum(1) / tot_s,
                                        f"{filt}.outward_lt1k": o[:, 2, short].sum(1) / tot_s,
                                        f"{filt}.inward_1k_5k": o[:, 1, mid].sum(1) / tot_m},
                                       index=pd.Index([str(c) for c in work._cell_ids_axis()])))
    feats = pd.concat(frames, axis=1)
    c = cd.cells.copy()
    c.index = pd.Index([str(i) for i in cd._cell_ids_axis()], name="cell_id")
    feats = feats.join(c[["section", "centroid_x", "centroid_y", "hic_contacts", "hic_cis_fraction", "rna_umi"]])
    feats["qc"] = _qc(feats)
    feats.to_parquet(out / "features.parquet")
    log(f"features: {feats.shape}, QC pass {int(feats.qc.sum())} of {len(feats)}")


def _cells_only(cd):
    """An in-memory ChromData with the store's cells and positions only (no spots), for the features."""
    from chromdata import ChromData

    cells = cd.cells.copy()
    out = ChromData(coords=np.zeros((0, 3)), spots=pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": [],
                                                                 "end": [], "trace_id": []}), cells=cells)
    out.uns["cell_spatial"] = cd.uns["cell_spatial"]
    return out


def _concat(a, b):
    from uchrom.io import ContactStats

    if a.chroms != b.chroms or not np.array_equal(a.edges, b.edges):
        raise ValueError("sections with different chromosomes / edges")
    out = ContactStats(list(a.cells) + list(b.cells), a.chroms, a.edges, orientation=a.orientation is not None)
    out.distance = np.concatenate([a.distance, b.distance])
    out.trans = np.concatenate([a.trans, b.trans])
    if out.orientation is not None:
        out.orientation = np.concatenate([a.orientation, b.orientation])
    out.n_other = a.n_other + b.n_other
    out.meta = getattr(a, "meta", {})
    return out


def _qc(f: pd.DataFrame) -> np.ndarray:
    """Spots kept: >= 50k contacts, not on the first / last barcode row, not in a dead barcode column."""
    keep = np.zeros(len(f), bool)
    for sec, g in f.groupby("section"):
        idx = f.index.get_indexer(g.index)
        y, x, hc = g.centroid_y.to_numpy(), g.centroid_x.to_numpy(), g.hic_contacts.to_numpy()
        edge = (y == y.min()) | (y == y.max())
        colmed = pd.Series(hc).groupby(x).median()
        dead = np.isin(x, colmed.index[colmed < 0.05 * np.median(hc)].to_numpy())
        keep[idx] = (hc >= MIN_CONTACTS) & ~edge & ~dead
    return keep


# ------------------------------------------------------------------------------------------------------------
# stage regions: anatomical regions from the spot RNA (marker sets), both sections
# ------------------------------------------------------------------------------------------------------------
def stage_regions(out: Path):
    from scipy.spatial import cKDTree

    cd = load_store()
    a = cd.linked_adata
    ids = [str(i) for i in cd._cell_ids_axis()]
    a = a[ids]
    X = a.X.tocsr().astype(np.float64)
    tot = np.asarray(X.sum(1)).ravel()
    gi = {g: i for i, g in enumerate(a.var_names)}
    c = cd.cells.copy()
    c.index = pd.Index(ids)
    scores = {}
    used = {}
    for reg, genes in REGION_MARKERS.items():
        g = [x for x in genes if x in gi]
        used[reg] = g
        sub = X[:, [gi[x] for x in g]].toarray()
        cp10k = np.log1p(sub / np.maximum(tot, 1)[:, None] * 1e4)
        scores[reg] = cp10k.mean(1)
    S = pd.DataFrame(scores, index=ids)
    # smooth over the spot and its neighbours within 2 spots, z-score per section, region = best z
    rows = []
    for sec in SECTIONS:
        m = (c.section == sec).to_numpy()
        xy = c.loc[m, ["centroid_x", "centroid_y"]].to_numpy(float)
        nb = cKDTree(xy).query_ball_point(xy, r=2.01)
        Sm = S.loc[m].to_numpy()
        sm = np.array([Sm[n].mean(0) for n in nb])
        z = (sm - sm.mean(0)) / sm.std(0)
        best = np.array(list(REGION_MARKERS))[z.argmax(1)]
        best = np.where(z.max(1) > 0.5, best, "other")
        rows.append(pd.DataFrame(z, index=S.index[m], columns=[f"z.{r}" for r in REGION_MARKERS])
                    .assign(region=best, section=sec))
    reg = pd.concat(rows)
    reg.to_parquet(out / "regions.parquet")
    log("regions:", reg.groupby("section").region.value_counts().to_dict(), "markers used:", used)
    pcs = pd.DataFrame(np.asarray(cd.cellm["rna_pca"]), index=ids, columns=[f"PC{i + 1}" for i in range(30)])
    pcs.to_parquet(out / "rna_pca.parquet")


# ------------------------------------------------------------------------------------------------------------
# stage sv: spatial tests per section
# ------------------------------------------------------------------------------------------------------------
FEATURES = ["short_long_ratio", "frac_short", "frac_long", "frac_2M_12M", "ps_slope_100k_1M", "ps_slope_1M_10M",
            "cis_fraction"]
CONTROLS = ["log_contacts"]              # depth: expected to vary (tissue density), a control, not a finding


def stage_sv(out: Path, n_perms: int, seed: int):
    from chromdata import ChromData
    from uchrom.spatial import spatial_autocorr, spatial_neighbors, sparkx

    f = pd.read_parquet(out / "features.parquet")
    pcs = pd.read_parquet(out / "rna_pca.parquet")
    f["log_contacts"] = np.log10(f["hic_contacts"])
    trans_cols = [c for c in f.columns if c.startswith("q30.trans_share.")]
    feats = [f"{filt}.{x}" for filt in FILTERS for x in FEATURES] + trans_cols + \
        [c for c in f.columns if c.endswith(("lt1k", "1k_5k"))] + CONTROLS
    tables = []
    for sec in SECTIONS:
        g = f[(f.section == sec) & f.qc]
        cells = pd.DataFrame({"cell_id": g.index, "section": sec})
        cdq = ChromData(coords=np.zeros((0, 3)), spots=pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": [],
                                                                     "end": [], "trace_id": []}), cells=cells)
        cdq.set_cell_positions(g[["centroid_x", "centroid_y"]].to_numpy(float), cell_ids=list(g.index), unit="spot",
                               frame="tissue", region_col="section")
        graph = spatial_neighbors(cdq, method="radius", radius=1.5)
        vals = g[feats]
        mi = spatial_autocorr(values=vals, graph=graph, n_perms=n_perms, seed=seed)
        xy = g[["centroid_x", "centroid_y"]].to_numpy(float)
        depth = g[["log_contacts"]].to_numpy(float)
        p10 = pcs.loc[g.index, [f"PC{i}" for i in range(1, 11)]].to_numpy(float)
        p30 = pcs.loc[g.index].to_numpy(float)
        runs = {"raw": None, "depth": depth, "depth_rna10": np.c_[depth, p10], "depth_rna30": np.c_[depth, p30]}
        t = mi[["n", "I", "z_rand", "pval", "padj"]].add_prefix("moran.")
        for name, cov in runs.items():
            v = vals.drop(columns=["log_contacts"]) if cov is not None else vals
            s = sparkx(v, xy, covariates=cov)
            t = t.join(s[["pval", "padj"]].add_prefix(f"sparkx_{name}."))
        t.insert(0, "section", sec)
        tables.append(t.reset_index())
        log(f"sv {sec}: {len(g)} spots, {graph.adjacency.nnz // 2} edges")
    sv = pd.concat(tables, ignore_index=True)
    sv.to_parquet(out / "sv.parquet")


# ------------------------------------------------------------------------------------------------------------
# stage summary: region means (Guo's statement), replication between sections, headline numbers
# ------------------------------------------------------------------------------------------------------------
def stage_summary(out: Path, results: Path, figdir: Path):
    from scipy import stats as ss

    from _record import save

    f = pd.read_parquet(out / "features.parquet")
    reg = pd.read_parquet(out / "regions.parquet")
    sv = pd.read_parquet(out / "sv.parquet")
    f = f.join(reg[["region"]])
    q = f[f.qc]
    res = {"n_spots": {s: int((f.section == s).sum()) for s in SECTIONS},
           "n_spots_qc": {s: int((q.section == s).sum()) for s in SECTIONS}}
    # 1. Guo et al.: short / long ratio higher in cortex, CA, DG than in white matter and choroid plexus
    region_means = {}
    for filt in FILTERS:
        col = f"{filt}.short_long_ratio"
        for sec in SECTIONS:
            g = q[q.section == sec]
            m = g.groupby("region")[col].agg(["median", "mean", "count"])
            region_means[f"{filt}/{sec}"] = m.round(4).to_dict(orient="index")
            hi = g[g.region.isin(GUO_ORDER["high"])][col]
            lo = g[g.region.isin(GUO_ORDER["low"])][col]
            u = ss.mannwhitneyu(hi, lo, alternative="greater")
            res[f"guo_high_vs_low/{filt}/{sec}"] = {
                "median_high": float(hi.median()), "median_low": float(lo.median()),
                "n_high": int(len(hi)), "n_low": int(len(lo)), "mannwhitney_p": float(u.pvalue),
                "auc": float(u.statistic / (len(hi) * len(lo)))}
    res["region_short_long"] = region_means
    # 2. spatial variation per feature and section, and replication
    piv = {}
    for col in [c for c in sv.columns if c.endswith(".padj")]:
        p = sv.pivot(index="feature", columns="section", values=col)
        piv[col] = {"n_sig_r1": int((p[SECTIONS[0]] < 0.05).sum()), "n_sig_r2": int((p[SECTIONS[1]] < 0.05).sum()),
                    "n_sig_both": int(((p[SECTIONS[0]] < 0.05) & (p[SECTIONS[1]] < 0.05)).sum()),
                    "n_features": int(len(p))}
    res["sv_counts"] = piv
    keep = ["moran.I", "moran.padj", "sparkx_raw.padj", "sparkx_depth.padj", "sparkx_depth_rna10.padj",
            "sparkx_depth_rna30.padj"]
    res["sv_table"] = {f"{r.section}/{r.feature}": {k: (None if pd.isna(getattr(r, k.replace('.', '_'), np.nan))
                                                         else float(getattr(r, k.replace('.', '_'))))
                                                     for k in keep}
                       for r in sv.rename(columns=lambda c: c.replace(".", "_")).itertuples()}
    results.mkdir(parents=True, exist_ok=True)
    save(results / "global_features.json", res, script=__file__, datasets=[DATASET, "spatial_hicrna"],
         params={"min_contacts": MIN_CONTACTS, "region_markers": REGION_MARKERS, "features": FEATURES})
    figdir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(figdir / "spatial_variable.npz",
                        cell_id=f.index.to_numpy(str), section=f.section.to_numpy(str),
                        x=f.centroid_x.to_numpy(float), y=f.centroid_y.to_numpy(float), qc=f.qc.to_numpy(bool),
                        region=f.region.fillna("other").to_numpy(str),
                        **{c.replace(".", "_"): f[c].to_numpy(float) for c in f.columns
                           if c.startswith(("q30.", "all.")) and not c.startswith(("q30.trans_share", "all.trans_share"))})
    with open(figdir / "spatial_variable.json", "w") as fh:
        json.dump(res, fh, indent=1, default=float)
    log("summary:", json.dumps({k: v for k, v in res.items() if k.startswith("guo_")}, indent=1))


def default_figdata(out: Path) -> Path:
    from _paper import paper_root

    root = paper_root()
    return root / "manuscripts" / "nmeth-bc" / "figures" / "results" if root else out / "figdata"


def main(argv=None):
    from uchrom.datasets import data_dir

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stats", required=False, help="folder of <sample>/<sample>.contact_stats_*.npz")
    ap.add_argument("--out", default=None, help="cache (default <data>/spatial_variable_cache)")
    ap.add_argument("--results", default=str(HERE / "results"))
    ap.add_argument("--figdata", default=None)
    ap.add_argument("--stages", default="features,regions,sv,summary")
    ap.add_argument("--perms", type=int, default=999)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else data_dir() / "spatial_variable_cache"
    out.mkdir(parents=True, exist_ok=True)
    figdir = Path(a.figdata) if a.figdata else default_figdata(out)
    stages = ["features", "regions", "sv", "summary"] if a.stages == "all" else a.stages.split(",")
    for st in stages:
        t = time.time()
        log(f"--- stage {st}")
        if st == "features":
            stage_features(Path(a.stats), out)
        elif st == "regions":
            stage_regions(out)
        elif st == "sv":
            stage_sv(out, a.perms, a.seed)
        elif st == "summary":
            stage_summary(out, Path(a.results), figdir)
        else:
            sys.exit(f"unknown stage {st!r}")
        log(f"--- stage {st} done in {time.time() - t:.0f} s")


if __name__ == "__main__":
    main()
