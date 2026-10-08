"""The tracing callers on reconstructed single-cell structures: Tan 2018 Dip-C GM12878, chr21.

    .venv/bin/python benchmarks/sc_structures/structures_callers.py [--out DIR] [--sections ...] [--workers 6]
        [--fishnet-sweep default|reduced]

A cluster job (FISHnet's published sweep takes ~1 h on 31 cores): ``sherlock/structures_gm.sbatch``.

Data: ``ds.load("tan2018_gm12878")`` — 14 GM12878 cells, the authors' Dip-C structures (20 kb particles;
each homolog a trace: 28 traces on chr21; replicate runs ``rep1`` / ``rep2`` as layers) and the per-cell
5 kb contact maps of the same cells.  The structures go to the tracing callers as they are; the only
preparation is, for compartments, the particles averaged into 100 kb bins (``structures_common.coarsen``).

Independent references (same cell type, bulk in situ Hi-C, Rao et al. 2014, hg19, chr21):

* compartments: E1 of the Rao GM12878 map at 100 kb (``call_compartments_eig``, GC-phased);
* TAD boundaries: the authors' Arrowhead domain edges, and ``call_tads_insulation`` on the Rao map at 20 kb
  (the structures' grid; 100 kb window) — boundaries compared on the structures' loci
  (``compare_boundaries``, tolerance 1 / 2 loci, chance = the same for random loci);
* loops: the authors' HiCCUPS loops (``match_loops``, anchors within 25 / 50 kb); and ``score_loops`` (3-D
  distance of the published loop anchors vs other pairs at the same separation) on the structures.

Sections (``--sections``, default all):

``calls``       axes-PC (100 kb and 20 kb), ArcFISH TADs, FISHnet (windows), axis-wise F loops on the 28 traces;
                runtime best of ``--repeats``.
``pseudobulk``  the same 14 cells' contacts summed (``fea.pseudobulk``): E1, insulation, HiCCUPS — vs the same
                references and vs the structures' calls.
``genome``      every chromosome at 250 kb in one ``call_compartments_axes_pc`` call vs the E1 of the same cells'
                pseudo-bulk map (structures vs contacts genome-wide).
``arms``        the genome-wide comparison per chromosome arm (arms from the structures' centromere gaps): which
                chromosomes fail and whether the arms' contrast is why.
``replicates``  the callers on the replicate runs (layers ``rep1`` / ``rep2``): how much of the difference to
                the references is reconstruction noise.
``ntraces``     4, 8, 16, 28 traces (``--seeds`` random draws): agreement with the references by number of traces.
``fishnet_check`` the reduced FISHnet sweep used here vs the published defaults on 3 traces x 4 windows.

Results: tables on stdout and ``structures_callers.json`` in ``--out``.
"""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import structures_common as sc  # noqa: E402

warnings.filterwarnings("ignore")

CHROM = "chr21"
COMP_RES = 100_000
FISHNET_WINDOW, FISHNET_STEP = 100, 50
N_TRACES = (4, 8, 16, 28)


#: "default": the published sweep (200 thresholds x 20 Louvain runs; ~80 s per 100-locus window and trace with
#: networkx's Louvain, ~21 CPU hours for chr21's 28 traces: a cluster job); "reduced": 50 x 5 (~6 s)
FISHNET_SWEEP = "default"


def fishnet_params(sweep: str = None):
    from uchrom.strc.tad import FISHnetParams

    if (sweep or FISHNET_SWEEP) == "reduced":
        return FISHnetParams(max_thresholds=50, n_louvain_runs=5)
    return FISHnetParams()


def _fishnet_job(args):
    path, traces, params = args
    import pandas as pd

    cd = pd.read_pickle(path)
    return sc.fishnet_windows(cd, CHROM, params, window=FISHNET_WINDOW, step=FISHNET_STEP, traces=traces)


