"""Unified scoring of real-data ensembles (any method, any resolution, any length unit).

For every ``--models`` file (``.npz``: ``chrom``, ``pos`` [2017 convention], ``coords``):

* **precision** (Stevens 2017 ED Table 2): RMSD of the models to the superposed ensemble
  mean and mean pairwise RMSD, native units and per bead unit (median consecutive-particle
  distance) - ``metrics.precision``;
* **violations** of the contacts the models were built from (``--contacts``; for held-out
  runs the *training* table), binned onto the method's particles: NucDynamics-style
  %V>3 / %V>4 and Si-C-style % contact pairs > 2 bead units - ``metrics.violations``;
* **vs reference** (``--reference``, e.g. the GEO 100 kb models of the cell, read with
  ``models_io.read_nucdyn_pdb`` when it ends in ``.pdb[.gz]``): reference particles
  mapped to the method's particles by genomic midpoint; for every (method model,
  reference model) pair the median over chromosomes of the Pearson r between distance
  matrices, and the RMSD after similarity superposition (mirror allowed) divided by the
  reference's radius of gyration; plus reference-vs-reference (ceiling).

    python benchmarks/screcon/score_real.py --contacts CELL.txt.gz --reference GEO.pdb.gz \\
        --models RUN/nucdyn.npz RUN/sic.npz --labels nucdyn sic --out score.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import ParticleIndex, bin_contacts, contact_pairs, load_models, read_contacts  # noqa: E402
from metrics import precision, superpose, violations  # noqa: E402
from models_io import read_nucdyn_pdb  # noqa: E402


def load_any(path, chroms=None):
    p = str(path)
    if p.endswith((".pdb", ".pdb.gz")):
        return read_nucdyn_pdb(p, chroms)
    return load_models(p)


def _zvecs(models, idx):
    iu = np.triu_indices(len(idx), 1)
    out = []
    for m in models:
        x = m[idx]
        d = np.sqrt(((x[:, None] - x[None]) ** 2).sum(-1))[iu].astype(np.float32)
        out.append((d - d.mean()) / (d.std() + 1e-12))
    return np.stack(out)


def cross_dist_r(A, B, chrom, min_particles: int = 10):
    """Median over chromosomes of Pearson r of distance matrices, for every (a, b) model pair."""
    rs = {}
    for c in np.unique(chrom):
        idx = np.flatnonzero(chrom == c)
        if len(idx) < min_particles:
            continue
        Va, Vb = _zvecs(A, idx), _zvecs(B, idx)
        C = Va @ Vb.T / Va.shape[1]
        for a, b in itertools.product(range(len(A)), range(len(B))):
            rs.setdefault((a, b), []).append(float(C[a, b]))
    return {k: float(np.median(v)) for k, v in rs.items()}


def rg(X):
    return float(np.sqrt(((X - X.mean(0)) ** 2).sum(1).mean()))


def vs_reference(chrom, pos, X, ref):
    rc, rp, R = ref
    size = int(np.median(np.diff(rp)[rc[1:] == rc[:-1]]))
    pidx = ParticleIndex(chrom, pos)(rc, rp - size // 2)
    keep = pidx >= 0
    _, first = np.unique(pidx[keep], return_index=True)       # one reference particle per method particle
    ri = np.flatnonzero(keep)[first]
    mi = pidx[ri]
    Xa, Rb = X[:, mi], R[:, ri]
    ch = rc[ri]
    rr = cross_dist_r(Xa, Rb, ch)
    rm = [superpose(Rb[b], Xa[a], scale=True, mirror=True)[1] / rg(Rb[b])
          for a in range(len(Xa)) for b in range(len(Rb))]
    return {"n_matched": int(len(ri)), "ref_coverage": float(len(ri) / len(rc)),
            "dist_r_median": float(np.median(list(rr.values()))),
            "dist_r_best": float(max(rr.values())),
            "rmsd_rel_median": float(np.median(rm))}


def score_run(chrom, pos, X, contacts, ref=None) -> dict:
    out = {"n_models": int(len(X)), "n_particles": int(X.shape[1])}
    out["precision"] = precision(X, chrom)
    i, j = bin_contacts(contacts, chrom, pos)
    pairs, counts = contact_pairs(i, j, chrom, min_sep=2)
    out["violations"] = violations(chrom, X, pairs, counts)
    out["violations"]["frac_contact_ends_covered"] = float(np.mean((i >= 0) & (j >= 0)))
    if ref is not None:
        out["vs_reference"] = vs_reference(chrom, pos, X, ref)
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contacts", required=True)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--labels", nargs="+")
    ap.add_argument("--reference")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    c = read_contacts(args.contacts)
    ref = load_any(args.reference, c.chroms) if args.reference else None
    labels = args.labels or [Path(m).stem for m in args.models]
    out = {"contacts": args.contacts, "reference": args.reference, "methods": {}}
    if ref is not None:
        rr = cross_dist_r(ref[2], ref[2], ref[0])
        out["reference_self"] = {"dist_r_median_pairs": float(np.median([v for (a, b), v in rr.items() if a < b])),
                                 **score_run(ref[0], ref[1], ref[2], c)}
    for path, lab in zip(args.models, labels):
        if not Path(path).exists():
            print(f"missing {path}")
            continue
        chrom, pos, X = load_any(path, c.chroms)
        r = score_run(chrom, pos, X, c, ref)
        r["models"] = str(path)
        out["methods"][lab] = r
        print(json.dumps({"method": lab, "rmsd_to_mean_per_unit": r["precision"].get("rmsd_to_mean_per_unit"),
                          "nd_v4": r["violations"].get("nd_pct_viol_gt4"),
                          "sic_v2": r["violations"].get("sic_pct_viol_gt2units"),
                          "vs_ref_r": r.get("vs_reference", {}).get("dist_r_median")}), flush=True)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
