"""Held-out contact test for diploid (homolog-resolved) structures.

Same idea and rules as ``heldout.py`` (10 % of the reads held out, seeded folds; evaluation pairs
at ``--eval-res`` fixed before any model exists; separation-matched never-contacted negatives,
10 per positive), on the *copy chains* (``diploid.py`` naming, ``chr1(0)`` / ``chr1(1)``):

* every read is expanded to its candidate copy pairs: a phased end on its homolog, an unphased
  end on either copy (single-copy chromosomes — male X / Y, hickit's rule: when chrY is present —
  on the one copy); no same-homolog prior is applied here (method-neutral);
* **positives** = copy-level bin pairs of held-out reads whose copy pair is known from the data
  (both ends phased, or on single-copy chromosomes), hit by no candidate of any training read;
  cis (same copy chain) pairs need |i - j| >= 2 bins; pairs between the two homologs of a
  chromosome count as trans;
* **negatives** = copy-level bin pairs hit by no candidate of any read (``heldout.sample_negatives``:
  same chain and separation for cis, shuffled anchors for trans).

``--cis-same-homolog BP`` (default 0 = off) also counts as resolved the cis reads closer than BP
with exactly one end phased, the other end put on the same homolog (the prior every diploid
method uses — hickit's imputation, Dip-C ``impute -d``); Dip-C GM12878 has 8 % of the ends phased,
so only ~0.7 % of the reads have both ends phased.

So a model scores well only if it puts the held-out contact on the right homolog; scoring is
``heldout.py score`` unchanged (models in the copy-chain convention).  The training table keeps
the input's header and lines byte-identical (hickit's imputed ``phase_prob`` columns, if any,
were computed from all reads — methods must not use them on a split; hickit re-imputes).

    python benchmarks/screcon/diploid_heldout.py split --contacts cell.pairs.gz --out SPLIT --folds 3 --seed 1
    python benchmarks/screcon/heldout.py score --eval SPLIT/fold1/eval_pairs.npz --models RUN/ember.npz ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import Contacts, Grid  # noqa: E402
from diploid import copy_name, read_phased, write_phased_subset  # noqa: E402
from heldout import _pair_keys, fold_indices, sample_negatives, save_eval  # noqa: E402


def ploidy_of(chroms) -> dict:
    """hickit's rule: two copies; X and Y single when a Y chromosome is present."""
    male = any(str(c).upper().endswith("Y") for c in chroms)
    return {c: (1 if male and str(c).upper().endswith(("X", "Y")) else 2) for c in chroms}


def expand(c, ploidy: dict, cis_same: int = 0):
    """Candidate copy-level contacts of every read -> (Contacts, read index, resolved flag).
    ``cis_same`` > 0: a cis read closer than this with one phased end is resolved to that homolog."""
    ca, pa, cb, pb, rd, res = [], [], [], [], [], []
    for k in range(len(c)):
        a, b = c.chrom_a[k], c.chrom_b[k]
        xa, xb = int(c.hap_a[k]), int(c.hap_b[k])
        if cis_same and a == b and ploidy[a] == 2 and abs(int(c.pos_a[k]) - int(c.pos_b[k])) < cis_same and (xa >= 0) != (xb >= 0):
            xa = xb = max(xa, xb)
        ha = [0] if ploidy[a] == 1 else ([xa] if xa >= 0 else [0, 1])
        hb = [0] if ploidy[b] == 1 else ([xb] if xb >= 0 else [0, 1])
        resolved = len(ha) * len(hb) == 1
        for x in ha:
            for y in hb:
                ca.append(copy_name(a, x, ploidy[a])); pa.append(c.pos_a[k])
                cb.append(copy_name(b, y, ploidy[b])); pb.append(c.pos_b[k])
                rd.append(k); res.append(resolved)
    e = Contacts(np.array(ca, dtype=object), np.array(pa, np.int64), np.array(cb, dtype=object), np.array(pb, np.int64))
    return e, np.array(rd, np.int64), np.array(res, bool)


