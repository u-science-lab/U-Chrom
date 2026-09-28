"""Fig. 3c first look: GEM-FISH on real IMR90 Hi-C + held-out FISH.

Feasibility check, not the final benchmark (the paper-faithful setup is
whole chromosomes with Wang et al. 2016 TAD-level FISH; see
``paper/fig3/PLAN.md``).  Here:

* Hi-C: Rao et al. 2014 IMR90, raw 5 kb counts summed into the 65 × 30 kb
  segments of Bintu et al. 2018 chr21:18.6-20.6 Mb (hg19
  chr21:20,000,032-21,950,032) — ``rao2014_imr90/IMR90_chr21_5kb_hg19.cool``
  from ``example-data/build_rao2014_slices.py``;
* FISH: Bintu 2018 traces of the same region, split by trace into a
  training half (fed to GEM-FISH as TAD-centre distances + TAD Rg²) and a
  held-out half (median distance matrix, never seen by the model);
* models: Hi-C only (``fish_cd=None``) vs Hi-C + training FISH;
* metrics: Pearson / Spearman of the model's pairwise distances vs the
  held-out FISH median distances (scale-free), runtime.

The region is written as a stand-alone pseudo-chromosome ``chr21_region``
(coordinates relative to the first segment) so the Hi-C and FISH bins
coincide exactly.

Usage::

    python benchmarks/fig3/c_gemfish_first_look.py [--data example-data] [--seeds 0 1 2]
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
SEG, N_SEG, START_HG19 = 30_000, 65, 20_000_032
CHROM = "chr21_region"


def region_cool(cool_5kb: Path, out: Path) -> None:
    import cooler

    c = cooler.Cooler(str(cool_5kb))
    lo = START_HG19 // 5000 * 5000
    m = c.matrix(balance=False).fetch(f"chr21:{lo}-{lo + N_SEG * SEG}").astype(float)
    agg = m.reshape(N_SEG, 6, N_SEG, 6).sum((1, 3))
    bins = pd.DataFrame({"chrom": CHROM, "start": np.arange(N_SEG) * SEG,
                         "end": np.arange(1, N_SEG + 1) * SEG})
    iu = np.triu_indices(N_SEG)
    px = pd.DataFrame({"bin1_id": iu[0], "bin2_id": iu[1], "count": agg[iu].astype(int)})
    cooler.create_cooler(str(out), bins, px[px["count"] > 0], assembly="none")
    cooler.balance_cooler(cooler.Cooler(str(out)), store=True, ignore_diags=1, min_nnz=1)


def fish(csv: Path):
    from uchrom import ChromData

    df = pd.read_csv(csv, skiprows=1)
    df.columns = ["trace_id", "seg", "z", "x", "y"]
    df = df.dropna()
    df["start"] = (df["seg"] - 1) * SEG
    df["end"] = df["start"] + SEG
    df["chrom"] = CHROM
    return df


def to_cd(df):
    from uchrom import ChromData

    return ChromData(coords=df[["x", "y", "z"]].to_numpy(float),
                     spots=df[["chrom", "start", "end", "trace_id"]].reset_index(drop=True))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "example-data")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    import torch
    from uchrom.fea.distance import mean_distance_matrix
    from uchrom.recon.fish import GEMFISHParams, reconstruct_gem_fish

    tmp = Path(tempfile.mkdtemp())
    cool = tmp / "imr90_bintu_region_30kb.cool"
    region_cool(args.data / "rao2014_imr90" / "IMR90_chr21_5kb_hg19.cool", cool)
    df = fish(args.data / "IMR90_chr21-18-20Mb.csv")
    tr = df["trace_id"].unique()
    train = df[df["trace_id"].isin(tr[::2])]
    test = df[df["trace_id"].isin(tr[1::2])]
    D_test, _, n_test = mean_distance_matrix(test, reduce="median")
    iu = np.triu_indices(N_SEG, 1)
    # reference: how well Hi-C alone predicts held-out distances (no 3-D model)
    import cooler
    H = cooler.Cooler(str(cool)).matrix(balance=True)[:]
    ok = np.isfinite(H[iu]) & (H[iu] > 0)
    ref = float(stats.spearmanr(-H[iu][ok], D_test[iu][ok])[0])
    # upper bound: FISH train half vs held-out half
    D_train, _, _ = mean_distance_matrix(train, reduce="median")
    ub = float(stats.pearsonr(D_train[iu], D_test[iu])[0])

    rows = []
    for mode in ("hic_only", "hic+fish"):
        for seed in args.seeds:
            torch.manual_seed(seed)
            np.random.seed(seed)
            t0 = time.time()
            cd = reconstruct_gem_fish(str(cool), CHROM, fish_cd=to_cd(train) if mode == "hic+fish" else None,
                                      params=GEMFISHParams(device="cpu", verbose=False,
                                                           tad_di_window=5, tad_di_min_size_frac=0.05,
                                                           tad_max_size_frac=0.3))
            dt = time.time() - t0
            X = cd.coords
            D = np.linalg.norm(X[:, None] - X[None], axis=-1)
            rows.append({"mode": mode, "seed": seed, "seconds": round(dt, 1),
                         "n_tads": cd.uns["gem_fish"]["n_tads"],
                         "pearson_vs_heldout": float(stats.pearsonr(D[iu], D_test[iu])[0]),
                         "spearman_vs_heldout": float(stats.spearmanr(D[iu], D_test[iu])[0])})
            print(rows[-1])
    summary = {"n_train_traces": int(len(tr[::2])), "n_test_traces": int(n_test),
               "hic_contacts_vs_heldout_spearman": ref, "fish_half_vs_half_pearson": ub,
               "runs": rows}
    for mode in ("hic_only", "hic+fish"):
        r = [x["pearson_vs_heldout"] for x in rows if x["mode"] == mode]
        print(f"{mode}: Pearson vs held-out FISH {np.mean(r):.3f} ± {np.std(r):.3f}")
    print(f"Hi-C balanced counts vs held-out distance (Spearman, sign flipped): {ref:.3f}; "
          f"FISH half vs half: {ub:.3f}")
    if args.out:
        args.out.write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
