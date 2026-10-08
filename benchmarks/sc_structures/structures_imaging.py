"""The tracing callers by number of traces on imaging data, and on the published mESC structures.

    .venv/bin/python benchmarks/sc_structures/structures_imaging.py [--out DIR] [--sections su2020 takei25 stevens]

The counterpart of ``structures_callers.py`` (Dip-C GM12878 structures, 4-28 traces): the same callers on
chromatin tracing of many cells, subsampled to the same and larger numbers of traces, against bulk Hi-C of
the same cell type — so that a disappointing number on structures can be read as a property of the
structures or of the cell count.

``su2020``   Su et al. 2020 IMR90 chr21 tracing (``ds.load("su2020_chr21")``: 651 loci of 50 kb, hg38, 7,591
             chromosome copies) vs Rao 2014 IMR90 (``rao2014_imr90_chr21``, hg19 5 kb; moved onto the hg38 loci
             by the constant chr21q offset, ``benchmarks/hic_structures/compartments.py``): axes-PC vs E1 at 50 kb
             (bins anchored on the loci), ArcFISH TAD boundaries (``window_bp`` 200 kb: two loci a side, as the
             100 kb default gives at 20-25 kb) vs insulation on the same 50 kb map and vs the Arrowhead edges
             (tolerance 1 locus).  4 ... 1024 traces and all.
``takei25``  Takei et al. 2021 mESC DNA seqFISH+ 25 kb (``ds.load("takei2021_mesc")``: 20 regions x 60 loci,
             ~400 homolog traces per region) — ArcFISH TAD boundaries vs insulation of Bonev et al. 2017 mESC
             Hi-C at 25 kb (4DN 4DNFIC21MG3U, ``bonev2017_mesc_4dn``: the copy in the data directory, else over
             HTTP range requests; the regions +- 1 Mb, balanced as stored).  4 ... 256 traces per region and all.
``stevens``  Stevens et al. 2017 haploid mESC structures (``ds.load("stevens2017_mesc")``, atlas: 8 cells, 100 kb
             particles, 10 models per cell as layers): axes-PC on the structures averaged into 1 Mb (and 250 kb)
             bins vs Bonev E1 at the same resolution (GC-phased, mm10) and vs the E1 of the same 8 cells' merged
             contacts; 1, 2, 4, 8 cells; the other models (layers) vs model 1.  The Takei 1 Mb genome-wide
             tracing (``takei2021_1mb``) cannot serve as the imaging counterpart: its traces hold both homologs
             of a chromosome (one trace per cell and chromosome, 1.5 spots per locus), so no single-copy
             distances.

Results: tables on stdout and ``structures_imaging.json`` in ``--out``.
"""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import structures_common as sc  # noqa: E402

warnings.filterwarnings("ignore")


def subsample_per_chrom(cd, n: int, seed: int):
    """``n`` traces per chromosome (seeded), all of a chromosome's traces when it has ``n`` or fewer."""
    loci = cd.spots_with_loci()
    tr = loci[["trace_id", "chrom"]].astype(str).drop_duplicates("trace_id")
    rng = np.random.default_rng(seed)
    keep = []
    for _, g in tr.groupby("chrom", sort=True):
        ids = g["trace_id"].to_numpy()
        keep.extend(ids if n >= len(ids) else rng.choice(ids, size=n, replace=False))
    mask = cd.spots["trace_id"].astype(str).isin(set(keep)).to_numpy()
    return cd[mask]


def traces_per_chrom(cd) -> float:
    tr = cd.spots_with_loci()[["trace_id", "chrom"]].astype(str).drop_duplicates("trace_id")
    return float(tr.groupby("chrom").size().median())


# ------------------------------------------------------------------------------------------------ remote Hi-C

def bonev_source() -> str:
    """The Bonev 2017 mcool: the copy in the data directory (``bonev2017_mesc_4dn``, e.g. on Sherlock) when
    there is one, else its 4DN URL (read over HTTP range requests)."""
    from uchrom.datasets import data_dir

    local = data_dir() / "bonev2017_mesc" / "4DNFIC21MG3U.mcool"
    return str(local) if local.exists() else sc.BONEV


