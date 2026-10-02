# `robust` development log (milestone M2, development set only)

Method: `PREREG.md` §7; engine `native/nucdyn/src/robust.rs` (protocol `"robust"`) and
`src/support.rs`; runner `run_robust.py`; jobs `sherlock/robust_*.sbatch` (`_env_robust.sh` refuses
non-development units: simulation truth cells 1-2, held-out / real cells 1-4); comparison
`robust_compare.py` (paired against the existing `nucdyn_gpu` runs of 2026-09-29/30, which were not
re-run or re-tuned); noise diagnostics `robust_diag.py` (regenerates the seeded simulated reads to
recover which reads are noise).  Data: only the catalogued datasets already used by the benchmark
(Stevens 2017 GEO tables, Su 2020 chr21, Takei 2021 1 Mb); nothing new was downloaded.

**No test-set unit (truth cells 3-5, held-out / real cells 5-8) was run, scored or read.**  The
baseline score files were copied filtered to development units before any comparison.

## Conventions

* **P2-dev**: mean over the 72 development simulations (2 datasets x 2 truth cells x 18 conditions)
  of robust - nucdyn_gpu in median-over-models cis Spearman r; 95 % CI by bootstrap over units
  ("cluster" CI over dataset x truth cell is also computed, but there are only 4 clusters).
* **P1-dev**: mean over 12 (cell, fold) of the mean of the five cis-band ROC-AUCs (median-distance
  score), CI by resampling cells.  "frac" = the same for the contact-fraction score.
* Strata CIs: bootstrap over the units of the stratum.  "worse" = CI below 0; the decision rule's
  bar is a difference worse than 0.01 with the CI excluding 0.
* Baseline development means: Spearman cis nucdyn_gpu 0.758 (su 0.709, takei 0.807; hickit 0.706,
  Si-C 0.734 on Takei only, original 0.763); held-out bands mean 0.843 (median score), 0.686 (frac).
* All simulation runs: 5 models, seed 1, full schedule, one GPU (mixed H100 / H200 / L40S / ...;
  timing only on H100, see the end); held-out: 10 models, 100 kb, as the baseline.
* Sherlock outputs: `$SCRATCH/uchrom-nd/runs/robust/{sim,heldout,real,timing}`; engine builds pinned
  per experiment batch (`engine-robust/e3..e6`).

## Engine / protocol facts established on the way

* Bit identity: `tests/regression.rs` hashes the CPU output of `nuc_dynamics_2017` (with and without
  the overflow emulation) and `release_1.3`; golden values recorded with the engine *before* this
  work on macOS arm64 and Linux x86-64 (the Linux values from the Sherlock build of commit 628746e
  + the test only); every later build reproduces them on both platforms.
* `robust` with re-weighting disabled (`robust_start_stage` beyond the schedule, no refinement) is
  the 2017 protocol bit for bit (Python test).  Control run **ctrl** (same, GPU) vs the existing
  nucdyn_gpu models: P2-dev +0.0001 [-0.001, +0.001], every stratum |diff| <= 0.002 -> run-to-run
  noise of the paired comparison is ~0.001.
* GPU vs CPU: weighted restraints (shared and per-model weights) and the no-contact term agree to
  < 3e-5 after 10 MD steps (`gpu::tests::gpu_matches_cpu_weighted`; Metal on the laptop, Vulkan on a
  Sherlock RTX 2080 Ti); ensemble statistics of a
  full robust run agree (Python GPU test).

## Entries (chronological)

### E1 — v0: first version (ensemble responsibilities, Gaussian kernel d0 = 2 radii, s and eps learned, weights before every stage from stage 2)
P2-dev **+0.0153 [+0.009, +0.022]**.  Gains where noise is present (su eps 0.2 +0.043, takei eps 0.2
+0.026, takei depth 160 +0.019), but **su eps 0 -0.0073 [-0.013, -0.002]**.  Diagnosis (one table,
local, then all): NucDynamics compresses the structure (Su d160: Rg ~4 radii for 727 particles,
40-70 % of pairs inside the kernel), so false contacts end up "satisfied" and their posteriors stay
high (mean weight of noise reads 0.71 Su / 0.61 Takei; weight AUC signal vs noise 0.84 / 0.94);
eps is underestimated (Takei eps 0.2: estimate 0.02-0.04).