def fishnet_parallel(cd, out: Path, workers: int, params=None, tag="main") -> pd.DataFrame:
    """FISHnet in windows on every trace of ``cd`` (chr21), traces spread over ``workers`` processes."""
    cache = out / "cache" / f"fishnet_{tag}_{FISHNET_SWEEP}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    params = params or fishnet_params()
    src = out / "cache" / f"fishnet_input_{tag}.pkl"
    src.parent.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(cd, src)
    tids = sc.trace_ids(cd)
    jobs = [(src, [t], params) for t in tids]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        parts = list(ex.map(_fishnet_job, jobs))
    res = pd.concat(parts, ignore_index=True)
    res.to_parquet(cache)
    return res


# ------------------------------------------------------------------------------------------------ pieces

def references(out: Path):
    import uchrom.datasets as ds

    cache = out / "cache" / "references.pkl"
    if cache.exists():
        return pd.read_pickle(cache)
    fasta = ds.fetch("hg19_chr21")
    cool = ds.fetch("rao2014_gm12878_chr21")
    ref = sc.map_references(cool, CHROM, fasta, out / "maps", "rao_gm12878", comp_res=COMP_RES, tad_res=20_000)
    ah = sc.arrowhead("GM12878", CHROM)
    ref["arrowhead"] = sc.edges_to_domains(CHROM, np.r_[ah["start"].to_numpy(), ah["end"].to_numpy()])
    ref["arrowhead_n_domains"] = int(len(ah))
    ref["hiccups"] = sc.hiccups("GM12878", CHROM)
    ref["fasta"] = str(fasta)
    ref["cool"] = str(cool)
    cache.parent.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(ref, cache)
    return ref


def comp_on(cd, ref, fasta, res=COMP_RES, layer=None):
    """axes-PC on ``cd`` coarsened to ``res`` (A named by GC), compared with the Rao E1 on those bins."""
    from uchrom.strc.comp import CompartmentCallerParams, call_compartments_axes_pc, compare_compartments

    co = sc.coarsen(cd, res, CHROM, layer=layer) if res else cd
    sc.with_track(co, sc.gc_table(co.bins, fasta), "gc")
    table = call_compartments_axes_pc(co, chrom=CHROM, params=CompartmentCallerParams(a_track="gc"), device="cpu")
    return co, table, compare_compartments(co, table, ref["e1"])


def tads_on(cd, params=None):
    from uchrom.strc.tad import call_tads_by_pval

    return call_tads_by_pval(cd, chrom=CHROM, params=params, device="cpu", key_added=None)


def tad_refs(ref):
    return {"insulation": ref["insulation"], "arrowhead": ref["arrowhead"]}


def finest(t: pd.DataFrame) -> pd.DataFrame:
    return t[t["level"] == t["level"].min()] if len(t) else t


def loop_scores(cd, loops: pd.DataFrame, seed: int = 0) -> dict:
    """score_loops of ``loops`` (snapped to the loci) and of the same loops shifted by a random 0.5-2 Mb (the
    control): median anchor / background distance ratio and the fraction of loops with ratio < 1."""
    from uchrom.strc.loop import score_loops

    snapped = sc.snap_loops(loops, cd, CHROM)
    rng = np.random.default_rng(seed)
    shift = rng.integers(25, 100, len(snapped)) * 20_000 * rng.choice([-1, 1], len(snapped))
    loci = set(cd.bins.loc[cd.bins["chrom"].astype(str) == CHROM, "start"].astype(np.int64))
    ctrl = snapped.assign(start1=snapped["start1"] + shift, start2=snapped["start2"] + shift)
    ctrl = ctrl[ctrl["start1"].isin(loci) & ctrl["start2"].isin(loci)]
    out = {}
    for name, t in (("published", snapped), ("shifted_control", ctrl)):
        s = score_loops(cd, t, chrom=CHROM)
        r = s["ratio"].to_numpy(dtype=float)
        r = r[np.isfinite(r)]
        out[name] = {"n_loops": int(len(r)), "median_ratio": float(np.median(r)) if len(r) else None,
                     "frac_ratio_below_1": float(np.mean(r < 1)) if len(r) else None}
    return out


