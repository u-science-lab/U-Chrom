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
