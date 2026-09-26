"""Real-data validation of format 2.1 (chromosome partitions) and streaming (roadmap step 7).

Steps (each measured in fresh processes; big ones run one at a time):

``convert``  2.0 ``.chromdata.zarr`` → 2.1 (``<name>.v21.chromdata.zarr`` next to
             it): time / peak RSS; value identity of the whole object (the
             2.1 store read with ``original_order=True`` equals the 2.0 store
             as read), backed ``get_cell`` / ``get_trace`` / ``get_chrom``
             (all columns and ``columns="coords"``) against in-memory scans.
``fofct``    Liu 2025 MOp FOF-CT: ``ChromData.from_fofct(out=...)`` (streaming,
             memory budget) vs the in-memory ``from_fofct``: peak RSS of each,
             value identity of the result (original order), cells / uns.
``seqfish``  Takei 2025 cerebellum rep 1, all FOVs:
             ``read_seqfish_multiomics(out=...)`` (FOV by FOV) vs in memory.
``stats``    streaming vs in-memory population statistics: exact median /
             mean distance maps per chromosome (``uchrom.fea.distance_map``;
             bitwise comparison) on Takei 2025 and Liu 2025 (Liu also against
             the dense ``mean_distance_matrix``); ArcFISH loop F-test and TAD
             caller, streaming vs torch, on Takei 2021 mESC (FOF-CT).

    python benchmarks/cd21_streaming_validation.py --data example-data --work /tmp/cd21 \\
        [--steps convert,fofct,seqfish,stats] [--only takei2025_cerebellum,liu2025_mop]

Writes ``paper/fig2/results/streaming_validation.json`` (merged per step).
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "paper" / "fig2" / "results" / "streaming_validation.json"

STORES = {
    "takei2025_cerebellum": "takei2025_cerebellum/takei2025_cerebellum_rep1.chromdata.zarr",
    "liu2025_mop": "liu2025_mop/liu2025_mop.chromdata.zarr",
}


def peak_rss_gb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 2**30 if sys.platform == "darwin" else r / 2**20


def emit(obj) -> None:
    print("__RESULT__" + json.dumps(obj, default=str), flush=True)


def run_child(args, timeout=4 * 3600):
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", *args],
                          capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0 or "__RESULT__" not in proc.stdout:
        raise RuntimeError(f"child {args} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-4000:]}")
    return json.loads(proc.stdout.rsplit("__RESULT__", 1)[1].strip().splitlines()[0])


def v21_path(src: Path) -> Path:
    return src.with_name(src.name.replace(".chromdata.zarr", ".v21.chromdata.zarr"))


def size_bytes(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size


# ----------------------------------------------------------------------------- identity helpers

def same_objects(a, b, *, check_order=True) -> dict:
    """Value identity of two in-memory ChromData (spots incl. dtypes /
    categories, coords NaN-aware, tracks, layers, small tables, uns)."""
    import numpy as np
    import pandas as pd

    out = {}

    def check(name, fn):
        try:
            fn()
            out[name] = True
        except AssertionError as exc:
            out[name] = f"DIFFERS: {str(exc)[:300]}"

    check("spots", lambda: pd.testing.assert_frame_equal(a.spots, b.spots))
    check("coords", lambda: np.testing.assert_array_equal(a.coords, b.coords))
    check("spot_tracks", lambda: pd.testing.assert_frame_equal(a.spot_tracks, b.spot_tracks))
    check("bin_tracks", lambda: pd.testing.assert_frame_equal(a.bin_tracks, b.bin_tracks))
    check("bins", lambda: pd.testing.assert_frame_equal(a.bins, b.bins))
    check("cells", lambda: pd.testing.assert_frame_equal(a.cells, b.cells))
    check("traces", lambda: pd.testing.assert_frame_equal(a.traces, b.traces))
    def cellm():
        assert list(a.cellm) == list(b.cellm), "cellm keys"
        for k in a.cellm:
            np.testing.assert_array_equal(a.cellm[k], b.cellm[k])

    def layers():
        assert list(a.layers) == list(b.layers), "layer keys"
        for k in a.layers:
            np.testing.assert_array_equal(a.layers[k], b.layers[k])

    def uns():
        assert json.dumps(a.uns, sort_keys=True, default=str) == json.dumps(b.uns, sort_keys=True, default=str)

    check("cellm", cellm)
    check("layers", layers)
    check("uns", uns)
    out["all"] = all(v is True for v in out.values())
    return out


# ----------------------------------------------------------------------------- steps (children)

def child_convert(src, dst):
    from uchrom import ChromData

    t0 = time.perf_counter()
    cd = ChromData.read(src)
    cd.write(dst)
    emit({"seconds": time.perf_counter() - t0, "peak_rss_gb": peak_rss_gb(), "bytes": size_bytes(Path(dst)),
          "src_bytes": size_bytes(Path(src))})


def child_verify(src, dst):
    import numpy as np
    import pandas as pd

    from uchrom import ChromData

    old = ChromData.read(src)
    new_orig = ChromData.read(dst, original_order=True)
    res = {"original_order": same_objects(old, new_orig)}
    del new_orig
    bk = ChromData.read(dst, backed=True)
    res["format_version"] = bk.format_version
    new = bk.to_memory()
    rng = np.random.default_rng(0)
    checks = {"cell": 0, "trace": 0, "chrom": 0, "coords_only": 0}
    cells = list(new.spots["cell_id"].cat.categories) if "cell_id" in new.spots else []
    traces = list(new.spots["trace_id"].cat.categories)
    for c in rng.choice(cells, min(5, len(cells)), replace=False):
        pd.testing.assert_frame_equal(bk.get_cell(c).to_dataframe(), new.get_cell(c).to_dataframe())
        pd.testing.assert_frame_equal(bk.get_cell(c).spot_tracks, new.get_cell(c).spot_tracks)
        checks["cell"] += 1
    for t in rng.choice(traces, 5, replace=False):
        pd.testing.assert_frame_equal(bk.get_trace(t).to_dataframe(), new.get_trace(t).to_dataframe())
        checks["trace"] += 1
    for ch in list(new.bins["chrom"].cat.categories)[:3]:
        x = bk.get_chrom(ch)
        y = new.get_chrom(ch)
        pd.testing.assert_frame_equal(x.to_dataframe(), y.to_dataframe())
        pd.testing.assert_frame_equal(x.spot_tracks, y.spot_tracks)
        z = bk.get_chrom(ch, columns="coords")
        pd.testing.assert_frame_equal(z.to_dataframe()[["chrom", "start", "end", "x", "y", "z"]],
                                      y.to_dataframe()[["chrom", "start", "end", "x", "y", "z"]])
        checks["chrom"] += 1
        checks["coords_only"] += 1
    res["backed_vs_memory"] = checks
    res["n_spots"] = int(new.n_spots)
    res["ok"] = bool(res["original_order"]["all"])
    emit(res)


def child_fofct(mode, core, cells, out, budget):
    from uchrom import ChromData, settings

    t0 = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if mode == "stream":
            cd = ChromData.from_fofct(core, cell_table=cells, cell_value_prefix=None, out=out,
                                      memory_budget=budget)
        else:
            cd = ChromData.from_fofct(core, cell_table=cells, cell_value_prefix=None)
            cd.write(out)
    emit({"mode": mode, "seconds": time.perf_counter() - t0, "peak_rss_gb": peak_rss_gb(),
          "n_spots": int(cd.n_spots), "bytes": size_bytes(Path(out)), "budget": budget})


def child_seqfish(mode, data_dir, out, budget):
    from uchrom.io.seqfish_multiomics import read_seqfish_multiomics

    d = Path(data_dir)
    kw = dict(locus_annotation=d / "LC1-100k-09022022-mm10-25kb-meta.csv",
              cell_clustering=d / "cerebellum_mRNA_cluster_nuc_vol_filtered.csv")
    t0 = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if mode == "stream":
            cd = read_seqfish_multiomics(str(d / "raw" / "cerebellum_rep1_pos*.csv"), out=out,
                                         memory_budget=budget, **kw)
        else:
            cd = read_seqfish_multiomics(str(d / "raw" / "cerebellum_rep1_pos*.csv"), **kw)
            cd.write(out)
    emit({"mode": mode, "seconds": time.perf_counter() - t0, "peak_rss_gb": peak_rss_gb(),
          "n_spots": int(cd.n_spots), "bytes": size_bytes(Path(out)), "budget": budget})


def child_compare(a, b):
    """Two stores (memory-built vs streamed): identity in stored and original order."""
    from uchrom import ChromData

    res = {"stored_order": same_objects(ChromData.read(a), ChromData.read(b))}
    res["original_order"] = same_objects(ChromData.read(a, original_order=True),
                                         ChromData.read(b, original_order=True))
    import zarr
    ia, ib = zarr.open_group(str(a), mode="r"), zarr.open_group(str(b), mode="r")
    import numpy as np
    res["index_identical"] = all(np.array_equal(ia[f"index/{k}"][:], ib[f"index/{k}"][:])
                                 for k in ("trace_offsets", "cell_offsets", "row_groups", "partition_offsets"))
    res["ok"] = bool(res["stored_order"]["all"] and res["original_order"]["all"])
    emit(res)


def child_stats(store, chroms, budget, dense):
    import numpy as np

    from uchrom import ChromData
    from uchrom.fea import distance_map, mean_distance_matrix

    bk = ChromData.read(store, backed=True)
    out = {}
    for ch in chroms.split(","):
        rec = {}
        mem = bk.get_chrom(ch, columns="coords")        # the chromosome, in memory
        for stat in ("median", "mean"):
            t0 = time.perf_counter()
            s = distance_map(bk, ch, stat, memory_budget=budget)
            ts = time.perf_counter() - t0
            m = distance_map(mem, ch, stat, streaming=False)
            same = bool(np.array_equal(s.matrix, m.matrix, equal_nan=True))
            diff = np.abs(s.matrix - m.matrix)
            r = {"identical": same, "max_abs_diff": float(np.nanmax(diff)) if np.isfinite(diff).any() else 0.0,
                 "n_bins": int(s.matrix.shape[0]), "n_traces": int(s.n_traces),
                 "n_pairs_observed": int((np.triu(s.count, 1) > 0).sum()),
                 "n_obs": int(np.triu(s.count, 1).sum()), "stream_s": ts, "n_bands": int(s.n_bands)}
            if dense == "1":
                import warnings as _w
                with _w.catch_warnings():
                    _w.simplefilter("ignore", RuntimeWarning)
                    ref, bins, n_tr = mean_distance_matrix(mem.to_dataframe(), chrom=ch, reduce=stat)
                r["identical_to_dense"] = bool(np.array_equal(s.matrix, ref, equal_nan=True))
            if ch == chroms.split(",")[0] and stat == "median":
                iu = np.triu_indices(s.matrix.shape[0], 1)
                ok = np.isfinite(s.matrix[iu]) & np.isfinite(m.matrix[iu])
                rng = np.random.default_rng(0)
                pick = rng.choice(np.flatnonzero(ok), min(3000, int(ok.sum())), replace=False)
                r["scatter"] = {"in_memory": m.matrix[iu][pick].round(6).tolist(),
                                "streaming": s.matrix[iu][pick].round(6).tolist()}
            rec[stat] = r
        out[ch] = rec
    emit({"store": store, "budget": budget, "chroms": out, "peak_rss_gb": peak_rss_gb()})


def child_callers(core):
    import numpy as np
    import pandas as pd

    from uchrom import ChromData
    from uchrom.strc.loop import call_loops_axiswise_f
    from uchrom.strc.tad import call_tads_by_pval

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cd = ChromData.from_fofct(core)
    res = {"n_spots": int(cd.n_spots), "n_traces": int(cd.n_traces), "chroms": cd.chroms}
    for name, fn in (("loops", call_loops_axiswise_f), ("tads", call_tads_by_pval)):
        t0 = time.perf_counter()
        ref = fn(cd, device="cpu", key_added=None)
        t1 = time.perf_counter()
        got = fn(cd, streaming=True, key_added=None, memory_budget="256MB")
        t2 = time.perf_counter()
        keys = [c for c in ref.columns if c not in ("score", "pval", "fdr", "contact_freq")]
        same_rows = len(ref) == len(got) and ref[keys].reset_index(drop=True).equals(got[keys].reset_index(drop=True))
        r = {"n_in_memory": int(len(ref)), "n_streaming": int(len(got)), "same_calls": bool(same_rows),
             "in_memory_s": t1 - t0, "streaming_s": t2 - t1}
        if same_rows and len(ref):
            rel = np.abs(got["pval"].to_numpy() - ref["pval"].to_numpy()) / np.maximum(ref["pval"].to_numpy(), 1e-300)
            r["max_rel_pval_diff"] = float(rel.max())
        res[name] = r
    emit(res)


# ----------------------------------------------------------------------------- driver

def merge(step: str, payload) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = json.loads(OUT.read_text()) if OUT.exists() else {}
    doc.setdefault("machine", _machine())
    doc[step] = payload
    OUT.write_text(json.dumps(doc, indent=1, default=str))


def _machine():
    sys.path.insert(0, str(ROOT / "benchmarks" / "fig2"))
    import _common as C
    return C.machine_info()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "example-data")
    ap.add_argument("--work", type=Path, default=Path("/tmp/cd21"))
    ap.add_argument("--steps", default="convert,fofct,seqfish,stats")
    ap.add_argument("--only", default=",".join(STORES))
    ap.add_argument("--budget", default="4GB", help="memory budget of the streaming imports")
    ap.add_argument("--child", nargs="+", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        kind, *rest = args.child
        return {"convert": child_convert, "verify": child_verify, "fofct": child_fofct,
                "seqfish": child_seqfish, "compare": child_compare, "stats": child_stats,
                "callers": child_callers}[kind](*rest)
    args.work.mkdir(parents=True, exist_ok=True)
    steps = args.steps.split(",")
    only = args.only.split(",")
    if "convert" in steps:
        res = {}
        for name in only:
            src = args.data / STORES[name]
            dst = v21_path(src)
            c = run_child(["convert", str(src), str(dst)])
            v = run_child(["verify", str(src), str(dst)])
            res[name] = {"src": str(src), "dst": str(dst), **c, "verify": v}
            print(name, json.dumps({k: v for k, v in res[name].items() if k != "verify"}), v["ok"], flush=True)
        merge("convert", res)
    if "fofct" in steps:
        d = args.data / "liu2025_mop"
        core, cells = d / "4DNFID46OABK.csv", d / "4DNFICX8IVEK.csv"
        mem_out = args.work / "liu_mem.chromdata.zarr"
        st_out = args.work / "liu_stream.chromdata.zarr"
        m = run_child(["fofct", "memory", str(core), str(cells), str(mem_out), args.budget])
        s = run_child(["fofct", "stream", str(core), str(cells), str(st_out), args.budget])
        cmp_ = run_child(["compare", str(mem_out), str(st_out)])
        merge("fofct", {"dataset": "Liu 2025 MOp FOF-CT (4DNFID46OABK + 4DNFICX8IVEK)", "in_memory": m,
                        "streaming": s, "compare": cmp_})
        print("fofct", m["peak_rss_gb"], s["peak_rss_gb"], cmp_["ok"], flush=True)
    if "seqfish" in steps:
        d = args.data / "takei2025_cerebellum"
        mem_out = args.work / "takei_mem.chromdata.zarr"
        st_out = args.work / "takei_stream.chromdata.zarr"
        s = run_child(["seqfish", "stream", str(d), str(st_out), args.budget])
        m = run_child(["seqfish", "memory", str(d), str(mem_out), args.budget])
        cmp_ = run_child(["compare", str(mem_out), str(st_out)])
        merge("seqfish", {"dataset": "Takei 2025 cerebellum rep 1, FOVs 0-2 (raw CSVs)", "in_memory": m,
                          "streaming": s, "compare": cmp_})
        print("seqfish", m["peak_rss_gb"], s["peak_rss_gb"], cmp_["ok"], flush=True)
    if "stats" in steps:
        res = {}
        takei = v21_path(args.data / STORES["takei2025_cerebellum"])
        liu = v21_path(args.data / STORES["liu2025_mop"])
        res["takei2025_cerebellum"] = run_child(["stats", str(takei), "chr19,chr11,chr1", "1GB", "0"])
        res["liu2025_mop"] = run_child(["stats", str(liu), ",".join(f"chr{i}" for i in range(1, 20)) + ",chrX",
                                        "256MB", "1"])
        res["arcfish_takei2021"] = run_child(["callers", str(args.data / "4DNFIHF3JCBY.csv")])
        merge("stats", res)
        print("stats", json.dumps(res["arcfish_takei2021"]), flush=True)
    print(OUT)


if __name__ == "__main__":
    main()
