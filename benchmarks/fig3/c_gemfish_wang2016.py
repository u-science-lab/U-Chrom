"""Fig. 3a/c feasibility: U-Chrom GEM-FISH in the GEM-FISH paper's own setup.

Abbas et al. 2019 (Nat Commun 10:2049) modelled IMR90 chr21 from Rao 2014
5 kb Hi-C plus the Wang et al. 2016 (Science 353:598) multiplexed FISH of
34 TAD centres in 120 chromosomes, and scored the model by the mean
relative error |d_model - d_FISH| / d_FISH over TAD pairs (Table 1:
0.14 final model; 0.30 for GEM on Hi-C alone; Supp. Table 9: 0.188 on
FISH held out by cells, 90/10 split).

This script runs ``uchrom.recon.fish.reconstruct_gem_fish`` on the same
inputs and scores it the same way:

* Hi-C: ``rao2014_imr90/IMR90_chr21_5kb_hg19.cool`` (Rao 2014 IMR90
  combined, raw counts, ICE-balanced here; the paper used MAPQ>=30 + KR);
* TADs: the Wang 2016 windows in hg19 shipped with GEM-FISH
  (``tads_chr21_hg19.txt``);
* FISH: Wang 2016 chr21 table shipped with GEM-FISH (``chr21.xlsx``, µm);
  cells split 90 % train / 10 % held out (seeded);
* model distances between TADs = mean distance over all bin pairs of the
  two TADs (as in the paper's code), rescaled by the one least-squares
  factor fitted on the *training* FISH (the port works in reduced units);
* reference: the paper's own final chr21 model
  (``chr21_high_res_str.txt``, nm) scored with the same code.

Inputs come from ``$UCHROM_DATA/abbas2019_gemfish/`` (``python -m uchrom.datasets fetch abbas2019_gemfish``) and ``build_rao2014_slices.py``.

Usage::

    python benchmarks/fig3/c_gemfish_wang2016.py [--data $UCHROM_DATA] [--splits 3] [--chrom 21]

``--chrom 20`` / ``22`` use the Wang 2016 chr20 / chr22 tables shipped with
GEM-FISH and ``build_rao2014_slices.py --cell IMR90 --chroms 20`` (``22``).
"""

from __future__ import annotations

from uchrom.datasets import data_dir
import argparse
import json
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]