### E2 — more EM iterations: seg2 (2 updates per stage), seg2ref1 (+1 refinement pass at the final size)
seg2 +0.0253 [+0.017, +0.034]; **seg2ref1 +0.0332 [+0.023, +0.044]** (su eps 0.2 +0.077, takei eps
0.2 +0.060) but su eps 0 **-0.0098 [-0.018, -0.004]** (just inside the 0.01 bar).  Held-out
seg2ref1: P1 -0.0008 [-0.002, -0.000], frac -0.0022 [-0.004, -0.001]; NucDynamics-style %V>3
0.67 -> 1.19 (down-weighted contacts stay violated, by design).
Local ablation (Su truth 1, d160 rc1 eps 0): with eps fixed at 0 the same schedule gives 0.917 vs
nd 0.918 -> the eps-0 loss comes from the weights, not from the re-heated schedule.  The
down-weighted true contacts are the kernel's tail: true distance median 2.0 rc (all true contacts
0.93 rc).  A weight floor of 0.25 or a later start stage (3 or 5) did not remove the loss.

### E3 — per-model responsibilities (pm_seg2)
+0.0270 [+0.018, +0.036]; worse than ensemble responsibilities on every noise stratum and no
better at eps 0 (-0.0086).  Dropped.

### E4 — oracle upper bound (local, Su truth 1 d160 rc1 eps 0.2; diagnostic only)
Noise reads given likelihood ratio 0 (`--oracle-truth`): Spearman 0.858 vs nd 0.707 and best
re-weighting 0.78 -> the ceiling of re-weighting is high; better noise detection is the lever.

### E5 — local-support evidence (structure-free; `robust_prior.py` prototype, then `support.rs`)
Support count in a W window around each contact vs at random locations of the same separation
(what a uniform false contact sees); per-stratum mixture (false: empirical, true: NB).  Offline on
development tables: Takei separates noise almost perfectly (AUC 0.95-0.99, fitted trans false
fraction 0.48 vs true 0.46), Su much less (AUC 0.6-0.9; one chromosome, noise is all cis).
* sr_mix4 (seg2ref1 + support, W = 4 x final size): +0.0439 [+0.027, +0.063], takei eps 0.2
  **+0.127**, but su eps 0 -0.0171 (support does not help Su).
* Rust port matches the prototype (same strata estimates, 0.843 vs 0.841 on the test table).

### E6 — kernel shape: exponential (heavy tail) instead of Gaussian
sr_exp alone: +0.0078, su eps 0 -0.0023 (tail contacts no longer called false; eps -> ~0 at eps 0)
but much smaller gains.  Combined with support: **sr_exp_mix4 +0.0370 [+0.022, +0.054]**, su eps 0
-0.0024 [-0.006, +0.000], takei eps 0.2 +0.111.  Smaller kernel widths (sr_exps, es4_s, s grid
from 0.15) bring the eps-0 loss back (-0.008 / -0.018).  Learning d0 by likelihood
(`robust_d0_grid`, local) always picks the smallest d0 and the largest eps-0 loss: not used.

### E7 — native engine version es4 (= sr_exp_mix4 with `robust_support_rel` = 4)
**P2-dev +0.0376 [+0.022, +0.056]** (cluster CI [+0.028, +0.047]); every simulation stratum in the
table below; worst stratum takei eps 0 -0.0015 [-0.004, -0.000].  Window 2 x (es2) +0.0341, more EM
(es4_seg4, es4_ref2) or per-model (es4_pm) no better.
Held-out: **P1-dev -0.0004 [-0.0009, +0.0001]**, frac +0.0004 [-0.0004, +0.0011]; on the real
tables eps goes to its floor (1e-4) at every stage and every weight is ~1, i.e. robust reduces to
NucDynamics on the Stevens data (after the isolation filter there is no structure-inconsistent
subset of contacts to remove).

