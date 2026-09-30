"""Run the consensus reconstruction on one real Hi-C input (the method under test).

    python benchmarks/bulk/consensus/run.py --cell imr90 --resolution 250000 \
        --n-runs 16 --seed 1 --device gpu --out RUNS/consensus/models/imr90_250kb_s1

Writes ``<out>.chromdata.zarr`` (the ChromData: consensus coords, layers run_k /
mean_refined, bin_tracks spread), ``<out>.npz`` (bins + consensus coords, the scoring
format; also ``<out>.mean_refined.npz``) and ``<out>.json`` (timings, peak RSS, alpha / nu
/ decay fit, stage restraint counts, per-run statistics, run-to-run precision).
``--chroms`` restricts the model (default: the whole genome minus Y / M / unplaced);
``--set key=value`` overrides any ``ConsensusParams`` field (JSON values).
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np

import _bc
from _bc import hic_source, peak_rss_gb, save_model_npz, write_json


def parse_sets(items):
    out = {}
    for s in items or []:
        k, v = s.split("=", 1)
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cell", choices=sorted(_bc.CELLS), help="Hi-C source (local 4DN mcool on Sherlock, else URL)")
    ap.add_argument("--source", default=None, help="explicit .cool / .mcool path or URL (overrides --cell)")
    ap.add_argument("--resolution", type=int, required=True)
    ap.add_argument("--chroms", nargs="*", default=None)
    ap.add_argument("--n-runs", type=int, default=16)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--set", nargs="*", default=[], help="ConsensusParams overrides key=value")
    ap.add_argument("--no-zarr", action="store_true", help="skip the ChromData store (scaling runs)")
    ap.add_argument("--out", required=True, help="output prefix")
    a = ap.parse_args(argv)
    from uchrom.recon.bulk.consensus import ConsensusParams, reconstruct_consensus

    src = a.source or hic_source(a.cell)
    over = parse_sets(a.set)
    p = ConsensusParams(n_threads=a.threads, verbose=True).replace(**over)
    t0 = time.time()
    cd = reconstruct_consensus(src, resolution=a.resolution, chrom=a.chroms or None, params=p,
                               n_runs=a.n_runs, seed=a.seed, device=a.device)
    wall = time.time() - t0
    u = cd.uns["consensus"]
    bins = cd.bins[["chrom", "start", "end"]].reset_index(drop=True)
    coords = np.full((len(bins), 3), np.nan)
    import pandas as pd
    pos = pd.Index(cd.bins.index).get_indexer(cd.spots["bin_id"].to_numpy())
    coords[pos] = cd.coords
    meta = {k: v for k, v in u.items() if k not in ("stages", "stage_coords", "stage_beads", "params")}
    save_model_npz(a.out + ".npz", bins, coords, {"model": "consensus", **meta})
    if "mean_refined" in cd.layers:
        c2 = np.full((len(bins), 3), np.nan)
        c2[pos] = cd.layers["mean_refined"]
        save_model_npz(a.out + ".mean_refined.npz", bins, c2, {"model": "consensus_mean_refined", **meta})
    if not a.no_zarr:
        cd.write(a.out + ".chromdata.zarr")
    stages = [{k: v for k, v in s.items() if k not in ("runs", "balance")} |
              {"violated_fraction_mean": float(np.mean([r["n_violated"] / max(r["n_restraints"], 1) for r in s["runs"]])),
               "energy_mean": float(np.mean([r["energy"] for r in s["runs"]]))} for s in u["stages"]]
    summary = {"cell": a.cell, "source": src, "resolution": a.resolution, "chroms": u["chroms"],
               "n_chroms": len(u["chroms"]), "n_beads": int(len(cd.spots)), "n_runs": a.n_runs, "seed": a.seed,
               "device": u["device"], "gpu": u["gpu"], "threads": a.threads, "overrides": over,
               "alpha": u["alpha"], "nu": u["nu"], "decay_fit": u["decay_fit"], "precision": u["precision"],
               "seconds_prepare": u["seconds_prepare"], "seconds_engine": u["seconds_engine"], "seconds_wall": wall,
               "peak_rss_gb": peak_rss_gb(), "stages": stages,
               "runs": cd.results["consensus.anneal"].to_dict(orient="records"), "params": u["params"]}
    write_json(a.out + ".json", summary)
    print(f"done: {summary['n_beads']} beads, {len(u['chroms'])} chromosomes, engine {u['seconds_engine']:.1f} s, "
          f"wall {wall:.1f} s, peak RSS {summary['peak_rss_gb']:.1f} GB, precision {u['precision']}")


if __name__ == "__main__":
    main()