def load_inputs(gdir: Path, tmp: Path, chrom: str = "21"):
    for z in ("complete_example.zip", "validation_tests_final_models.zip"):
        with zipfile.ZipFile(gdir / z) as zf:
            zf.extractall(tmp)
    tads = pd.read_csv(next(tmp.rglob(f"tads_chr{chrom}_hg19.txt")), sep=r"\s+", header=None,
                       names=["start", "end"])
    co = pd.read_excel(next(tmp.rglob(f"create_TAD_level_model/chr{chrom}.xlsx")), header=None).to_numpy()
    nt = len(tads)
    P = co[: len(co) // nt * nt, 2:5].astype(float).reshape(-1, nt, 3)   # cells × TADs × µm
    ref = np.loadtxt(next(tmp.rglob(f"chr{chrom}_high_res_str.txt")), delimiter=",")
    sizes = [len(np.loadtxt(next(tmp.rglob(f"Rao_files_{chrom}_5kb/loci_tad_{i}_Rao_5kb.txt")))) for i in range(nt)]
    return tads, P, ref, sizes


def fish_F(P: np.ndarray) -> np.ndarray:
    return np.nanmean(np.linalg.norm(P[:, :, None] - P[:, None], axis=-1), 0)


def tad_dist(X: np.ndarray, groups: list[np.ndarray]) -> np.ndarray:
    nt = len(groups)
    M = np.zeros((nt, nt))
    for i in range(nt):
        for j in range(i + 1, nt):
            M[i, j] = M[j, i] = np.linalg.norm(X[groups[i]][:, None] - X[groups[j]][None], axis=-1).mean()
    return M


def score(M, F_train, F_test, fit_scale=True):
    iu = np.triu_indices(len(M), 1)
    m, a, b = M[iu], F_train[iu], F_test[iu]
    s = float((m / a).sum() / ((m / a) ** 2).sum()) if fit_scale else 1.0
    return {"scale": s,
            "re_train": float(np.mean(np.abs(s * m - a) / a)),
            "re_heldout": float(np.mean(np.abs(s * m - b) / b)),
            "pearson_heldout": float(stats.pearsonr(m, b)[0]),
            "spearman_heldout": float(stats.spearmanr(m, b)[0])}


def fish_cd(P: np.ndarray, tads: pd.DataFrame, chrom: str = "chr21"):
    from uchrom import ChromData

    n_cells, nt, _ = P.shape
    spots = pd.DataFrame({"chrom": chrom,
                          "start": np.tile(tads["start"].to_numpy(), n_cells),
                          "end": np.tile(tads["end"].to_numpy(), n_cells),
                          "trace_id": np.repeat(np.arange(n_cells), nt)})
    xyz = P.reshape(-1, 3)
    ok = np.isfinite(xyz).all(1)
    return ChromData(coords=xyz[ok], spots=spots[ok].reset_index(drop=True))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=data_dir())
    ap.add_argument("--splits", type=int, default=3)
    ap.add_argument("--chrom", default="21", help="20, 21 or 22 (Wang 2016 autosomes shipped with GEM-FISH)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    import cooler
    import torch
    from uchrom.recon.fish import GEMFISHParams, reconstruct_gem_fish

    tmp = Path(tempfile.mkdtemp())
    chrom = f"chr{args.chrom}"
    tads, P, ref_model, sizes = load_inputs(args.data / "abbas2019_gemfish", tmp, args.chrom)
    cool = tmp / f"imr90_{chrom}_5kb.cool"
    shutil.copy(args.data / "rao2014_imr90" / f"IMR90_{chrom}_5kb_hg19.cool", cool)
    cooler.balance_cooler(cooler.Cooler(str(cool)), store=True, ignore_diags=1)
    ref_idx = np.cumsum([0] + sizes)
    ref_groups = [np.arange(ref_idx[i], ref_idx[i + 1]) for i in range(len(tads))]
    M_ref = tad_dist(ref_model, ref_groups)

    rng = np.random.default_rng(0)
    runs = []
    for split in range(args.splits):
        perm = rng.permutation(len(P))
        n_test = max(1, len(P) // 10)
        test, train = P[perm[:n_test]], P[perm[n_test:]]
        F_tr, F_te = fish_F(train), fish_F(test)
        runs.append({"chrom": chrom, "split": split, "model": "paper GEM-FISH final (nm, no rescale)",
                     **score(M_ref / 1000.0, F_tr, F_te, fit_scale=False)})
        print(runs[-1])
        for mode in ("hic_only", "hic+fish"):
            torch.manual_seed(split)
            t0 = time.time()
            cd = reconstruct_gem_fish(str(cool), chrom, fish_cd=fish_cd(train, tads, chrom) if mode == "hic+fish" else None,
                                      tads=tads, params=GEMFISHParams(device="cpu", verbose=False))
            dt = time.time() - t0
            st = cd.spots_with_loci()["start"].to_numpy()
            groups = [np.flatnonzero((st >= s) & (st < e)) for s, e in tads.itertuples(index=False)]
            runs.append({"chrom": chrom, "split": split, "model": f"uchrom {mode}", "seconds": round(dt, 1),
                         "n_bins": int(len(st)), **score(tad_dist(cd.coords, groups), F_tr, F_te)})
            print(runs[-1])
    df = pd.DataFrame(runs)
    print(df.groupby("model")[["re_train", "re_heldout", "pearson_heldout", "spearman_heldout"]].mean().round(3))
    if args.out:
        args.out.write_text(json.dumps(runs, indent=1))


if __name__ == "__main__":
    main()