def remote_level(url: str, res: int):
    import cooler
    import fsspec
    import h5py

    if not url.startswith(("http://", "https://")):
        return cooler.Cooler(f"{url}::resolutions/{res}")
    fh = fsspec.open(url, block_size=2 ** 20, cache_type="blockcache").open()
    return cooler.Cooler(h5py.File(fh, "r")[f"resolutions/{res}"])


def local_cis_cool(url: str, res: int, out: Path, chroms, windows=None) -> Path:
    """A local ``.cool`` with the bins of ``chroms`` (weights as stored) and their cis pixels — only those
    inside ``windows`` (``{chrom: [(lo, hi), ...]}``) when given — read over HTTP range requests."""
    import cooler

    if out.exists():
        return out
    clr = remote_level(url, res)
    allbins = clr.bins()[:]
    parts_b, parts_p, offset = [], [], 0
    for c in chroms:
        lo_g, hi_g = clr.extent(c)
        b = allbins.iloc[lo_g:hi_g][["chrom", "start", "end", "weight"]].reset_index(drop=True)
        if windows:                       # bins outside the windows have no pixels here: masked
            inside = np.zeros(len(b), bool)
            for lo, hi in windows[c]:
                inside |= (b["end"].to_numpy() > lo) & (b["start"].to_numpy() < hi)
            b.loc[~inside, "weight"] = np.nan
        regions = [f"{c}:{lo}-{hi}" for lo, hi in windows[c]] if windows else [c]
        for reg in regions:
            px = clr.matrix(balance=False, as_pixels=True).fetch(reg)
            if len(px):
                parts_p.append(pd.DataFrame({"bin1_id": px["bin1_id"].to_numpy(np.int64) - lo_g + offset,
                                             "bin2_id": px["bin2_id"].to_numpy(np.int64) - lo_g + offset,
                                             "count": px["count"].to_numpy()}))
        parts_b.append(b)
        offset += hi_g - lo_g
    bins = pd.concat(parts_b, ignore_index=True)
    bins["chrom"] = bins["chrom"].astype(str)
    pixels = (pd.concat(parts_p, ignore_index=True).drop_duplicates(["bin1_id", "bin2_id"])
              .sort_values(["bin1_id", "bin2_id"]).reset_index(drop=True))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.cool")
    cooler.create_cooler(str(tmp), bins, pixels, ordered=True, assembly="mm10")
    tmp.rename(out)
    return out


# ------------------------------------------------------------------------------------------------ Su 2020

