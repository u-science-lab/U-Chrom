"""Development diagnostics of the ``robust`` method on simulated tables (dev set only).

The simulated reads are regenerated from the truth with the table's own settings (seeded, so
byte-identical: checked) to recover which reads are noise (``is_noise``, not stored in the
table).  Reports how well the method's final contact weights, and the models' distances,
separate noise from signal reads:

    python benchmarks/screcon/robust_diag.py --table SIM/reads/.../truth_1_d160_rc1_e0.2_s1.txt.gz \\
        --truth SIM/truth/su2020_chr21/truth_1.npz --models RUN/robust.npz [RUN/nucdyn_gpu.npz ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import ParticleIndex, load_models, read_contacts  # noqa: E402
from metrics import roc_auc  # noqa: E402
from simulate import kernel  # noqa: E402
from truth import interpolate_missing, load_truth  # noqa: E402


def noise_flags(t: dict, info: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Re-run ``simulate.simulate_reads`` (fixed-depth branch) -> (is_noise, pos_a, pos_b)."""
    rng = np.random.default_rng(info["seed"])
    chrom, start, end = t["chrom"], t["start"], t["end"]
    X = np.asarray(t["coords"], float)
    filled, measured = interpolate_missing(chrom, start, X)
    usable = np.ones(len(chrom), bool) if info["missing"] == "interp" else measured
    rc = info["rc_nm"]
    L = len(chrom)
    iu = np.triu_indices(L, 1)
    ok = usable[iu[0]] & usable[iu[1]]
    ia, ib = iu[0][ok], iu[1][ok]
    d = np.linalg.norm(filled[ia] - filled[ib], axis=1)
    p = info["q"] * kernel(d, rc, info["kernel"])
    reads = info["reads_requested"]
    n_noise = int(rng.binomial(reads, info["eps"]))
    n_sig = reads - n_noise
    cnt = rng.multinomial(n_sig, p / p.sum())
    noise = rng.integers(0, len(ia), n_noise)
    pair = np.concatenate([np.repeat(np.arange(len(ia)), cnt), noise])
    is_noise = np.concatenate([np.zeros(int(cnt.sum()), bool), np.ones(n_noise, bool)])
    order = rng.permutation(len(pair))
    pair, is_noise = pair[order], is_noise[order]
    A, B = ia[pair], ib[pair]

    def draw(k):
        lo, hi = start[k] + 1, end[k] - 1
        return lo + (rng.random(len(k)) * (hi - lo + 1)).astype(np.int64)

    pa, pb = draw(A), draw(B)
    # noise reads that happen to land on truly close pairs are not "wrong": distance in rc units
    dtrue = np.linalg.norm(filled[A] - filled[B], axis=1) / rc
    return is_noise, pa, pb, dtrue


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    info = json.loads(Path(args.table + ".json").read_text())
    t = load_truth(args.truth)
    is_noise, pa, pb, dtrue = noise_flags(t, info)
    c = read_contacts(args.table)
    assert np.array_equal(c.pos_a, pa) and np.array_equal(c.pos_b, pb), "regenerated reads differ from the table"
    out = {"table": args.table, "n": int(len(c)), "n_noise": int(is_noise.sum()), "methods": {}}
    for mp in args.models:
        z = np.load(mp, allow_pickle=True)
        chrom, pos, X = load_models(mp)
        idx = ParticleIndex(chrom, pos)
        i = idx(c.chrom_a.astype(str), c.pos_a)
        j = idx(c.chrom_b.astype(str), c.pos_b)
        ok = (i >= 0) & (j >= 0)
        nb = np.median(np.linalg.norm(np.diff(X, axis=1), axis=2))
        dm = np.full(len(c), np.nan)
        dm[ok] = np.median(np.linalg.norm(X[:, i[ok]] - X[:, j[ok]], axis=2), axis=0) / nb
        r = {"bead_unit": float(nb),
             "auc_dist_noise_vs_signal": float(roc_auc(dm[is_noise & np.isfinite(dm)], dm[~is_noise & np.isfinite(dm)])),
             "median_dist_signal": float(np.nanmedian(dm[~is_noise])),
             "median_dist_noise": float(np.nanmedian(dm[is_noise]))}
        if "contact_weights" in z.files and len(z["contact_weights"]) == len(c):
            w = z["contact_weights"]
            f = np.isfinite(w)
            r.update({"auc_weight_signal_vs_noise": float(roc_auc(w[f & ~is_noise], w[f & is_noise])),
                      "mean_w_signal": float(np.nanmean(w[~is_noise])), "mean_w_noise": float(np.nanmean(w[is_noise])),
                      "frac_noise_w_lt_half": float(np.mean(w[is_noise & f] < 0.5)),
                      "frac_signal_w_lt_half": float(np.mean(w[~is_noise & f] < 0.5)),
                      "filtered_signal": int((~f & ~is_noise).sum()), "filtered_noise": int((~f & is_noise).sum())})
        out["methods"][Path(mp).stem] = r
        print(Path(mp).stem, json.dumps({k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()}))
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