def fishnet_metrics(bounds: pd.DataFrame, cd, traces, ref) -> dict:
    """FISHnet boundary frequency over ``traces``: AUC for the loci near reference boundaries, and the top
    peaks (as many as the reference has boundaries) compared like a boundary call."""
    from uchrom.strc._traces import chrom_loci

    n = len(chrom_loci(cd, CHROM))
    freq = sc.fishnet_frequency(bounds, n, traces)
    out = {"n_boundaries_per_trace": float(bounds[bounds["trace_id"].isin(set(traces))].groupby("trace_id").size()
                                             .reindex(list(traces)).fillna(0).mean())}
    for name, dom in tad_refs(ref).items():
        for tol in (1, 2):
            out[f"auc_{name}_tol{tol}"] = sc.frequency_auc(freq, sc.near_loci(cd, CHROM, dom, tol))
    from uchrom.strc.tad import tad_boundaries

    n_ref = int(len(tad_boundaries(cd, ref["insulation"])))
    peaks = sc.frequency_peaks(freq, n_ref)
    out["peaks"] = sc.boundaries_vs(cd, sc.peaks_to_domains(cd, CHROM, peaks), tad_refs(ref))
    return out, freq


# ------------------------------------------------------------------------------------------------ sections

def section_calls(cd, ref, out: Path, repeats: int, workers: int) -> dict:
    from uchrom.strc.comp import CompartmentCallerParams, call_compartments_axes_pc, compare_compartments
    from uchrom.strc.loop import call_loops_axiswise_f

    res: dict = {"runtime": {}}
    fasta = ref["fasta"]
    # compartments: 100 kb (particles averaged) and the 20 kb particles
    (co, comp100, agree100), rt = sc.timed(comp_on, cd, ref, fasta, repeats=repeats)
    res["runtime"]["axes_pc_100kb"] = rt
    res["compartments_100kb"] = agree100
    sc.with_track(cd, sc.gc_table(cd.bins[cd.bins["chrom"].astype(str) == CHROM], fasta), "gc")
    comp20, rt = sc.timed(call_compartments_axes_pc, cd, chrom=CHROM, params=CompartmentCallerParams(a_track="gc"),
                          device="cpu", key_added=None, repeats=repeats)
    res["runtime"]["axes_pc_20kb"] = rt
    res["compartments_20kb"] = compare_compartments(cd, comp20, ref["e1"])
    res["n_bins"] = {"20kb": int(len(comp20)), "100kb": int(len(comp100))}
    print(f"compartments vs Rao E1: 100 kb {agree100}; 20 kb {res['compartments_20kb']}", flush=True)
    pd.to_pickle({"comp100": comp100, "comp20": comp20}, out / "cache" / "calls_comp.pkl")

    # TADs: ArcFISH at 20 kb (default window 100 kb; and 200 kb)
    from uchrom.strc.tad import TADCallerParams

    tads, rt = sc.timed(tads_on, cd, repeats=repeats)
    res["runtime"]["arcfish_tads"] = rt
    res["arcfish"] = {"n_boundaries": int(len(finest(tads)) - 1),
                      "vs": sc.boundaries_vs(cd, finest(tads), tad_refs(ref))}
    tads200 = tads_on(cd, TADCallerParams(window_bp=2e5))
    res["arcfish_window200kb"] = {"n_boundaries": int(len(finest(tads200)) - 1),
                                  "vs": sc.boundaries_vs(cd, finest(tads200), tad_refs(ref))}
    res["insulation_vs_arrowhead"] = sc.boundaries_vs(cd, ref["insulation"], {"arrowhead": ref["arrowhead"]})
    print(f"ArcFISH: {res['arcfish']['n_boundaries']} boundaries; vs insulation tol1 "
          f"{res['arcfish']['vs']['insulation_tol1']}; vs arrowhead tol1 {res['arcfish']['vs']['arrowhead_tol1']}",
          flush=True)
    pd.to_pickle({"tads": tads, "tads200": tads200}, out / "cache" / "calls_tads.pkl")

    # FISHnet per trace in windows
    t = time.perf_counter()
    bounds = fishnet_parallel(cd, out, workers)
    res["runtime"]["fishnet_windows"] = {"s": time.perf_counter() - t, "workers": workers,
                                         "params": vars(fishnet_params()) | {"window": FISHNET_WINDOW,
                                                                             "step": FISHNET_STEP}}
    fm, freq = fishnet_metrics(bounds, cd, sc.trace_ids(cd), ref)
    res["fishnet"] = fm
    print(f"FISHnet: {fm['n_boundaries_per_trace']:.1f} boundaries / trace; AUC vs insulation "
          f"{fm['auc_insulation_tol1']:.3f}, arrowhead {fm['auc_arrowhead_tol1']:.3f}", flush=True)

    # loops: axis-wise F; the published loops scored on the structures
    loops, rt = sc.timed(call_loops_axiswise_f, cd, chrom=CHROM, device="cpu", key_added=None, repeats=repeats)
    res["runtime"]["axiswise_f_loops"] = rt
    res["loops"] = sc.loops_vs(loops, ref["hiccups"])
    res["loop_scores"] = loop_scores(cd, ref["hiccups"])
    print(f"axis-wise F loops: {len(loops)} calls, vs HiCCUPS {res['loops']}; published loops scored on the "
          f"structures {res['loop_scores']}", flush=True)
    return res


