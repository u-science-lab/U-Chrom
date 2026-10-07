"""Validation of the cis-eigenvector compartments and the saddle strength (``uchrom.strc.comp.eig``) on the
Rao et al. 2014 maps (Cell 159:1665, GEO GSE63525).

1. **Agreement with cooltools** 0.7.1 (``eigs_cis``, ``expected_cis``, ``saddle``, ``saddle_strength``;
   Open2C 2024) on the same balanced maps, run as a separate process in an environment that has cooltools
   (``--cooltools-python``; ``compartments_ref_cooltools.py``): IMR90 and GM12878 chr21 at 100 kb, IMR90
   chr21 at 25 kb, IMR90 chr1 at 100 kb and 25 kb.  Numbers: Pearson r and max |difference| of E1..E3,
   relative difference of the eigenvalues, max difference of the saddle sums / counts and of the strength
   curve, the strength at the 20 % corners; run times of both.
2. **E1 of IMR90 vs chromatin tracing** of IMR90 chr21 (Su et al. 2020, Cell 182:1641; hg38, 651 loci of
   50 kb, ``call_compartments_axes_pc`` on the imaging, A named by the genes per locus): the hg38 loci are
   moved onto hg19 by the constant liftover offset of chr21q (+1,372,318 bp: the hg38 / hg19 starts of the
   Bintu 2018 loci, 18,627,714 / 20,000,032; UCSC liftOver of APP and RUNX1 gives the same to 20 bp) and E1
   is called on the IMR90 5 kb map rebinned to 50 kb with bin edges on the moved loci (``rebin_map(anchor=)``).
   Also against ``call_compartments_hic`` on the authors' Hi-C in their own loci, and for a scan of offsets.
3. **Depth thinning**: binomial thinning of the 5 kb counts to 20 %, 5 %, 2 % (seed 0; the depth of atlas
   cell-type pseudo-bulks), rebinned to 100 kb and balanced: Pearson r and A/B agreement of E1 with full
   depth, strength.

Phasing: GC content of every bin from the UCSC hg19 chromosome FASTA (``--fasta-dir`` holding
``hg19_chr21.fa.gz`` / ``hg19_chr1.fa.gz``, or the datasets ``hg19_chr21`` / ``hg19_chr1`` once registered).
Writes ``compartments.json`` to ``--out`` (default ``$UCHROM_BENCH_OUT``, else a temporary directory)::

    python benchmarks/hic_structures/compartments.py --cooltools-python /path/to/venv/bin/python \\
        --fasta-dir /path/to/fasta --out /path/to/scratch
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
OFFSET_HG38_TO_HG19_CHR21 = 1_372_318
SU_FIRST_LOCUS = 10_400_000


def _fasta(name: str, fasta_dir):
    """The UCSC chromosome FASTA ``name`` (``hg19_chr21``): a registered dataset, else ``fasta_dir/<name>.fa.gz``."""
    import uchrom.datasets as ds

    try:
        return Path(ds.fetch(name))
    except (KeyError, ValueError):
        pass
    if fasta_dir is None:
        raise SystemExit(f"{name}: not a registered dataset; pass --fasta-dir with {name}.fa.gz "
                         f"(https://hgdownload.soe.ucsc.edu/goldenPath/hg19/chromosomes/)")
    path = Path(fasta_dir) / f"{name}.fa.gz"
    if not path.exists():
        raise SystemExit(f"{path} is missing")
    return path


def _empty_cd(path, key="map"):
    from uchrom import ChromData

    spots = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                          [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str)]})
    cd = ChromData(np.zeros((0, 3)), spots)
    cd.link_cool(str(path), key=key)
    return cd


def _rebinned(src, res, out_dir, tag, anchor=0):
    from uchrom.fea.maps import rebin_map

    out = Path(out_dir) / f"{tag}_{res // 1000}k{'' if not anchor else f'_at{anchor}'}.cool"
    if not out.exists():
        rebin_map(str(src), resolution=res, anchor=anchor, out=str(out))
    return out


def _gc_table(path, fasta, cache: dict):
    import cooler
    from uchrom.fea.sequence import compute_sequence_features

    key = (str(path), str(fasta))
    if key not in cache:
        bins = cooler.Cooler(str(path)).bins()[:][["chrom", "start", "end"]]
        gc = compute_sequence_features(bins, fasta, features=["gc_fraction"], missing="ignore")
        cache[key] = gc.rename(columns={"gc_fraction": "value"})
    return cache[key]


def _ours(path, gc, n_bins=38):
    from uchrom.strc.comp.eig import call_compartments_eig, compartment_strength

    cd = _empty_cd(path)
    t = time.time()
    table = call_compartments_eig(cd, phasing=gc)
    t_eig = time.time() - t
    t = time.time()
    sad = compartment_strength(cd, n_bins=n_bins)
    t_sad = time.time() - t
    return cd, table, sad, t_eig, t_sad


def compare_cooltools(maps, gcs, py, out_dir):
    """Section 1: the same maps through cooltools in its own process."""
    from uchrom.strc.comp.eig import compartment_strength

    rows = []
    for name, path in maps.items():
        gc = gcs[name]
        tsv = Path(out_dir) / f"{path.stem}.gc.tsv"
        gc.to_csv(tsv, sep="\t", index=False)
        ref_path = Path(out_dir) / f"{path.stem}.cooltools.npz"
        t = time.time()
        subprocess.run([py, str(HERE / "compartments_ref_cooltools.py"), str(path), str(tsv), str(ref_path), "38"],
                       check=True, capture_output=True)
        t_ref_total = time.time() - t
        ref = np.load(ref_path)
        cd, table, sad, t_eig, t_sad = _ours(path, gc)
        bins = pd.DataFrame({"chrom": ref["chrom"], "start": ref["start"]})
        idx = pd.Series(np.arange(len(bins)), index=pd.MultiIndex.from_frame(bins))
        at = idx.reindex(pd.MultiIndex.from_frame(table[["chrom", "start"]])).to_numpy()
        row = {"map": name, "valid_bins": int(len(table)), "cooltools_valid_bins": int(np.isfinite(ref["E1"]).sum())}
        for k in (1, 2, 3):
            a, b = table[f"E{k}"].to_numpy(), ref[f"E{k}"][at]
            row[f"E{k}_r"] = float(np.corrcoef(a, b)[0, 1])
            row[f"E{k}_max_abs_diff"] = float(np.nanmax(np.abs(a - b)))
        ours_ev = cd.results["compartments.eig.eigvals"][["eigval1", "eigval2", "eigval3"]].to_numpy()[0]
        row["eigvals"] = [round(float(x), 6) for x in ours_ev]
        row["eigvals_max_rel_diff"] = float(np.max(np.abs(ours_ev - ref["eigvals"][0]) / np.abs(ref["eigvals"][0])))
        # the saddle on cooltools' own E1 (same track in both): sums, counts, strength
        e1_ref = pd.DataFrame({"chrom": ref["chrom"], "start": ref["start"], "end": ref["start"] + 1, "E1": ref["E1"]})
        e1_ref["end"] = table["end"].iloc[0] - table["start"].iloc[0] + e1_ref["start"]
        same = compartment_strength(str(path), compartments=e1_ref, n_bins=38)
        row["saddle_sum_max_rel_diff"] = float(np.nanmax(np.abs(same["sum"] - ref["S"]) / np.maximum(np.abs(ref["S"]), 1e-300)))
        row["saddle_count_equal"] = bool(np.array_equal(same["count"], ref["C"]))
        row["strength_curve_max_abs_diff"] = float(np.nanmax(np.abs(same["strength_curve"][1:] - ref["strength"][1:])))
        k = sad["corner_groups"]
        row["strength_20pct_ours"] = float(sad["strength"])
        row["strength_20pct_cooltools"] = float(ref["strength"][k])
        row["AA_BB_AB_ours"] = [round(sad["AA"], 4), round(sad["BB"], 4), round(sad["AB"], 4)]
        row["phasing_r1"] = float(cd.results["compartments.eig.eigvals"]["phasing_r1"].iloc[0])
        row["t_eig_s"], row["t_saddle_s"] = round(t_eig, 3), round(t_sad, 3)
        row["t_cooltools_eig_s"], row["t_cooltools_saddle_s"] = round(float(ref["t_eig"]), 3), round(float(ref["t_saddle"]), 3)
        rows.append(row)
        print(f"  {name}: E1 r={row['E1_r']:.12f}  eigvals rel diff={row['eigvals_max_rel_diff']:.1e}  "
              f"saddle sum diff={row['saddle_sum_max_rel_diff']:.1e}  strength {row['strength_20pct_ours']:.3f} vs "
              f"{row['strength_20pct_cooltools']:.3f}  ({row['t_eig_s']} s vs cooltools {row['t_cooltools_eig_s']} s)",
              flush=True)
    return rows


def compare_tracing(imr90_5k, fasta, out_dir):
    """Section 2: E1 of IMR90 (hg19) vs the Su 2020 tracing compartments (hg38 loci moved by the offset)."""
    import uchrom.datasets as ds
    from uchrom.strc.comp import (CompartmentCallerParams, call_compartments_axes_pc, call_compartments_hic,
                                  compare_compartments)
    from uchrom.strc.comp.eig import call_compartments_eig

    su = ds.load("su2020_chr21")
    t = time.time()
    call_compartments_axes_pc(su, params=CompartmentCallerParams(a_track="n_genes"), device="cpu")
    t_axes = time.time() - t
    call_compartments_hic(su, contacts="rao2014", orient_by="n_genes")
    out = {"n_loci": int(su.n_bins), "offset_bp": OFFSET_HG38_TO_HG19_CHR21, "t_axes_pc_s": round(t_axes, 1),
           "axes_pc_vs_su_hic_pc1": compare_compartments(su, "compartments.axes_pc", "compartments.hic_pc1")}
    scan = []
    for shift in (-20_000, -10_000, -5_000, 0, 5_000, 10_000, 20_000):
        off = OFFSET_HG38_TO_HG19_CHR21 + shift
        path = _rebinned(imr90_5k, 50_000, out_dir, "imr90_chr21", anchor=SU_FIRST_LOCUS + off)
        e1 = call_compartments_eig(str(path), phasing=str(fasta))
        moved = e1.assign(start=e1["start"] - off, end=e1["end"] - off)
        rec = {"offset_bp": off,
               "vs_axes_pc": compare_compartments(su, "compartments.axes_pc", moved),
               "vs_su_hic_pc1": compare_compartments(su, "compartments.hic_pc1", moved)}
        scan.append(rec)
        if shift == 0:
            out.update(e1_50kb_vs_axes_pc=rec["vs_axes_pc"], e1_50kb_vs_su_hic_pc1=rec["vs_su_hic_pc1"])
    out["offset_scan"] = scan
    path = _rebinned(imr90_5k, 100_000, out_dir, "imr90_chr21")
    e1 = call_compartments_eig(str(path), phasing=str(fasta))
    moved = e1.assign(start=e1["start"] - OFFSET_HG38_TO_HG19_CHR21, end=e1["end"] - OFFSET_HG38_TO_HG19_CHR21)
    out["e1_100kb_vs_axes_pc"] = compare_compartments(su, "compartments.axes_pc", moved)
    print(f"  Su 2020 tracing (axes_pc) vs IMR90 E1 50 kb: {out['e1_50kb_vs_axes_pc']}; 100 kb: "
          f"{out['e1_100kb_vs_axes_pc']}; Su Hi-C PC1 vs axes_pc: {out['axes_pc_vs_su_hic_pc1']}", flush=True)
    return out


def depth_thinning(src5k, fasta, out_dir, tag, fractions=(0.2, 0.05, 0.02), seed=0):
    """Section 3: binomial thinning of the 5 kb counts, 100 kb E1 and strength vs full depth."""
    import cooler

    from uchrom.strc.comp.eig import call_compartments_eig, compartment_strength

    full = _rebinned(src5k, 100_000, out_dir, tag)
    base = call_compartments_eig(str(full), phasing=str(fasta))
    base_s = compartment_strength(str(full), compartments=base)
    clr = cooler.Cooler(str(src5k))
    px = clr.pixels()[:]
    bins = clr.bins()[:][["chrom", "start", "end"]]
    rng = np.random.default_rng(seed)
    rows = [{"map": tag, "fraction": 1.0, "contacts": int(px["count"].sum()), "valid_bins": int(len(base)),
             "E1_r": 1.0, "agreement": 1.0, "strength": float(base_s["strength"])}]
    for frac in fractions:
        p = px.assign(count=rng.binomial(px["count"].to_numpy(), frac))
        p = p[p["count"] > 0]
        thin5 = Path(out_dir) / f"{tag}_thin{frac}_5k.cool"
        cooler.create_cooler(str(thin5), bins, p, ordered=True)
        thin = _rebinned(thin5, 100_000, out_dir, f"{tag}_thin{frac}")
        e1 = call_compartments_eig(str(thin), phasing=str(fasta))
        m = base.merge(e1, on=["chrom", "start"], suffixes=("", "_t"))
        s = compartment_strength(str(thin), compartments=e1)
        rows.append({"map": tag, "fraction": frac, "contacts": int(p["count"].sum()), "valid_bins": int(len(e1)),
                     "E1_r": float(np.corrcoef(m["E1"], m["E1_t"])[0, 1]),
                     "agreement": float((m["compartment"] == m["compartment_t"]).mean()),
                     "strength": float(s["strength"])})
        print(f"  {tag} {frac:.0%}: {rows[-1]}", flush=True)
    return rows


def main(argv=None):
    import uchrom.datasets as ds

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cooltools-python", default=os.environ.get("COOLTOOLS_PYTHON"),
                    help="python of an environment with cooltools (section 1 is skipped without it)")
    ap.add_argument("--fasta-dir", default=None)
    ap.add_argument("--out", default=os.environ.get("UCHROM_BENCH_OUT") or tempfile.mkdtemp(prefix="hic_comp_"))
    ap.add_argument("--skip-chr1", action="store_true")
    args = ap.parse_args(argv)
    out = Path(args.out)
    (out / "maps").mkdir(parents=True, exist_ok=True)
    maps_dir = out / "maps"

    imr21 = Path(ds.fetch("rao2014_imr90_chr21"))
    gm21 = Path(ds.fetch("rao2014_gm12878_chr21"))
    fa21 = _fasta("hg19_chr21", args.fasta_dir)
    maps = {"IMR90 chr21 100 kb": _rebinned(imr21, 100_000, maps_dir, "imr90_chr21"),
            "GM12878 chr21 100 kb": _rebinned(gm21, 100_000, maps_dir, "gm12878_chr21"),
            "IMR90 chr21 25 kb": _rebinned(imr21, 25_000, maps_dir, "imr90_chr21")}
    fastas = {k: fa21 for k in maps}
    if not args.skip_chr1:
        imr1 = Path(ds.fetch("rao2014_imr90_chr1"))
        fa1 = _fasta("hg19_chr1", args.fasta_dir)
        for res in (100_000, 25_000):
            name = f"IMR90 chr1 {res // 1000} kb"
            maps[name] = _rebinned(imr1, res, maps_dir, "imr90_chr1")
            fastas[name] = fa1
    cache: dict = {}
    gcs = {k: _gc_table(p, fastas[k], cache) for k, p in maps.items()}

    result = {"maps": {k: str(v) for k, v in maps.items()}}
    if args.cooltools_python:
        print("1. vs cooltools 0.7.1 (eigs_cis, saddle) on the same maps", flush=True)
        result["vs_cooltools"] = compare_cooltools(maps, gcs, args.cooltools_python, maps_dir)
        print(pd.DataFrame(result["vs_cooltools"]).set_index("map")[
            ["valid_bins", "E1_r", "E1_max_abs_diff", "E2_r", "E3_r", "eigvals_max_rel_diff",
             "saddle_sum_max_rel_diff", "saddle_count_equal", "strength_20pct_ours", "strength_20pct_cooltools",
             "t_eig_s", "t_cooltools_eig_s"]].to_string())
    print("2. IMR90 E1 vs Su 2020 chromatin tracing (chr21)", flush=True)
    result["vs_tracing"] = compare_tracing(imr21, fa21, maps_dir)
    print("3. depth thinning", flush=True)
    rows = depth_thinning(imr21, fa21, maps_dir, "imr90_chr21")
    if not args.skip_chr1:
        rows += depth_thinning(Path(ds.fetch("rao2014_imr90_chr1")), _fasta("hg19_chr1", args.fasta_dir),
                               maps_dir, "imr90_chr1")
    result["depth_thinning"] = rows
    print(pd.DataFrame(rows).to_string(index=False))
    (out / "compartments.json").write_text(json.dumps(result, indent=1, default=float))
    print(f"wrote {out / 'compartments.json'}")
    return result


if __name__ == "__main__":
    main(sys.argv[1:])
