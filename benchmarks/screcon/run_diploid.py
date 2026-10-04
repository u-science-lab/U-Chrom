"""Diploid reconstruction with the native engine on a phased contact table.

Methods (``--method``):

* ``ember``: EMber (protocol ``robust``) with its frozen haploid parameters (``run_robust.ROBUST_DEFAULTS``
  = engine defaults) and the diploid extension (``native/nucdyn/src/diploid.rs``); diploid-only
  parameters via ``--params`` (e.g. ``{"robust_dip_split": false}``).
* ``nucdyn``: the NucDynamics 2017 protocol with diploid ambiguous restraints (combined
  distance of the candidate copy pairs).

Input: hickit ``.pairs[.gz]`` with ``phase0`` / ``phase1`` (optionally ``phase_prob00..11``,
used as EMber's candidate prior only with ``--phase-prior``) or Dip-C ``.con``.  Same
particle schedule as ``run_nucdyn.py`` (8, 4, 2, 0.4, 0.2, 0.1 Mb truncated above ``--res``).

Output ``.npz`` (``diploid.py`` convention: copy chains ``chr1(0)`` / ``chr1(1)``, single-copy
chromosomes plain): ``chrom``, ``pos`` (2017 convention, particle end), ``coords`` (M, N, 3),
``phase_probs`` (input rows x 4: P(hap_a, hap_b | true); NaN = filtered), ``contact_weights``
(EMber: P(true)); ``<out>.json`` with timings, stages, EM log, parameters::

    python benchmarks/screcon/run_diploid.py --method ember --contacts cell.pairs.gz --res 100000 \\
        --device gpu --n-models 10 --seed 1 --out RUN/ember.npz
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diploid import copy_name, save_models  # noqa: E402
from run_nucdyn import peak_rss_mb, schedule  # noqa: E402
from run_robust import ROBUST_DEFAULTS  # noqa: E402


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--method", required=True, choices=["ember", "nucdyn"])
    ap.add_argument("--contacts", required=True)
    ap.add_argument("--res", type=float, default=1e5)
    ap.add_argument("--sizes", help="explicit schedule, Mb, comma separated (overrides --res)")
    ap.add_argument("--device", default="gpu", choices=["cpu", "gpu"])
    ap.add_argument("--n-models", type=int, default=10)
    ap.add_argument("--n-threads", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--ploidy", default="auto", help='"auto" (male when chrY present), "diploid", "male" or JSON {chrom: copies}')
    ap.add_argument("--phase-prior", action="store_true", help="EMber: hickit phase_prob00..11 as the candidate prior")
    ap.add_argument("--hickit-prior", help="EMber: run this hickit binary's 2-D phase imputation (-u) on the table and\n"
                    "use its probabilities as the candidate prior (rows hickit drops: uniform)")
    ap.add_argument("--params", default="{}", help="JSON of engine parameters")
    ap.add_argument("--label", default=None)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    import uchrom_nucdyn as un

    proto = "robust" if args.method == "ember" else "nuc_dynamics_2017"
    params = {**(ROBUST_DEFAULTS if proto == "robust" else {}), **json.loads(args.params)}
    sizes = [float(x) * 1e6 for x in args.sizes.split(",")] if args.sizes else schedule(args.res)
    ploidy = json.loads(args.ploidy) if args.ploidy.startswith("{") else args.ploidy
    tr = time.time()
    c = un.read_phased_contacts(args.contacts)
    read_seconds = time.time() - tr
    prior = c.get("phase_prob") if args.phase_prior else None
    if args.hickit_prior:
        import subprocess
        import tempfile
        from diploid import read_phased
        from run_hickit import map_imputed
        with tempfile.TemporaryDirectory() as tmp:
            imp = Path(tmp) / "impute.pairs"
            with open(imp, "w") as fh:
                subprocess.run([args.hickit_prior, "-i", args.contacts, "-u", "-o", "-"], stdout=fh, check=True,
                               stderr=subprocess.DEVNULL)
            prior = map_imputed(read_phased(args.contacts), str(imp))
        prior = np.where(np.isfinite(prior), prior, 0.0)
    t0 = time.time()
    res = un.calc_genome_structure(
        c["chrom_a"].astype(str), c["pos_a"], c["chrom_b"].astype(str), c["pos_b"], protocol=proto,
        hap_a=c["hap_a"], hap_b=c["hap_b"], ploidy=ploidy,
        phase_prior=prior,
        particle_sizes=sizes, n_models=args.n_models, seed=args.seed, device=args.device,
        n_threads=args.n_threads, verbose=True, **params)
    wall = time.time() - t0
    k = res["ploidy"]
    chrom = np.array([copy_name(ch, h, k[ch]) for ch, h in zip(res["chrom"].astype(str), res["copy"])])
    save_models(args.out, chrom, res["position"], res["coords"], phase_probs=res["phase_probs"],
                contact_weights=res["contact_weights"])
    pp = res["phase_probs"]
    ok = np.isfinite(pp).all(1)
    ha, hb = c["hap_a"], c["hap_b"]
    meta = {"method": args.label or args.method, "protocol": proto, "contacts": str(args.contacts), "n_contacts": int(len(ha)),
            "particle_sizes": sizes, "n_models": args.n_models, "seed": args.seed, "device": args.device,
            "params_given": params, "phase_prior": "hickit -u" if args.hickit_prior else bool(prior is not None), "ploidy": k,
            "frac_ends_phased": float(((ha >= 0).sum() + (hb >= 0).sum()) / max(2 * len(ha), 1)),
            "contacts_kept": int(ok.sum()),
            "read_seconds": read_seconds, "wall_seconds": wall, "engine_seconds": res["seconds_total"],
            "peak_rss_mb": peak_rss_mb(), "stages": res["stages"], "params": res["params"],
            "engine_version": un.__version__, "gpu": un.gpu_info() if args.device == "gpu" else None,
            "slurm_job_id": os.environ.get("SLURM_JOB_ID")}
    Path(str(args.out) + ".json").write_text(json.dumps(meta, indent=1, default=str))
    print(f"{args.contacts}: {args.method} {res['coords'].shape} in {wall:.1f} s", flush=True)


if __name__ == "__main__":
    main()