def section_pseudobulk(cd_all, cd, ref, out: Path) -> dict:
    """The same 14 cells' contacts: pseudo-bulk map -> E1 / insulation / HiCCUPS."""
    import cooler

    from uchrom.fea import pseudobulk
    from uchrom.strc.comp import compare_compartments
    from uchrom.strc.comp.eig import call_compartments_eig
    from uchrom.strc.loop import call_loops_hiccups
    from uchrom.strc.tad import call_tads_insulation

    res: dict = {}
    t = time.perf_counter()
    summary = pseudobulk(cd_all, None, trans=False, key_prefix="sc_structures_pb", out_dir=out / "maps")
    res["pseudobulk_s"] = time.perf_counter() - t
    row = summary.iloc[0]
    path = Path(row["path"])
    clr = cooler.Cooler(str(path))
    n21 = int(clr.matrix(balance=False, as_pixels=True).fetch(CHROM)["count"].sum())
    res["map"] = {"n_cells": int(row["n_cells"]), "n_contacts": int(row["n_contacts"]), "chr21_contacts": n21}
    p100 = sc.rebinned(path, COMP_RES, out / "maps", "pb_gm12878", chrom=CHROM)
    e1 = call_compartments_eig(str(p100), chrom=CHROM, phasing=ref["fasta"])
    res["e1_vs_rao_e1"] = compare_compartments(sc.coarsen(cd, COMP_RES, CHROM), e1, ref["e1"])
    p20 = sc.rebinned(path, 20_000, out / "maps", "pb_gm12878", chrom=CHROM)
    ins = call_tads_insulation(str(p20), chrom=CHROM)
    res["insulation"] = {"n_boundaries": int(len(ins) - 1), "vs": sc.boundaries_vs(cd, ins, tad_refs(ref))}
    p10 = sc.rebinned(path, 10_000, out / "maps", "pb_gm12878", chrom=CHROM)
    loops = call_loops_hiccups(str(p10), chrom=CHROM, key_added=None)   # a path: nothing to store on
    res["hiccups"] = sc.loops_vs(loops, ref["hiccups"])
    # structures vs contacts of the same cells
    calls = pd.read_pickle(out / "cache" / "calls_comp.pkl")
    tads = pd.read_pickle(out / "cache" / "calls_tads.pkl")["tads"]
    co = sc.coarsen(cd, COMP_RES, CHROM)
    res["structures_axes_pc_vs_pseudobulk_e1"] = compare_compartments(co, calls["comp100"], e1)
    res["structures_arcfish_vs_pseudobulk_insulation"] = sc.boundaries_vs(cd, finest(tads), {"pb_insulation": ins})
    print(f"pseudo-bulk ({res['map']}): E1 vs Rao {res['e1_vs_rao_e1']}; insulation "
          f"{res['insulation']['n_boundaries']} "
          f"boundaries, vs insulation tol1 {res['insulation']['vs']['insulation_tol1']}; HiCCUPS {res['hiccups']}; "
          f"structures axes-PC vs pseudo-bulk E1 {res['structures_axes_pc_vs_pseudobulk_e1']}", flush=True)
    return res