def su2020(out: Path, seeds: int) -> dict:
    import uchrom.datasets as ds
    from uchrom.strc.comp import CompartmentCallerParams, call_compartments_axes_pc, compare_compartments
    from uchrom.strc.comp.eig import call_compartments_eig
    from uchrom.strc.tad import TADCallerParams, call_tads_by_pval, call_tads_insulation

    off = sc.OFFSET_HG38_TO_HG19_CHR21
    su_all = ds.load("su2020_chr21")
    first = int(su_all.bins["start"].min())
    cool = ds.fetch("rao2014_imr90_chr21")
    fasta = ds.fetch("hg19_chr21")
    p50 = sc.rebinned(cool, 50_000, out / "maps", "rao_imr90", anchor=first + off)
    e1 = call_compartments_eig(str(p50), phasing=str(fasta))
    e1 = e1.assign(start=e1["start"] - off, end=e1["end"] - off)
    ins = call_tads_insulation(str(p50))
    ins = ins.assign(start=ins["start"] - off, end=ins["end"] - off)
    ah = sc.arrowhead("IMR90", "chr21")
    arrow = sc.edges_to_domains("chr21", np.r_[ah["start"].to_numpy(), ah["end"].to_numpy()] - off)
    refs = {"insulation": ins, "arrowhead": arrow}
    res = {"n_traces": int(su_all.n_traces), "n_loci": int(su_all.n_bins),
           "references": {"e1_bins": int(len(e1)), "insulation_boundaries": int(len(ins) - 1),
                          "arrowhead_domains": int(len(ah))},
           "insulation_vs_arrowhead": sc.boundaries_vs(su_all, ins, {"arrowhead": arrow}, tols=(1,))}
    rows = []
    for n in (4, 8, 16, 28, 64, 256, 1024, su_all.n_traces):
        for seed in range(seeds if n < su_all.n_traces else 1):
            sub, _ = sc.subsample(su_all, n, seed)
            t = time.perf_counter()
            comp = call_compartments_axes_pc(sub, params=CompartmentCallerParams(a_track="n_genes"), device="cpu",
                                             key_added=None)
            t_comp = time.perf_counter() - t
            agree = compare_compartments(su_all, comp, e1)
            t = time.perf_counter()
            # two loci each side of a candidate boundary, as ArcFISH's 100 kb default does at 25 kb (and as
            # benchmarks/hic_structures/insulation.py runs it on these data)
            tads = call_tads_by_pval(sub, params=TADCallerParams(window_bp=2e5), device="cpu", key_added=None)
            t_tad = time.perf_counter() - t
            tads = tads[tads["level"] == tads["level"].min()] if len(tads) else tads
            vs = sc.boundaries_vs(su_all, tads, refs, tols=(1,))
            rows.append({"n_traces": int(n), "seed": seed, "comp_r": agree["pearson_r"],
                         "comp_agreement": agree["agreement"], "arcfish_n": int(max(len(tads) - 1, 0)),
                         "arcfish_precision_insulation": vs["insulation_tol1"]["precision"],
                         "arcfish_recall_insulation": vs["insulation_tol1"]["recall"],
                         "arcfish_precision_arrowhead": vs["arrowhead_tol1"]["precision"],
                         "arcfish_recall_arrowhead": vs["arrowhead_tol1"]["recall"],
                         "precision_chance_insulation": vs["insulation_tol1"]["precision_chance"],
                         "t_axes_pc_s": t_comp, "t_arcfish_s": t_tad})
            print(rows[-1], flush=True)
    res.update(_summary(rows))
    return res


def _summary(rows):
    df = pd.DataFrame(rows)
    summary = df.drop(columns=["seed"]).groupby("n_traces").agg(["mean", "std"])
    summary.columns = [f"{a}_{b}" for a, b in summary.columns]
    print(summary.round(3).to_string(), flush=True)
    return {"rows": df.to_dict("records"), "summary": summary.reset_index().to_dict("records")}


# ------------------------------------------------------------------------------------------------ Takei 25 kb

def takei25(out: Path, seeds: int, flank: int = 1_000_000) -> dict:
    import uchrom.datasets as ds
    from uchrom.strc.tad import call_tads_by_pval, call_tads_insulation

    tk = ds.load("takei2021_mesc")
    tk = tk[np.isfinite(np.asarray(tk.coords)).all(1)]
    loci = tk.bins.astype({"chrom": str})
    chroms = sorted(loci["chrom"].unique(), key=lambda c: (len(c), c))
    windows = {c: [(max(0, int(g["start"].min()) - flank), int(g["end"].max()) + flank)]
               for c, g in loci.groupby("chrom")}
    t = time.perf_counter()
    path = local_cis_cool(bonev_source(), 25_000, out / "maps" / "bonev_25kb_takei_regions.cool", chroms, windows)
    t_read = time.perf_counter() - t
    ins = call_tads_insulation(str(path), chrom=chroms)
    print(f"Bonev 25 kb ({bonev_source()}): {len(ins)} insulation domains in the regions", flush=True)
    refs = {"bonev_insulation": ins}
    per = traces_per_chrom(tk)
    res = {"n_traces": int(tk.n_traces), "traces_per_region_median": per, "bonev_read_s": t_read,
           "bonev_boundaries_in_regions":
               int(sc.boundaries_vs(tk, ins, {"self": ins}, tols=(0,))["self_tol0"]["n_query"])}
    rows = []
    for n in (4, 8, 16, 28, 64, 256, 10_000):
        for seed in range(seeds if n < per else 1):
            sub = subsample_per_chrom(tk, n, seed)
            t = time.perf_counter()
            tads = call_tads_by_pval(sub, device="cpu", key_added=None)
            t_tad = time.perf_counter() - t
            tads = tads[tads["level"] == 1] if len(tads) else tads
            vs = sc.boundaries_vs(tk, tads, refs, tols=(1,))["bonev_insulation_tol1"]
            rows.append({"n_traces": int(min(n, per)), "seed": seed, "arcfish_n": vs["n_query"],
                         "arcfish_precision_insulation": vs["precision"], "arcfish_recall_insulation": vs["recall"],
                         "precision_chance_insulation": vs["precision_chance"], "t_arcfish_s": t_tad})
            print(rows[-1], flush=True)
    res.update(_summary(rows))
    return res


