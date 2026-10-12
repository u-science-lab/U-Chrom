"""What the shared ExN - Oligo locus differences are: each Liu 2025 locus's structural effect (the mean, over its cis
pairs, of the ExN - Oligo difference of log median distance, detrended per chromosome and separation; ``recon.py``
stage loci, column ``chromband``) in imaging and in every reconstruction, against the expression difference of the
genes around it (TSS within +-500 kb of the locus midpoint; pseudo-bulk RNA of the same cells: GAGE-seq, HiRES,
scHiCAR; UCSC mm10 refGene).  Positive structural effect = the locus lies farther from the rest of its chromosome in
neurons.

Outputs: ``--out``/locus_effects.parquet (locus x source: structural effects, expression differences), the figure
inputs ``--figdata``/cross_assay_loci_{tracks,maps}.parquet, ``--results``/biology.json (Spearman correlations).

    python benchmarks/cross_assay/biology.py --recon-root $SCRATCH/uchrom-nd/runs/xassay --liu STORE --out DIR \
        --figdata DIR    (or --panel liu2025_panel.parquet: the store's bins, to run where the store is not)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

AUTOS = [f"chr{k}" for k in range(1, 20)]
WINDOW = 500_000
#: (folder under --recon-root, variant, label) of the structural sources (reference reconstruction per dataset)
SOURCES = [("recon_tan", "imaging", "imaging (Liu 2025)"), ("recon_tan", "dip", "Dip-C (Tan), EMber diploid"),
           ("recon_hires_brain", "dip", "HiRES, EMber diploid"), ("recon_gageseq_mouse_cortex", "hap", "GAGE-seq, EMber"),
           ("recon_dschic_aging_cortex", "hap", "dscHi-C, EMber"), ("recon_droplet_hic_mouse_cortex", "hap", "Droplet Hi-C, EMber"),
           ("recon_schicar_mouse_cortex", "hap", "scHiCAR, EMber")]
RNA = ["gageseq_mouse_cortex", "hires_brain", "schicar_mouse_cortex"]
MAP_CHROM = "chr2"                                     # the chromosome of the difference-map panel


def locus_effect(t: pd.DataFrame, col: str = "chromband") -> pd.Series:
    """Per panel locus: mean of ``col`` over its cis pairs (as i or j)."""
    r = t.reset_index()
    s = pd.concat([pd.Series(r[col].to_numpy(), index=r["i"].to_numpy()),
                   pd.Series(r[col].to_numpy(), index=r["j"].to_numpy())])
    return s.groupby(level=0).mean()


def pseudobulk_rna(name: str) -> pd.DataFrame:
    """Genes x {ExN, Oligo}: counts per million of the summed counts of each class's cells (atlas store's RNA)."""
    import pilot as P
    import uchrom.datasets as ds

    P._pandas_compat()
    cd = ds.load(name)
    ad = cd.linked_adata
    spec = P.DATASETS[name]
    lab = cd.cells[spec["column"]].astype(str).map(spec["classes"])
    lab.index = lab.index.astype(str)
    obs = pd.Index(ad.obs_names.astype(str))
    out = {}
    for c in ("ExN", "Oligo"):
        m = obs.isin(lab.index[lab == c])
        x = ad.X[np.flatnonzero(m)]
        s = np.asarray(x.sum(0)).ravel().astype(float)
        out[c] = s / s.sum() * 1e6
        out[f"n_{c}"] = int(m.sum())
    t = pd.DataFrame({c: out[c] for c in ("ExN", "Oligo")}, index=pd.Index(ad.var_names.astype(str), name="gene"))
    t.attrs = {k: v for k, v in out.items() if k.startswith("n_")}
    return t


def gene_tss() -> pd.DataFrame:
    import uchrom.datasets as ds
    from uchrom.fea import read_gtf

    g = read_gtf(ds.path("mm10_refgene") if ds.path("mm10_refgene").exists() else ds.fetch("mm10_refgene"))
    g = g[g["feature"] == "gene"]                      # gene loci derived from the refGene transcripts
    name = g["gene_name"].where(g["gene_name"].notna() & (g["gene_name"] != ""), g["gene_id"])
    tss = np.where(g["strand"] == "+", g["start"], g["end"] - 1)
    t = pd.DataFrame({"gene": name.astype(str).to_numpy(), "chrom": g["chrom"].astype(str).to_numpy(), "tss": tss})
    return t.groupby("gene").first().reset_index()     # one locus per gene name (the first of paralogous loci)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--recon-root", type=Path, required=True)
    ap.add_argument("--liu", type=Path, help="the Liu 2025 store (its bins are the panel)")
    ap.add_argument("--panel", type=Path, help="or the panel itself: parquet of the store's bins (chrom, start, end)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--figdata", type=Path, required=True)
    ap.add_argument("--results", type=Path, default=HERE / "results")
    a = ap.parse_args()
    from _record import save
    from chromdata import ChromData
    from scipy.stats import spearmanr

    a.out.mkdir(parents=True, exist_ok=True)
    a.figdata.mkdir(parents=True, exist_ok=True)
    bins = pd.read_parquet(a.panel) if a.panel else ChromData.read(str(a.liu), backed=True).bins
    panel = bins[bins["chrom"].astype(str).isin(AUTOS)][["chrom", "start", "end"]].copy()
    panel["chrom"] = panel["chrom"].astype(str)
    panel["mid"] = (panel["start"] + panel["end"]) // 2
    eff = pd.DataFrame(index=panel.index)
    tables = {}
    for folder, v, label in SOURCES:
        p = a.recon_root / folder / f"loci_liu2025_{v}.parquet"
        if p.exists():
            tables[label] = pd.read_parquet(p)
            eff[label] = locus_effect(tables[label]).reindex(panel.index)
    # expression around each locus
    tss = gene_tss()
    tss = tss[tss["chrom"].isin(AUTOS)]
    rna = {}
    for name in RNA:
        pb = pseudobulk_rna(name)
        g = tss.merge(pb, left_on="gene", right_index=True)
        rows = []
        for ch, loci in panel.groupby("chrom"):
            gg = g[g["chrom"] == ch]
            t = gg["tss"].to_numpy()
            for idx, mid in zip(loci.index, loci["mid"]):
                k = np.abs(t - mid) <= WINDOW
                e, o = gg["ExN"].to_numpy()[k].sum(), gg["Oligo"].to_numpy()[k].sum()
                rows.append((idx, int(k.sum()), np.log2((e + 1) / (o + 1))))
        r = pd.DataFrame(rows, columns=["locus", "n_genes", "lfc"]).set_index("locus")
        eff[f"rna_lfc:{name}"] = r["lfc"].reindex(panel.index)
        eff[f"rna_genes:{name}"] = r["n_genes"].reindex(panel.index)
        rna[name] = pb.attrs
        print(f"[rna] {name}: {pb.attrs}", flush=True)
    eff = panel.join(eff)
    eff.to_parquet(a.out / "locus_effects.parquet")
    # correlations: structure (each source) ~ expression (each RNA source; loci with >= 1 gene)
    res = {"structure_vs_structure": {}, "structure_vs_expression": {}, "rna_cells": rna}
    labels = [l for _, _, l in SOURCES if l in eff]
    for x in labels:
        res["structure_vs_structure"][x] = {y: float(spearmanr(eff[x], eff[y], nan_policy="omit").statistic)
                                            for y in labels}
        res["structure_vs_expression"][x] = {}
        for name in RNA:
            m = eff[f"rna_genes:{name}"] > 0
            res["structure_vs_expression"][x][name] = {
                "spearman": float(spearmanr(eff.loc[m, x], eff.loc[m, f"rna_lfc:{name}"], nan_policy="omit").statistic),
                "n_loci": int(m.sum())}
        print(f"[biology] {x}: " + json.dumps({k: round(v["spearman"], 3) for k, v in res["structure_vs_expression"][x].items()}),
              flush=True)
    # figure inputs: per-locus tracks, and the difference maps of one chromosome
    eff.reset_index().rename(columns={"index": "locus"}).to_parquet(a.figdata / "cross_assay_loci_tracks.parquet")
    maps = []
    for label, t in tables.items():
        r = t.reset_index()
        r = r[r["chrom"] == MAP_CHROM][["i", "j", "sep", "diff", "resid", "chromband"]]
        maps.append(r.assign(source=label))
    pd.concat(maps, ignore_index=True).to_parquet(a.figdata / "cross_assay_loci_maps.parquet")
    path = save(a.results / "biology.json", res, script="benchmarks/cross_assay/biology.py",
                datasets=["liu2025_mop", "mm10_refgene"] + RNA,
                params={"window_bp": WINDOW, "effect": "mean over pairs of loci column chromband", "map_chrom": MAP_CHROM})
    print(f"results: {path}", flush=True)


if __name__ == "__main__":
    main()