def _fishnet_window_job(args):
    X, params, seed = args
    from uchrom.strc.tad.fishnet import _fishnet_on_matrix

    d = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(-1))
    t = time.perf_counter()
    r = _fishnet_on_matrix(d, params, seed)
    return r["boundaries"], time.perf_counter() - t


def section_fishnet_check(cd, out: Path, workers: int, n_traces: int = 3, n_windows: int = 4) -> dict:
    """The reduced FISHnet sweep used here vs the published defaults (200 thresholds x 20 Louvain runs) on a
    sample of traces and windows: how many boundaries each finds and how many fall within 1 locus of the
    other's."""
    from uchrom.strc._traces import coord_cube
    from uchrom.strc.tad import FISHnetParams
    from uchrom.strc.tad.fishnet import trace_seed

    cube, _, tids = coord_cube(cd, CHROM)
    rng = np.random.default_rng(0)
    picks = [(int(t), int(a)) for t in rng.choice(len(tids), n_traces, replace=False)
             for a in rng.choice(np.arange(0, cube.shape[1] - FISHNET_WINDOW, FISHNET_STEP), n_windows,
                                 replace=False)]
    jobs = {name: [(cube[t, a:a + FISHNET_WINDOW], p, trace_seed(f"{tids[t]}:{a}")) for t, a in picks]
            for name, p in (("reduced", fishnet_params("reduced")), ("default", FISHnetParams()))}
    got = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for name, js in jobs.items():
            got[name] = list(ex.map(_fishnet_window_job, js))

    def near(a, b):
        return [any(abs(x - y) <= 1 for y in b) for x in a]

    n_red = sum(len(b) for b, _ in got["reduced"])
    n_def = sum(len(b) for b, _ in got["default"])
    red_near = sum(sum(near(r[0], d[0])) for r, d in zip(got["reduced"], got["default"]))
    def_near = sum(sum(near(d[0], r[0])) for r, d in zip(got["reduced"], got["default"]))
    res = {"windows": len(picks), "boundaries_reduced": n_red, "boundaries_default": n_def,
           "reduced_near_default": red_near / max(n_red, 1), "default_near_reduced": def_near / max(n_def, 1),
           "s_per_window_reduced": float(np.median([s for _, s in got["reduced"]])),
           "s_per_window_default": float(np.median([s for _, s in got["default"]]))}
    print(f"FISHnet reduced vs default sweep: {res}", flush=True)
    return res


def section_genome(cd_all, out: Path, res_bp: int = 250_000) -> dict:
    """Every chromosome: axes-PC on the structures averaged into ``res_bp`` bins (one call on the whole
    object) vs the E1 of the same cells' pseudo-bulk map (GC-phased, hg19) — structures vs contacts
    genome-wide (no genome-wide Rao GM12878 map is registered)."""
    import uchrom.datasets as ds
    from chromdata import ChromData
    from uchrom.fea import pseudobulk
    from uchrom.strc.comp import CompartmentCallerParams, call_compartments_axes_pc, compare_compartments
    from uchrom.strc.comp.eig import call_compartments_eig

    chroms = [str(c) for c in cd_all.bins["chrom"].cat.categories]
    t = time.perf_counter()
    parts = [sc.coarsen(cd_all, res_bp, c) for c in chroms]
    co = ChromData(np.concatenate([p.coords for p in parts]),
                   pd.concat([p.spots_with_loci()[["chrom", "start", "end", "trace_id", "cell_id"]] for p in parts],
                             ignore_index=True))
    t_coarsen = time.perf_counter() - t
    fasta = ds.fetch("hg19_genome")
    summary = pseudobulk(cd_all, None, trans=False, key_prefix="sc_structures_pb", out_dir=out / "maps")
    p = sc.rebinned(Path(summary.iloc[0]["path"]), res_bp, out / "maps", "pb_gm12878_genome")
    import cooler

    bins = cooler.Cooler(str(p)).bins()[:][["chrom", "start", "end"]]
    gc = sc.gc_table(bins, fasta)
    e1 = call_compartments_eig(str(p), chrom=chroms, phasing=gc)
    sc.with_track(co, gc, "gc")
    table, rt = sc.timed(call_compartments_axes_pc, co, params=CompartmentCallerParams(a_track="gc"), device="cpu",
                         key_added=None)
    per = {c: compare_compartments(co, table, e1, chrom=c) for c in chroms}
    rs = np.array([v["pearson_r"] for v in per.values()], dtype=float)
    res = {"resolution": res_bp, "n_chroms": len(chroms), "n_traces": int(co.n_traces), "n_loci": int(co.n_bins),
           "coarsen_s": t_coarsen, "axes_pc_runtime": rt, "all": compare_compartments(co, table, e1),
           "per_chrom": per, "per_chrom_r_median": float(np.nanmedian(rs)),
           "per_chrom_r_range": [float(np.nanmin(rs)), float(np.nanmax(rs))]}
    print(f"genome-wide {res_bp // 1000} kb: axes-PC on {co.n_traces} traces vs pseudo-bulk E1 {res['all']}; per "
          f"chromosome median r {res['per_chrom_r_median']:.3f} {res['per_chrom_r_range']}; {rt}", flush=True)
    return res


