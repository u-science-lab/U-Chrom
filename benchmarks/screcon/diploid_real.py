"""Real diploid data (Dip-C GM12878, Tan et al. 2018): reference structures, phase hold-back, scores.

Subcommands
-----------
``ref``     Published structures -> ``.npz`` copy chains (``diploid.py`` convention) on a regular grid
            (``--res``; a grid bin takes the bead covering its midpoint, ``models_io.resample_3dg``,
            clipped to the span of the input contacts): Dip-C ``impute3.round4.clean.3dg``
            (``1(pat)`` / ``1(mat)`` -> ``1(0)`` / ``1(1)``; hap 0 = paternal) and hickit 3dg
            (``1a`` / ``1b`` -> ``1(0)`` / ``1(1)``).  Several files = several models.

``mask``    Phase hold-back (hickit ``--val-*`` idea): the phase of a random ``--frac`` (10 %) of the
            phased ends of a phased table is removed (``.``); writes the masked table (header and the
            other lines unchanged, so hickit's ``phase_prob`` columns are dropped) and
            ``<out>.mask.npz`` (rows, end, true haplotype).  Every method runs on the masked table;
            ``score --mask`` reports the accuracy of the phases it infers for the masked ends.

``score``   Per method (``.npz`` models in the copy-chain convention):
            * vs each reference: distance-matrix r per copy chain (median over chains and model x
              reference pairs, ``score_real.vs_reference``) and over a random sample of all particle
              pairs (whole genome, homologs and trans included: ``whole_r``);
            * precision (ensemble RMSD to the superposed mean, bead units);
            * ``--mask``: accuracy of the most probable haplotype of every masked end
              (``phase_probs``; hickit: its 2-D imputation), overall / cis < 10 Mb / cis >= 10 Mb /
              trans, and the fraction assigned with probability >= 0.75.

    python benchmarks/screcon/diploid_real.py ref --res 100000 --contacts cell.pairs.gz --out REF/dipc.npz FILES...
    python benchmarks/screcon/diploid_real.py mask --contacts cell.pairs.gz --frac 0.1 --seed 1 --out MASK/cell.pairs.gz
    python benchmarks/screcon/diploid_real.py score --refs REF/dipc.npz REF/hickit.npz --models RUN/*.npz --out S.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import ParticleIndex, load_models  # noqa: E402
from diploid import copy_name, read_phased, save_models  # noqa: E402
from metrics import precision  # noqa: E402
from models_io import read_3dg, resample_3dg  # noqa: E402
from score_real import vs_reference  # noqa: E402

DIPC_HAP = {"pat": 0, "mat": 1}


def ref_copy(name: str, ploidy: dict) -> str:
    """Dip-C ``1(mat)`` / hickit ``1b`` -> copy-chain name."""
    if name.endswith(")") and "(" in name:
        base, h = name[:-1].split("(")
        return copy_name(base, DIPC_HAP.get(h, h if h.isdigit() else 0), ploidy.get(base, 2))
    if ploidy.get(name) == 1:
        return name
    if name[-1] in "ab" and name[:-1] in ploidy:
        return copy_name(name[:-1], "ab".index(name[-1]), ploidy[name[:-1]])
    return name


def cmd_ref(args) -> None:
    c = read_phased(args.contacts)
    male = any(x.upper().endswith("Y") for x in c.chroms)
    ploidy = {x: (1 if male and x.upper().endswith(("X", "Y")) else 2) for x in c.chroms}
    spans = {}
    for g in c.chroms:
        p = np.concatenate([c.pos_a[c.chrom_a == g], c.pos_b[c.chrom_b == g]])
        for h in range(ploidy[g]):
            spans[copy_name(g, h, ploidy[g])] = (int(p.min()), int(p.max()))
    sets = []
    for f in args.files:
        ch, st, xyz = read_3dg(f)
        ch = np.array([ref_copy(x, ploidy) for x in ch])
        sets.append(resample_3dg(ch, st, xyz, args.res, spans))
    from models_io import common_particles
    sets = common_particles(sets)
    save_models(args.out, sets[0][0], sets[0][1], np.stack([s[2] for s in sets]))
    Path(str(args.out) + ".json").write_text(json.dumps({"files": args.files, "res": args.res,
                                                         "n_particles": int(len(sets[0][0])), "ploidy": ploidy}, indent=1))
    print(args.out, len(sets[0][0]), "particles", len(sets), "models", flush=True)


def cmd_mask(args) -> None:
    c = read_phased(args.contacts)
    rng = np.random.default_rng(args.seed)
    rows_a = np.flatnonzero(c.hap_a >= 0)
    rows_b = np.flatnonzero(c.hap_b >= 0)
    ends = np.concatenate([np.stack([rows_a, np.zeros_like(rows_a)], 1), np.stack([rows_b, np.ones_like(rows_b)], 1)])
    pick = ends[np.sort(rng.choice(len(ends), int(round(args.frac * len(ends))), replace=False))]
    true = np.where(pick[:, 1] == 0, c.hap_a[pick[:, 0]], c.hap_b[pick[:, 0]])
    masked = {(int(r), int(e)) for r, e in pick}
    # rewrite: header without the phase_prob columns (computed from the unmasked phases)
    cols = None
    for h in c.header:
        if h.startswith("#columns:"):
            cols = h.split()[1:]
    i0, i1 = cols.index("phase0"), cols.index("phase1")
    keep = [k for k, x in enumerate(cols) if not x.startswith("phase_prob")]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out, "wt") as fh:
        for h in c.header:
            fh.write(("#columns: " + " ".join(cols[k] for k in keep)) if h.startswith("#columns:") else h)
            fh.write("\n")
        for r, line in enumerate(c.lines):
            f = line.split("\t")
            if (r, 0) in masked:
                f[i0] = "."
            if (r, 1) in masked:
                f[i1] = "."
            fh.write("\t".join(f[k] for k in keep) + "\n")
    np.savez_compressed(str(args.out) + ".mask.npz", row=pick[:, 0], end=pick[:, 1], true_hap=true)
    print(json.dumps({"n_contacts": len(c), "n_phased_ends": int(len(ends)), "n_masked": int(len(pick))}), flush=True)


def whole_r(A, B, n_pairs: int = 2_000_000, seed: int = 0) -> float:
    """Pearson r of distances over random particle pairs (all chains), median over (a, b) model pairs."""
    rng = np.random.default_rng(seed)
    n = A.shape[1]
    i, j = rng.integers(0, n, n_pairs), rng.integers(0, n, n_pairs)
    ok = i != j
    i, j = i[ok], j[ok]
    rs = []
    for a in range(len(A)):
        da = np.linalg.norm(A[a, i] - A[a, j], axis=1)
        for b in range(len(B)):
            db = np.linalg.norm(B[b, i] - B[b, j], axis=1)
            rs.append(float(np.corrcoef(da, db)[0, 1]))
    return float(np.median(rs))


def phase_mask_metrics(table, mask_npz, probs) -> dict:
    c = read_phased(table)
    z = np.load(mask_npz)
    rows, end, true = z["row"], z["end"], z["true_hap"]
    p = probs[rows]
    ok = np.isfinite(p).all(1)
    best = np.argmax(np.nan_to_num(p, nan=-1), 1)
    hap = np.where(end == 0, best >> 1, best & 1)
    # marginal probability of the inferred haplotype of the masked end
    pm = np.where(end == 0, np.where(hap == 0, p[:, 0] + p[:, 1], p[:, 2] + p[:, 3]),
                  np.where(hap == 0, p[:, 0] + p[:, 2], p[:, 1] + p[:, 3]))
    cis = c.chrom_a[rows] == c.chrom_b[rows]
    sep = np.abs(c.pos_a[rows] - c.pos_b[rows])
    out = {"n_masked": int(len(rows)), "assigned_frac": float(ok.mean())}
    for name, sel in {"all": np.ones(len(rows), bool), "cis_lt10mb": cis & (sep < 10_000_000),
                      "cis_ge10mb": cis & (sep >= 10_000_000), "trans": ~cis}.items():
        s = sel & ok
        out[f"acc_{name}"] = float((hap[s] == true[s]).mean()) if s.any() else None
        out[f"n_{name}"] = int(s.sum())
        conf = s & (pm >= 0.75)
        out[f"acc_conf_{name}"] = float((hap[conf] == true[conf]).mean()) if conf.any() else None
        out[f"conf_frac_{name}"] = float(conf.sum() / max(s.sum(), 1))
    return out


def cmd_score(args) -> None:
    refs = {Path(r).stem: load_models(r) for r in args.refs}
    out = {"refs": args.refs, "methods": {}, "refs_vs_refs": {}}
    names = list(refs)
    for a in range(len(names)):                                   # published vs published (ceilings)
        for b in range(a + 1, len(names)):
            ca, pa, XA = refs[names[a]]
            r = vs_reference(ca, pa, XA, refs[names[b]])
            out["refs_vs_refs"][f"{names[a]}~{names[b]}"] = r
        out["refs_vs_refs"][f"{names[a]}.precision"] = precision(refs[names[a]][2], refs[names[a]][0])
    for path, lab in zip(args.models, args.labels or [Path(m).stem for m in args.models]):
        if not Path(path).exists():
            print(f"missing {path}")
            continue
        chrom, pos, X = load_models(path)
        r = {"precision": precision(X, chrom), "vs": {}}
        for rn, (rc, rp, R) in refs.items():
            v = vs_reference(chrom, pos, X, (rc, rp, R))
            # whole genome: matched particles as vs_reference
            size = int(np.median(np.diff(rp)[rc[1:] == rc[:-1]]))
            pidx = ParticleIndex(chrom, pos)(rc, rp - size // 2)
            keep = pidx >= 0
            _, first = np.unique(pidx[keep], return_index=True)
            ri = np.flatnonzero(keep)[first]
            v["whole_r"] = whole_r(X[:, pidx[ri]], R[:, ri])
            r["vs"][rn] = v
        z = np.load(path, allow_pickle=False)
        if args.mask and "phase_probs" in z.files:
            r["phase_holdback"] = phase_mask_metrics(args.table, args.mask, z["phase_probs"])
        out["methods"][lab] = r
        print(json.dumps({"method": lab, **{f"{rn}.r_cis": round(v["dist_r_median"], 3) for rn, v in r["vs"].items()},
                          **{f"{rn}.r_whole": round(v["whole_r"], 3) for rn, v in r["vs"].items()},
                          "precision_units": r["precision"].get("rmsd_to_mean_per_unit"),
                          "phase_acc": r.get("phase_holdback", {}).get("acc_all")}), flush=True)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=1, default=float))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("ref")
    s.add_argument("--contacts", required=True)
    s.add_argument("--res", type=int, default=100_000)
    s.add_argument("--out", required=True)
    s.add_argument("files", nargs="+")
    s.set_defaults(fn=cmd_ref)
    m = sub.add_parser("mask")
    m.add_argument("--contacts", required=True)
    m.add_argument("--frac", type=float, default=0.1)
    m.add_argument("--seed", type=int, default=1)
    m.add_argument("--out", required=True)
    m.set_defaults(fn=cmd_mask)
    c = sub.add_parser("score")
    c.add_argument("--refs", nargs="+", required=True)
    c.add_argument("--models", nargs="+", required=True)
    c.add_argument("--labels", nargs="*")
    c.add_argument("--table", help="masked table (with --mask)")
    c.add_argument("--mask", help="<masked table>.mask.npz")
    c.add_argument("--out")
    c.set_defaults(fn=cmd_score)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
