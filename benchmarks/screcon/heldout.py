"""Held-out contact test for single-cell Hi-C 3-D structures (method-neutral).

The idea: hide some contacts (reads) of a cell, let every method build models from the
rest, and ask whether the models place the hidden contacts close together.  Nothing
here uses any method's objective; every method is scored on the *same* pairs.

``split``
    Randomly holds out a fraction of the reads (default 10 %; seeded).  ``--folds K``
    gives K disjoint held-out sets (K x frac <= 1; without ``--frac`` a plain K-fold
    partition).  For each fold writes ``train.<ext>`` (the input's own format and header,
    the kept lines byte-identical, so any method consumes it unchanged), ``heldout.<ext>``
    and ``eval_pairs.npz`` - the evaluation pairs, fixed *before* any model exists:

    * genomic grid at ``--eval-res`` (bin k of a chromosome = [k R, (k+1) R)) over the span
      of the cell's contacts;
    * **positives** = bin pairs hit by a held-out read and by no training read; cis pairs
      need |i - j| >= 2 bins (adjacent bins are trivially close in every chain model);
    * **negatives** = bin pairs with no read at all in the full table, ``--n-neg`` (10) per
      positive: cis negatives on the same chromosome at the **same separation**
      |i - j| (fallback: same log2-spaced separation band, factor sqrt 2, when a
      chromosome has too few free pairs at that separation; the fallback rate is
      reported); trans negatives keep one anchor of the positive and take the partner
      from the anchors of the other trans positives (``--trans-match shuffle``, default;
      on another chromosome, never contacted), so both ends of the negatives follow the
      positives' anchor distribution.  Plain random trans pairs (``any``) let a
      structure-free per-bin prior win: in any chain model the middle of a chromosome sits
      closer to the other chromosomes than its ends (on a 3-chromosome toy, random-polymer
      ensembles scored mean trans ROC-AUC 0.57 over 8 seeds with ``any``, 0.51 with
      ``shuffle``).  ``chrom_pair``
      draws random pairs on the positive's chromosome pair.

    Why separation matching: in a single cell the contact probability falls steeply with
    genomic separation s, so an unmatched test mostly rewards "near in sequence = near in
    space", which every chain model (and a random polymer) gets for free.  With exact
    matching, positives and negatives of a stratum share s, so *any* score that is a
    function of s alone (expected distance from a polymer / P(s) prior, a random-walk
    ensemble in expectation) ties or is exchangeable within each stratum and has an
    expected cis ROC-AUC of exactly 0.5.  Only structure beyond P(s) scores above 0.5.
    ``score`` reports this check (``ps_baseline_auc``, score = -s).

``score``
    Maps each method's models (``.npz``: ``chrom``, ``pos`` [2017 convention: particle
    covers (pos - size, pos]], ``coords`` (M, N, 3)) onto the grid by genomic position
    (bin midpoint -> covering particle; a bin without a particle counts as "far": median
    distance +inf, never within the threshold), divides distances by each model's bead
    unit (median consecutive-particle distance) and scores every pair by

    * ``median``: minus the ensemble-median distance (lower distance = contact),
    * ``frac``: fraction of models with distance < ``--threshold`` bead units (2).

    Reports ROC-AUC and PR-AUC (average precision; chance = 1 / (1 + n_neg)) overall, cis,
    trans and per cis separation band, with a bootstrap 95 % CI resampling positives
    together with their matched negatives.

Usage::

    python benchmarks/screcon/heldout.py split --contacts CELL.txt.gz --out SPLIT_DIR \\
        --frac 0.1 --folds 3 --seed 1 --eval-res 100000
    python benchmarks/screcon/heldout.py score --eval SPLIT_DIR/fold1/eval_pairs.npz \\
        --models RUN/nucdyn.npz RUN/sic.npz --labels nucdyn sic --out score.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import Grid, ParticleIndex, load_models, read_contacts, write_contacts  # noqa: E402
from metrics import average_precision, bead_unit, bootstrap_ci, roc_auc  # noqa: E402

REPORT_BANDS = [(2, 4), (4, 16), (16, 64), (64, 256), (256, 10 ** 9)]


def log_band(s):
    """Log-spaced separation band (factor sqrt 2): 2 -> 2, 3 -> 3, 4-5 -> 4, 6-7 -> 5, 8-11 -> 6 ..."""
    return np.floor(2 * np.log2(np.maximum(np.asarray(s, float), 1))).astype(int)


def _pair_keys(i, j, n):
    a, b = np.minimum(i, j), np.maximum(i, j)
    return a.astype(np.int64) * n + b


def _suffix(path: Path) -> str:
    name = path.name
    return ".txt.gz" if name.endswith(".gz") else ".txt"


# --------------------------------------------------------------------------- split

def fold_indices(n: int, frac: float | None, folds: int, seed: int) -> list[np.ndarray]:
    """Disjoint held-out read index sets (sorted)."""
    rng = np.random.default_rng(seed)
    perm = rng.permutation(n)
    if frac is None:
        return [np.sort(x) for x in np.array_split(perm, folds)]
    if frac * folds > 1 + 1e-9:
        raise ValueError("folds x frac must be <= 1 for disjoint held-out sets")
    k = int(round(frac * n))
    return [np.sort(perm[f * k:(f + 1) * k]) for f in range(folds)]


def sample_negatives(grid, pa, pb, same, all_keys, n_neg: int, seed: int, max_tries: int = 50,
                     trans_match: str = "shuffle"):
    """Separation-matched negatives of the positives (pa, pb) (see the module docstring): never-contacted
    bin pairs (not in ``all_keys``), ``n_neg`` per positive.  -> (neg_a, neg_b, neg_group, n band
    fallbacks, n trans fallbacks)."""
    n = grid.n
    rng = np.random.default_rng(seed)
    chrom_of = grid.chrom
    offs = np.array([grid.offset[c] for c in grid.chroms])
    sizes = np.array([grid.nbins[c] for c in grid.chroms])
    cidx = {c: k for k, c in enumerate(grid.chroms)}
    used = set()
    neg_a, neg_b, neg_g, fallback, trans_fallback = [], [], [], 0, 0
    pool = np.concatenate([pa[~same], pb[~same]])          # anchors of the trans positives
    for g, (a, b, cis) in enumerate(zip(pa, pb, same)):
        got = 0
        if cis:
            c = cidx[chrom_of[a]]
            s = int(b - a)
            off, nb = offs[c], sizes[c]
            for _ in range(max_tries * n_neg):
                if got >= n_neg or nb - s <= 0:
                    break
                x = off + int(rng.integers(0, nb - s))
                key = x * n + x + s
                if key in all_keys or key in used:
                    continue
                used.add(key); neg_a.append(x); neg_b.append(x + s); neg_g.append(g); got += 1
            if got < n_neg:                        # fallback: same log band on the same chromosome
                fallback += 1
                band = log_band(s)
                cand_s = np.arange(2, nb)
                cand_s = cand_s[log_band(cand_s) == band]
                for _ in range(max_tries * n_neg):
                    if got >= n_neg or not len(cand_s):
                        break
                    ss = int(rng.choice(cand_s))
                    if nb - ss <= 0:
                        continue
                    x = off + int(rng.integers(0, nb - ss))
                    key = x * n + x + ss
                    if key in all_keys or key in used:
                        continue
                    used.add(key); neg_a.append(x); neg_b.append(x + ss); neg_g.append(g); got += 1
        else:
            mode = trans_match
            for t_ in range(2 * max_tries * n_neg):
                if got >= n_neg:
                    break
                if mode == "shuffle" and t_ >= max_tries * n_neg:
                    mode = "any"                        # fallback
                    trans_fallback += 1
                if mode == "shuffle":                   # keep one anchor, partner from the positives' anchors
                    other = int(pool[rng.integers(0, len(pool))])
                    x, y = (int(a), other) if rng.random() < 0.5 else (other, int(b))
                elif mode == "chrom_pair":              # same chromosome pair as the positive
                    ca, cb = cidx[chrom_of[a]], cidx[chrom_of[b]]
                    x = offs[ca] + int(rng.integers(0, sizes[ca]))
                    y = offs[cb] + int(rng.integers(0, sizes[cb]))
                else:
                    x, y = int(rng.integers(0, n)), int(rng.integers(0, n))
                if chrom_of[x] == chrom_of[y]:
                    continue
                key = min(x, y) * n + max(x, y)
                if key in all_keys or key in used:
                    continue
                used.add(key); neg_a.append(min(x, y)); neg_b.append(max(x, y)); neg_g.append(g); got += 1
    neg_a, neg_b, neg_g = np.array(neg_a, np.int64), np.array(neg_b, np.int64), np.array(neg_g, np.int64)
    return neg_a, neg_b, neg_g, fallback, trans_fallback


def build_eval_pairs(contacts, held_idx, res: int, n_neg: int = 10, seed: int = 0,
                     sep_match: str = "exact", max_tries: int = 50, trans_match: str = "shuffle") -> dict:
    """Positive / separation-matched negative bin pairs for one fold (see module docstring)."""
    grid = Grid.from_contacts(contacts, res)
    gi = grid.index(contacts.chrom_a, contacts.pos_a)
    gj = grid.index(contacts.chrom_b, contacts.pos_b)
    n = grid.n
    ok = (gi >= 0) & (gj >= 0) & (gi != gj)
    held = np.zeros(len(contacts), bool)
    held[held_idx] = True
    all_keys = set(_pair_keys(gi[ok], gj[ok], n).tolist())
    train_keys = set(_pair_keys(gi[ok & ~held], gj[ok & ~held], n).tolist())
    hk = np.unique(_pair_keys(gi[ok & held], gj[ok & held], n))
    pa, pb = hk // n, hk % n
    same = grid.chrom[pa] == grid.chrom[pb]
    keep = np.array([k not in train_keys for k in hk.tolist()], bool) & (~same | (pb - pa >= 2))
    pa, pb, same = pa[keep], pb[keep], same[keep]

    neg_a, neg_b, neg_g, fallback, trans_fallback = sample_negatives(
        grid, pa, pb, same, all_keys, n_neg, seed, max_tries, trans_match)
    chrom_of = grid.chrom
    return {
        "grid": grid, "pos_a": pa, "pos_b": pb, "pos_cis": same,
        "neg_a": neg_a, "neg_b": neg_b, "neg_group": neg_g,
        "neg_cis": chrom_of[neg_a] == chrom_of[neg_b] if len(neg_a) else np.zeros(0, bool),
        "stats": {"n_reads": int(len(contacts)), "n_heldout_reads": int(held.sum()),
                  "n_pos": int(len(pa)), "n_pos_cis": int(same.sum()), "n_pos_trans": int((~same).sum()),
                  "n_neg": int(len(neg_a)), "n_grid_bins": int(n), "eval_res": int(res),
                  "n_neg_per_pos": n_neg, "sep_match": sep_match, "trans_match": trans_match,
                  "n_pos_with_band_fallback": int(fallback), "n_trans_pos_with_fallback": int(trans_fallback),
                  "n_heldout_pairs_already_in_training": int((~np.array([k not in train_keys for k in hk.tolist()], bool)).sum())},
    }


def save_eval(path: Path, ev: dict) -> None:
    g: Grid = ev["grid"]
    np.savez_compressed(path, grid=json.dumps(g.to_dict()), pos_a=ev["pos_a"], pos_b=ev["pos_b"],
                        neg_a=ev["neg_a"], neg_b=ev["neg_b"], neg_group=ev["neg_group"],
                        stats=json.dumps(ev["stats"]))


def load_eval(path) -> dict:
    z = np.load(path, allow_pickle=False)
    grid = Grid.from_dict(json.loads(str(z["grid"])))
    ev = {k: z[k] for k in ("pos_a", "pos_b", "neg_a", "neg_b", "neg_group")}
    ev["grid"] = grid
    ev["stats"] = json.loads(str(z["stats"]))
    return ev


def cmd_split(args) -> None:
    src = Path(args.contacts)
    c = read_contacts(src)
    folds = fold_indices(len(c), args.frac, args.folds, args.seed)
    out = Path(args.out)
    ext = _suffix(src)
    summary = []
    for f, held in enumerate(folds, 1):
        d = out / f"fold{f}"
        d.mkdir(parents=True, exist_ok=True)
        mask = np.zeros(len(c), bool)
        mask[held] = True
        write_contacts(d / f"train{ext}", c, ~mask)
        write_contacts(d / f"heldout{ext}", c, mask)
        ev = build_eval_pairs(c, held, args.eval_res, args.n_neg, seed=args.seed * 1000 + f,
                              trans_match=args.trans_match)
        save_eval(d / "eval_pairs.npz", ev)
        meta = {"fold": f, "input": str(src), "frac": args.frac, "folds": args.folds, "seed": args.seed,
                "n_train": int((~mask).sum()), "n_heldout": int(mask.sum()), **ev["stats"]}
        (d / "split.json").write_text(json.dumps(meta, indent=1))
        summary.append(meta)
        print(json.dumps(meta), flush=True)
    (out / "split_summary.json").write_text(json.dumps(summary, indent=1))


# --------------------------------------------------------------------------- score

def model_pair_distances(ev: dict, chrom, pos, X, size=None):
    """Distances (M, P) in bead units for all evaluation pairs (positives then negatives);
    +inf where a bin has no particle.  Also returns the coverage mask."""
    g: Grid = ev["grid"]
    pidx = ParticleIndex(chrom, pos, size)
    b2p = pidx(g.chrom, g.mid)
    a = np.concatenate([ev["pos_a"], ev["neg_a"]])
    b = np.concatenate([ev["pos_b"], ev["neg_b"]])
    ia, ib = b2p[a], b2p[b]
    cov = (ia >= 0) & (ib >= 0)
    D = np.full((len(X), len(a)), np.inf)
    for m in range(len(X)):
        unit = bead_unit(chrom, X[m])
        D[m, cov] = np.linalg.norm(X[m, ia[cov]] - X[m, ib[cov]], axis=1) / unit
    return D, cov


def _summ(pos, neg, gpos, gneg, n_boot, seed):
    out = {"n_pos": int(len(pos)), "n_neg": int(len(neg)),
           "roc_auc": roc_auc(pos, neg), "pr_auc": average_precision(pos, neg),
           "pr_auc_chance": float(len(pos) / max(len(pos) + len(neg), 1))}
    if n_boot and len(gpos) > 1:
        out["roc_auc_ci95"] = bootstrap_ci(gpos, gneg, roc_auc, n_boot, seed)
        out["pr_auc_ci95"] = bootstrap_ci(gpos, gneg, average_precision, n_boot, seed)
    return out


def score_models(ev: dict, chrom, pos, X, threshold: float = 2.0, n_boot: int = 1000, seed: int = 0) -> dict:
    g: Grid = ev["grid"]
    D, cov = model_pair_distances(ev, chrom, pos, X)
    npos = len(ev["pos_a"])
    scores = {"median": -np.median(D, axis=0), "frac": (D < threshold).mean(0)}
    a = np.concatenate([ev["pos_a"], ev["neg_a"]])
    b = np.concatenate([ev["pos_b"], ev["neg_b"]])
    cis = g.chrom[a] == g.chrom[b]
    sep = np.where(cis, np.abs(b - a), -1)
    group = np.concatenate([np.arange(npos), ev["neg_group"]])
    ispos = np.arange(len(a)) < npos
    res = {"n_models": int(len(X)), "coverage_pos": float(cov[:npos].mean()) if npos else None,
           "coverage_neg": float(cov[npos:].mean()) if len(cov) > npos else None,
           "threshold_units": threshold}

    def subset_eval(sel, s):
        # groups follow the positives kept by `sel`
        gp_ids = np.unique(group[sel & ispos])
        pos_s, neg_s = s[sel & ispos], s[sel & ~ispos]
        gpos, gneg = [], []
        if n_boot:
            order_pos = {k: [] for k in gp_ids.tolist()}
            order_neg = {k: [] for k in gp_ids.tolist()}
            for k, v, p in zip(group[sel], s[sel], ispos[sel]):
                d = order_pos if p else order_neg
                if k in d:
                    d[k].append(v)
            gpos = [np.array(order_pos[k]) for k in gp_ids.tolist()]
            gneg = [np.array(order_neg[k]) for k in gp_ids.tolist()]
        return _summ(pos_s, neg_s, gpos, gneg, n_boot, seed)

    for name, s in scores.items():
        r = {"all": subset_eval(np.ones(len(a), bool), s),
             "cis": subset_eval(cis, s), "trans": subset_eval(~cis, s)}
        bands = {}
        for lo, hi in REPORT_BANDS:
            sel = cis & (sep >= lo) & (sep < hi)
            if (sel & ispos).sum() >= 5:
                bands[f"{lo}-{hi if hi < 10 ** 9 else 'inf'}"] = subset_eval(sel, s) if n_boot else \
                    _summ(s[sel & ispos], s[sel & ~ispos], [], [], 0, seed)
        r["cis_bands"] = bands
        res[name] = r
    # structure-free check: score = -separation (cis only)
    if (cis & ispos).any():
        res["ps_baseline_cis_auc"] = roc_auc(-sep[cis & ispos], -sep[cis & ~ispos])
    return res


def cmd_score(args) -> None:
    ev = load_eval(args.eval)
    labels = args.labels or [Path(m).stem for m in args.models]
    out = {"eval": str(args.eval), "eval_stats": ev["stats"], "methods": {}}
    for path, lab in zip(args.models, labels):
        if not Path(path).exists():
            print(f"missing {path}", flush=True)
            continue
        chrom, pos, X = load_models(path)
        r = score_models(ev, chrom, pos, X, args.threshold, args.n_boot, args.seed)
        r["models"] = str(path)
        out["methods"][lab] = r
        print(json.dumps({"method": lab, "cis_auc_median": r["median"]["cis"]["roc_auc"],
                          "trans_auc_median": r["median"]["trans"]["roc_auc"],
                          "all_auc_frac": r["frac"]["all"]["roc_auc"], "coverage": r["coverage_pos"],
                          "ps_baseline": r.get("ps_baseline_cis_auc")}), flush=True)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=1))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split")
    s.add_argument("--contacts", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--frac", type=float, default=0.1, help="held-out fraction per fold; 0 = plain K-fold")
    s.add_argument("--folds", type=int, default=1)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--eval-res", type=int, default=100_000)
    s.add_argument("--n-neg", type=int, default=10)
    s.add_argument("--trans-match", default="shuffle", choices=["shuffle", "any", "chrom_pair"],
                   help="trans negatives: anchor-preserving shuffle (default), random trans pairs (any), "
                        "or random pairs on the positive's chromosome pair")
    s.set_defaults(fn=cmd_split)
    c = sub.add_parser("score")
    c.add_argument("--eval", required=True)
    c.add_argument("--models", nargs="+", required=True)
    c.add_argument("--labels", nargs="+")
    c.add_argument("--threshold", type=float, default=2.0, help="contact threshold in bead units")
    c.add_argument("--n-boot", type=int, default=1000)
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("--out")
    c.set_defaults(fn=cmd_score)
    args = ap.parse_args(argv)
    if getattr(args, "frac", None) == 0:
        args.frac = None
    args.fn(args)


if __name__ == "__main__":
    main()
