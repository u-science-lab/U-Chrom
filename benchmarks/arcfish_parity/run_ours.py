"""One dataset of the ArcFISH parity check with U-Chrom: the same FOF-CT input (``inputs.py``) read by
``ChromData.from_fofct``, then ``uchrom.fea.arc`` (in memory and streaming), ``call_tads_by_pval`` /
``arcfish_boundary_stats``, ``arcfish_loop_matrices`` and ``call_compartments_axes_pc``.  Writes
OUT/<name>.ours.npz (+ parquet tables).

    python run_ours.py --manifest IN/manifest.json --name NAME --out OUT
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd


def load(m: dict):
    """The dataset as one in-memory ChromData of its chromosome, coordinates in nm, traces as the authors' loader
    names them (``<key>_<trace>`` for several files)."""
    from chromdata import ChromData

    files = m["files"]
    items = list(files.items()) if isinstance(files, dict) else [(None, files)]
    coords, spots = [], []
    for key, path in items:
        cd = ChromData.from_fofct(path)
        sp = cd.spots_with_loci()
        on = (sp["chrom"].astype(str) == m["chrom"]).to_numpy()
        tid = sp["trace_id"].astype(str).to_numpy()[on]
        spots.append(pd.DataFrame({"chrom": m["chrom"], "start": sp["start"].to_numpy()[on].astype(np.int64),
                                   "end": sp["end"].to_numpy()[on].astype(np.int64),
                                   "trace_id": tid if key is None else np.char.add(f"{key}_", tid.astype(str))}))
        coords.append(np.asarray(cd.coords, dtype=np.float64)[on])
    spots = pd.concat(spots, ignore_index=True)
    xyz = np.concatenate(coords) * (m["nm_ratio"] or 1)
    if m.get("n_traces"):
        keep = pd.unique(spots["trace_id"])[:m["n_traces"]]
        on = spots["trace_id"].isin(keep).to_numpy()
        spots, xyz = spots[on].reset_index(drop=True), xyz[on]
    return ChromData(coords=xyz, spots=spots)


def main():
    from uchrom.fea.arc import axis_variance_cube, filter_normalize
    from uchrom.fea.arc_stream import axis_cube_streaming
    from uchrom.strc.comp import CompartmentCallerParams, call_compartments_axes_pc
    from uchrom.strc.loop.axiswise_f import arcfish_loop_matrices
    from uchrom.strc.tad import TADCallerParams, call_tads_by_pval
    from uchrom.strc.tad.arc_pval import arcfish_boundary_stats

    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    m = json.loads(a.manifest.read_text())[a.name]
    chrom = m["chrom"]
    t0 = time.time()
    cd = load(m)
    cube = filter_normalize(axis_variance_cube(cd, chrom, device="cpu"))
    tt = {"load_normalise": time.time() - t0}
    out = {"starts": np.array([s for s, _ in cube["bin_ids"]]), "ends": np.array([e for _, e in cube["bin_ids"]]),
           "n_traces": np.array(cube["n_traces"]), "weight": cube["axis_weight"]}
    for i, c in enumerate("XYZ"):
        out[f"var_{c}"] = cube["norm_var"][i]
        out[f"count_{c}"] = cube["count"][i]
    t0 = time.time()
    sc = axis_cube_streaming(cd, chrom, streaming=True, memory_budget=2 ** 30)
    tt["streaming_normalise"] = time.time() - t0
    out["stream_weight"] = sc["axis_weight"]
    for i, c in enumerate("XYZ"):
        out[f"stream_var_{c}"] = sc["norm_var"][i]
        out[f"stream_count_{c}"] = sc["count"][i]

    t0 = time.time()
    params = TADCallerParams(window_bp=m["window"])
    st = arcfish_boundary_stats(cd, chrom=chrom, params=params, device="cpu", streaming=False)
    tads = call_tads_by_pval(cd, chrom=chrom, params=params, device="cpu", key_added=None)
    tt["tad"] = time.time() - t0
    for k in ("stat", "stat_prox", "pval", "fdr", "peak", "raw_peak", "fdr_peak"):
        out[f"tad_{k}"] = st[k].to_numpy()
    tads.to_parquet(a.out / f"{a.name}.ours.tads.parquet")

    t0 = time.time()
    ins = m.get("insulation", {"window": m["window"], "prominence": 0.1})
    ip = TADCallerParams(window_bp=ins["window"], method="insulation", prominence=ins["prominence"])
    ist = arcfish_boundary_stats(cd, chrom=chrom, params=ip, device="cpu")
    call_tads_by_pval(cd, chrom=chrom, params=ip, device="cpu", key_added=None).to_parquet(
        a.out / f"{a.name}.ours.ins.parquet")
    out["ins_score"] = ist["insulation"].to_numpy()
    out["ins_peak"] = ist["peak"].to_numpy()
    tt["insulation"] = time.time() - t0

    t0 = time.time()
    from uchrom.strc.loop import LoopCallerParams

    lm = arcfish_loop_matrices(cd, chrom=chrom, device="cpu", streaming=False,
                               params=LoopCallerParams(**m.get("loop", {})))
    tt["loop"] = time.time() - t0
    for k in ("stat", "pval", "fdr", "candidate", "label", "summit", "final", "axis_pval", "freq"):
        out[f"loop_{k}"] = lm[k]

    t0 = time.time()
    try:
        cp = call_compartments_axes_pc(cd, chrom=chrom, params=CompartmentCallerParams(
            min_compartment_bp=m["min_cpmt"]), device="cpu", key_added=None)
        cp.to_parquet(a.out / f"{a.name}.ours.cpmt.parquet")
    except Exception as e:
        out["cpmt_error"] = np.array(repr(e))
    tt["cpmt"] = time.time() - t0
    out["timing"] = np.array(json.dumps(tt))
    np.savez_compressed(a.out / f"{a.name}.ours.npz", **out)
    print(a.name, "ours", tt)


if __name__ == "__main__":
    main()