### E8 — Poisson "no contact" term (U = x q exp(-((d - 2) / 0.5)^2) on every pair |i - j| >= 2)
nc5_seg2 (Gaussian kernel, q up to 10): su eps 0.2 +0.112 but eps 0 -0.020 / -0.026.  With the
exponential kernel + support (es4_nc, q <= 1): **P2-dev +0.0569 [+0.040, +0.077]** and *no* eps-0
loss (su +0.0072, takei +0.0012); scale 2.5 / 10 and q caps 0.5 / 2 bracket it (+0.051 ... +0.057).
**But held-out es4_nc: frac score -0.0271 [-0.037, -0.019]** (every band from 4-16 on, trans
-0.053), P1 +0.0018 [+0.001, +0.003]; precision 1.71 -> 2.28 bead units, Si-C-style violations
8.4 % -> 13.0 %.  The term pushes apart exactly the pairs the held-out test asks about (truly close
pairs without a training contact); at single-cell capture efficiency that costs more than it gains.
Fails the decision rule (frac stratum worse by > 0.01): **not in the recommended set**.

## Results table (simulation P2-dev and the eps strata; held-out where run)

| variant | n | P2-dev [95 % CI] | su eps 0 | su eps 0.2 | takei eps 0 | takei eps 0.2 | worst sim stratum | held-out P1 | held-out frac |
|---|---|---|---|---|---|---|---|---|---|
| ctrl | 72 | +0.0001 [-0.001, +0.001] | -0.0006 [-0.002, +0.000] | -0.0001 [-0.003, +0.005] | -0.0008 [-0.002, +0.000] | -0.0007 [-0.002, +0.001] | takei depth 10 -0.0021 |  |  |
| v0 | 72 | +0.0153 [+0.009, +0.022] | -0.0073 [-0.013, -0.002] | +0.0428 [+0.026, +0.059] | -0.0027 [-0.005, +0.000] | +0.0257 [+0.014, +0.038] | su eps 0 -0.0073 |  |  |
| seg2 | 72 | +0.0253 [+0.017, +0.034] | -0.0078 [-0.015, -0.002] | +0.0573 [+0.037, +0.078] | -0.0014 [-0.004, +0.001] | +0.0431 [+0.026, +0.061] | su eps 0 -0.0078 |  |  |
| seg2ref1 | 72 | +0.0332 [+0.023, +0.044] | -0.0098 [-0.018, -0.004] | +0.0773 [+0.053, +0.104] | -0.0005 [-0.003, +0.002] | +0.0603 [+0.038, +0.082] | su eps 0 -0.0098 | -0.0008 [-0.002, -0.000] | -0.0022 [-0.004, -0.001] |
| pm_seg2 | 72 | +0.0270 [+0.018, +0.036] | -0.0086 [-0.016, -0.002] | +0.0677 [+0.045, +0.091] | -0.0018 [-0.004, +0.001] | +0.0471 [+0.029, +0.065] | su eps 0 -0.0086 |  |  |
| nc5_seg2 | 72 | +0.0361 [+0.020, +0.052] | -0.0198 [-0.035, -0.006] | +0.1116 [+0.075, +0.147] | -0.0256 [-0.039, -0.013] | +0.0750 [+0.047, +0.104] | takei eps 0 -0.0256 |  |  |
| nc5q1_seg2 | 72 | +0.0483 [+0.032, +0.064] | -0.0103 [-0.023, +0.000] | +0.1144 [+0.079, +0.149] | -0.0026 [-0.006, +0.001] | +0.0972 [+0.058, +0.139] | su eps 0 -0.0103 |  |  |
| sr_mix4 | 72 | +0.0439 [+0.027, +0.063] | -0.0171 [-0.031, -0.006] | +0.0872 [+0.057, +0.117] | -0.0012 [-0.003, +0.001] | +0.1269 [+0.067, +0.198] | su eps 0 -0.0171 |  |  |
| sr_exp | 72 | +0.0078 [+0.005, +0.011] | -0.0023 [-0.004, -0.001] | +0.0241 [+0.017, +0.032] | +0.0002 [-0.001, +0.001] | +0.0113 [+0.004, +0.019] | su eps 0 -0.0023 |  |  |
| sr_exps | 72 | +0.0436 [+0.030, +0.058] | -0.0081 [-0.011, -0.005] | +0.0988 [+0.069, +0.130] | -0.0007 [-0.003, +0.002] | +0.0873 [+0.052, +0.123] | su eps 0 -0.0081 |  |  |
| sr_exp_mix4 | 72 | +0.0370 [+0.022, +0.054] | -0.0024 [-0.006, +0.000] | +0.0683 [+0.048, +0.090] | +0.0001 [-0.001, +0.001] | +0.1106 [+0.052, +0.179] | su eps 0 -0.0024 |  |  |
| es2 | 72 | +0.0341 [+0.021, +0.050] | -0.0025 [-0.005, -0.000] | +0.0657 [+0.045, +0.092] | -0.0004 [-0.001, +0.001] | +0.0943 [+0.042, +0.159] | su eps 0 -0.0025 |  |  |
| **es4** | 72 | **+0.0376 [+0.022, +0.056]** | -0.0013 [-0.003, +0.000] | +0.0626 [+0.046, +0.082] | -0.0015 [-0.004, -0.000] | +0.1205 [+0.055, +0.199] | takei eps 0 -0.0015 | -0.0004 [-0.001, +0.000] | +0.0004 [-0.000, +0.001] |
| es4_ref2 | 72 | +0.0387 [+0.023, +0.057] | -0.0021 [-0.004, -0.000] | +0.0654 [+0.048, +0.086] | -0.0014 [-0.003, +0.000] | +0.1223 [+0.058, +0.199] | su eps 0 -0.0021 |  |  |
| es4_nc | 72 | +0.0569 [+0.040, +0.077] | +0.0072 [+0.001, +0.013] | +0.0991 [+0.072, +0.129] | +0.0012 [-0.003, +0.005] | +0.1374 [+0.072, +0.215] | takei eps 0 +0.0012 | +0.0018 [+0.001, +0.003] | **-0.0271 [-0.037, -0.019]** |
| es4_nc2 | 72 | +0.0512 [+0.035, +0.070] | +0.0066 [+0.000, +0.012] | +0.0760 [+0.053, +0.102] | +0.0033 [-0.000, +0.006] | +0.1338 [+0.068, +0.211] | takei eps 0 +0.0033 |  |  |
| es4_nc10 | 72 | +0.0549 [+0.037, +0.076] | +0.0002 [-0.007, +0.007] | +0.1212 [+0.086, +0.155] | -0.0074 [-0.013, -0.003] | +0.1307 [+0.067, +0.205] | takei eps 0 -0.0074 |  |  |
| es4_nc5q05 | 72 | +0.0569 [+0.040, +0.077] | +0.0068 [-0.001, +0.014] | +0.1005 [+0.073, +0.129] | +0.0033 [-0.000, +0.006] | +0.1363 [+0.070, +0.214] | takei eps 0 +0.0033 |  |  |
| es4_nc5q2 | 72 | +0.0528 [+0.036, +0.073] | +0.0045 [-0.001, +0.010] | +0.1027 [+0.075, +0.133] | -0.0055 [-0.011, -0.000] | +0.1313 [+0.068, +0.205] | takei eps 0 -0.0055 |  |  |

