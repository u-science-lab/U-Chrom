"""One dataset of the ArcFISH parity check with the authors' package (github.com/hyuyu104/ArcFISH, a21d889), as
their tutorials call it: ``FOF_CT_Loader`` → ``create_adata`` → ``filter_normalize``, ``TADCaller``,
``LoopCaller``, ``ABCaller``.  Writes OUT/<name>.upstream.npz (+ CSV tables: the authors' environment has no working parquet engine).

    PYTHONPATH=<ArcFISH source> python run_upstream.py --manifest IN/manifest.json --name NAME --out OUT
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np


def main():
    import arcfish as af
    from arcfish.utils.eval import axis_weight

    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    m = json.loads(a.manifest.read_text())[a.name]
    t0 = time.time()
    loader = af.pp.FOF_CT_Loader(m["files"], nm_ratio=None if m["nm_ratio"] is None
                                 else {c: m["nm_ratio"] for c in "XYZ"})
    adata = loader.create_adata(m["chrom"])
    if m.get("n_traces"):
        adata = adata[:m["n_traces"], :].copy()
    af.pp.filter_normalize(adata)
    tt = {"load_normalise": time.time() - t0}
    out = {"starts": adata.var["Chrom_Start"].to_numpy(), "ends": adata.var["Chrom_End"].to_numpy(),
           "n_traces": np.array(adata.n_obs), "weight": axis_weight(adata, inplace=False)}
    for c in "XYZ":
        out[f"var_{c}"] = adata.varp[f"var_{c}"]
        out[f"count_{c}"] = adata.varp[f"count_{c}"]
        out[f"raw_var_{c}"] = adata.varp[f"raw_var_{c}"]

    t0 = time.time()
    tc = af.tl.TADCaller(window=m["window"])
    tad = tc.call_tads(adata)
    bedpe = tc.to_bedpe(tad)
    tt["tad"] = time.time() - t0
    for k in ("stat", "stat_prox", "pval", "fdr", "peak", "raw_peak", "fdr_peak"):
        out[f"tad_{k}"] = tad[k].to_numpy()
    bedpe.to_csv(a.out / f"{a.name}.upstream.tads.csv", index=False)

    t0 = time.time()
    ins = m.get("insulation", {"window": m["window"], "prominence": 0.1})
    ic = af.tl.TADCaller(window=ins["window"], method="insulation", prominence=ins["prominence"])
    ir = ic.call_tads(adata)
    ic.to_bedpe(ir).to_csv(a.out / f"{a.name}.upstream.ins.csv", index=False)
    out["ins_score"] = ir["insulation"].to_numpy()
    out["ins_peak"] = ir["peak"].to_numpy()
    tt["insulation"] = time.time() - t0

    t0 = time.time()
    lc = af.tl.LoopCaller(**m.get("loop", {}))
    lr = lc.call_loops(adata)
    tt["loop"] = time.time() - t0
    for k in ("stat", "pval", "fdr", "candidate", "label", "summit", "final", "axis_pval"):
        out[f"loop_{k}"] = lr[k]

    t0 = time.time()
    try:
        cp = af.tl.ABCaller(min_cpmt_size=m["min_cpmt"]).call_cpmt(adata)
        cp.to_csv(a.out / f"{a.name}.upstream.cpmt.csv", index=False)
    except Exception as e:                      # recorded, compared as a failure
        out["cpmt_error"] = np.array(repr(e))
    tt["cpmt"] = time.time() - t0
    out["timing"] = np.array(json.dumps(tt))
    np.savez_compressed(a.out / f"{a.name}.upstream.npz", **out)
    print(a.name, "upstream", tt)


if __name__ == "__main__":
    main()
