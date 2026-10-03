# Test-set results of `robust` vs NucDynamics (PREREG.md §2-§5)

> **Name (2026-10-03):** the frozen method "robust" is published in U-Chrom as **EMber**
> (`uchrom.recon.sc.reconstruct_ember`; engine protocol `"robust"`, alias `"ember"`).  Naming only:
> no change to the method, its parameters or any result below.

Run once, 2026-10-02, with the frozen method (tag `robust-frozen`, commit 075da66; engine build
"frozen" of that commit: regression hashes of the existing protocols unchanged on Linux;
`run_robust.py` without `--params`).  Test units exactly as pre-registered: held-out Stevens 2017
cells 5-8 x folds 1-3 (existing splits / evaluation pairs), simulations truth cells 3-5 x all 18
conditions of Su 2020 chr21 and Takei 2021 1 Mb (existing reads), real-data checks on cells 5-8,
and the held-back matched-imaging half (202 Nagano serum cells; secondary, PREREG §6).  Baseline:
the existing NucDynamics native GPU runs (2026-09-29/30), not re-run.  robust ran on CPU nodes
(f64, 16 threads; the GPU path computes the same algorithm in f32), 10 models (held-out, real) /
5 models (simulations), seed 1, as the baseline.  Nothing was changed after these numbers were
seen.  Job script `sherlock/robust_test.sbatch`; comparison `robust_compare.py --test`.

## §3 Primary endpoints

| endpoint | units | robust | NucDynamics | difference [95 % CI] |
|---|---|---|---|---|
| **P1** held-out ROC-AUC, median-distance score, cis, mean of the 5 bands | 12 (cell, fold); CI resampling cells | 0.8430 | 0.8401 | **+0.0028 [+0.0025, +0.0031]** |
| **P2** cis Spearman r, median model vs truth | 108 simulations; CI resampling truth cells (dataset x truth, 6 groups) | 0.8073 | 0.7706 | **+0.0367 [+0.0291, +0.0448]** (unit bootstrap [+0.024, +0.052]) |

Context (same test units): P1 hickit 0.8011, Si-C 0.8306, original NucDynamics 0.8411; P2 per
dataset: Su chr21 robust 0.782 / NucDynamics 0.751 / original 0.749 / hickit 0.669; Takei 1 Mb
0.832 / 0.790 / 0.798 / 0.763, Si-C 0.722.

## §4 Secondary endpoints (every stratum; robust - NucDynamics, 95 % CI)

Held-out (12 units, CI resampling cells):

| subset | median-distance score | contact-fraction score |
|---|---|---|
| band 2-4 (0.2-0.4 Mb) | +0.0038 [+0.0018, +0.0059] | +0.0245 [+0.0197, +0.0282] |
| band 4-16 | +0.0056 [+0.0046, +0.0067] | +0.0327 [+0.0314, +0.0339] |
| band 16-64 | +0.0029 [+0.0016, +0.0050] | +0.0635 [+0.0572, +0.0705] |
| band 64-256 | +0.0017 [+0.0004, +0.0034] | +0.0635 [+0.0532, +0.0723] |
| band 256-inf | -0.0000 [-0.0006, +0.0005] | +0.0604 [+0.0550, +0.0656] |
| trans | +0.0000 [-0.0001, +0.0001] | +0.0726 [+0.0668, +0.0784] |
| cis (all separations) | **-0.0022 [-0.0034, -0.0010]** | +0.0304 [+0.0259, +0.0362] |
| all | **-0.0025 [-0.0037, -0.0012]** | +0.0337 [+0.0291, +0.0388] |
| PR-AUC, cis | **-0.0031 [-0.0043, -0.0016]** | +0.0235 [+0.0173, +0.0312] |
| bands mean (contact fraction) | | 0.7317 vs 0.6828: +0.0489 [+0.0471, +0.0507] (hickit 0.7240) |

Simulations (cis Spearman, median model; CI over units):

| dataset | stratum | robust | NucDynamics | difference |
|---|---|---|---|---|
| Su chr21 | all (54) | 0.782 | 0.751 | +0.0312 [+0.021, +0.043] |
| Takei 1 Mb | all (54) | 0.832 | 0.790 | +0.0423 [+0.020, +0.070] |
| Su chr21 | eps 0 / 0.05 / 0.2 | 0.870 / 0.813 / 0.664 | 0.875 / 0.767 / 0.612 | **-0.0044 [-0.0067, -0.0022]** / +0.0464 / +0.0516 |
| Takei 1 Mb | eps 0 / 0.05 / 0.2 | 0.850 / 0.839 / 0.808 | 0.855 / 0.825 / 0.691 | **-0.0045 [-0.0069, -0.0026]** / +0.0141 / +0.1173 |
| Su chr21 | depth 40 / 160 / 640 | 0.683 / 0.816 / 0.848 | 0.667 / 0.778 / 0.808 | +0.0156 / +0.0377 / +0.0403 |
| Takei 1 Mb | depth 10 / 40 / 160 | 0.788 / 0.845 / 0.864 | 0.787 / 0.822 / 0.761 | +0.0003 [-0.003, +0.003] / +0.0233 / +0.1032 |
| Su chr21 | rc 0.5 / 1 | 0.735 / 0.830 | 0.690 / 0.812 | +0.0449 / +0.0175 |
| Takei 1 Mb | rc 0.5 / 1 | 0.788 / 0.877 | 0.728 / 0.853 | +0.0603 / +0.0243 |