| es4_pm | 72 | +0.0387 [+0.023, +0.057] | -0.0025 [-0.005, +0.000] | +0.0647 [+0.047, +0.084] | -0.0004 [-0.002, +0.001] | +0.1220 [+0.058, +0.198] | su eps 0 -0.0025 |  |  |
| es4_seg4 | 72 | +0.0380 [+0.022, +0.057] | -0.0025 [-0.005, -0.000] | +0.0634 [+0.045, +0.085] | -0.0010 [-0.003, +0.000] | +0.1235 [+0.059, +0.201] | su eps 0 -0.0025 |  |  |
| es4_s | 72 | +0.0490 [+0.031, +0.069] | -0.0177 [-0.028, -0.009] | +0.0965 [+0.067, +0.126] | -0.0009 [-0.004, +0.003] | +0.1343 [+0.069, +0.212] | su eps 0 -0.0177 |  |  |
| **final** (engine defaults = es4, build e6) | 72 | +0.0380 [+0.023, +0.056] | -0.0024 [-0.005, +0.000] | +0.0644 [+0.047, +0.084] | -0.0012 [-0.003, +0.001] | +0.1212 [+0.056, +0.199] | su eps 0 -0.0024 |  |  |

The **final** row re-runs es4 through the new engine defaults (no parameters passed): it reproduces
es4 within the ~0.001 run-to-run noise of the control.