# ------------------------------------------------------------------------------------------------ Stevens 2017

def per_chrom_r(co, query, ref, chroms) -> dict:
    """``compare_compartments`` chromosome by chromosome: median and range of r (a pooled r mixes the
    chromosomes' scales and signs)."""
    from uchrom.strc.comp import compare_compartments

    rs = np.array([compare_compartments(co, query, ref, chrom=c)["pearson_r"] for c in chroms], dtype=float)
    return {"median_r": float(np.nanmedian(rs)), "min_r": float(np.nanmin(rs)), "max_r": float(np.nanmax(rs)),
            "per_chrom": {c: float(r) for c, r in zip(chroms, rs)}}


def stevens(out: Path, seeds: int) -> dict:
    import uchrom.datasets as ds
    from chromdata import ChromData
    from uchrom.strc.comp import CompartmentCallerParams, call_compartments_axes_pc, compare_compartments
    from uchrom.strc.comp.eig import call_compartments_eig

    t = time.perf_counter()
    st = ds.load("stevens2017_mesc", backed=True).to_memory()   # small (205,706 particles x 10 models): read once
    print(f"stevens: loaded {st} in {time.perf_counter() - t:.0f} s", flush=True)
    res = {"load_s": time.perf_counter() - t, "n_cells": int(len(st.cells)), "n_traces": int(st.n_traces),
           "n_particles": int(st.n_spots), "layers": list(st.layers)}
    chroms = [c for c in pd.unique(st.spots["chrom"].astype(str)) if c != "chrY"]
    fasta = ds.fetch("mm10_genome")
    # every caller runs on the atlas store as it is (one chromosome, 100 kb particles, 8 traces)
    from uchrom.strc.loop import call_loops_axiswise_f
    from uchrom.strc.tad import call_tads_by_pval

    c19 = sc.in_memory_chrom(st, "chr19")
    smoke = {}
    for name, fn in (("axes_pc", lambda: call_compartments_axes_pc(c19, chrom="chr19", device="cpu", key_added=None)),
                     ("arcfish_tads", lambda: call_tads_by_pval(c19, chrom="chr19", device="cpu", key_added=None)),
                     ("axiswise_f_loops", lambda: call_loops_axiswise_f(c19, chrom="chr19", device="cpu",
                                                                        key_added=None))):
        out_t, rt = sc.timed(fn)
        smoke[name] = {"rows": int(len(out_t)), **rt}
    res["chr19_smoke"] = {"n_loci": int(c19.n_spots // max(c19.n_traces, 1)), **smoke}
    print("stevens chr19 (100 kb, 8 traces):", res["chr19_smoke"], flush=True)
    for res_bp in (1_000_000, 250_000):
        tag = f"{res_bp // 1000}kb"
        t = time.perf_counter()
        path = local_cis_cool(bonev_source(), res_bp, out / "maps" / f"bonev_{tag}.cool", chroms)
        t_read = time.perf_counter() - t
        import cooler

        bins = cooler.Cooler(str(path)).bins()[:][["chrom", "start", "end"]]
        t = time.perf_counter()
        gc = sc.gc_table(bins, fasta)
        print(f"{tag}: Bonev read {t_read:.0f} s, GC {time.perf_counter() - t:.0f} s", flush=True)
        e1 = call_compartments_eig(str(path),
                                   phasing=gc.rename(columns={"value": "gc"})[["chrom", "start", "end", "gc"]])
        # the same 8 cells' merged contacts (the store's linked map)
        try:
            e1_pb = call_compartments_eig(st, contacts="bulk", resolution=res_bp,
                                          phasing=gc.rename(columns={"value": "gc"})[["chrom", "start", "end", "gc"]],
                                          key_added=None)
        except Exception as exc:                                # the map lacks this level
            e1_pb, res[f"pseudobulk_{tag}_error"] = None, repr(exc)

        def structures_on(cd_, layer=None):
            parts = [sc.coarsen(cd_, res_bp, c, layer=layer) for c in chroms]
            co = ChromData(np.concatenate([p.coords for p in parts]),
                           pd.concat([p.spots_with_loci()[["chrom", "start", "end", "trace_id", "cell_id"]]
                                      for p in parts], ignore_index=True))
            sc.with_track(co, gc, "gc")
            return co

        t = time.perf_counter()
        co_all = structures_on(st)
        print(f"{tag}: E1s and coarsening done ({time.perf_counter() - t:.0f} s coarsening)", flush=True)
        r: dict = {"bonev_read_s": t_read, "e1_bins": int(len(e1))}
        if e1_pb is not None:
            r["pseudobulk_e1_vs_bonev"] = compare_compartments(co_all, e1_pb, e1)
            r["pseudobulk_e1_vs_bonev_per_chrom"] = per_chrom_r(co_all, e1_pb, e1, chroms)
            print(tag, "pseudo-bulk E1 vs Bonev", r["pseudobulk_e1_vs_bonev"],
                  {k: v for k, v in r["pseudobulk_e1_vs_bonev_per_chrom"].items() if k != "per_chrom"}, flush=True)
        rows = []
        for n in (1, 2, 4, 8):
            for seed in range(seeds if n < 8 else 1):
                cells = (list(st.cells.index) if n >= 8 else
                         list(np.random.default_rng(seed).choice(st.cells.index, size=n, replace=False)))
                sub = co_all[co_all.spots["cell_id"].astype(str).isin(set(cells)).to_numpy()]
                t = time.perf_counter()
                comp = call_compartments_axes_pc(sub, params=CompartmentCallerParams(a_track="gc"), device="cpu",
                                                 key_added=None)
                row = {"n_traces": n, "seed": seed, "t_axes_pc_s": time.perf_counter() - t}
                a = compare_compartments(co_all, comp, e1)
                row.update(comp_r=a["pearson_r"], comp_agreement=a["agreement"],
                           comp_r_chrom_median=per_chrom_r(co_all, comp, e1, chroms)["median_r"])
                if e1_pb is not None:
                    b = compare_compartments(co_all, comp, e1_pb)
                    row.update(comp_r_vs_pseudobulk=b["pearson_r"], comp_agreement_vs_pseudobulk=b["agreement"])
                rows.append(row)
                print(tag, rows[-1], flush=True)
        r.update(_summary(rows))
        # model variability: models 2..10 (layers) through the caller, vs model 1 and vs Bonev
        full = call_compartments_axes_pc(co_all, params=CompartmentCallerParams(a_track="gc"), device="cpu",
                                         key_added=None)
        mv = []
        for layer in [x for x in st.layers][:3]:
            co_l = structures_on(st, layer=layer)
            comp_l = call_compartments_axes_pc(co_l, params=CompartmentCallerParams(a_track="gc"), device="cpu",
                                               key_added=None)
            mv.append({"layer": layer, "vs_model1": compare_compartments(co_all, comp_l, full),
                       "vs_model1_chrom_median": per_chrom_r(co_all, comp_l, full, chroms)["median_r"],
                       "vs_bonev": compare_compartments(co_all, comp_l, e1),
                       "vs_bonev_chrom_median": per_chrom_r(co_all, comp_l, e1, chroms)["median_r"]})
        r["other_models"] = mv
        r["all_cells_per_chrom"] = per_chrom_r(co_all, full, e1, chroms)
        print(tag, "other models", mv, flush=True)
        res[tag] = r
    return res


def mesc_e1_check(out: Path, seeds: int) -> dict:
    """mESC references (``--sections mesc_e1_check``) — why the Stevens numbers are low: the two references
    themselves.  Per chromosome at 1 Mb and 250 kb:
    E1 vs GC (the phasing track) for Bonev and for the 8 Stevens cells' merged contacts, the r between the
    two E1s, and the same with the Stevens E1 shifted by -2 .. +2 bins (a coordinate mismatch would peak
    off zero); plus the cis contacts per chromosome of the Stevens map."""
    import cooler

    import uchrom.datasets as ds
    from uchrom.fea.maps import map_path
    from uchrom.strc.comp.eig import call_compartments_eig

    st = ds.load("stevens2017_mesc", backed=True)
    fasta = ds.fetch("mm10_genome")
    chroms = [f"chr{i}" for i in range(1, 20)] + ["chrX"]
    res = {}
    for res_bp in (1_000_000, 250_000):
        tag = f"{res_bp // 1000}kb"
        bonev = local_cis_cool(bonev_source(), res_bp, out / "maps" / f"bonev_{tag}.cool", chroms)
        stev = map_path(st, "bulk", resolution=res_bp)
        gc = sc.gc_table(cooler.Cooler(str(bonev)).bins()[:][["chrom", "start", "end"]], fasta)
        e_b = call_compartments_eig(str(bonev), phasing=gc)
        e_s = call_compartments_eig(st, contacts="bulk", resolution=res_bp, chrom=chroms, phasing=gc, key_added=None)
        clr = cooler.Cooler(str(stev) if "::" in str(stev) else f"{stev}::/resolutions/{res_bp}")
        rows = []
        for c in chroms:
            b = e_b[e_b["chrom"] == c].set_index("start")["E1"]
            s = e_s[e_s["chrom"] == c].set_index("start")["E1"]
            g = gc[gc["chrom"] == c].set_index("start")["value"]
            j = b.index.intersection(s.index)
            row = {"chrom": c, "n_bins": int(len(j)),
                   "cis_contacts": int(clr.matrix(balance=False, as_pixels=True).fetch(c)["count"].sum()),
                   "bonev_e1_vs_gc": float(np.corrcoef(b.reindex(g.index).dropna(),
                                                        g.reindex(b.dropna().index))[0, 1]) if len(b) > 2 else np.nan,
                   "stevens_e1_vs_gc": float(np.corrcoef(s.dropna(), g.reindex(s.dropna().index))[0, 1])
                   if len(s) > 2 else np.nan}
            for k in (-2, -1, 0, 1, 2):
                sh = pd.Series(s.to_numpy(), index=s.index + k * res_bp)
                jj = b.index.intersection(sh.index)
                row[f"r_shift{k:+d}"] = float(np.corrcoef(b[jj], sh[jj])[0, 1]) if len(jj) > 2 else np.nan
            rows.append(row)
        df = pd.DataFrame(rows)
        print(tag, "\n", df.round(3).to_string(), flush=True)
        res[tag] = {"rows": df.to_dict("records"), "medians": df.drop(columns=["chrom"]).median().to_dict()}
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=sc.default_out("sc_structures_imaging"))
    ap.add_argument("--sections", nargs="+", default=["su2020", "takei25", "stevens"])
    ap.add_argument("--seeds", type=int, default=5)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    path = a.out / "structures_imaging.json"
    res = {} if not path.exists() else __import__("json").loads(path.read_text())
    for s in a.sections:
        t = time.perf_counter()
        sections = {"su2020": su2020, "takei25": takei25, "stevens": stevens, "mesc_e1_check": mesc_e1_check}
        res[s] = sections[s](a.out, a.seeds)
        print(f"[{s}] {time.perf_counter() - t:.0f} s", flush=True)
        sc.dump(res, path)
    print(f"-> {path}")


if __name__ == "__main__":
    main()