All positive strata have CIs excluding 0.  Scale-free RMSD (median model, / Rg; + = robust better):
overall +0.0228 [+0.015, +0.029]; worse only at Su eps 0, **-0.0073 [-0.0125, -0.0022]**; Takei eps 0
-0.0037 [-0.017, +0.009]; all other strata >= 0.  Ensemble-mean distances (cis Spearman): +0.0348
[+0.030, +0.041]; no stratum worse (Su eps 0 +0.0012, Takei eps 0 -0.0000).

Real data, cells 5-8:

| metric | training tables of the 12 folds: robust / NucDynamics | full tables (4 cells): robust / NucDynamics native GPU |
|---|---|---|
| precision, RMSD to mean (bead units) | **3.14 / 1.33** (+1.81 [+0.62, +3.00]) | **3.02 / 1.07** (+1.95 [+0.66, +3.06]) |
| NucDynamics-style %V>3 / %V>4 | 0.47 / 0.43; 0.23 / 0.19 | 0.29 / 0.24; 0.12 / 0.08 |
| Si-C-style % contacts > 2 units | 5.07 / 4.24 | 4.97 / 4.20 |
| r vs published GEO models | 0.939 / 0.954 | 0.950 / 0.963 |
| RMSD/Rg vs GEO models | 0.170 / 0.115 | 0.194 / 0.103 |

Precision per fold: cell 5 ~0.93 vs 0.84; cells 6-8 2.1-5.6 vs 0.8-2.2 (hickit 6.4-10.9).  The
sampled ensembles of cells 6-8 are much less tight than NucDynamics' (by design the method samples
at a finite temperature; on these cells the spread is larger than on the development cells, where
precision was 1.57 vs 1.71) and agree slightly less with the published models.

Cost (PREREG §4-5: one H100, same input, 10 models, 100 kb; same node, same engine build, both
methods alternating; development training tables): NucDynamics 38.7 / 38.5 / 35.7 s, robust 7.4 /
7.5 / 7.2 s (**0.19-0.20x**); peak RSS 266 / 238 / 224 MB vs 268 / 268 / 247 MB.  One model, CPU
1 thread (AMD EPYC 9754, Stevens Cell 1): robust 22.8 / 112 / 202 / 337 / 498 / 1183 s at 500 /
100 / 50 / 20 / 10 / 1 kb vs NucDynamics 273 / 1465 / 2869 / 5711 / 12083 s / - and hickit 27 /
143 / 222 / 578 / 1138 / 2083 s (robust_devlog.md E12).  One-model GPU timing: the first job
failed (engine / runner mismatch, no timing), resubmitted with the frozen build (job 46383709).

## §5 Decision rule, applied literally

1. P1 > 0 with CI excluding 0 (+0.0028 [+0.0025, +0.0031]) **and** P2 > 0 with CI excluding 0
   (+0.0367 [+0.0291, +0.0448]): **met**.
2. No secondary stratum (held-out band / trans / score type; simulation noise / depth / radius /
   dataset) worse by more than 0.01 with a CI excluding 0: the worse strata are held-out cis-all
   -0.0022, all -0.0025, PR-AUC cis -0.0031; simulations Su eps 0 -0.0044, Takei eps 0 -0.0045;
   RMSD at Su eps 0 -0.0073 — all smaller than 0.01: **met**.
3. Wall time on one H100 at most 3x NucDynamics': 0.2x: **met**.

**Result: robust is better than NucDynamics on the pre-registered test (all three conditions of
§5 hold).**  Reported alongside, as §4 requires: it is slightly worse (< 0.01) at zero noise in
both simulation datasets and on the whole-cis / all-pairs and PR-AUC held-out summaries, and its
real-data ensembles are markedly less precise (RMSD to mean 3.0 vs 1.1 bead units on the cells 5-8 full
tables) and agree slightly less with the published models (r 0.950 vs 0.963) — quantities the
decision rule does not threshold.

## Matched imaging, held-back half (secondary, PREREG §6; 202 cells, 188 after masking)

`model [size-matched imaging ceiling ± sd; best structure-free baseline]`:

| method | pair.median_resid_spearman | variab.cv_spearman | variab.cv_ratio | radial.locus_spearman | radial.chrom_spearman | trans.spearman |
|---|---|---|---|---|---|---|
| NucDynamics | 0.58 [0.72 ± 0.01; 0.13] | 0.43 [0.77 ± 0.01; 0.02] | 0.55 [1.00 ± 0.01; 0.51] | 0.28 [0.73 ± 0.02; -0.12] | 0.61 [0.62 ± 0.05; 0.77] | 0.31 [0.75 ± 0.02; 0.72] |
| hickit | 0.55 | 0.47 | 0.52 | 0.24 | 0.57 | 0.39 |
| robust | 0.58 | 0.46 | 0.56 | 0.28 | 0.55 | 0.37 |

As on the development half: equal to NucDynamics on detrended pairs and radial position per locus,
slightly better variability ranking (0.46 vs 0.43; hickit 0.47) and trans proximity (0.37 vs
0.31), slightly lower radial per chromosome (0.55 vs 0.61); the variability ratio stays ~0.56 (the
imaging/model gap is not closed by sampling).
