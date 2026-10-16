"""The ArcFISH part of benchmarks/cd21_streaming_validation.py (child_callers), re-run with the callers of U-Chrom
origin/main (after the parity re-implementation, de8384e): loop F-test and TAD caller on Takei 2021 mESC (FOF-CT
4DNFIHF3JCBY), in memory (device="cpu") against streaming=True (memory_budget="256MB"), as the original did; the
comparison also reports every float column's largest difference and exact equality of the whole tables.

    python benchmarks/arcfish_parity/streaming_check.py CORE.csv OUT.json   (sherlock/streaming_check.sbatch)
"""
from __future__ import annotations

import json
import os
import platform
import socket
import sys
import time
import warnings

import numpy as np
import pandas as pd

warnings.simplefilter("ignore")


def versions():
    out = {}
    for m in ("uchrom", "chromdata", "numpy", "pandas", "scipy", "torch", "zarr", "pyarrow"):
        try:
            out[m] = __import__(m).__version__
        except Exception:
            out[m] = None
    return out


def compare(ref: pd.DataFrame, got: pd.DataFrame) -> dict:
    r = {"n_in_memory": int(len(ref)), "n_streaming": int(len(got)), "columns": list(map(str, ref.columns)),
         "same_columns": list(ref.columns) == list(got.columns)}
    keys = [c for c in ref.columns if c not in ("score", "pval", "fdr", "contact_freq")]
    r["same_calls"] = bool(len(ref) == len(got) and r["same_columns"]
                           and ref[keys].reset_index(drop=True).equals(got[keys].reset_index(drop=True)))
    if len(ref) == len(got) and r["same_columns"]:
        a_, b_ = ref.reset_index(drop=True), got.reset_index(drop=True)
        r["identical"] = bool(a_.equals(b_))
        nonfloat = [c for c in a_.columns if not pd.api.types.is_float_dtype(a_[c])]
        r["nonfloat_columns"] = list(map(str, nonfloat))
        r["same_nonfloat"] = bool(a_[nonfloat].equals(b_[nonfloat]))   # positions, levels, summits, sizes
        fl = {}
        for c in a_.columns:
            if pd.api.types.is_float_dtype(a_[c]):
                a, b = a_[c].to_numpy(float), b_[c].to_numpy(float)
                both_nan = np.isnan(a) & np.isnan(b)
                d = np.where(both_nan, 0.0, np.abs(a - b))
                rel = d / np.maximum(np.abs(a), 1e-300)
                fl[str(c)] = {"max_abs_diff": float(np.nanmax(d)) if len(d) else 0.0,
                              "max_rel_diff": float(np.nanmax(rel)) if len(rel) else 0.0,
                              "nan_mismatch": int((np.isnan(a) != np.isnan(b)).sum())}
        r["float_columns"] = fl
        if "pval" in a_.columns and len(a_):
            p0, p1 = a_["pval"].to_numpy(float), b_["pval"].to_numpy(float)
            r["max_rel_pval_diff"] = float(np.nanmax(np.abs(p1 - p0) / np.maximum(p0, 1e-300)))
    return r


def main(core: str, out: str) -> None:
    from uchrom import ChromData
    from uchrom.strc.loop import call_loops_axiswise_f
    from uchrom.strc.tad import call_tads_by_pval

    t0 = time.perf_counter()
    cd = ChromData.from_fofct(core)
    res = {"n_spots": int(cd.n_spots), "n_traces": int(cd.n_traces), "chroms": list(cd.chroms),
           "read_s": time.perf_counter() - t0}
    for name, fn in (("loops", call_loops_axiswise_f), ("tads", call_tads_by_pval)):
        t0 = time.perf_counter()
        ref = fn(cd, device="cpu", key_added=None)
        t1 = time.perf_counter()
        got = fn(cd, streaming=True, key_added=None, memory_budget="256MB")
        t2 = time.perf_counter()
        r = compare(ref, got)
        stem = os.path.splitext(out)[0]
        ref.to_csv(f"{stem}_{name}_in_memory.csv", index=False)
        got.to_csv(f"{stem}_{name}_streaming.csv", index=False)
        r.update({"in_memory_s": t1 - t0, "streaming_s": t2 - t1})
        if name == "tads" and {"chrom", "start", "end"} <= set(ref.columns):
            b = pd.concat([ref[["chrom", "start"]].rename(columns={"start": "pos"}),
                           ref[["chrom", "end"]].rename(columns={"end": "pos"})]).drop_duplicates()
            r["n_boundaries_in_memory"] = int(len(b))
        if len(ref) and "chrom" in ref.columns:
            r["per_chrom_in_memory"] = {str(k): int(v) for k, v in ref["chrom"].astype(str).value_counts().sort_index().items()}
        res[name] = r
        print(name, json.dumps({k: v for k, v in r.items() if k not in ("float_columns", "per_chrom_in_memory", "columns")}), flush=True)
    doc = {"results": {"arcfish_takei2021": res},
           "provenance": {"script": "arcfish_stream_check.py (copy of benchmarks/cd21_streaming_validation.py "
                                    "child_callers, stricter comparison)",
                          "uchrom_revision": os.environ.get("UCHROM_REVISION"), "versions": versions(),
                          "host": socket.gethostname(), "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
                          "cpus": os.environ.get("SLURM_CPUS_PER_TASK"), "python": platform.python_version(),
                          "platform": platform.platform(), "input": core,
                          "input_bytes": os.path.getsize(core),
                          "parameters": {"in_memory": {"device": "cpu"},
                                         "streaming": {"streaming": True, "memory_budget": "256MB"},
                                         "params": "defaults (LoopCallerParams, TADCallerParams)"},
                          "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}
    with open(out, "w") as fh:
        json.dump(doc, fh, indent=1, default=str)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
