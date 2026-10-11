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

Local level (stage ``local``): every spot's insulation of the boundaries and strength of the loops called on its
tissue's pooled map (``bulk_calls.py``), from the contacts the second pass counts in their windows
(``spatial_pairs_windows.py``), tested the same way, structure by structure, and replicated between sections.

Tissues (``--tissue``): ``brain`` (atlas ``hicrna_mouse_brain``) and ``melanoma`` (``hicrna_human_melanoma``).
Inputs: the atlas store (``uchrom.datasets.load``: cells, positions, the linked spot RNA) and
``<stats>/<sample>/<sample>.contact_stats_{q30,all}.npz`` / ``.window_counts.npz``.  Outputs: the cache
(``--out``/<tissue>), the headline numbers ``benchmarks/spatial_variable/results/*_<tissue>.json``
(``benchmarks/_record.py``) and the figure data ``spatial_variable_<tissue>.{json,npz}`` in the paper repository.
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

MIN_CONTACTS = 50_000                      # spot QC of benchmarks/spatial_composition (pitfall 3)
FILTERS = ["q30", "all"]

# Per tissue: the atlas store, its sections, the genome (scA/B), region marker sets (spot RNA, log1p CP10k, mean
# over the set) and the regions Guo et al. 2026 contrast for the short / long ratio.
TISSUES = {
    "brain": {
        "dataset": "hicrna_mouse_brain", "sections": ["mouse_brain_r1", "mouse_brain_r2"], "genome": "mm10_genome",
        # a coronal section through the dorsal hippocampus
        "markers": {"white_matter": ["Mbp", "Plp1", "Mobp", "Mog", "Cldn11", "Mal", "Trf"],
                    "choroid_plexus": ["Ttr", "Kl", "Folr1", "Clic6"],
                    "DG": ["Prox1", "C1ql2", "Dsp", "Pdzd2"],
                    "CA": ["Wfs1", "Fibcd1", "Pou3f1", "Spink8", "Nov"],
                    "cortex": ["Satb2", "Stx1a", "Cux2", "Rorb", "Fezf2", "Tbr1"],
                    "thalamus": ["Tcf7l2", "Prkcd", "Slc17a6", "Plekhg1"]},
        "contrast": {"high": ["cortex", "CA", "DG"], "low": ["white_matter", "choroid_plexus"]},
        # the authors' spatial domains (CellCharter on the RNA's scVI latent; published for section r1 only),
        # named from their marker genes (log fold change against the other domains): cortex L2-4 Cux2 / Rorb /
        # Satb2, L5-6 Bcl11b / Tshz2, striatum Pde10a / Gpr88 / Penk, habenula Pou4f1 / Tac2 / Gpr151, CA3 Grik4,
        # CA1 Bcl11b / Wfs1 / Fibcd1, DG Prox1, thalamus Tcf7l2 / Slc17a6 / Ntng1, white matter Plp1 / Mbp,
        # choroid plexus Ttr, neuropil (cortical layer 1, hippocampal strata) Ddn / Slc1a2
        "domains": {"column": "cluster_cellcharter",
                    "names": {"0": "cortex L5-6", "1": "striatum", "2": "cortex L2-4", "3": "habenula", "4": "CA3",
                              "5": "choroid plexus", "6": "thalamus 1", "7": "white matter", "8": "thalamus 2",
                              "9": "neuropil", "10": "DG", "11": "CA1"},
                    "contrast": {"high": ["cortex L2-4", "cortex L5-6", "CA1", "CA3", "DG"],
                                 "low": ["white matter", "choroid plexus"]}},
    },
    "melanoma": {
        "dataset": "hicrna_human_melanoma", "sections": ["human_melanoma_r1", "human_melanoma_r2"],
        "genome": "hg38_genome",
        "markers": {"tumour": ["MLANA", "PMEL", "TYR", "SOX10", "MITF", "DCT"],
                    "immune": ["PTPRC", "CD3E", "CD2", "MS4A1", "CD79A", "LYZ", "CD74"],
                    "stroma": ["COL1A1", "COL1A2", "COL3A1", "DCN", "LUM"],
                    "endothelial": ["PECAM1", "VWF", "CDH5", "PLVAP"]},
        "contrast": {"high": ["tumour"], "low": ["immune", "stroma"]},
    },
}
TISSUE = "brain"
DATASET = TISSUES[TISSUE]["dataset"]
SECTIONS = TISSUES[TISSUE]["sections"]
REGION_MARKERS = TISSUES[TISSUE]["markers"]
GUO_ORDER = TISSUES[TISSUE]["contrast"]


def configure(tissue: str) -> None:
    """Point the stages at one tissue (module-level settings)."""
    global TISSUE, DATASET, SECTIONS, REGION_MARKERS, GUO_ORDER
    cfg = TISSUES[tissue]
    TISSUE, DATASET, SECTIONS = tissue, cfg["dataset"], cfg["sections"]
    REGION_MARKERS, GUO_ORDER = cfg["markers"], cfg["contrast"]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def load_store():
    import uchrom.datasets as ds

    return ds.load(DATASET)


def _published_domains() -> pd.DataFrame | None:
    """The authors' spatial domains of the spots, named (``TISSUES[...]["domains"]``), column ``domain``; spots
    without one (sections the authors did not publish) are missing.  None when the tissue has none configured."""
    cfg = TISSUES[TISSUE].get("domains")
    if cfg is None:
        return None
    cd = load_store()
    cells = cd.cells.copy()
    cells.index = pd.Index([str(i) for i in cd._cell_ids_axis()])
    lab = cells[cfg["column"]].dropna().astype(str)
    return pd.DataFrame({"domain": lab.map(cfg["names"])}, index=lab.index)


# ------------------------------------------------------------------------------------------------------------
# stage features: per-spot contact features of every section, both filters
# ------------------------------------------------------------------------------------------------------------
def stage_features(stats_root: Path, out: Path):
    from uchrom.fea import ContactFeatureParams, contact_features

    cd = load_store()
    frames = []
    for filt in FILTERS:
        work = _with_stats(cd, stats_root, filt)
        for name, params in (("guo", ContactFeatureParams.guo2026()), ("bycentre", ContactFeatureParams()),
                             ("chrom", ContactFeatureParams.guo2026(per_chromosome=True))):
            f = contact_features(work, params=params, key_added=None)
            if name == "chrom":                   # per chromosome, equal weights: blind to whole-chromosome gains
                log(f"features {filt} per chromosome over {f.attrs['chroms']}")
                f = f[[c for c in FEATURES if not c.endswith("@chrom")]]
            elif name == "bycentre":
                f = f[[c for c in f.columns if c.startswith(("frac_short", "frac_long", "short_long"))]]
            f.columns = [c if name == "guo" else f"{c}@{name}" for c in f.columns]
            f.columns = [f"{filt}.{c}" for c in f.columns]
            frames.append(f)
        # orientation QC: inward / outward share of the contacts below 2.5 kb (histogram column 0) and
        # between 2.5 and 5 kb, and the share of all cis contacts below 2.5 kb
        o = work.cellm["contacts.orientation"].astype(float)
        edges = np.asarray(work.uns["contact_stats"]["contacts"]["edges"])
        hi = np.r_[edges, np.inf]                                # upper edge of each histogram column
        short = np.arange(len(hi)) == 0
        mid = ~short & (hi <= 5_000)
        tot_s, tot_m = o[:, :, short].sum((1, 2)), o[:, :, mid].sum((1, 2))
        with np.errstate(divide="ignore", invalid="ignore"):
            frames.append(pd.DataFrame({f"{filt}.inward_lt2k5": o[:, 1, short].sum(1) / tot_s,
                                        f"{filt}.outward_lt2k5": o[:, 2, short].sum(1) / tot_s,
                                        f"{filt}.inward_2k5_5k": o[:, 1, mid].sum(1) / tot_m,
                                        f"{filt}.frac_lt2k5": tot_s / o.sum((1, 2))},
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


def _with_stats(cd, stats_root: Path, filt: str):
    """The store's cells (:func:`_cells_only`) with the contact statistics of every section (filter ``filt``) under
    the key ``contacts``."""
    from uchrom.io import ContactStats

    work = _cells_only(cd)
    merged = None
    for sec in SECTIONS:
        st = ContactStats.load(stats_root / sec / f"{sec}.contact_stats_{filt}.npz")
        st.cells = np.asarray([f"{sec}:{b}" for b in st.cells], dtype=object)
        merged = st if merged is None else _concat(merged, st)
    merged.write(work, key="contacts", source=f"{stats_root}/<section>/<section>.contact_stats_{filt}.npz")
    return work


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


HOT = 2.5            # a barcode row / column whose median contacts exceed this multiple of the section's: an
                     # array-edge channel (Guo 2026 brain: the first and last rows 2-10x, the last column 3.6-10x)


def _qc(f: pd.DataFrame) -> np.ndarray:
    """Spots kept: >= 50k contacts, not on the first / last barcode row, not in a dead barcode column (median
    contacts < 5 % of the section's) nor a hot row / column (> ``HOT`` x the section's)."""
    keep = np.zeros(len(f), bool)
    for sec, g in f.groupby("section", observed=True):
        idx = f.index.get_indexer(g.index)
        y, x, hc = g.centroid_y.to_numpy(), g.centroid_x.to_numpy(), g.hic_contacts.to_numpy()
        med = np.median(hc)
        edge = (y == y.min()) | (y == y.max())
        colmed = pd.Series(hc).groupby(x).median()
        rowmed = pd.Series(hc).groupby(y).median()
        dead = np.isin(x, colmed.index[colmed < 0.05 * med].to_numpy())
        hot = np.isin(x, colmed.index[colmed > HOT * med].to_numpy()) | np.isin(y, rowmed.index[rowmed > HOT * med].to_numpy())
        keep[idx] = (hc >= MIN_CONTACTS) & ~edge & ~dead & ~hot
    return keep


# ------------------------------------------------------------------------------------------------------------
# stage check: the per-spot counts of this pass equal those of the map build (same filters, same pairs)
# ------------------------------------------------------------------------------------------------------------
def stage_check(stats_root: Path, results: Path):
    from uchrom.io import ContactStats
    from _record import save

    res = {}
    for sec in SECTIONS:
        st = ContactStats.load(stats_root / sec / f"{sec}.contact_stats_q30.npz")
        old = pd.read_csv(stats_root / sec / f"{sec}.spot_stats.tsv", sep="\t").set_index("barcode")
        mine = pd.DataFrame({"cis": st.n_cis, "trans": st.n_trans}, index=pd.Index(st.cells.astype(str)))
        old = old.reindex(mine.index)
        res[sec] = {"n_spots": int(len(mine)), "cis_equal": int((mine.cis == old.cis).sum()),
                    "trans_equal": int((mine.trans == old.trans).sum()),
                    "cis_max_abs_diff": int((mine.cis - old.cis).abs().max()),
                    "trans_max_abs_diff": int((mine.trans - old.trans).abs().max()),
                    "total_cis": int(mine.cis.sum()), "total_trans": int(mine.trans.sum())}
        log("check", sec, res[sec])
    results.mkdir(parents=True, exist_ok=True)
    save(results / f"contact_stats_check_{TISSUE}.json", res, script=__file__, datasets=["spatial_hicrna"],
         params={"compared": "<sample>.contact_stats_q30.npz vs <sample>.spot_stats.tsv (spatial_pairs_to_cool.py)"})


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
        if not g:
            continue
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
        best = np.array(list(S.columns))[z.argmax(1)]
        best = np.where(z.max(1) > 0.5, best, "other")
        rows.append(pd.DataFrame(z, index=S.index[m], columns=[f"z.{r}" for r in S.columns])
                    .assign(region=best, section=sec))
    reg = pd.concat(rows)
    reg.to_parquet(out / "regions.parquet")
    log("regions:", reg.groupby("section").region.value_counts().to_dict(), "markers used:", used)
    pca = np.asarray(cd.cellm["rna_pca"])
    pcs = pd.DataFrame(pca, index=ids, columns=[f"PC{i + 1}" for i in range(pca.shape[1])])
    pcs.to_parquet(out / "rna_pca.parquet")


# ------------------------------------------------------------------------------------------------------------
# stage sv: spatial tests per section
# ------------------------------------------------------------------------------------------------------------
FEATURES = ["short_long_ratio", "frac_short", "frac_long", "frac_2M_12M", "ps_slope_100k_1M", "ps_slope_1M_10M",
            "cis_fraction"]
# the same computed per chromosome and averaged with equal weights (uchrom.fea.ContactFeatureParams
# per_chromosome): a tumour's gains and losses of whole chromosomes change the pooled ones, not these
FEATURES += [f"{x}@chrom" for x in FEATURES]
CONTROLS = ["log_contacts"]              # depth: expected to vary (tissue density), a control, not a finding


def _grid_graph(g):
    from chromdata import ChromData
    from uchrom.spatial import spatial_neighbors

    cdq = ChromData(coords=np.zeros((0, 3)), spots=pd.DataFrame({"chrom": pd.Series([], dtype=str), "start": [],
                                                                 "end": [], "trace_id": []}),
                    cells=pd.DataFrame({"cell_id": g.index}))
    cdq.set_cell_positions(g[["centroid_x", "centroid_y"]].to_numpy(float), cell_ids=list(g.index), unit="spot",
                           frame="tissue")
    return spatial_neighbors(cdq, method="radius", radius=1.5)


def _residuals(V: pd.DataFrame, X) -> pd.DataFrame:
    """Least-squares residuals of each column on X (+ intercept), where the column has a value (columns with
    the same missing spots fitted together)."""
    if X is None:
        return V
    Xi = np.c_[np.ones(len(V)), X]
    A = V.to_numpy(float)
    out = np.full_like(A, np.nan)
    fin = np.isfinite(A)
    groups: dict = {}
    for j in range(A.shape[1]):
        groups.setdefault(fin[:, j].tobytes(), []).append(j)
    for _, js in groups.items():
        m = fin[:, js[0]]
        if m.sum() <= Xi.shape[1]:
            continue
        b, *_ = np.linalg.lstsq(Xi[m], A[np.ix_(m, js)], rcond=None)
        out[np.ix_(m, js)] = A[np.ix_(m, js)] - Xi[m] @ b
    return pd.DataFrame(out, index=V.index, columns=V.columns)


def _smooth_var(V: pd.DataFrame, xy) -> np.ndarray:
    """The variance each column's smooth surface carries (smooth share x variance)."""
    from uchrom.spatial import smooth_share

    return smooth_share(V, xy) * np.nanvar(V.to_numpy(float), axis=0)


TECHNICAL = ["frac_lt2k5", "inward_lt2k5", "outward_lt2k5"]     # undigested / self-ligated share: QC, not biology


def stage_sv(out: Path, n_perms: int, seed: int):
    """Per section and feature: Moran's I, the smooth share of the variance and SPARK-X, on the raw values, after
    the barcode stripes are removed (destripe), + depth, + the spot's RNA (30 PCs); the smooth variance left at
    each step relative to the destriped values."""
    from uchrom.spatial import destripe, spatial_autocorr, sparkx

    f = pd.read_parquet(out / "features.parquet")
    pcs = pd.read_parquet(out / "rna_pca.parquet")
    f["log_contacts"] = np.log10(f["hic_contacts"])
    trans_cols = [c for c in f.columns if c.startswith("q30.trans_share.")]
    feats = [f"{filt}.{x}" for filt in FILTERS for x in FEATURES] + trans_cols + \
        [f"q30.{x}" for x in TECHNICAL] + CONTROLS
    tables = []
    for sec in SECTIONS:
        g = f[(f.section == sec) & f.qc]
        graph = _grid_graph(g)
        xy = g[["centroid_x", "centroid_y"]].to_numpy(float)
        rows, cols = g.centroid_y.to_numpy(int), g.centroid_x.to_numpy(int)
        raw = g[feats]
        ds = destripe(raw, rows, cols)
        depth = g[["log_contacts"]].to_numpy(float)
        P = pcs.loc[g.index].to_numpy(float)
        steps = {"raw": (raw, None), "destriped": (ds, None), "depth": (_residuals(ds.drop(columns=CONTROLS), depth), depth),
                 "depth_rna30": (_residuals(ds.drop(columns=CONTROLS), np.c_[depth, P]), np.c_[depth, P])}
        base = _smooth_var(ds, xy)
        t = pd.DataFrame(index=pd.Index(feats, name="feature"))
        for name, (V, cov) in steps.items():
            mi = spatial_autocorr(values=V, graph=graph, n_perms=n_perms if name in ("raw", "depth_rna30") else 0,
                                  seed=seed)
            t[f"{name}.moran_I"] = mi["I"]
            t[f"{name}.moran_padj"] = mi["padj"]
            sv_ = _smooth_var(V, xy)
            t[f"{name}.smooth_share"] = pd.Series(sv_ / np.nanvar(V.to_numpy(float), axis=0), index=V.columns)
            t[f"{name}.smooth_left"] = pd.Series(sv_ / base[[feats.index(c) for c in V.columns]], index=V.columns)
            # SPARK-X on the destriped values with the step's covariates (raw: the values as measured)
            sx = sparkx(raw if name == "raw" else ds[V.columns], xy, covariates=cov)
            t[f"{name}.sparkx_padj"] = sx["padj"]
        t.insert(0, "section", sec)
        tables.append(t.reset_index())
        log(f"sv {sec}: {len(g)} spots, {graph.adjacency.nnz // 2} edges")
    sv = pd.concat(tables, ignore_index=True)
    sv.to_parquet(out / "sv.parquet")


# ------------------------------------------------------------------------------------------------------------
# stage calibrate: how much smooth spatial variance the same RNA adjustment leaves in held-out genes
# ------------------------------------------------------------------------------------------------------------
def _gene_modules(genes: pd.DataFrame, xy, lumi, PCs, n_clusters: int = 40, min_genes: int = 5):
    """Modules of held-out genes that share a spatial pattern (average-linkage clusters of the correlation of their
    smooth surfaces), each scored per spot as the mean of its genes z-scored; the modules' smooth variance left
    after the RNA PCs (as the genes') and smooth share after the RNA depth.  A module averages many genes as a
    contact feature averages many contacts: the yardstick at a comparable noise level."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    from uchrom.spatial import smooth_basis

    G = genes.to_numpy(float)
    G = np.where(np.isfinite(G), G, np.nanmean(G, axis=0))
    Z = (G - G.mean(0)) / np.maximum(G.std(0), 1e-12)
    S = smooth_basis(xy)
    sm = S @ np.linalg.lstsq(S, Z, rcond=None)[0]                 # each gene's smooth surface
    sm = (sm - sm.mean(0)) / np.maximum(sm.std(0), 1e-12)
    D = np.clip(1 - (sm.T @ sm) / len(sm), 0, 2)
    np.fill_diagonal(D, 0)
    lab = fcluster(linkage(squareform(D, checks=False), "average"), n_clusters, criterion="maxclust")
    mods = [np.flatnonzero(lab == k) for k in np.unique(lab) if (lab == k).sum() >= min_genes]
    if not mods:
        return [], np.zeros(0), np.zeros(0)
    M = pd.DataFrame(np.column_stack([Z[:, m].mean(1) for m in mods]), index=genes.index)
    left = _smooth_var(_residuals(M, np.c_[lumi, PCs]), xy) / _smooth_var(_residuals(M, lumi), xy)
    r = _residuals(M, lumi)
    share = _smooth_var(r, xy) / np.nanvar(r.to_numpy(), 0)
    return mods, left, share


def stage_calibrate(out: Path, seed: int, n_pcs: int = 30, min_detect: float = 0.10):
    """Per section: genes detected in >= 10 % of the spots split at random in two halves; 30 PCs of half A
    (log1p CP10k, z-scored); the genes of half B — held out of the PCs — and the Hi-C features, destriped, are
    regressed on (log depth, PCs of A); the smooth variance left (relative to before the PCs) is compared."""
    import scipy.sparse as sps

    from uchrom.spatial import destripe

    cd = load_store()
    ids = pd.Index([str(i) for i in cd._cell_ids_axis()])
    adata = cd.linked_adata
    f = pd.read_parquet(out / "features.parquet")
    f["log_contacts"] = np.log10(f["hic_contacts"])
    feats = [f"q30.{x}" for x in FEATURES] + [f"q30.{x}" for x in TECHNICAL]
    rng = np.random.default_rng(seed)
    rows_out, res = [], {}
    for sec in SECTIONS:
        g = f[(f.section == sec) & f.qc]
        X = sps.csr_matrix(adata[list(g.index)].X).astype(np.float64)
        tot = np.asarray(X.sum(1)).ravel()
        det = np.asarray((X > 0).mean(0)).ravel()
        keep = np.flatnonzero(det >= min_detect)
        L = np.log1p(X[:, keep].toarray() / np.maximum(tot, 1)[:, None] * 1e4)
        names = np.asarray(adata.var_names)[keep]
        perm = rng.permutation(len(keep))
        A, B = perm[: len(keep) // 2], perm[len(keep) // 2:]
        Z = (L[:, A] - L[:, A].mean(0)) / np.maximum(L[:, A].std(0), 1e-12)
        u, sv_, _ = np.linalg.svd(Z - Z.mean(0), full_matrices=False)
        PCs = u[:, :n_pcs] * sv_[:n_pcs]
        xy = g[["centroid_x", "centroid_y"]].to_numpy(float)
        rows, cols = g.centroid_y.to_numpy(int), g.centroid_x.to_numpy(int)
        genes = destripe(pd.DataFrame(L[:, B], index=g.index, columns=names[B]), rows, cols)
        hic = destripe(g[feats], rows, cols)
        lumi = np.log10(tot + 1)[:, None]
        dep = g[["log_contacts"]].to_numpy(float)
        left_g = _smooth_var(_residuals(genes, np.c_[lumi, PCs]), xy) / _smooth_var(_residuals(genes, lumi), xy)
        left_h = _smooth_var(_residuals(hic, np.c_[dep, PCs]), xy) / _smooth_var(_residuals(hic, dep), xy)
        share_g = _smooth_var(_residuals(genes, lumi), xy) / np.nanvar(_residuals(genes, lumi).to_numpy(), 0)
        mods, left_m, share_m = _gene_modules(genes, xy, lumi, PCs)
        q = np.nanquantile(left_g, [0.1, 0.25, 0.5, 0.75, 0.9])
        res[sec] = {"n_genes_pcs": int(len(A)), "n_genes_held_out": int(len(B)), "n_spots": int(len(g)),
                    "held_out_genes_smooth_left_quantiles_10_25_50_75_90": [float(v) for v in q],
                    "held_out_genes_spatial_only": {"n": int((share_g > 0.2).sum()),
                                                    "median_smooth_left": float(np.nanmedian(left_g[share_g > 0.2]))},
                    "held_out_modules": {
                        "n": int(len(mods)), "n_spatial": int((share_m > 0.2).sum()),
                        "median_smooth_left_spatial": float(np.nanmedian(left_m[share_m > 0.2]))
                        if (share_m > 0.2).any() else None,
                        "genes_per_module": [int(len(m)) for m in mods]},
                    "hic_smooth_left": {k: float(v) for k, v in zip(feats, left_h)},
                    "hic_percentile_among_genes": {k: float((left_g < v).mean()) for k, v in zip(feats, left_h)}}
        log(f"calibrate {sec}:", json.dumps(res[sec], indent=1))
        share_h = _smooth_var(_residuals(hic, dep), xy) / np.nanvar(_residuals(hic, dep).to_numpy(), 0)
        rows_out.append(pd.DataFrame({"section": sec,
                                      "feature": list(names[B]) + feats + [f"module{i}" for i in range(len(mods))],
                                      "kind": ["gene"] * len(B) + ["hic"] * len(feats) + ["module"] * len(mods),
                                      "smooth_left": np.r_[left_g, left_h, left_m],
                                      "smooth_share_depth": np.r_[share_g, share_h, share_m],
                                      "n_genes": [1] * len(B) + [0] * len(feats) + [len(m) for m in mods]}))
    pd.concat(rows_out, ignore_index=True).to_parquet(out / "calibrate.parquet")
    with open(out / "calibrate.json", "w") as fh:
        json.dump(res, fh, indent=1)


# ------------------------------------------------------------------------------------------------------------
# stage cnv: copy-number-like profiles of the spots (each chromosome's share of the contact legs) as covariates
# ------------------------------------------------------------------------------------------------------------
def stage_cnv(stats_root: Path, out: Path, n_cnv: int = 5):
    """Per spot and chromosome, log2 of the chromosome's share of the contact legs (2 x cis + trans) over the
    section's median share (``uchrom.fea.chromosome_dosage``, chrY left out) — the coverage profile that gains and
    losses of a tumour clone shift; destriped, its first ``n_cnv`` principal components added to depth + RNA as
    covariates: how much of the contact features' smooth spatial variance is left (``smooth_left``) with and
    without them, next to the same for held-out genes is in stage calibrate.  A tissue without copy-number changes
    is the control."""
    from uchrom.fea import chromosome_dosage
    from uchrom.spatial import destripe

    f = pd.read_parquet(out / "features.parquet")
    pcs = pd.read_parquet(out / "rna_pca.parquet")
    feats = [f"q30.{x}" for x in FEATURES] + [f"q30.{x}" for x in TECHNICAL]
    work = _with_stats(load_store(), stats_root, "q30")
    res, profiles = {}, []
    for sec in SECTIONS:
        g = f[(f.section == sec) & f.qc]
        L = chromosome_dosage(work, cells=g.index, key_added=None)          # QC spots: the median over them
        L = destripe(L, g.centroid_y.to_numpy(int), g.centroid_x.to_numpy(int))
        Z = (L - L.mean()) / L.std()
        u, sv_, vt = np.linalg.svd(Z.to_numpy(), full_matrices=False)
        C = u[:, :n_cnv] * sv_[:n_cnv]
        profiles.append(L.assign(section=sec))
        xy = g[["centroid_x", "centroid_y"]].to_numpy(float)
        D = destripe(g[feats], g.centroid_y.to_numpy(int), g.centroid_x.to_numpy(int))
        dep = np.log10(g[["hic_contacts"]].to_numpy(float))
        P = pcs.loc[g.index].to_numpy(float)
        base = _smooth_var(_residuals(D, dep), xy)
        left = {}
        for name, X in (("rna30", np.c_[dep, P]), ("cnv", np.c_[dep, C]), ("rna30+cnv", np.c_[dep, P, C])):
            left[name] = dict(zip(feats, (_smooth_var(_residuals(D, X), xy) / base).round(4).tolist()))
        cnv_var = (sv_ ** 2 / (sv_ ** 2).sum())[:n_cnv]
        # how much of the chromosome-share variation is spatially smooth (a clone is a patch)
        sm = _smooth_var(L, xy) / np.nanvar(L.to_numpy(), axis=0)
        res[sec] = {"smooth_left": left, "cnv_pc_variance": cnv_var.round(4).tolist(),
                    "chrom_share_smooth_share": dict(zip(L.columns, np.round(sm, 3).tolist())),
                    "chrom_share_sd": dict(zip(L.columns, L.std().round(4).tolist()))}
        log(f"cnv {sec}:", json.dumps(res[sec]["smooth_left"], indent=1))
    pd.concat(profiles).to_parquet(out / "cnv_profiles.parquet")
    with open(out / "cnv.json", "w") as fh:
        json.dump(res, fh, indent=1)


# ------------------------------------------------------------------------------------------------------------
# stage cellcycle: S and G2/M scores of the spots' RNA (Tirosh et al. 2016 genes) as covariates
# ------------------------------------------------------------------------------------------------------------
def _cell_cycle_genes() -> dict:
    """{"S": [...], "G2M": [...]}: Seurat's cc.genes.updated.2019 (registered dataset seurat_cc_genes_2019), read
    with R; mouse symbols are the human ones in title case."""
    import subprocess

    import uchrom.datasets as ds

    f = Path(ds.fetch("seurat_cc_genes_2019", verbose=False))
    f = next(f.rglob("*.rda")) if f.is_dir() else f
    code = (f'load("{f}"); x <- cc.genes.updated.2019; '
            'writeLines(c(paste0("S\\t", x$s.genes), paste0("G2M\\t", x$g2m.genes)))')
    txt = subprocess.run(["Rscript", "-e", code], check=True, capture_output=True, text=True).stdout
    out: dict = {"S": [], "G2M": []}
    for line in txt.splitlines():
        phase, gene = line.split("\t")
        out[phase].append(gene)
    if TISSUES[TISSUE]["genome"].startswith("mm"):
        out = {k: [g[:1].upper() + g[1:].lower() for g in v] for k, v in out.items()}
    return out


def stage_cellcycle(out: Path):
    """Per section: S and G2/M scores of every spot (mean of the phase's genes, log1p CP10k z-scored), how much of
    them the 30 RNA PCs carry, their smooth share, and the contact features' smooth variance left after depth + RNA
    + copy number with and without the two scores (relative to depth alone, as stage cnv)."""
    import scipy.sparse as sps

    from uchrom.spatial import destripe

    genes = _cell_cycle_genes()
    cd = load_store()
    ids = [str(i) for i in cd._cell_ids_axis()]
    adata = cd.linked_adata[ids]
    gi = {g: i for i, g in enumerate(adata.var_names)}
    f = pd.read_parquet(out / "features.parquet")
    pcs = pd.read_parquet(out / "rna_pca.parquet")
    feats = [f"q30.{x}" for x in FEATURES]
    res, scores = {}, []
    for sec in SECTIONS:
        g = f[(f.section == sec) & f.qc]
        X = sps.csr_matrix(adata[list(g.index)].X).astype(np.float64)
        tot = np.maximum(np.asarray(X.sum(1)).ravel(), 1)
        sc = {}
        used = {}
        for phase, names in genes.items():
            idx = [gi[x] for x in names if x in gi]
            used[phase] = len(idx)
            L = np.log1p(X[:, idx].toarray() / tot[:, None] * 1e4)
            sd = L.std(0)
            L = (L[:, sd > 0] - L[:, sd > 0].mean(0)) / sd[sd > 0]
            sc[phase] = L.mean(1)
        C = pd.DataFrame(sc, index=g.index)
        rows, cols = g.centroid_y.to_numpy(int), g.centroid_x.to_numpy(int)
        xy = g[["centroid_x", "centroid_y"]].to_numpy(float)
        Cd = destripe(C, rows, cols)
        P = pcs.loc[g.index].to_numpy(float)
        dep = np.log10(g[["hic_contacts"]].to_numpy(float))
        lumi = np.log10(tot + 1)[:, None]
        r2_pcs = {k: float(1 - _residuals(Cd[[k]], np.c_[lumi, P]).var().iloc[0] / _residuals(Cd[[k]], lumi).var().iloc[0])
                  for k in C.columns}
        share_cc = (_smooth_var(_residuals(Cd, lumi), xy) / np.nanvar(_residuals(Cd, lumi).to_numpy(), 0)).round(4)
        cnv = _cnv_pcs(out, g)
        D = destripe(g[feats], rows, cols)
        base = _smooth_var(_residuals(D, dep), xy)
        left = {}
        steps = [("rna30", np.c_[dep, P]), ("rna30+cc", np.c_[dep, P, Cd.to_numpy()])]
        if cnv is not None:
            steps += [("rna30+cnv", np.c_[dep, P, cnv]), ("rna30+cnv+cc", np.c_[dep, P, cnv, Cd.to_numpy()])]
        for name, cov in steps:
            left[name] = dict(zip(feats, (_smooth_var(_residuals(D, cov), xy) / base).round(4).tolist()))
        last = "rna30+cnv" if cnv is not None else "rna30"
        rem = _residuals(D, steps[[n for n, _ in steps].index(last)][1])
        corr = {k: {ft: float(rem[ft].corr(Cd[k], method="spearman")) for ft in feats} for k in C.columns}
        res[sec] = {"genes_found": used, "r2_of_scores_by_rna_pcs": r2_pcs,
                    "scores_smooth_share": dict(zip(C.columns, share_cc.tolist())),
                    "smooth_left": left, f"spearman_scores_vs_features_after_{last}": corr}
        scores.append(Cd.add_prefix("cc.").assign(section=sec))
        log(f"cellcycle {sec}:", json.dumps({k: v for k, v in res[sec].items() if k != "smooth_left"}, indent=1),
            json.dumps(left, indent=1))
    pd.concat(scores).to_parquet(out / "cellcycle_scores.parquet")
    with open(out / "cellcycle.json", "w") as fh:
        json.dump(res, fh, indent=1)


# ------------------------------------------------------------------------------------------------------------
# stage patch: the copy-number patch of a section, chromosome by chromosome
# ------------------------------------------------------------------------------------------------------------
def _smoothed_grid(x, y, v, sigma: float = 2.0) -> np.ndarray:
    """Gaussian smoothing of per-spot values over the spot grid, skipping missing spots."""
    from scipy.ndimage import gaussian_filter

    img = np.full((y.max() + 1, x.max() + 1), np.nan)
    img[y, x] = v
    ok = np.isfinite(img)
    num = gaussian_filter(np.where(ok, img, 0.0), sigma)
    den = gaussian_filter(ok.astype(float), sigma)
    return (num / np.maximum(den, 1e-12))[y, x]


def stage_patch(stats_root: Path, out: Path, pc: int = 2, frac: float = 0.2):
    """Per section: the copy-number patch -- the QC spots in the top ``frac`` of copy-number principal component
    ``pc`` (stage cnv's profiles: chromosome shares of the contact legs; smoothed over the spot grid, Gaussian
    sigma 2 spots).  PC1 separates tumour from the rest of the tissue, which the RNA follows; PC2 is the copy-number
    axis along which what the RNA leaves of the contact features varies (the sign, arbitrary, is set so that the
    patch is the end with the higher pooled short / long ratio).  The patch is defined by copy number alone, not by
    any contact distance.  Then per chromosome: its copy-number change (log2 of its share of the legs, patch vs
    rest) and the change of its own short / long ratio (median of the spots' log2 ratios, patch minus rest;
    Mann-Whitney): if the ratio rises also on chromosomes whose copy number does not change, the patch folds
    differently genome-wide, not through its gains and losses.  Also the genome-wide contact-decay curves (contacts
    per bp of distance, normalised per group) of the patch and the rest, the patch at 10 % / 30 %, and (with stage
    compartments' table) how the patch's mean scA/B profile compares with the rest's."""
    from scipy import stats as ss

    from uchrom.io import ContactStats

    f = pd.read_parquet(out / "features.parquet")
    prof = pd.read_parquet(out / "cnv_profiles.parquet")
    res, member = {}, []
    for sec in SECTIONS:
        g = f[(f.section == sec) & f.qc]
        st = ContactStats.load(stats_root / sec / f"{sec}.contact_stats_q30.npz")
        row = {f"{sec}:{b}": i for i, b in enumerate(st.cells)}
        idx = np.array([row[c] for c in g.index])
        D, Tr = st.distance[idx].astype(float), st.trans[idx].astype(float)
        L = prof.drop(columns="section").reindex(g.index)
        Z = ((L - L.mean()) / L.std()).fillna(0).to_numpy()
        u, sv_, _ = np.linalg.svd(Z, full_matrices=False)
        comp = u[:, pc - 1] * sv_[pc - 1]
        x, y = g.centroid_x.to_numpy(int), g.centroid_y.to_numpy(int)
        sm = _smoothed_grid(x, y, comp)
        ratio = g["q30.short_long_ratio"].to_numpy(float)
        hi_end = sm >= np.quantile(sm, 1 - frac)
        sign = 1.0 if np.nanmedian(ratio[hi_end]) >= np.nanmedian(ratio[sm <= np.quantile(sm, frac)]) else -1.0
        sm = sign * sm
        legs = 2 * D.sum(axis=2) + Tr
        share = legs / legs.sum(axis=1, keepdims=True)
        SB, LB = slice(51, 77), slice(103, 115)              # Guo et al.'s short / long bins

        def per_chrom(patch):
            rows = []
            for i, c in enumerate(st.chroms):
                if c == "chrY":
                    continue
                sl = np.log2((D[:, i, SB].sum(1) + 0.5) / (D[:, i, LB].sum(1) + 0.5))
                cn = np.log2(share[patch, i].sum() / share[patch].sum() / (share[~patch, i].sum() / share[~patch].sum()))
                rows.append({"chrom": c, "cn_log2": float(cn),
                             "short_long_log2_change": float(np.median(sl[patch]) - np.median(sl[~patch])),
                             "mannwhitney_p": float(ss.mannwhitneyu(sl[patch], sl[~patch]).pvalue),
                             "median_long_contacts": float(np.median(D[:, i, LB].sum(1)))})
            return pd.DataFrame(rows)

        out_sec = {}
        for q in (0.1, frac, 0.3):
            patch = sm >= np.quantile(sm, 1 - q)
            t = per_chrom(patch)
            neutral = t[t.cn_log2.abs() < 0.02]
            pooled = ss.mannwhitneyu(ratio[patch], ratio[~patch])
            out_sec[f"top_{int(q * 100)}"] = {
                "n_patch": int(patch.sum()), "n_spots": int(len(patch)),
                "pooled_short_long": {"median_patch": float(np.median(ratio[patch])),
                                      "median_rest": float(np.median(ratio[~patch])), "mannwhitney_p": float(pooled.pvalue),
                                      "auc": float(pooled.statistic / (patch.sum() * (~patch).sum()))},
                "chromosomes": t.round(6).to_dict(orient="records"),
                "cn_neutral": {"chroms": list(neutral.chrom), "median_change": float(neutral.short_long_log2_change.median()),
                               "n_up": int((neutral.short_long_log2_change > 0).sum())},
                "n_chroms_up": int((t.short_long_log2_change > 0).sum()), "n_chroms": int(len(t)),
                "max_p": float(t.mannwhitney_p.max()),
                "spearman_cn_vs_change": float(ss.spearmanr(t.cn_log2, t.short_long_log2_change)[0])}
            if q == frac:
                edges = np.asarray(st.edges, float)
                width = np.diff(edges)
                curves = {}
                for name, m in (("patch", patch), ("rest", ~patch)):
                    h = D[m].sum(axis=(0, 1))[1:-1]
                    curves[name] = (h / width / h.sum()).tolist()
                out_sec["decay"] = {"distance_lo": edges[:-1].tolist(), "distance_hi": edges[1:].tolist(), **curves}
                c10 = list(st.chroms).index("chr10")
                s10 = np.log2(share[:, c10] / np.median(share[:, c10]))
                out_sec["chr10_share"] = {"median_patch": float(np.median(s10[patch])), "median_rest": float(np.median(s10[~patch])),
                                          "mannwhitney_p": float(ss.mannwhitneyu(s10[patch], s10[~patch]).pvalue)}
                member.append(pd.DataFrame({"in_patch": patch, "cnv_pc_patch": sm}, index=g.index))
                scab = out / f"scab_{sec}.parquet"                 # stage compartments: are the compartments the same?
                if scab.exists():
                    ab = pd.read_parquet(scab)
                    ab = ab.set_index("cell_id") if "cell_id" in ab.columns else ab
                    mp = ab.reindex(g.index[patch]).mean() - 0.5
                    mr = ab.reindex(g.index[~patch]).mean() - 0.5
                    ok = mp.notna() & mr.notna()
                    out_sec["scab_patch_vs_rest"] = {
                        "n_bins": int(ok.sum()), "pearson": float(np.corrcoef(mp[ok], mr[ok])[0, 1]),
                        "same_sign": float((np.sign(mp[ok]) == np.sign(mr[ok])).mean())}
        out_sec.update({"pc": pc, "sign": sign, "frac": frac})
        res[sec] = out_sec
        m = out_sec[f"top_{int(frac * 100)}"]
        log(f"patch {sec}: {m['n_patch']} spots; pooled short/long {m['pooled_short_long']['median_patch']:.3f} vs "
            f"{m['pooled_short_long']['median_rest']:.3f}; chromosomes up {m['n_chroms_up']}/{m['n_chroms']}, "
            f"CN-neutral {m['cn_neutral']['chroms']} median change {m['cn_neutral']['median_change']:.4f}, "
            f"Spearman CN vs change {m['spearman_cn_vs_change']:.2f}")
    pd.concat(member).to_parquet(out / "patch_spots.parquet")
    with open(out / "patch.json", "w") as fh:
        json.dump(res, fh, indent=1)


# ------------------------------------------------------------------------------------------------------------
# stage patch_null: is the copy-number patch special, once the choices made with the contacts are taken out?
# ------------------------------------------------------------------------------------------------------------
def _grid_compactness(x, y, mask) -> float:
    """Mean share of a patch spot's grid neighbours (8-neighbourhood, among the spots present) that are in the
    patch: 1 for a solid blob, about ``mask.mean()`` for scattered spots."""
    from scipy.ndimage import convolve

    present = np.zeros((y.max() + 1, x.max() + 1))
    inside = np.zeros_like(present)
    present[y, x] = 1.0
    inside[y[mask], x[mask]] = 1.0
    k = np.ones((3, 3))
    k[1, 1] = 0.0
    n_present = convolve(present, k, mode="constant")[y, x]
    n_inside = convolve(inside, k, mode="constant")[y, x]
    ok = mask & (n_present > 0)
    return float(np.mean(n_inside[ok] / n_present[ok]))


def stage_patch_null(stats_root: Path, out: Path, results: Path, n_random: int = 1000, seed: int = 0,
                     frac: float = 0.2, n_cnv: int = 5, discovery: str | None = None):
    """Stage ``patch`` chose the copy-number component (PC2, the one along which the contact features left after RNA
    vary) and its sign (the end with the higher short / long ratio) with the contacts.  Three checks without
    those choices, per section (same profiles, smoothing, patch size and statistics as stage ``patch``):

    * every one of the first ``n_cnv`` copy-number components, both ends: the ratio change of the patch (pooled;
      after depth and RNA) and the chromosomes whose own ratio moves the same way;
    * random patches of the same size and compactness (white noise smoothed over the spot grid with the width that
      matches the copy-number patch's compactness, top ``frac``): how often a random patch moves the ratio as much,
      and how often a random patch that does moves every chromosome the same way;
    * the discovery section's component carried to the other section by its chromosome loadings (the component
      whose loadings correlate best, oriented by that correlation): no use of the second section's contacts.

    Writes ``results/patch_null_<tissue>.json``."""
    from scipy import stats as ss

    from _record import save
    from uchrom.io import ContactStats
    from uchrom.spatial import destripe

    rng = np.random.default_rng(seed)
    f = pd.read_parquet(out / "features.parquet")
    prof = pd.read_parquet(out / "cnv_profiles.parquet")
    rna = pd.read_parquet(out / "rna_pca.parquet")
    discovery = discovery or SECTIONS[0]
    SB, LB = slice(51, 77), slice(103, 115)                  # Guo et al.'s short / long bins (stage patch)
    sections, loadings = {}, {}
    for sec in SECTIONS:                                     # per-section arrays
        g = f[(f.section == sec) & f.qc]
        st = ContactStats.load(stats_root / sec / f"{sec}.contact_stats_q30.npz")
        row = {f"{sec}:{b}": i for i, b in enumerate(st.cells)}
        idx = np.array([row[c] for c in g.index])
        D, Tr = st.distance[idx].astype(float), st.trans[idx].astype(float)
        keep = np.array([c != "chrY" for c in st.chroms])
        chroms = [c for c in st.chroms if c != "chrY"]
        SL = np.log2((D[:, keep, SB].sum(2) + 0.5) / (D[:, keep, LB].sum(2) + 0.5))    # spot x chromosome
        legs = (2 * D.sum(axis=2) + Tr)[:, keep]
        share = legs / legs.sum(axis=1, keepdims=True)
        x, y = g.centroid_x.to_numpy(int), g.centroid_y.to_numpy(int)
        ratio = g["q30.short_long_ratio"].to_numpy(float)
        dr = destripe(g[["q30.short_long_ratio"]], y, x)
        X = np.c_[np.log10(g[["hic_contacts"]].to_numpy(float)), rna.loc[g.index].to_numpy(float)]
        resid = _residuals(dr, X).iloc[:, 0].to_numpy(float)
        L = prof.drop(columns="section").reindex(g.index)
        Z = ((L - L.mean()) / L.std()).fillna(0)
        u, sv_, vt = np.linalg.svd(Z.to_numpy(), full_matrices=False)
        sections[sec] = dict(g=g, x=x, y=y, SL=SL, share=share, chroms=chroms, ratio=ratio, resid=resid,
                             comps=u[:, :n_cnv] * sv_[:n_cnv], var=(sv_ ** 2 / (sv_ ** 2).sum())[:n_cnv])
        loadings[sec] = pd.DataFrame(vt[:n_cnv].T, index=Z.columns, columns=[f"pc{k + 1}" for k in range(n_cnv)])

    def evaluate(s, patch) -> dict:
        rest = ~patch
        ch = np.median(s["SL"][patch], axis=0) - np.median(s["SL"][rest], axis=0)
        cn = np.log2((s["share"][patch].sum(0) / s["share"][patch].sum()) / (s["share"][rest].sum(0) / s["share"][rest].sum()))
        pooled = float(np.median(s["ratio"][patch]) - np.median(s["ratio"][rest]))
        sign = np.sign(pooled) if pooled != 0 else 1.0
        neutral = np.abs(cn) < 0.02
        return {"n_patch": int(patch.sum()), "pooled_change": pooled,
                "resid_change": float(np.nanmedian(s["resid"][patch]) - np.nanmedian(s["resid"][rest])),
                "n_chroms_same_way": int((np.sign(ch) == sign).sum()), "n_chroms": int(len(ch)),
                "n_cn_neutral": int(neutral.sum()),
                "cn_neutral_median_change": float(np.median(ch[neutral])) if neutral.any() else None,
                "spearman_cn_vs_change": float(ss.spearmanr(cn, ch)[0]),
                "compactness": _grid_compactness(s["x"], s["y"], patch)}

    def ends(s, comp) -> dict:
        sm = _smoothed_grid(s["x"], s["y"], comp)
        return {"top": sm >= np.quantile(sm, 1 - frac), "bottom": sm <= np.quantile(sm, frac)}

    def _random_field(s, width):
        """White noise over the section's spots, smoothed over the grid (``width`` spots); ``ends`` then smooths it
        with stage patch's 2 spots as it does a copy-number component."""
        return _smoothed_grid(s["x"], s["y"], rng.standard_normal(len(s["ratio"])), width)

    res = {"params": {"frac": frac, "n_random": n_random, "seed": seed, "n_cnv": n_cnv, "discovery": discovery,
                      "short_bins": [SB.start, SB.stop], "long_bins": [LB.start, LB.stop]}, "sections": {}}
    for sec, s in sections.items():
        log(f"patch_null {sec}: {len(s['ratio'])} spots")
        comps = {}
        for k in range(n_cnv):                               # every component, both ends: no choice made
            for end, patch in ends(s, s["comps"][:, k]).items():
                comps[f"pc{k + 1}_{end}"] = evaluate(s, patch)
        # the patch as stage patch defines it (PC2, the end with the higher pooled ratio) and its compactness
        e2 = ends(s, s["comps"][:, 1])
        obs_end = "top" if np.median(s["ratio"][e2["top"]]) >= np.median(s["ratio"][e2["bottom"]]) else "bottom"
        observed = comps[f"pc2_{obs_end}"]
        target = observed["compactness"]
        # random patches: white noise smoothed with the width whose patches match that compactness
        widths = [2, 3, 4, 6, 8, 12, 16]
        calib = {}
        for w in widths:
            cs = [_grid_compactness(s["x"], s["y"], ends(s, _random_field(s, w))["top"]) for _ in range(20)]
            calib[w] = float(np.mean(cs))
        width = min(widths, key=lambda w: abs(calib[w] - target))
        null = []
        for _ in range(n_random):
            null.append(evaluate(s, ends(s, _random_field(s, width))["top"]))
        nd = pd.DataFrame(null)
        big = nd[nd.pooled_change.abs() >= abs(observed["pooled_change"])]

        def p_two(col):
            return float((1 + (nd[col].abs() >= abs(observed[col])).sum()) / (len(nd) + 1))

        res["sections"][sec] = {
            "n_spots": int(len(s["ratio"])), "cnv_pc_variance": s["var"].round(4).tolist(),
            "components": comps, "observed": {"component": "pc2", "end": obs_end, **observed},
            "null": {"width": width, "compactness_by_width": calib, "target_compactness": target,
                     "compactness_median": float(nd.compactness.median()),
                     "pooled_change_quantiles": nd.pooled_change.quantile([0.025, 0.5, 0.975]).round(4).tolist(),
                     "resid_change_quantiles": nd.resid_change.quantile([0.025, 0.5, 0.975]).round(4).tolist(),
                     "p_pooled": p_two("pooled_change"), "p_resid": p_two("resid_change"),
                     "n_as_large": int(len(big)),
                     "share_all_chroms_same_way_given_as_large":
                         float((big.n_chroms_same_way == big.n_chroms).mean()) if len(big) else None,
                     "share_all_chroms_same_way": float((nd.n_chroms_same_way == nd.n_chroms).mean()),
                     "components_p_pooled": {k: float((1 + (nd.pooled_change.abs() >= abs(v["pooled_change"])).sum())
                                                      / (len(nd) + 1)) for k, v in comps.items()},
                     "components_p_resid": {k: float((1 + (nd.resid_change.abs() >= abs(v["resid_change"])).sum())
                                                     / (len(nd) + 1)) for k, v in comps.items()}}}
        log(f"  observed {obs_end}: pooled {observed['pooled_change']:+.4f}, resid {observed['resid_change']:+.4f}, "
            f"chromosomes {observed['n_chroms_same_way']}/{observed['n_chroms']}; null width {width}: "
            f"p_pooled {res['sections'][sec]['null']['p_pooled']:.3f}, p_resid {res['sections'][sec]['null']['p_resid']:.3f}, "
            f"all chromosomes given as large {res['sections'][sec]['null']['share_all_chroms_same_way_given_as_large']}")
    # the discovery section's component, carried to the others by its loadings
    d = res["sections"][discovery]["observed"]
    ref = loadings[discovery]["pc2"] * (1.0 if d["end"] == "top" else -1.0)
    res["carried"] = {}
    for sec, s in sections.items():
        if sec == discovery:
            continue
        lo = loadings[sec].reindex(ref.index)
        r = lo.apply(lambda c: float(np.corrcoef(c, ref)[0, 1]))
        k = int(np.argmax(np.abs(r.to_numpy())))
        comp = s["comps"][:, k] * np.sign(r.iloc[k])            # oriented like the discovery patch
        ev = evaluate(s, ends(s, comp)["top"])
        null = res["sections"][sec]["null"]
        res["carried"][sec] = {"component": f"pc{k + 1}", "loading_correlation": float(r.iloc[k]),
                               "all_loading_correlations": r.round(3).to_dict(), **ev,
                               "p_pooled_vs_null": None, "p_resid_vs_null": None}
        log(f"  carried to {sec}: pc{k + 1} (loading r {r.iloc[k]:+.2f}): pooled {ev['pooled_change']:+.4f}, "
            f"resid {ev['resid_change']:+.4f}, chromosomes {ev['n_chroms_same_way']}/{ev['n_chroms']}")
    # p values of the carried patches against their section's random patches (re-drawn, same width)
    for sec, c in res["carried"].items():
        s = sections[sec]
        width = res["sections"][sec]["null"]["width"]
        nd = pd.DataFrame([evaluate(s, ends(s, _random_field(s, width))["top"]) for _ in range(n_random)])
        c["p_pooled_vs_null"] = float((1 + (nd.pooled_change.abs() >= abs(c["pooled_change"])).sum()) / (len(nd) + 1))
        c["p_resid_vs_null"] = float((1 + (nd.resid_change.abs() >= abs(c["resid_change"])).sum()) / (len(nd) + 1))
    save(results / f"patch_null_{TISSUE}.json", res, script=__file__, datasets=[DATASET, "spatial_hicrna"],
         params=res["params"])


# ------------------------------------------------------------------------------------------------------------
# stage local: per-spot boundary insulation and loop strength (window counts of the pooled-map structures)
# ------------------------------------------------------------------------------------------------------------
def _cnv_pcs(out: Path, g: pd.DataFrame, n: int = 5):
    """The first ``n`` principal components of the spots' chromosome-share profiles (stage cnv), or None."""
    p = out / "cnv_profiles.parquet"
    if not p.exists():
        return None
    L = pd.read_parquet(p).drop(columns="section").reindex(g.index)
    Z = (L - L.mean()) / L.std()
    u, sv_, _ = np.linalg.svd(Z.fillna(0).to_numpy(), full_matrices=False)
    return u[:, :n] * sv_[:n]


def _adjusted_tests(g: pd.DataFrame, V: pd.DataFrame, pcs: pd.DataFrame, cnv=None, *, with_moran: bool = True,
                    with_sparkx: bool = True, n_null: int = 0, seed: int = 0):
    """Per column of V on the spots g, destriped: the smooth share of the variance after depth, + RNA (30 PCs)
    [, + copy-number PCs], SPARK-X p-values (optional), Moran's I (optional) and the smooth share of the same
    values with the spots shuffled (``n_null`` times; the noise level of the measure)."""
    from uchrom.spatial import destripe, smooth_share, spatial_autocorr, sparkx

    xy = g[["centroid_x", "centroid_y"]].to_numpy(float)
    ds = destripe(V, g.centroid_y.to_numpy(int), g.centroid_x.to_numpy(int))
    dep = np.log10(g[["hic_contacts"]].to_numpy(float))
    P = pcs.loc[g.index].to_numpy(float)
    steps = [("depth", dep), ("depth_rna30", np.c_[dep, P])]
    if cnv is not None:
        steps.append(("depth_rna30_cnv", np.c_[dep, P, cnv]))
    t = pd.DataFrame(index=pd.Index(V.columns, name="feature"))
    graph = _grid_graph(g) if with_moran else None
    rng = np.random.default_rng(seed)
    base = None
    for name, cov in steps:
        r = _residuals(ds, cov)
        sm = smooth_share(r, xy)
        t[f"{name}.smooth_share"] = sm
        var = np.nanvar(r.to_numpy(float), axis=0)
        if base is None:
            base = sm * var
        t[f"{name}.smooth_left"] = sm * var / base
        if n_null:
            nulls = [smooth_share(r.iloc[rng.permutation(len(r))].set_axis(r.index), xy) for _ in range(n_null)]
            t[f"{name}.smooth_share_null"] = np.mean(nulls, axis=0)
        if with_sparkx:
            t[f"{name}.sparkx_padj"] = sparkx(ds, xy, covariates=cov)["padj"]
        if with_moran:
            t[f"{name}.moran_I"] = spatial_autocorr(values=r, graph=graph)["I"]
    return t


SCORES = {"boundary": {"logratio": "insulation", "oe": "insulation_oe"}, "loop": {"logratio": "loops", "oe": "loops_oe"}}


def _structures(wc, kind: str) -> pd.DataFrame:
    """Chromosome and span (bp, outermost window edges) of each structure of one kind."""
    w = wc.windows[wc.windows["kind"] == kind]
    t = w.groupby("feature").agg(chrom=("chrom", "first"), lo=("start1", "min"), hi=("end2", "max"))
    t.index = t.index.astype(str)
    t["span"] = t["hi"] - t["lo"]
    return t


def _replication(a: pd.DataFrame, b: pd.DataFrame, col: str, info: pd.DataFrame) -> dict:
    """How the structures' smooth shares above the shuffled ones (the excess) agree between two sections, and
    what else orders them: their contacts, their chromosome (X: haploid in a male tissue), their span."""
    from scipy import stats as ss

    common = a.index.intersection(b.index)
    ea = a.loc[common, col] - a.loc[common, col + "_null"]
    eb = b.loc[common, col] - b.loc[common, col + "_null"]
    top_a, top_b = ea >= ea.quantile(0.9), eb >= eb.quantile(0.9)
    lc = np.log(a.loc[common, "counts_per_spot"] * b.loc[common, "counts_per_spot"])
    ranks = [pd.Series(ss.rankdata(x), index=common) for x in (ea, eb, lc)]

    def resid(y):
        return y - np.polyval(np.polyfit(ranks[2], y, 1), ranks[2])

    both = np.minimum(ea, eb)
    top = both >= both.quantile(0.9)
    is_x = info.loc[common, "chrom"].isin(["chrX", "X"])
    return {"n_both": int(len(common)),
            "median_excess_r1": float(ea.median()), "median_excess_r2": float(eb.median()),
            "spearman_excess_between_sections": float(ea.corr(eb, method="spearman")),
            "partial_spearman_given_counts": float(np.corrcoef(resid(ranks[0]), resid(ranks[1]))[0, 1]),
            "spearman_excess_counts": [float(ss.spearmanr(ea, a.loc[common, "counts_per_spot"])[0]),
                                       float(ss.spearmanr(eb, b.loc[common, "counts_per_spot"])[0])],
            "spearman_excess_span": float(ss.spearmanr(both, info.loc[common, "span"])[0]),
            "chrX_share_all": float(is_x.mean()), "chrX_share_top_decile": float(is_x[top].mean()),
            "top_decile_overlap": int((top_a & top_b).sum()), "top_decile_expected": float(top_a.sum() * top_b.mean()),
            "n_excess_over_0.02_both": int(((ea > 0.02) & (eb > 0.02)).sum())}


def stage_local(stats_root: Path, out: Path, min_counts: float = 2.0, seed: int = 0):
    """Per section: window_scores of the spots, against each spot's own expected (its contact-distance histogram
    per chromosome, ``uchrom.fea.window_expected``) and as plain log ratios.  The pooled per-spot boundary and loop
    strengths are tested like the global features; every boundary / loop with >= ``min_counts`` contacts per spot
    in its windows (on average) on its own, in both versions: its smooth share after depth / + RNA / + copy number
    against shuffled spots, and how the structures' smooth shares agree between the two sections."""
    import cooler

    from uchrom.fea import window_expected, window_scores
    from uchrom.io import ContactStats, WindowCounts

    f = pd.read_parquet(out / "features.parquet")
    pcs = pd.read_parquet(out / "rna_pca.parquet")
    glob, per, info = [], {}, {}
    for sec in SECTIONS:
        wc = WindowCounts.load(stats_root / sec / f"{sec}.window_counts.npz")
        wc.cells = np.asarray([f"{sec}:{b}" for b in wc.cells], dtype=object)
        st = ContactStats.load(stats_root / sec / f"{sec}.contact_stats_q30.npz")
        st.cells = np.asarray([f"{sec}:{b}" for b in st.cells], dtype=object)
        sizes = cooler.Cooler(str(stats_root / sec / f"{sec}.bulk_25000.cool")).chromsizes.to_dict()
        sc = window_scores(wc, expected=window_expected(wc, st, chromsizes=sizes))
        g = f[(f.section == sec) & f.qc]
        cnv = _cnv_pcs(out, g)
        cells = sc["cells"].reindex(g.index)
        cells.to_parquet(out / f"window_cells_{sec}.parquet")
        cols = [c for c in ("boundary_strength", "boundary_ratio", "interior_ratio", "loop_strength",
                            "boundary_strength_oe", "interior_oe", "loop_strength_oe") if c in cells]
        t = _adjusted_tests(g, cells[cols], pcs, cnv, n_null=5, seed=seed)
        t.insert(0, "section", sec)
        glob.append(t.reset_index())
        for kind, counts_key in (("boundary", "boundary_counts"), ("loop", "loop_counts")):
            if SCORES[kind]["oe"] not in sc:
                continue
            info[kind] = _structures(wc, kind)
            cnt = sum(v for v in sc[counts_key].values())
            n_per_spot = pd.DataFrame(cnt, index=sc["cells"].index).reindex(g.index).mean()
            keep = n_per_spot.index[n_per_spot >= min_counts]
            for version, score_key in SCORES[kind].items():
                S = sc[score_key].reindex(g.index)[keep]
                S.columns = [str(c) for c in S.columns]
                tt = _adjusted_tests(g, S, pcs, cnv, with_moran=False, with_sparkx=False, n_null=2, seed=seed)
                tt["counts_per_spot"] = n_per_spot[keep].to_numpy()
                per[(sec, kind, version)] = tt
                last = [c for c in tt.columns if c.endswith(".smooth_share")][-1]
                null = last + "_null"
                log(f"local {sec} {kind} {version}: {len(keep)} of {len(n_per_spot)} with >= {min_counts} contacts "
                    f"per spot; {last} median {tt[last].median():.3f} (shuffled {tt[null].median():.3f}), "
                    f"> 3x shuffled: {(tt[last] > 3 * tt[null]).sum()}")
    pd.concat(glob, ignore_index=True).to_parquet(out / "local_global.parquet")
    rep = {}
    for kind in ("boundary", "loop"):
        for version in SCORES[kind]:
            if (SECTIONS[0], kind, version) not in per:
                continue
            a, b = per[(SECTIONS[0], kind, version)], per[(SECTIONS[1], kind, version)]
            for col in [c for c in a.columns if c.endswith(".smooth_share")]:
                rep[f"{kind}/{version}/{col}"] = _replication(a, b, col, info[kind])
            tab = pd.concat({s: per[(s, kind, version)] for s in SECTIONS}, names=["section"]).reset_index()
            tab.join(info[kind], on="feature").to_parquet(out / f"local_{kind}s_{version}.parquet")
    with open(out / "local_replication.json", "w") as fh:
        json.dump(rep, fh, indent=1)
    log("local replication:", json.dumps({k: v for k, v in rep.items() if "depth_rna30_cnv" in k}, indent=1))


# ------------------------------------------------------------------------------------------------------------
# stage compartments: scA/B of every spot from its 1-Mb map (CpG of the contact partners), per section
# ------------------------------------------------------------------------------------------------------------
def stage_compartments(out: Path, workers: int):
    import uchrom.datasets as ds
    from uchrom.strc.comp import single_cell_compartments

    cd = load_store()
    ids = pd.Index([str(i) for i in cd._cell_ids_axis()])
    sec_of = pd.Series(cd.cells["section"].to_numpy(), index=ids)
    track = ds.fetch(TISSUES[TISSUE]["genome"], verbose=False)
    for sec in SECTIONS:
        t = time.time()
        m = single_cell_compartments(cd, contacts=f"per_spot.{sec}", track=track, cells=list(ids[sec_of == sec]),
                                     key_added=None, workers=workers)
        m.columns = m.columns.astype(str)
        m.astype(np.float32).to_parquet(out / f"scab_{sec}.parquet")
        log(f"compartments {sec}: {m.shape}, {np.isfinite(m.to_numpy()).mean():.2f} of the values set, "
            f"{time.time() - t:.0f} s")


def stage_compartments_sv(out: Path, min_cells: float = 0.8):
    """SPARK-X per 1-Mb bin of the scA/B values, raw / depth / depth + RNA, bins set in >= 80 % of the spots."""
    from uchrom.spatial import sparkx

    f = pd.read_parquet(out / "features.parquet")
    pcs = pd.read_parquet(out / "rna_pca.parquet")
    tables = []
    for sec in SECTIONS:
        m = pd.read_parquet(out / f"scab_{sec}.parquet")
        g = f[(f.section == sec) & f.qc]
        m = m.reindex(g.index)
        keep = np.isfinite(m.to_numpy()).mean(0) >= min_cells
        m = m.loc[:, keep]
        xy = g[["centroid_x", "centroid_y"]].to_numpy(float)
        depth = np.log10(g[["hic_contacts"]].to_numpy(float))
        p10 = pcs.loc[g.index, [f"PC{i}" for i in range(1, 11)]].to_numpy(float)
        t = pd.DataFrame(index=m.columns)
        for name, cov in {"raw": None, "depth": depth, "depth_rna10": np.c_[depth, p10]}.items():
            r = sparkx(m, xy, covariates=cov)
            t[f"sparkx_{name}.pval"] = r["pval"]
            t[f"sparkx_{name}.padj"] = r["padj"]
        t["mean"] = m.mean().to_numpy()
        t.insert(0, "section", sec)
        tables.append(t.rename_axis("bin").reset_index())
        log(f"compartments sv {sec}: {m.shape[1]} bins, raw significant {(t['sparkx_raw.padj'] < 0.05).sum()}, "
            f"after RNA {(t['sparkx_depth_rna10.padj'] < 0.05).sum()}")
    pd.concat(tables, ignore_index=True).to_parquet(out / "compartments_sv.parquet")


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
    # 1b. the same contrast on the authors' spatial domains, where they were published
    dom = _published_domains()
    if dom is not None:
        cfg = TISSUES[TISSUE]["domains"]
        qd = q.join(dom)
        dom_means = {}
        for sec in SECTIONS:
            g = qd[(qd.section == sec) & qd.domain.notna()]
            if g.empty:
                continue
            col = "q30.short_long_ratio"
            dom_means[f"q30/{sec}"] = g.groupby("domain")[col].agg(["median", "mean", "count"]).round(4) \
                .to_dict(orient="index")
            hi = g[g.domain.isin(cfg["contrast"]["high"])][col]
            lo = g[g.domain.isin(cfg["contrast"]["low"])][col]
            u = ss.mannwhitneyu(hi, lo, alternative="two-sided")
            res[f"domain_high_vs_low/q30/{sec}"] = {
                "median_high": float(hi.median()), "median_low": float(lo.median()),
                "n_high": int(len(hi)), "n_low": int(len(lo)), "mannwhitney_p_two_sided": float(u.pvalue),
                "auc": float(u.statistic / (len(hi) * len(lo)))}
        res["domain_short_long"] = dom_means
    # 2. spatial variation per feature and section: effect sizes at each adjustment step, both sections
    steps = ["raw", "destriped", "depth", "depth_rna30"]
    table = {}
    for d in sv.to_dict(orient="records"):          # column names with dots: not itertuples (renames them)
        table[f"{d['section']}/{d['feature']}"] = {
            k: (None if pd.isna(v) else float(v)) for k, v in d.items() if k not in ("section", "feature")}
    res["sv_table"] = table
    res["sv_columns"] = [c for c in sv.columns if c not in ("section", "feature")]
    # 3. replication: region means of the destriped, depth- and RNA-adjusted values (sd units), correlated
    # between the sections over the regions
    from uchrom.spatial import destripe

    pcs = pd.read_parquet(out / "rna_pca.parquet")
    feats = [f"q30.{x}" for x in FEATURES]
    means = {}
    for sec in SECTIONS:
        g = q[q.section == sec]
        ds = destripe(g[feats], g.centroid_y.to_numpy(int), g.centroid_x.to_numpy(int))
        dep = np.log10(g[["hic_contacts"]].to_numpy(float))
        for step, X in (("depth", dep), ("depth_rna30", np.c_[dep, pcs.loc[g.index].to_numpy(float)])):
            r = _residuals(ds, X)
            r = (r - r.mean()) / r.std()
            means[(sec, step)] = r.join(g["region"]).groupby("region")[feats].mean().drop(index="other",
                                                                                          errors="ignore")
    rep = {}
    for step in ("depth", "depth_rna30"):
        a, b = means[(SECTIONS[0], step)], means[(SECTIONS[1], step)]
        common = a.index.intersection(b.index)
        rep[step] = {c: {"r_between_sections": float(np.corrcoef(a.loc[common, c], b.loc[common, c])[0, 1]),
                         SECTIONS[0]: a.loc[common, c].round(3).to_dict(), SECTIONS[1]: b.loc[common, c].round(3).to_dict()}
                     for c in feats}
    res["region_replication"] = rep
    cal = out / "calibrate.json"
    if cal.exists():
        res["calibration"] = json.loads(cal.read_text())
    cnv = out / "cnv.json"
    if cnv.exists():
        res["cnv"] = json.loads(cnv.read_text())
    cc = out / "cellcycle.json"
    if cc.exists():
        res["cellcycle"] = json.loads(cc.read_text())
    pj = out / "patch.json"
    if pj.exists():
        res["patch"] = json.loads(pj.read_text())
    loc = out / "local_replication.json"
    if loc.exists():
        res["local_replication"] = json.loads(loc.read_text())
        lg = pd.read_parquet(out / "local_global.parquet")
        res["local_per_spot"] = {f"{r['section']}/{r['feature']}": {k: (None if pd.isna(v) else float(v))
                                                                    for k, v in r.items() if k not in ("section", "feature")}
                                 for r in lg.to_dict(orient="records")}
    results.mkdir(parents=True, exist_ok=True)
    save(results / f"global_features_{TISSUE}.json", res, script=__file__, datasets=[DATASET, "spatial_hicrna"],
         params={"min_contacts": MIN_CONTACTS, "region_markers": REGION_MARKERS, "features": FEATURES,
                 "domains": TISSUES[TISSUE].get("domains")})
    figdir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(figdir / f"spatial_variable_{TISSUE}.npz",
                        cell_id=f.index.to_numpy(str), section=f.section.to_numpy(str),
                        x=f.centroid_x.to_numpy(float), y=f.centroid_y.to_numpy(float), qc=f.qc.to_numpy(bool),
                        region=f.region.fillna("other").to_numpy(str),
                        **{c.replace(".", "_"): f[c].to_numpy(float) for c in f.columns
                           if c.startswith(("q30.", "all.")) and not c.startswith(("q30.trans_share", "all.trans_share"))})
    with open(figdir / f"spatial_variable_{TISSUE}.json", "w") as fh:
        json.dump(res, fh, indent=1, default=float)
    _figdata_tables(out, figdir, f, q, pcs)
    log("summary:", json.dumps({k: v for k, v in res.items() if k.startswith("guo_")}, indent=1))


def _figdata_tables(out: Path, figdir: Path, f: pd.DataFrame, q: pd.DataFrame, pcs: pd.DataFrame) -> None:
    """Figure data beyond the per-spot features: ``spatial_variable_<tissue>_spots.parquet`` (QC spots: the
    features destriped, their residuals after depth + RNA and + copy number, the copy-number PCs, the region
    scores, the pooled window scores), ``_calibration.parquet`` (stage calibrate) and ``_local.parquet`` (every
    structure's smooth shares in both sections and both score versions)."""
    from uchrom.spatial import destripe

    reg = pd.read_parquet(out / "regions.parquet")
    feats = [f"q30.{x}" for x in FEATURES]
    parts = []
    for sec in SECTIONS:
        g = q[q.section == sec]
        rows, cols = g.centroid_y.to_numpy(int), g.centroid_x.to_numpy(int)
        ds = destripe(g[feats], rows, cols)
        dep = np.log10(g[["hic_contacts"]].to_numpy(float))
        P = pcs.loc[g.index].to_numpy(float)
        t = pd.DataFrame({"section": sec, "x": g.centroid_x, "y": g.centroid_y}, index=g.index)
        t["log_contacts"] = dep[:, 0]
        t["destriped.log_contacts"] = destripe(pd.DataFrame({"v": dep[:, 0]}, index=g.index), rows, cols)["v"]
        t = t.join(ds.add_prefix("destriped."))
        t = t.join(_residuals(ds, np.c_[dep, P]).add_prefix("rna30."))
        C = _cnv_pcs(out, g)
        if C is not None:
            t = t.join(_residuals(ds, np.c_[dep, P, C]).add_prefix("rna30_cnv."))
            for i in range(min(3, C.shape[1])):
                t[f"cnv_pc{i + 1}"] = C[:, i]
        ccp = out / "cellcycle_scores.parquet"
        if ccp.exists() and C is not None:
            cc = pd.read_parquet(ccp).reindex(g.index)[["cc.S", "cc.G2M"]]
            t = t.join(cc)
            t = t.join(_residuals(ds, np.c_[dep, P, C, cc.to_numpy(float)]).add_prefix("rna30_cnv_cc."))
        wcells = out / f"window_cells_{sec}.parquet"
        if wcells.exists():
            w = pd.read_parquet(wcells).reindex(g.index)
            keep = [c for c in w.columns if c.endswith(("_oe", "strength"))]
            t = t.join(destripe(w[keep], rows, cols).add_prefix("window."))
        pp = out / "patch_spots.parquet"
        if pp.exists():
            t = t.join(pd.read_parquet(pp))
        parts.append(t.join(reg[[c for c in reg.columns if c.startswith("z.")] + ["region"]]))
    spots = pd.concat(parts).rename_axis("cell_id")
    cd = load_store()                                      # the authors' cell types, where they gave them
    cells = cd.cells.copy()
    cells.index = pd.Index([str(i) for i in cd._cell_ids_axis()])
    if "cell_type" in cells:
        spots = spots.join(cells[["cell_type"]].astype(str).replace({"nan": None, "None": None}))
    dom = _published_domains()
    if dom is not None:
        spots = spots.join(dom)
    spots.to_parquet(figdir / f"spatial_variable_{TISSUE}_spots.parquet")
    cal = out / "calibrate.parquet"
    if cal.exists():
        pd.read_parquet(cal).to_parquet(figdir / f"spatial_variable_{TISSUE}_calibration.parquet")
    loc = [pd.read_parquet(p).assign(kind=p.stem.split("_")[1][:-1], version=p.stem.split("_")[2])
           for p in sorted(out.glob("local_*s_*.parquet"))]
    if loc:
        pd.concat(loc, ignore_index=True).to_parquet(figdir / f"spatial_variable_{TISSUE}_local.parquet")


def default_figdata(out: Path) -> Path:
    from _paper import paper_root

    root = paper_root()
    return root / "manuscripts" / "nmeth-bc" / "figures" / "results" if root else out / "figdata"


def main(argv=None):
    from uchrom.datasets import data_dir

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tissue", default="brain", choices=sorted(TISSUES))
    ap.add_argument("--stats", required=False, help="folder of <sample>/<sample>.contact_stats_*.npz")
    ap.add_argument("--out", default=None, help="cache (default <data>/spatial_variable_cache)")
    ap.add_argument("--results", default=str(HERE / "results"))
    ap.add_argument("--figdata", default=None)
    ap.add_argument("--stages", default="features,regions,sv,summary",
                    help="comma-separated: check, features, regions, sv, calibrate, cnv, cellcycle, patch, patch_null, local, compartments, "
                         "compartments_sv, summary (all: "
                         "every stage)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--perms", type=int, default=999)
    ap.add_argument("--random", type=int, default=1000, help="random patches of stage patch_null")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    configure(a.tissue)
    out = (Path(a.out) if a.out else data_dir() / "spatial_variable_cache") / a.tissue
    out.mkdir(parents=True, exist_ok=True)
    figdir = Path(a.figdata) if a.figdata else default_figdata(out)
    stages = (["check", "features", "regions", "sv", "calibrate", "compartments", "compartments_sv", "summary"]
              if a.stages == "all"
              else a.stages.split(","))
    for st in stages:
        t = time.time()
        log(f"--- stage {st}")
        if st == "check":
            stage_check(Path(a.stats), Path(a.results))
        elif st == "features":
            stage_features(Path(a.stats), out)
        elif st == "regions":
            stage_regions(out)
        elif st == "sv":
            stage_sv(out, a.perms, a.seed)
        elif st == "compartments":
            stage_compartments(out, a.workers)
        elif st == "compartments_sv":
            stage_compartments_sv(out)
        elif st == "cnv":
            stage_cnv(Path(a.stats), out)
        elif st == "local":
            stage_local(Path(a.stats), out)
        elif st == "calibrate":
            stage_calibrate(out, a.seed)
        elif st == "cellcycle":
            stage_cellcycle(out)
        elif st == "patch":
            stage_patch(Path(a.stats), out)
        elif st == "patch_null":
            stage_patch_null(Path(a.stats), out, Path(a.results), n_random=a.random, seed=a.seed)
        elif st == "summary":
            stage_summary(out, Path(a.results), figdir)
        else:
            sys.exit(f"unknown stage {st!r}")
        log(f"--- stage {st} done in {time.time() - t:.0f} s")


if __name__ == "__main__":
    main()