def build_eval_pairs_diploid(c, held_idx, res: int, n_neg: int = 10, seed: int = 0, max_tries: int = 50,
                             trans_match: str = "shuffle", cis_same: int = 0) -> dict:
    ploidy = ploidy_of(c.chroms)
    e, rd, resolved = expand(c, ploidy, cis_same)
    grid = Grid.from_contacts(e, res)
    gi = grid.index(e.chrom_a, e.pos_a)
    gj = grid.index(e.chrom_b, e.pos_b)
    n = grid.n
    ok = (gi >= 0) & (gj >= 0) & (gi != gj)
    held_read = np.zeros(len(c), bool)
    held_read[held_idx] = True
    held = held_read[rd]
    all_keys = set(_pair_keys(gi[ok], gj[ok], n).tolist())
    train_keys = set(_pair_keys(gi[ok & ~held], gj[ok & ~held], n).tolist())
    hk = np.unique(_pair_keys(gi[ok & held & resolved], gj[ok & held & resolved], n))
    pa, pb = hk // n, hk % n
    same = grid.chrom[pa] == grid.chrom[pb]
    in_train = np.array([k in train_keys for k in hk.tolist()], bool)
    keep = ~in_train & (~same | (pb - pa >= 2))
    pa, pb, same = pa[keep], pb[keep], same[keep]
    neg_a, neg_b, neg_g, fallback, trans_fallback = sample_negatives(grid, pa, pb, same, all_keys, n_neg, seed,
                                                                     max_tries, trans_match)
    base = lambda x: np.array([str(s).split("(")[0] for s in x])  # noqa: E731
    homolog = (~same) & (base(grid.chrom[pa]) == base(grid.chrom[pb]))
    hr = held_read
    resolved_read = np.zeros(len(c), bool)
    resolved_read[rd[resolved]] = True
    return {
        "grid": grid, "pos_a": pa, "pos_b": pb, "pos_cis": same, "neg_a": neg_a, "neg_b": neg_b, "neg_group": neg_g,
        "stats": {"n_reads": int(len(c)), "n_heldout_reads": int(hr.sum()),
                  "n_heldout_reads_resolved": int((hr & resolved_read).sum()),
                  "frac_reads_resolved": float(resolved_read.mean()), "ploidy": ploidy,
                  "n_pos": int(len(pa)), "n_pos_cis": int(same.sum()), "n_pos_trans": int((~same).sum()),
                  "n_pos_inter_homolog": int(homolog.sum()), "n_neg": int(len(neg_a)), "n_grid_bins": int(n),
                  "eval_res": int(res), "n_neg_per_pos": n_neg, "sep_match": "exact", "trans_match": trans_match,
                  "n_pos_with_band_fallback": int(fallback), "n_trans_pos_with_fallback": int(trans_fallback),
                  "n_heldout_pairs_already_in_training": int(in_train.sum()),
                  "copy_level": True, "cis_same_homolog_bp": int(cis_same)},
    }


def cmd_split(args) -> None:
    src = Path(args.contacts)
    c = read_phased(src)
    folds = fold_indices(len(c), args.frac, args.folds, args.seed)
    out = Path(args.out)
    # keep the format visible in the name (readers pick .con vs .pairs by suffix)
    name = src.name[:-3] if src.name.endswith(".gz") else src.name
    ext = (".con" if name.endswith((".con", ".con.txt")) else ".pairs") + (".gz" if src.name.endswith(".gz") else "")
    summary = []
    for f, held in enumerate(folds, 1):
        d = out / f"fold{f}"
        d.mkdir(parents=True, exist_ok=True)
        mask = np.zeros(len(c), bool)
        mask[held] = True
        write_phased_subset(d / f"train{ext}", c, ~mask)
        write_phased_subset(d / f"heldout{ext}", c, mask)
        # strict (both ends phased) -> eval_pairs.npz; with --cis-same-homolog also eval_pairs_cis.npz
        for name, cs in [("eval_pairs", 0)] + ([("eval_pairs_cis", args.cis_same_homolog)] if args.cis_same_homolog else []):
            ev = build_eval_pairs_diploid(c, held, args.eval_res, args.n_neg, seed=args.seed * 1000 + f, cis_same=cs)
            save_eval(d / f"{name}.npz", ev)
            meta = {"fold": f, "input": str(src), "frac": args.frac, "folds": args.folds, "seed": args.seed,
                    "eval": name, "n_train": int((~mask).sum()), "n_heldout": int(mask.sum()), **ev["stats"]}
            (d / f"split_{name}.json").write_text(json.dumps(meta, indent=1))
            summary.append(meta)
            print(json.dumps({k: v for k, v in meta.items() if k != "ploidy"}), flush=True)
    (out / "split_summary.json").write_text(json.dumps(summary, indent=1))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split")
    s.add_argument("--contacts", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--frac", type=float, default=0.1)
    s.add_argument("--folds", type=int, default=3)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--eval-res", type=int, default=100_000)
    s.add_argument("--n-neg", type=int, default=10)
    s.add_argument("--cis-same-homolog", type=int, default=0, help="bp; see the module docstring")
    s.set_defaults(fn=cmd_split)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