def _arm_gaps(cd_all, chroms) -> dict:
    """Per chromosome, the largest stretch without any particle (all cells pooled): the centromere (with its
    flanking heterochromatin) of a metacentric / submetacentric chromosome; for an acrocentric one the
    stretch before the first particle (the p arm) is longer than any internal gap — no split.  Read from the
    structures themselves (no annotation needed)."""
    out = {}
    for c in chroms:
        b = cd_all.bins[cd_all.bins["chrom"].astype(str) == c].sort_values("start")
        s, e = b["start"].to_numpy(np.int64), b["end"].to_numpy(np.int64)
        gaps = s[1:] - e[:-1]
        k = int(np.argmax(gaps))
        split = bool(gaps[k] > s[0])
        out[c] = {"gap_start": int(e[k]), "gap_end": int(s[k + 1]), "gap_bp": int(gaps[k]), "first_locus": int(s[0]),
                  "split": split, "centromere": int((e[k] + s[k + 1]) // 2) if split else None}
    return out


def section_arms(cd_all, out: Path, res_bp: int = 250_000) -> dict:
    """Why some chromosomes fail genome-wide: the same comparison per chromosome arm.  Arms from the
    structures' own centromere gaps (``_arm_gaps``); the reference E1 decomposed per arm
    (``call_compartments_eig(centromeres=)``) and axes-PC per arm (``call_compartments_axes_pc(centromeres=)``).  Per chromosome: axes-PC (whole chromosome) vs E1 (whole / per arm), axes-PC per arm vs E1
    per arm, and E1 whole vs E1 per arm (the arm contrast in the reference itself)."""
    import cooler

    import uchrom.datasets as ds
    from chromdata import ChromData
    from uchrom.fea import pseudobulk
    from uchrom.strc.comp import CompartmentCallerParams, call_compartments_axes_pc, compare_compartments
    from uchrom.strc.comp.eig import call_compartments_eig

    chroms = [str(c) for c in cd_all.bins["chrom"].cat.categories]
    gaps = _arm_gaps(cd_all, chroms)
    cen = {c: g["centromere"] for c, g in gaps.items() if g["split"]}
    parts = [sc.coarsen(cd_all, res_bp, c) for c in chroms]
    spots = pd.concat([p.spots_with_loci()[["chrom", "start", "end", "trace_id", "cell_id"]] for p in parts],
                      ignore_index=True)
    xyz = np.concatenate([p.coords for p in parts])
    co = ChromData(xyz, spots)
    summary = pseudobulk(cd_all, None, trans=False, key_prefix="sc_structures_pb", out_dir=out / "maps")
    p = sc.rebinned(Path(summary.iloc[0]["path"]), res_bp, out / "maps", "pb_gm12878_genome")
    bins = cooler.Cooler(str(p)).bins()[:][["chrom", "start", "end"]]
    gc = sc.gc_table(bins, ds.fetch("hg19_genome"))
    e1 = call_compartments_eig(str(p), chrom=chroms, phasing=gc)
    e1_arm = call_compartments_eig(str(p), chrom=chroms, phasing=gc, centromeres=cen)
    sc.with_track(co, gc, "gc")
    params = CompartmentCallerParams(a_track="gc")
    whole = call_compartments_axes_pc(co, params=params, device="cpu", key_added=None)
    arm_back, rt = sc.timed(call_compartments_axes_pc, co, params=params, device="cpu", key_added=None,
                            centromeres=cen)
    rows = []
    for c in chroms:
        r = {"chrom": c, **{k: gaps[c][k] for k in ("split", "gap_bp", "first_locus")}}
        r["axes_pc_vs_e1"] = compare_compartments(co, whole, e1, chrom=c)["pearson_r"]
        r["axes_pc_vs_e1_arms"] = compare_compartments(co, whole, e1_arm, chrom=c)["pearson_r"]
        r["axes_pc_arms_vs_e1_arms"] = compare_compartments(co, arm_back, e1_arm, chrom=c)["pearson_r"]
        r["e1_vs_e1_arms"] = compare_compartments(co, e1, e1_arm, chrom=c)["pearson_r"]
        rows.append(r)
    df = pd.DataFrame(rows)
    print(df.round(3).to_string(), flush=True)
    med = df[["axes_pc_vs_e1", "axes_pc_vs_e1_arms", "axes_pc_arms_vs_e1_arms", "e1_vs_e1_arms"]].median()
    print("medians", med.round(3).to_dict(), "axes-PC per arm", rt, flush=True)
    return {"rows": df.to_dict("records"), "medians": med.to_dict(), "axes_pc_arms_runtime": rt,
            "all_arms": compare_compartments(co, arm_back, e1_arm), "centromere_gaps": gaps}


def section_replicates(cd, ref, out: Path) -> dict:
    from chromdata import ChromData
    from uchrom.strc.comp import compare_compartments

    res: dict = {}
    main = pd.read_pickle(out / "cache" / "calls_comp.pkl")["comp100"]
    main_tads = finest(pd.read_pickle(out / "cache" / "calls_tads.pkl")["tads"])
    rep_comp, rep_tads = {}, {}
    for rep in ("rep1", "rep2"):
        co, table, agree = comp_on(cd, ref, ref["fasta"], layer=rep)
        rep_comp[rep] = table
        r = {"compartments_vs_rao_e1": agree, "compartments_vs_main_run": compare_compartments(co, table, main)}
        xyz = np.asarray(cd.layers[rep])
        ok = np.isfinite(xyz).all(1)
        rc = ChromData(xyz[ok], cd.spots_with_loci()[["chrom", "start", "end", "trace_id", "cell_id"]][ok])
        t = finest(tads_on(rc))
        rep_tads[rep] = t
        r["arcfish_n_boundaries"] = int(len(t) - 1)
        r["arcfish_vs_refs"] = sc.boundaries_vs(cd, t, tad_refs(ref))
        r["arcfish_vs_main_run"] = sc.boundaries_vs(cd, t, {"main_run": main_tads})
        res[rep] = r
        print(f"{rep}: compartments vs Rao {agree}, vs main run {r['compartments_vs_main_run']}; ArcFISH vs main run "
              f"tol1 {r['arcfish_vs_main_run']['main_run_tol1']}", flush=True)
    co = sc.coarsen(cd, COMP_RES, CHROM)
    res["rep1_vs_rep2_compartments"] = compare_compartments(co, rep_comp["rep1"], rep_comp["rep2"])
    res["rep1_vs_rep2_arcfish"] = sc.boundaries_vs(cd, rep_tads["rep1"], {"rep2": rep_tads["rep2"]})
    return res


def section_ntraces(cd, ref, out: Path, seeds: int) -> dict:
    rows = []
    bounds = fishnet_parallel(cd, out, 1)            # cached by the calls section
    all_ids = sc.trace_ids(cd)
    for n in N_TRACES:
        for seed in range(seeds if n < len(all_ids) else 1):
            sub, picked = sc.subsample(cd, n, seed)
            t = time.perf_counter()
            _, _, comp = comp_on(sub, ref, ref["fasta"])
            tads = finest(tads_on(sub))
            vs = sc.boundaries_vs(cd, tads, tad_refs(ref), tols=(1,))
            fm, _ = fishnet_metrics(bounds, cd, picked, ref)
            rows.append({"n_traces": n, "seed": seed, "comp_r": comp["pearson_r"], "comp_agreement": comp["agreement"],
                         "arcfish_n": int(len(tads) - 1),
                         "arcfish_precision_insulation": vs["insulation_tol1"]["precision"],
                         "arcfish_recall_insulation": vs["insulation_tol1"]["recall"],
                         "arcfish_precision_arrowhead": vs["arrowhead_tol1"]["precision"],
                         "arcfish_recall_arrowhead": vs["arrowhead_tol1"]["recall"],
                         "precision_chance_insulation": vs["insulation_tol1"]["precision_chance"],
                         "fishnet_auc_insulation": fm["auc_insulation_tol1"],
                         "fishnet_auc_arrowhead": fm["auc_arrowhead_tol1"], "s": time.perf_counter() - t})
            print(rows[-1], flush=True)
    df = pd.DataFrame(rows)
    summary = df.drop(columns=["seed"]).groupby("n_traces").agg(["mean", "std"])
    summary.columns = [f"{a}_{b}" for a, b in summary.columns]
    print(summary.round(3).to_string(), flush=True)
    return {"rows": df.to_dict("records"), "summary": summary.reset_index().to_dict("records")}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=sc.default_out("sc_structures_callers"))
    ap.add_argument("--sections", nargs="+",
                    default=["calls", "pseudobulk", "genome", "arms", "replicates", "ntraces", "fishnet_check"])
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--fishnet-sweep", choices=["default", "reduced"], default="default")
    a = ap.parse_args()
    global FISHNET_SWEEP
    FISHNET_SWEEP = a.fishnet_sweep
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "cache").mkdir(exist_ok=True)

    import uchrom.datasets as ds

    res_path = a.out / "structures_callers.json"
    res = {} if not res_path.exists() else __import__("json").loads(res_path.read_text())
    (cd_all, rt) = sc.timed(ds.load, "tan2018_gm12878", backed=True)
    res["load"] = rt
    cd = sc.in_memory_chrom(cd_all, CHROM)
    cells = cd_all.cells
    res["data"] = {"n_cells": int(len(cells)), "n_traces_chr21": int(cd.n_traces), "n_particles_chr21": int(cd.n_spots),
                   "particles_per_trace": float(cd.n_spots / cd.n_traces),
                   "rmsd_rep1_median": float(cells["rmsd_rep1"].median()),
                   "rmsd_rep2_median": float(cells["rmsd_rep2"].median()),
                   "median_dev_rep1_median": float(cells["median_dev_rep1"].median()),
                   "rep_deviation_chr21_median": float(np.nanmedian(cd.spot_tracks["rep_deviation"]))}
    print(res["data"], flush=True)
    ref = references(a.out)
    res["references"] = {"e1_bins": int(len(ref["e1"])), "insulation_boundaries": int(len(ref["insulation"]) - 1),
                         "arrowhead_domains": ref["arrowhead_n_domains"],
                         "arrowhead_edges": int(len(ref["arrowhead"]) + 1),
                         "hiccups_loops": int(len(ref["hiccups"]))}
    for s in a.sections:
        t = time.perf_counter()
        if s == "calls":
            res["calls"] = section_calls(cd, ref, a.out, a.repeats, a.workers)
        elif s == "pseudobulk":
            res["pseudobulk"] = section_pseudobulk(cd_all, cd, ref, a.out)
        elif s == "replicates":
            res["replicates"] = section_replicates(cd, ref, a.out)
        elif s == "genome":
            res["genome"] = section_genome(cd_all, a.out)
        elif s == "arms":
            res["arms"] = section_arms(cd_all, a.out)
        elif s == "fishnet_check":
            res["fishnet_check"] = section_fishnet_check(cd, a.out, a.workers)
        elif s == "ntraces":
            res["ntraces"] = section_ntraces(cd, ref, a.out, a.seeds)
        else:
            raise SystemExit(f"unknown section {s}")
        print(f"[{s}] {time.perf_counter() - t:.0f} s", flush=True)
        sc.dump(res, res_path)
    print(f"-> {res_path}")


if __name__ == "__main__":
    main()
