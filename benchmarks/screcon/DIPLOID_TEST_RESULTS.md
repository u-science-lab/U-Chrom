# Pre-registered diploid test: EMber diploid vs NucDynamics-diploid and hickit

Run once, 2026-10-04, with the frozen configuration (tag `ember-diploid-frozen`, commit 0b467dc;
engine build `dipfrozen` of that commit, regression hashes unchanged; PREREG.md §6 "diploid
configuration frozen").  Test units exactly as pre-registered: imaging-truth simulation truth
cells 3-5 of `su2020_genome` and `takei2021_1mb`, all 24 conditions (144 tables; 1 Mb, 5 models,
seed 1); Dip-C GM12878 cells 5-7, 9-15, 17 (11 cells; the authors' hickit phased pairs; 100 kb,
10 models, seed 1; references, all-contact runs with seeds 1 and 2, 10 % phase hold-back,
3-fold held-out).  Jobs `sherlock/dip_sim_run.sbatch SET=test` and `sherlock/dip_real.sbatch`
(GPUs: RTX 2080 Ti x 7 cells, TITAN Xp x 2, A100 x 1, H100 x 1); analysis `diploid_test.py`
(written before the run), output `results/diploid_test.json`.  Nothing was changed after these
numbers were seen.  Methods: EMber = frozen EMber diploid; NucDynamics = 2017 protocol with
diploid ambiguous restraints; hickit = 0.1.1 Dip-C pipeline (`-u -S`).

## Primary endpoints

| endpoint | units | difference [95 % CI] | criterion | met |
| --- | --- | --- | --- | --- |
| D1 simulation within-chain Spearman, EMber − NucDynamics | 6 truth cells (144 tables) | **+0.027 [+0.013, +0.040]** | CI > 0 | yes |
| D2 GM12878 strict held-out cis AUC, EMber − NucDynamics | 33 cell x fold | **+0.000 [−0.002, +0.002]** | CI lower > −0.01 | yes |
| D3 GM12878 masked-phase accuracy, EMber − hickit | 11 cells | **+0.025 [+0.022, +0.028]** | CI > 0 | yes |

No secondary stratum is worse by more than 0.01 with a CI excluding 0.  **By the pre-registered
rule: EMber diploid is better than NucDynamics-diploid and hickit on this test.**

## Secondary (all strata, differences [95 % CI])

Simulation, EMber − NucDynamics (unit = truth cell):

| stratum | within-chain Spearman | whole-genome Spearman | homolog Spearman | − swapped homologs |
| --- | --- | --- | --- | --- |
| all | +0.027 [+0.013, +0.040] | +0.087 [+0.046, +0.122] | +0.078 [+0.034, +0.127] | +0.009 [−0.002, +0.021] |
| su2020_genome | +0.013 [−0.007, +0.024] | +0.089 [−0.004, +0.147] | +0.111 [+0.017, +0.173] | +0.010 [−0.004, +0.020] |
| takei2021_1mb | +0.042 [+0.037, +0.049] | +0.084 [+0.062, +0.102] | +0.046 [+0.026, +0.061] | +0.008 [−0.009, +0.033] |
| depth 20 / 80 | +0.011 / +0.044 | +0.066 / +0.107 | +0.067 / +0.089 | +0.008 / +0.009 |
| rc 0.5 / 1.0 | +0.039 / +0.016 | +0.098 / +0.075 | +0.105 / +0.051 | +0.014 / +0.003 |
| eps 0.05 / 0.2 | +0.007 / +0.048 | +0.057 / +0.116 | +0.060 / +0.097 | +0.010 / +0.008 |
| phased 0.1 / 0.2 / 0.4 | +0.023 / +0.027 / +0.033 | +0.083 / +0.093 / +0.084 | +0.071 / +0.076 / +0.088 | +0.007 / +0.013 / +0.007 |

Means per dataset (within-chain / whole / homolog / phase accuracy of unphased ends):
su2020_genome EMber 0.850 / 0.800 / 0.748 / 0.874, NucDynamics 0.837 / 0.711 / 0.637 / 0.873,
hickit 0.593 / 0.727 / 0.562 / 0.809; takei2021_1mb EMber 0.803 / 0.632 / 0.468 / 0.887,
NucDynamics 0.762 / 0.549 / 0.422 / 0.808, hickit 0.671 / 0.558 / 0.379 / 0.865.

GM12878 held-out (ROC-AUC of the median distance; EMber − NucDynamics, unit = cell x fold):

| evaluation set | EMber | NucDynamics | hickit | EMber − NucDynamics |
| --- | --- | --- | --- | --- |
| strict (both ends phased; mean 81 positives per fold): cis | 0.816 | 0.816 | 0.780 | +0.000 [−0.002, +0.002] |
| strict: trans | 0.685 | 0.685 | 0.683 | −0.000 [−0.003, +0.002] |
| strict: all | 0.711 | 0.712 | 0.695 | −0.001 [−0.003, +0.000] |
| cis-2 Mb (+ one-end-phased cis < 2 Mb; 421 per fold): cis | 0.786 | 0.781 | 0.704 | +0.005 [+0.003, +0.006] |
| cis-2 Mb: trans | 0.688 | 0.688 | 0.688 | −0.000 [−0.003, +0.002] |
| cis-2 Mb: all | 0.758 | 0.755 | 0.689 | +0.003 [+0.002, +0.005] |

GM12878 masked-phase accuracy (10 % of the phased ends unphased):

| | all | cis < 10 Mb | cis >= 10 Mb | trans |
| --- | --- | --- | --- | --- |
| EMber | 0.911 | 0.879 | 0.970 | 0.990 |
| hickit (2-D imputation) | 0.886 | 0.868 | 0.935 | 0.904 |
| NucDynamics (closest candidate) | 0.773 | 0.682 | 0.959 | 0.970 |
| EMber − hickit [95 % CI] | +0.025 [+0.022, +0.028] | +0.011 [+0.008, +0.015] | +0.035 [+0.031, +0.040] | +0.086 [+0.077, +0.096] |

EMber is ahead of hickit in every one of the 11 cells (0.888-0.924 vs 0.851-0.902).

## Descriptive (not thresholded)

* **Agreement with the published structures** (median r per copy chain / whole genome, all
  contacts, mean over cells and seeds): EMber 0.882 / 0.862 vs published Dip-C, 0.858 / 0.819 vs
  published hickit; NucDynamics 0.865 / 0.872 and 0.845 / 0.826; our hickit runs (masked input)
  0.946 / 0.971 vs published Dip-C; published hickit vs published Dip-C 0.950.  The published
  structures are hickit's / Dip-C's own outputs, so this measures closeness to those pipelines
  (hickit, the pipeline itself, is closest), not accuracy.
* **Ensemble precision** (RMSD to the superposed ensemble mean, bead units): EMber 6.0, NucDynamics
  4.4; the published Dip-C replicate runs ~0.2.  EMber samples a finite-temperature ensemble
  (frozen sampling stage), so its spread is a property of the ensemble, not a measured error.
* **Wall time** (all contacts, 10 models, 100 kb, mostly RTX 2080 Ti): EMber mean 156 s (median
  149 s), NucDynamics-diploid mean 1,340 s (median 1,236 s) — 8.6x.

## Reading

* EMber's structures are at least as good as NucDynamics' on every structural endpoint and
  clearly better on the simulated whole-genome and homolog placement (+0.09 / +0.08) and in noisy
  (eps 0.2: +0.05 within-chain) and deep conditions.  On the GM12878 held-out contacts the two are
  equal (strict) or EMber slightly ahead (cis-2 Mb, +0.005); both are well ahead of hickit on cis
  (0.816 vs 0.780; 0.786 vs 0.704).
* The phase gain over hickit comes from combining hickit-style neighbourhood votes with the
  structure: distant cis and trans phases (0.97-0.99) are where the structure helps most.
* Limits: the strict held-out set is small (81 positives per fold; 0.7 % of GM12878 contacts are
  phased at both ends); simulations are at 1 Mb on imaging loci (Takei homologs split by a
  heuristic); 100 kb only — finer resolutions and Uni-C (needs read-level phasing) are not tested.
