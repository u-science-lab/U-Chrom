# Pre-registration: new single-cell reconstruction method vs NucDynamics

Written **2026-10-01, before any code of the new method exists**.  Changes to this file
after the test set has been looked at must be listed in §6 with the date and the reason.

## 1. Question

Does the new method (working name **`robust`**; noise-aware observation model, §7)
reconstruct single-cell genome structures better than
NucDynamics, as implemented in U-Chrom (native engine, protocol `nuc_dynamics_2017`,
GPU), on the neutral tests of this directory?

## 2. Development and test sets (fixed now)

| | development (tuning allowed) | test (reported, looked at once) |
|---|---|---|
| held-out test, Stevens 2017 (`heldout.py`) | cells 1-4, folds 1-3 | cells 5-8, folds 1-3 |
| simulation, Su 2020 chr21 (`simulate.py`) | truth cells 1-2, all conditions | truth cells 3-5, all conditions |
| simulation, Takei 2021 1 Mb | truth cells 1-2, all conditions | truth cells 3-5, all conditions |
| real-data checks (`score_real.py`, precision, violations) | cells 1-4 | cells 5-8 |

* Every parameter of the new method (and every design choice) is fixed on the development
  set only.  The test runs are made once, with the frozen parameters recorded in the commit
  that freezes the method (tag `robust-frozen`).
* The NucDynamics baseline runs already exist for both sets (`runs/screcon`, 2026-09-29/30);
  they are not re-tuned.  Other methods (original NucDynamics, Si-C, hickit, baselines)
  are reported alongside but are not part of the decision.
* The split, the folds, the evaluation pairs and the simulated reads are the existing ones
  (seeded, `heldout.py split`, `simulate.py grid`); nothing is regenerated.

## 3. Primary endpoints (test set)

Both are paired differences new − NucDynamics over the same units, with a 95 % bootstrap
CI resampling the units (cells for P1, truth cells × conditions grouped by truth cell for P2).

* **P1 — held-out contacts**: ROC-AUC, median-distance score, cis, mean over the five
  separation bands, per (cell, fold); 12 units.
* **P2 — imaging truth**: Spearman r of cis distances, median model vs truth, per
  simulation (dataset × truth × depth × contact radius × noise); 2 × 3 × 18 = 108 units.

## 4. Secondary endpoints (reported in full, every stratum)

* held-out: every separation band; trans; the contact-fraction score; PR-AUC.
* simulation: every noise level, depth, contact radius and dataset; scale-free RMSD;
  ensemble-mean distances.
* real data: ensemble precision (ED Table 2 metric), NucDynamics-style and Si-C-style
  violations, agreement with the published models.
* cost: wall time and peak memory, one H100, same input, 10 models.

## 5. Decision rule

The new method is called **better than NucDynamics** only if

1. P1 and P2 are both > 0 with 95 % CIs excluding 0, **and**
2. no secondary stratum of §4 (held-out band / trans / score type; simulation noise /
   depth / radius / dataset) is worse by more than 0.01 with a 95 % CI excluding 0, **and**
3. wall time on one H100 is at most 3 × NucDynamics' at the same resolution.

Otherwise the result is reported as it is: "better on X, equal on Y, worse on Z".  The
paper reports every endpoint of §3-§4 whatever the outcome.

## 6. Changes after the test set was looked at

(none)

### Additions made before the test set was looked at

* **2026-10-01 — matched-imaging analysis (added secondary analysis, not pre-registered in
  §3-§4; for development of milestone M3 "calibrated ensembles").**  The matched-modality
  comparison of `matched.py` (Nagano 2017 haploid serum mESC structures vs Takei 2021 E14
  imaging) is added as a secondary analysis.  Its cells are split *before any robust run on
  them*: the 403 serum cells of `nagano/serum/manifest.tsv`, sorted by name and permuted with
  `numpy.random.default_rng(20261001)` (`robust_matched_split.py`), first 201 = development
  (tuning allowed), remaining 202 = held back (run once, with the frozen parameters, like the
  test set); the Nagano 2i cells are not used for tuning.  Development metrics: the
  per-pair variability ranking (`variab.cv_spearman`), the variability ratio
  (`variab.cv_ratio`), radial position per locus (`radial.locus_spearman`) and the
  P(s)-detrended pair medians (`pair.median_resid_spearman`), each against NucDynamics and
  hickit on the same development cells and the size-matched imaging ceiling.  This analysis
  is not part of the decision rule of §5.
* **2026-10-01 — milestone M3 (speed and sampling) is developed on the development set of
  §2 only; the method is not frozen yet.**  Schedule / resolution changes and the sampling
  stage are accepted only if the development held-out (P1 and strata) and simulation (P2 and
  strata) numbers do not get worse (`robust_devlog.md`).
* **2026-10-02 — method frozen (tag `robust-frozen`).**  The method tested is protocol `"robust"`
  of `native/nucdyn` with its engine defaults (= `ROBUST_DEFAULTS` of `run_robust.py`, the
  development candidate "c2" of `robust_devlog.md`): 2017 NucDynamics base (particle sizes,
  isolation filter, violated-contact removal, restraints, repulsion); EM re-weighting of contact
  restraints from stage 2 on, twice per stage (exponential kernel, d0 = 2 radii, width and eps
  learned); local-support evidence (window 4 x final particle size); 50 x 50 MD steps per stage;
  one refinement pass at the final size (10 x 50 steps from T = 500); sampling at T = 1000 for
  20 x 20 steps after the final anneal; contact-free particles merged below 25 kb.  Test runs
  use the build of the tagged commit and `run_robust.py` with no `--params`, the same models /
  seeds / resolutions as the NucDynamics baseline runs of each test (10 models held-out / real,
  5 models simulations, seed 1).  No parameter or code change to the method after this line.

## 7. The method being tested (design as of this date)

* Observation model: each observed contact is a mixture of a true proximity and a false
  contact (rate ε estimated from the data), so contacts inconsistent with the structure lose
  weight (EM-style re-weighting) instead of being pulled together; pairs without a contact
  give a weak "not close" term weighted by the capture efficiency q; contact radius, q and ε
  are learned from the data.
* Priors: chain connectivity, excluded volume, nuclear confinement (as NucDynamics);
  later, distance statistics calibrated on chromatin tracing.
* Inference (later milestones): GPU sampling (Langevin / replica exchange) for calibrated
  ensembles; adaptive resolution with an effective-resolution map.
* Implementation: the U-Chrom native engine (`native/nucdyn`), same particle / neighbour
  grid / batched-ensemble machinery.
