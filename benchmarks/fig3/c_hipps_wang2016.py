"""Fig. 3c external baseline: HIPPS (Hi-C only) scored like U-Chrom GEM-FISH.

HIPPS (Shi & Thirumalai, Phys Rev X 11:011051, 2021,
doi:10.1103/PhysRevX.11.011051; the contact-probability / distance relation
is from Shi & Thirumalai, Nat Commun 10:3894, 2019) turns a Hi-C contact map
into mean distances, <r_ij> = Lambda * p_ij^(-1/alpha) with alpha = 4 and p
normalised by its maximum, and then builds the maximum-entropy (Gaussian)
ensemble whose mean squared distances match (3 pi / 8) <r_ij>^2, by
iterative scaling.  It uses no FISH, so it is the external counterpart of
"U-Chrom GEM-FISH, Hi-C only".

Inputs and scoring are exactly those of ``c_gemfish_wang2016.py`` (imported
from it): Rao 2014 IMR90 5 kb Hi-C (``rao2014_imr90/IMR90_chr<N>_5kb_hg19.cool``,
ICE-balanced with ``ignore_diags=1``), the Wang 2016 TAD windows and FISH
tables shipped with GEM-FISH, the same seeded 90/10 cell splits
(``default_rng(0)``, one permutation per split), and the same relative error
with one least-squares scale fitted on the training FISH.

Two ways to bring Hi-C to the TADs (both are HIPPS's own recipes):

* ``tad``   — block-average (HIPPS PRX Appendix C) of the balanced 5 kb
  contacts over every TAD x TAD block (the 5 kb main diagonal left out), a
  N_TAD x N_TAD contact map, HIPPS on it; TAD distance = ensemble mean distance.
* ``100kb`` — the paper's resolution: raw 5 kb counts summed to 100 kb,
  ICE-balanced, unmappable bins removed, HIPPS on the whole chromosome;
  TAD distance = mean over all 100 kb bin pairs of the two TADs (as for the
  U-Chrom and GEM-FISH models).  Also scored with the paper's own length
  scale Lambda = 117 nm per 100 kb (fitted in the PRX paper to chromosome
  volumes), i.e. with no scale fitted to FISH.

HIPPS-DIMES is not vendored.  Clone it once::

    git clone https://github.com/anyuzx/HIPPS-DIMES
    git -C HIPPS-DIMES checkout beee45d15ed1c99fc32e7b98036cebdf7ef2943e   # MIT licence

and pass ``--hipps-dimes path/to/HIPPS-DIMES`` (it is imported from there;
its dependencies — numpy >= 2, scipy, pandas, click, rich-click, rich,
tqdm, cooler — are all in the U-Chrom environment).

Usage::

    python benchmarks/fig3/c_hipps_wang2016.py --hipps-dimes ../HIPPS-DIMES \
        [--chrom 20 21 22] [--splits 3] [--out u-chrom-paper/manuscripts/full/figures/fig3/results/c_hipps_wang2016.json]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from c_gemfish_wang2016 import fish_F, load_inputs, score, tad_dist  # noqa: E402

LAMBDA_NM = 117.0   # HIPPS PRX 2021: length scale per 100 kb locus


def import_hd(path: Path | None):
    if path is not None:
        sys.path.insert(0, str(Path(path).resolve()))
    import hipps_dimes as HD

    return HD


def tad_bins(starts: np.ndarray, tads: pd.DataFrame) -> list[np.ndarray]:
    return [np.flatnonzero((starts >= s) & (starts < e)) for s, e in tads.itertuples(index=False)]


def block_average_tads(clr, chrom: str, tads: pd.DataFrame) -> np.ndarray:
    """HIPPS block average of balanced contacts over TAD x TAD blocks."""
    bins = clr.bins().fetch(chrom)
    starts = bins["start"].to_numpy()
    groups = tad_bins(starts, tads)
    lo = min(g.min() for g in groups)
    hi = max(g.max() for g in groups) + 1
    off = int(bins.index[0])
    m = clr.matrix(balance=True)[off + lo:off + hi, off + lo:off + hi].astype(float)
    np.fill_diagonal(m, np.nan)            # 5 kb self-contacts (ignored by ICE too)
    nt = len(groups)
    C = np.zeros((nt, nt))
    for i in range(nt):
        for j in range(i, nt):
            C[i, j] = C[j, i] = np.nanmean(m[np.ix_(groups[i] - lo, groups[j] - lo)])
    return C


def coarse_balanced(cool5: Path, chrom: str, factor: int, tmp: Path):
    import cooler

    out = tmp / f"{chrom}_{factor * 5}kb.cool"
    cooler.coarsen_cooler(str(cool5), str(out), factor=factor, chunksize=10_000_000)
    clr = cooler.Cooler(str(out))
    cooler.balance_cooler(clr, store=True, ignore_diags=1)
    return clr


def run_hipps(HD, cmap: np.ndarray, args, seed: int) -> dict:
    np.random.seed(seed)
    t0 = time.time()
    res = HD.run_optimization(
        input_matrix=cmap, input_type="cmap", alpha=args.alpha, method="IS",
        iteration=args.iterations, learning_rate=args.lr, ensemble=args.ensemble,
        save_steps=[1000] if args.iterations > 1000 else None, verbose=False, show_progress=False)
    dt = time.time() - t0
    xyz = res["xyzs"]                                   # (ensemble, n, 3), Lambda = 1
    D = np.zeros((xyz.shape[1],) * 2)
    for b in range(0, len(xyz), 100):
        c = xyz[b:b + 100]
        D += np.linalg.norm(c[:, :, None] - c[:, None], axis=-1).sum(0)
    D /= len(xyz)
    out = {"seconds": dt, "D_ensemble": D, "D_theory": res["dmap_final"],
           "final_loss": float(res["optimization"]["final_loss"]),
           "final_entropy": float(res["optimization"]["final_entropy"]),
           "rc_optimal": res.get("rc_optimal")}
    steps = res.get("connectivity_matrix_at_steps") or {}
    if 1000 in steps:
        out["D_theory_iter1000"] = HD.a2dmap_theory(steps[1000], force_positive_definite=True)
        ser = res["iteration_series"]
        out["loss_iter1000"] = float(ser.loc[ser["iteration"] == 1000, "loss"].iloc[0])
    # HIPPS's own target distances (before the max-ent step), for reference
    with np.errstate(divide="ignore"):
        tgt = HD.cmap2dmap_missing_data(cmap, args.alpha, False)
    out["D_target"] = np.where(np.isfinite(tgt), tgt, np.nan)   # zero-contact pairs -> missing
    return out


def block_mean(D: np.ndarray, groups: list[np.ndarray]) -> np.ndarray:
    nt = len(groups)
    M = np.zeros((nt, nt))
    for i in range(nt):
        for j in range(i + 1, nt):
            M[i, j] = M[j, i] = np.nanmean(D[np.ix_(groups[i], groups[j])])
    return M


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "example-data")
    ap.add_argument("--hipps-dimes", type=Path, default=None, help="path to the HIPPS-DIMES clone")
    ap.add_argument("--chrom", nargs="+", default=["20", "21", "22"])
    ap.add_argument("--splits", type=int, default=3)
    ap.add_argument("--alpha", type=float, default=4.0, help="HIPPS exponent (paper and code default 4)")
    ap.add_argument("--iterations", type=int, default=10_000, help="IS iterations (code default)")
    ap.add_argument("--lr", type=float, default=10.0, help="IS learning rate (paper and code default 10)")
    ap.add_argument("--ensemble", type=int, default=1000, help="conformations (paper and code default 1000)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    import cooler

    HD = import_hd(args.hipps_dimes)
    runs, meta = [], {}
    for c in args.chrom:
        chrom = f"chr{c}"
        tmp = Path(tempfile.mkdtemp())
        tads, P, ref_model, sizes = load_inputs(args.data / "abbas2019_gemfish", tmp, c)
        ref_idx = np.cumsum([0] + sizes)
        M_ref = tad_dist(ref_model, [np.arange(ref_idx[i], ref_idx[i + 1]) for i in range(len(tads))]) / 1000.0
        cool5 = tmp / f"imr90_{chrom}_5kb.cool"
        shutil.copy(args.data / "rao2014_imr90" / f"IMR90_{chrom}_5kb_hg19.cool", cool5)
        clr5 = cooler.Cooler(str(cool5))
        cooler.balance_cooler(clr5, store=True, ignore_diags=1)

        models = {}
        # (1) TAD level: block average of balanced 5 kb contacts
        t0 = time.time()
        C = block_average_tads(clr5, chrom, tads)
        prep = time.time() - t0
        h = run_hipps(HD, C, args, seed=0)
        models["hipps tad-level"] = (h["D_ensemble"], h)
        models["hipps tad-level, theory mean"] = (h["D_theory"], None)
        models["hipps tad-level, 1000 IS iterations"] = (h.get("D_theory_iter1000"), None)
        models["hipps tad-level target (Hi-C^-1/4, before max-ent)"] = (h["D_target"], None)
        meta[f"{chrom} tad-level"] = {"n_loci": len(C), "prep_seconds": prep,
                                      **{k: v for k, v in h.items() if not k.startswith("D_")}}

        # (2) 100 kb chromosome (the PRX paper's resolution)
        t0 = time.time()
        clr = coarse_balanced(cool5, chrom, 20, tmp)
        m = clr.matrix(balance=True).fetch(chrom)
        starts = clr.bins().fetch(chrom)["start"].to_numpy()
        keep = np.flatnonzero(np.isfinite(m).any(0) & (np.nan_to_num(m).sum(0) > 0))
        m = m[np.ix_(keep, keep)]
        prep = time.time() - t0
        h = run_hipps(HD, m, args, seed=0)
        groups = tad_bins(starts[keep], tads)
        models["hipps 100kb"] = (block_mean(h["D_ensemble"], groups), h)
        models["hipps 100kb, theory mean"] = (block_mean(h["D_theory"], groups), None)
        models["hipps 100kb, 1000 IS iterations"] = (
            block_mean(h["D_theory_iter1000"], groups) if "D_theory_iter1000" in h else None, None)
        models["hipps 100kb target (Hi-C^-1/4, before max-ent)"] = (block_mean(h["D_target"], groups), None)
        meta[f"{chrom} 100kb"] = {"n_loci": int(len(keep)), "n_bins_chrom": int(len(starts)),
                                  "tad_bins_min": int(min(len(g) for g in groups)), "prep_seconds": prep,
                                  **{k: v for k, v in h.items() if not k.startswith("D_")}}

        rng = np.random.default_rng(0)                     # same splits as c_gemfish_wang2016.py
        for split in range(args.splits):
            perm = rng.permutation(len(P))
            n_test = max(1, len(P) // 10)
            test, train = P[perm[:n_test]], P[perm[n_test:]]
            F_tr, F_te = fish_F(train), fish_F(test)
            for name, (M, h) in models.items():
                if M is None:
                    continue
                row = {"chrom": chrom, "split": split, "model": name, **score(M, F_tr, F_te)}
                if h is not None:
                    row["seconds"] = round(h["seconds"], 2)
                runs.append(row)
            # reference: the GEM-FISH paper's final model (Hi-C + all FISH), as in c_gemfish_wang2016.py
            # (no rescale) and with the same one-scale rule that HIPPS and U-Chrom get
            runs.append({"chrom": chrom, "split": split, "model": "paper GEM-FISH final (nm, no rescale)",
                         **score(M_ref, F_tr, F_te, fit_scale=False)})
            runs.append({"chrom": chrom, "split": split, "model": "paper GEM-FISH final, same LS scale",
                         **score(M_ref, F_tr, F_te)})
            # the paper's length scale, no fit to FISH (100 kb model only; Lambda per 100 kb locus)
            M = models["hipps 100kb"][0] * LAMBDA_NM / 1000.0
            runs.append({"chrom": chrom, "split": split, "model": "hipps 100kb, Lambda=117 nm (no FISH scale)",
                         **score(M, F_tr, F_te, fit_scale=False)})
        shutil.rmtree(tmp, ignore_errors=True)
        df = pd.DataFrame([r for r in runs if r["chrom"] == chrom])
        print(chrom, {k: v for k, v in meta.items() if k.startswith(chrom)})
        print(df.groupby("model")[["re_train", "re_heldout", "pearson_heldout", "spearman_heldout"]]
              .mean().round(3).to_string())
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"params": {"alpha": args.alpha, "method": "IS", "iterations": args.iterations,
                                                   "learning_rate": args.lr, "ensemble": args.ensemble,
                                                   "lambda_nm_per_100kb": LAMBDA_NM, "splits": args.splits},
                                        "hipps_runs": meta, "scores": runs}, indent=1, default=float))
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