## Recommended (development) parameter set — es4

`protocol="robust"` with its defaults: Weighted 2017 restraints; EM before every stage from the 2nd
(`robust_start_stage` 1) and once more halfway through it (`robust_segments` 2), one refinement pass
at the final particle size (`robust_refine` 1); contact kernel `exp`, d0 = 2 radii, width learned
on the grid 0.5 ... 6 radii; eps learned (start 0.1, range 1e-4 ... 0.5); ensemble-mean
responsibilities; restraint weight 1 - (1 - r)^c; no weight floor; local-support evidence with a
window of 4 x the final particle size; isolated-contact filter and >= 6-radii violated-contact
removal as NucDynamics; no-contact term off.  Tag `robust-frozen` **not** created (decision for
the user).

### es4: every development stratum

Simulations, median-over-models cis Spearman (robust - nucdyn_gpu; mean [95 % CI]):

| dataset | stratum | n | robust | NucDynamics | diff |
|---|---|---|---|---|---|
| su2020_chr21 | all | 36 | 0.737 | 0.709 | +0.0278 [+0.017, +0.040] |
| takei2021_1mb | all | 36 | 0.854 | 0.807 | +0.0474 [+0.020, +0.080] |
| su2020_chr21 | eps 0 / 0.05 / 0.2 | 12 each | 0.839 / 0.736 / 0.636 | 0.840 / 0.714 / 0.573 | -0.0013 [-0.003, +0.000] / +0.0222 [+0.008, +0.036] / +0.0626 [+0.046, +0.082] |
| takei2021_1mb | eps 0 / 0.05 / 0.2 | 12 each | 0.869 / 0.861 / 0.832 | 0.871 / 0.838 / 0.712 | -0.0015 [-0.004, -0.000] / +0.0231 [+0.006, +0.045] / +0.1205 [+0.055, +0.199] |
| su2020_chr21 | depth 40 / 160 / 640 | 12 each | 0.654 / 0.766 / 0.792 | 0.645 / 0.732 / 0.751 | +0.0086 [-0.003, +0.022] / +0.0335 [+0.018, +0.050] / +0.0414 [+0.018, +0.068] |
| takei2021_1mb | depth 10 / 40 / 160 | 12 each | 0.808 / 0.867 / 0.887 | 0.806 / 0.839 / 0.776 | +0.0027 [-0.001, +0.007] / +0.0284 [+0.009, +0.052] / +0.1110 [+0.042, +0.196] |
| su2020_chr21 | rc 0.5 / 1 | 18 each | 0.685 / 0.790 | 0.652 / 0.766 | +0.0324 [+0.015, +0.053] / +0.0233 [+0.011, +0.036] |
| takei2021_1mb | rc 0.5 / 1 | 18 each | 0.820 / 0.888 | 0.755 / 0.859 | +0.0656 [+0.018, +0.127] / +0.0291 [+0.008, +0.060] |

