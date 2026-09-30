"""Run the population deconvolution on a benchmark input (thin driver; needs U-Chrom + the engine).

Reads a probability matrix ``.npz`` (``forward.py`` / ``real_inputs.py`` /
``uchrom.recon.bulk.deconv.preprocess.ProbabilityMatrix.save``), calls
``uchrom.recon.bulk.deconv.deconvolve(probabilities=<scipy.sparse>, bins=<DataFrame chrom,start,end>,
method="igm", ...)`` and writes its ChromData (cells = structures, traces = chromosome copies).
Extra keyword arguments go through ``--kw key=value`` (JSON values), e.g. the nucleus the
forward model used (``forward.py`` provenance: ``nucleus_radius_nm``, ``occupancy``).

The output is scored by ``score.py score --pop igm=OUT.chromdata.zarr`` (``population.from_chromdata``).
Until the engine branch is merged, ``--dry-run`` only checks the input and prints the call.

    python benchmarks/bulk/run_deconv.py --input SIM/su/bulk_step_inf.npz --n-structures 1000 --seed 1 \\
        --kw nucleus_radius=7516 --out RUNS/su/igm_S1000_seed1.chromdata.zarr
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import jdump, load_preprocess  # noqa: E402


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True)
    ap.add_argument("--method", default="igm")
    ap.add_argument("--n-structures", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--kw", action="append", default=[], help="key=JSON value passed to deconvolve()")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    pm = load_preprocess().ProbabilityMatrix.load(args.input)
    kw = {k: json.loads(v) for k, v in (s.split("=", 1) for s in args.kw)}
    call = {"method": args.method, "n_structures": args.n_structures, "seed": args.seed, "device": args.device, **kw}
    print(f"input {args.input}: {len(pm.bins)} bins, {pm.probabilities.nnz:,} stored probabilities; call {call}", flush=True)
    if args.dry_run:
        return
    from uchrom.recon.bulk.deconv import deconvolve
    t0 = time.time()
    cd = deconvolve(probabilities=pm.probabilities, bins=pm.bins[["chrom", "start", "end"]], **call)
    cd.uns.setdefault("benchmark", {}).update({"input": str(args.input), "input_provenance": pm.provenance,
                                               "seconds": time.time() - t0, "call": call})
    cd.write(args.out)
    print(jdump({"out": args.out, "seconds": time.time() - t0}), flush=True)


if __name__ == "__main__":
    main()