Takei depth 160 (NucDynamics' known weak point; hickit 0.854 there): 0.887.  Scale-free RMSD
(median model, / Rg; sign flipped so + = better): +0.0375 [+0.023, +0.054]; no stratum worse (su eps
0 +0.0001, takei eps 0 +0.0097).  Ensemble-mean distances (cis Spearman): +0.0296 [+0.016, +0.046];
worst stratum su eps 0 -0.0023 [-0.006, +0.001].

Held-out (12 cell x fold): P1-dev -0.0004 [-0.0009, +0.0001]; per band (median score) 2-4 -0.0006
[-0.0008, -0.0003], 4-16 -0.0006, 16-64 -0.0002, 64-256 -0.0003, 256-inf -0.0002; trans -0.0000;
cis PR-AUC -0.0001.  Frac score bands mean +0.0004 [-0.0004, +0.0011]; per band -0.0005 / -0.0001 /
+0.0013 / +0.0016 / -0.0003; trans -0.0026 [-0.009, +0.004].  All |diff| < 0.003.

Real-data checks (development cells): training tables of the 12 folds — precision 1.730 vs 1.714
bead units (+0.016 [-0.030, +0.078]), %V>3 0.706 vs 0.673 (+0.033 [+0.013, +0.063]), %V>4 0.277
vs 0.239, Si-C-style violations 8.44 % vs 8.44 %, r vs GEO models 0.9707 vs 0.9713.  Full tables
cells 1-4 (vs the fig3 native GPU full runs): precision 1.636 vs 1.645, %V>3 0.497 vs 0.467, Si-C
8.38 % vs 8.38 %, r vs GEO 0.9766 vs 0.9767.

Cost (one H100, same node, same engine build, 100 kb, 10 models, development training tables
cell1 fold1/2, cell2 fold1): NucDynamics 41.2 / 38.4 / 35.8 s, robust 54.1 / 54.2 / 51.8 s
(**1.31-1.45 x**); peak RSS 266 / 237 / 224 MB vs 273 / 270 / 254 MB (+3 to +14 %).  The support
evidence takes 0.1-0.3 s, each EM update < 0.2 s; the extra time is the refinement pass.

## Open problems

* P1 (held-out contacts) does not move: on the Stevens tables the EM finds no false-contact
  component (eps at its floor), so robust = NucDynamics there.  Whatever limits NucDynamics on
  real data (e.g. over-confident ensembles in the frac score: hickit 0.734 vs 0.686) is not
  addressed by a noise model; it is the target of the sampling milestone.
* The remaining eps-0 cost on Su (-0.001 ... -0.003) comes from down-weighting true contacts in the
  kernel tail; a Gaussian kernel makes it -0.007 ... -0.010.
* The Poisson no-contact term improves every simulation stratum (+0.057) but hurts the held-out
  frac score by 0.027: kept in the engine (`robust_nc_scale`, off) for the sampling milestone,
  where it may be re-weighted by a calibrated capture efficiency.
* Su noise is hard to detect (weight AUC 0.87, noise weights 0.77 on average); the oracle bound
  on the E4 table (oracle 0.858, es4 0.763, NucDynamics 0.707) shows room left.

---

# Milestone M3 — speed and calibrated ensembles (development set only; not frozen)

Added before any run (PREREG §6, 2026-10-01): the matched-imaging development half (201 of the 403
Nagano serum cells, `robust_matched_split.py`, seed 20261001); the other 202 and the 2i cells are
untouched.  Engine additions (all off by default for the other protocols; regression hashes
unchanged on macOS and Linux): adaptive resolution (`robust_merge_below`, `robust_merge_nu`:
contact-free particles dropped, coordinates interpolated on the full grid), a sampling stage
after the final anneal (`robust_sample_temp/_steps/_dyn_steps/_snapshots`, constant temperature,
velocities re-drawn every temperature step), shorter / cooler refinement passes
(`robust_refine_temp_steps`, `robust_refine_temp_start`); `run_robust.py` takes the schedule from
`ROBUST_DEFAULTS` / `--params` / `$ROBUST_PARAMS`.  All M3 dev runs below are on CPU nodes
(16 threads; 5 models for simulations, 10 for held-out) unless stated.

## Profiling (where the CPU time goes)

* NucDynamics' schedule is 500 x 100 = 50,000 MD steps per stage; hickit runs 1,000 gradient
  iterations per stage on merged beads.  Our per step cost is not the problem: 0.2-0.35 us per
  particle-step (laptop, 1 thread; ~0.6-0.8 us on the Sherlock EPYC 9754), against ~3.4 us per
  bead-iteration for hickit.  The force evaluation (cell-grid repulsion) is ~85-100 % of a step.
* Tried and dropped: f32 repulsion loop (no gain on aarch64 or x86), Verlet lists with a small
  skin (rebuilt nearly every step at annealing temperatures: 6-8x slower), finer cell stencils.
* So the speed lever is the number of steps (and of particles at fine resolution).

## E9 — schedule length (sims + held-out, 72 / 12 dev units)

| variant | steps / stage | P2-dev | su eps 0 | takei eps 0 | worst sim stratum | held-out P1 | held-out frac |
|---|---|---|---|---|---|---|---|
| es4 (M2) | 500 x 100 | +0.0376 [+0.022, +0.056] | -0.0013 | -0.0015 | takei eps 0 -0.0015 | -0.0004 | +0.0004 |
| t100d50 | 100 x 50 | +0.0364 [+0.021, +0.054] | -0.0019 | -0.0009 | su eps 0 -0.0019 | +0.0002 | +0.0092 |
| t50d50 | 50 x 50 | +0.0365 [+0.021, +0.054] | -0.0009 | -0.0014 | takei eps 0 -0.0014 | +0.0005 | +0.0134 |
| t50d20 | 50 x 20 | +0.0346 [+0.019, +0.052] | **-0.0095 [-0.019, -0.002]** | -0.0039 | su eps 0 -0.0095 | -0.0008 | +0.0294 |
| t25d20 | 25 x 20 | +0.0321 [+0.017, +0.050] | **-0.0100 [-0.020, -0.003]** | -0.0053 | su eps 0 -0.0100 | -0.0020 | +0.0414 |
| t50d20dt2 | 50 x 20, dt x 2 | +0.0230 | -0.0155 | -0.0108 | su eps 0 -0.0155 | +0.0002 | +0.0170 |
| t50d50dt2 | 50 x 50, dt x 2 | +0.0237 | -0.0131 | -0.0092 | su eps 0 -0.0131 | +0.0003 | +0.0102 |
| t50d20m | 50 x 20 + merge <= 2 Mb | +0.0119 | **-0.0482** | **-0.0285** | su depth 40 -0.0486 | -0.0067 | +0.0194 |
| t100d50r0 | 100 x 50, no refinement | +0.0329 | -0.0002 | -0.0024 | takei eps 0 -0.0024 | +0.0004 | +0.0084 |
| t50d50r0 | 50 x 50, no refinement | +0.0332 | -0.0002 | -0.0023 | takei eps 0 -0.0023 | +0.0004 | +0.0140 |
| t50d50r10 | 50 x 50, refinement 10 x 50 | +0.0354 | -0.0013 | -0.0019 | takei eps 0 -0.0019 | +0.0004 | +0.0256 |
| t50d50r10c | as r10, refinement from T = 500 | +0.0349 | -0.0006 | -0.0021 | takei eps 0 -0.0021 | -0.0000 | +0.0148 |

* 2,500 MD steps per stage (20x fewer than NucDynamics) lose nothing on the dev set; 1,000 or 500
  steps cost ~0.01 at eps 0 (Su) — over the bar.  A larger time step hurts.  Shorter schedules
  leave the models less converged and more diverse, which raises the held-out contact-fraction
  score.
* **Adaptive resolution** (merging contact-free particles) at 50 kb on the sparse Su tables costs
  0.03-0.05: rejected at the resolutions the dev set covers.  It is kept only below 25 kb
  (`robust_merge_below` 25 kb in the speed configuration), where it is needed for speed (1 kb:
  2.56 M grid particles -> 0.195 M simulated) but **cannot be validated on the dev set** (no dev
  benchmark finer than 50 kb): open problem.

## E10 — sampling temperature (on t100d50; 50 temperature steps x 20 MD steps at T after the anneal)

| variant | P2-dev | takei eps 0 | worst sim stratum | held-out P1 | held-out frac |
|---|---|---|---|---|---|
| t100d50 (no sampling) | +0.0364 | -0.0009 | su eps 0 -0.0019 | +0.0002 | +0.0092 |
| T = 300 | +0.0363 | -0.0017 | su eps 0 -0.0020 | +0.0006 | +0.0227 |
| T = 1000 | +0.0354 | -0.0034 [-0.006, -0.001] | takei eps 0 -0.0034 | +0.0021 | +0.0452 |
| T = 3000 | +0.0316 | **-0.0094 [-0.012, -0.007]** | takei eps 0 -0.0094 | +0.0031 | +0.0877 |

(T in the engine's units: final anneal temperature 10, start 5000.)  The contact-fraction score
rises monotonically with T (hickit's dev level is +0.048 over NucDynamics); single-model
accuracy in the simulations falls at T = 3000 (just inside the 0.01 bar, CI excluding 0).
T = 1000 reaches hickit's contact-fraction level without a stratum loss > 0.005.

## E11 — candidates c1 / c2 (speed + sampling)

c1 = 50 x 50 per stage, refinement 10 x 50 from T = 500, sampling T = 1000 for 20 x 50 steps,
merge below 25 kb (dev numbers = variant t50d50r10c_T1000, identical at >= 50 kb).
c2 = c1 with a 20 x 20 sampling block (cheaper).

**c2, every development stratum** (robust - nucdyn_gpu; 95 % CI):

* Simulations (72 units, median-model cis Spearman): **P2-dev +0.0337 [+0.019, +0.052]** (cluster CI
  [+0.025, +0.044]); su eps 0 / 0.05 / 0.2: -0.0010 [-0.004, +0.002] / +0.0216 / +0.0534; takei
  eps 0 / 0.05 / 0.2: **-0.0042 [-0.008, -0.001]** / +0.0185 / +0.1139; su depth 40 / 160 / 640:
  +0.0124 / +0.0268 / +0.0348; takei depth 10 / 40 / 160: -0.0004 / +0.0231 / +0.1056; su rc
  0.5 / 1: +0.0310 / +0.0184; takei rc 0.5 / 1: +0.0600 / +0.0255.  RMSD/Rg: +0.036 better;
  ensemble-mean Spearman +0.0315.
* Held-out (12 cell x fold): **P1-dev +0.0015 [+0.0013, +0.0019]**; median-score bands +0.0014 /
  +0.0027 / +0.0021 / +0.0011 / +0.0004, trans +0.0001; cis (all separations) **-0.0018
  [-0.0023, -0.0015]**, all -0.0018, cis PR-AUC -0.0030.  **Contact-fraction score: bands mean
  0.7323 vs 0.6860 (+0.0463 [+0.042, +0.051]; hickit 0.734)**, every band +0.026 ... +0.059, trans
  +0.067, cis PR-AUC 0.136 vs 0.109.
* Real-data checks on the training tables: precision 1.57 vs 1.71 bead units (n.s.), %V>3 0.66 vs
  0.67, Si-C-style violations 9.2 % vs 8.4 % (+0.75 [+0.42, +1.05]), r vs GEO 0.9680 vs 0.9713
  (-0.003), RMSD/Rg vs GEO 0.119 vs 0.107 — the sampled models are slightly less tight, as intended.
* PREREG §5 rule on dev: P2 and P1 both > 0 with CIs excluding 0; worst stratum -0.0042 (> -0.01);
  cost below (rule 3 met).  Stratum losses within 0.01 but with CI excluding 0: takei eps 0
  (-0.004), held-out "cis all separations" (-0.002) and cis PR-AUC (-0.003).

## E12 — one-model wall time (Fig. 3d protocol: Stevens Cell 1, 1 model, Sherlock AMD EPYC 9754 for CPU, median of repeats)

hickit is single-threaded by design (lh3/hickit c945bb6 has no pthread / OpenMP), so the
like-for-like comparison is robust 1 thread vs hickit 1 thread; 16 threads and GPU are reported
separately.

| resolution | hickit 1 t | NucDynamics 1 t | **robust c2 1 t** | robust c1 1 t | NucDynamics 16 t | robust c2 16 t | NucDynamics GPU (H100) |
|---|---|---|---|---|---|---|---|
| 500 kb | 27 s | 273 s | **22.8 s** | 25 s | 189 s | 13.2 s | 17.8 s |
| 100 kb | 143 s | 1465 s | **112 s** | 125 s | 651 s | 34.5 s | 27 s |
| 50 kb | 222 s | 2869 s | **202 s** | 234 s | 1071 s | 57.9 s | 32 s |
| 20 kb | 578 s | 5711 s | **337 s** | 395 s | 1224 s | 89.4 s | 38 s |
| 10 kb | 1138 s | 12083 s | **498 s** | 639 s | 2183 s | 135 s | 50 s |
| 1 kb | 2083 s | — | **1183 s** | 1248 s | — | 259 s | 180 s |

robust c2 on 1 thread is faster than hickit at every resolution (1.10x at 50 kb, 1.18x at 500 kb,
1.28x at 100 kb, 1.7-2.3x at 20 kb ... 1 kb); 16 threads: 2-9x faster than hickit.  Peak RSS (1
thread) 91 MB (500 kb) ... 440 MB (1 kb).  Simulated particles at 1 kb: 195,112 of 2,564,332 grid
positions.  robust GPU (H100) timing: job submitted, result not collected (see status).  Margins
at 50 kb / 500 kb on 1 thread are thin (10-18 %).
