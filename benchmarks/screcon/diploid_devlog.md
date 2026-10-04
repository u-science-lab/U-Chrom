# Diploid EMber — development log

Development set only (PREREG.md §6, diploid addition of 2026-10-03): imaging-truth simulation
truth cells 1-2 of `su2020_genome` and `takei2021_1mb`; Dip-C GM12878 cells 1-3.  Held back:
truth cells 3-5, GM12878 cells 5-7, 9-15, 17, Uni-C GM12878.  EMber's haploid parameters are
the frozen ones throughout; only the diploid options below were compared.

Methods: `nucdyn` = NucDynamics 2017 protocol with diploid ambiguous restraints (combined
distance); `ember` (split) = EMber, every candidate copy pair its own restraint weighted by
P(true, c); `ember_nosplit` = EMber, candidates one ambiguous restraint weighted by P(true);
`*_prior` = hickit's 2-D imputed phase probabilities as the candidate prior; `hickit` = hickit
0.1.1, Dip-C pipeline (`-u -S`, schedule truncated at the final size).

## 1. Imaging-truth simulation (2026-10-03, `sherlock/dip_sim_run.sbatch`, job 46425229)

64 development tables: 2 datasets x truth cells 1-2 x depth 20 / 80 reads per Mb of the diploid
span x rc 0.5 / 1.0 x eps 0.05 / 0.2 x phased ends 0.2 / 0.4 (phase errors 1 %); 1 Mb final
particles (schedule 8, 4, 2, 1 Mb), 5 models, seed 1, one GPU (RTX 2080 Ti class).  Metrics =
median over models; "cis" = within a copy chain, "whole" = every copy-locus pair, "homolog" =
distances between the two copies of a chromosome, "swap" = fraction of chromosomes whose two
copies fit the truth better swapped, "phase" = accuracy of the most probable copy pair of
signal reads with an unphased end.

| dataset | method | Spearman cis | Spearman whole | homolog | swap | phase acc. |
| --- | --- | --- | --- | --- | --- | --- |
| su2020_genome | nucdyn | 0.916 | 0.744 | 0.718 | 0.039 | 0.923 |
| | ember (split) | 0.693 | 0.463 | 0.221 | 0.079 | 0.667 |
| | ember_prior (split) | 0.853 | 0.691 | 0.563 | 0.048 | 0.880 |
| | **ember_nosplit** | **0.937** | 0.838 | **0.836** | 0.020 | 0.889 |
| | ember_nosplit_prior | 0.936 | 0.837 | 0.838 | 0.031 | 0.909 |
| | hickit | 0.819 | **0.890** | 0.764 | 0.000 | 0.912 |
| takei2021_1mb | nucdyn | 0.787 | 0.566 | 0.413 | 0.056 | 0.823 |
| | ember (split) | 0.611 | 0.314 | 0.069 | 0.125 | 0.625 |
| | ember_prior (split) | 0.712 | 0.460 | 0.201 | 0.092 | 0.817 |
| | **ember_nosplit** | **0.823** | 0.676 | 0.494 | 0.036 | 0.823 |
| | ember_nosplit_prior | 0.822 | **0.684** | **0.511** | 0.030 | 0.860 |
| | hickit | 0.713 | 0.666 | 0.490 | 0.021 | **0.884** |

Paired differences vs `nucdyn` (mean over the 64 tables; 95 % bootstrap CI over the 4 truth
cells):

| metric | ember (split) | ember_nosplit | ember_nosplit_prior | hickit |
| --- | --- | --- | --- | --- |
| Spearman cis | −0.199 [−0.224, −0.175] | **+0.028 [+0.021, +0.036]** | +0.028 [+0.020, +0.036] | −0.086 [−0.110, −0.072] |
| Spearman whole | −0.266 [−0.334, −0.199] | +0.102 [+0.082, +0.114] | +0.105 [+0.083, +0.119] | **+0.123 [+0.100, +0.155]** |
| homolog Spearman | −0.421 | +0.099 [+0.077, +0.125] | **+0.109** | +0.061 |
| swap fraction | +0.054 | −0.019 | −0.017 | **−0.037** |
| phase accuracy | −0.227 | −0.017 [−0.034, +0.001] | +0.012 [−0.014, +0.037] | +0.025 [−0.011, +0.061] |

Strata (all methods, means): eps 0.05 → 0.2 costs `nucdyn` 0.07 cis, `ember_nosplit` 0.03;
EMber's lead holds at both depths, both contact radii and both phasing rates.  hickit is the
best whole-genome / homolog-placement method at depth 80 but loses ~0.1 cis at every condition
(its `-S` split drops contacts below imputed probability 0.75, and `-c5` isolation filtering at
1 Mb loci is harsh); its 2-D imputation gives the best phases (0.91 vs 0.89 EMber).

**Decision (diploid parameter `robust_dip_split`)**: `false` becomes the engine default.
Splitting the candidates into separately weighted restraints is the literal soft M-step, but
early in the annealing the posteriors of most ambiguous contacts are ~uniform, so every
candidate pulls with half weight and the two homologs are dragged onto each other (homolog
Spearman 0.22 / 0.07, whole-genome 0.46 / 0.31) — a mean-field collapse the combined-distance
restraint (a smooth max over candidates) avoids.  The EM still computes P(true, c); it enters
the restraint as P(true) and is reported as the phase posterior.
**Not adopted**: the hickit prior (phase accuracy +0.03, structure unchanged; adds a hickit
run).  It stays available (`run_diploid.py --hickit-prior`, `phase_prior=`).

Added afterwards (job 46440437, §3): the same grid at 10 %
phased ends — Dip-C GM12878 has only 8 % of the ends phased (0.7 % of the contacts at both
ends), well below the 20-40 % assumed at the outset.

## 2. Dip-C GM12878, development cells 1-3 (100 kb, 10 models, one RTX 2080 Ti)

Input: the authors' hickit phased pairs (0.89-1.09 M contacts; 8 % of the ends phased, 0.7 % of
the contacts at both ends).  References: the published Dip-C structure (`impute3.round4.clean.3dg`,
3 replicate runs; NucDynamics-based, 20 kb) and the published hickit structure, both resampled to
the 100 kb grid.  `ember` = split variant (rejected in §1), run with the split explicitly.

**Agreement with the published Dip-C structure** (median distance-matrix r per copy chain /
r over 2 M random particle pairs, whole genome incl. homologs and trans; all contacts, seeds 1
and 2; mean over the 3 cells):

| method | r per chain | r whole genome | precision (bead units) | wall time / cell |
| --- | --- | --- | --- | --- |
| nucdyn | 0.907 | 0.900 | 3.0 | ~1,055 s |
| ember (split) | 0.567 | 0.349 | 2.0 | ~115 s |
| ember_nosplit | 0.911 | 0.902 | 4.3 | ~105 s |
| ember_nosplit_prior (hickit prior) | 0.905 | 0.907 | 3.6 | ~150 s |
| ember_nbr (native prior) | 0.908 | 0.901 | 4.3 | ~120 s |
| published hickit vs published Dip-C | 0.952 | — | — | — |
| published Dip-C replicate runs (precision) | — | — | 0.24 | — |

Per cell (r per chain, seed 1 / 2): cell 1 nucdyn 0.939 / 0.940, ember_nosplit 0.945 / 0.944,
ember_nbr 0.943 / 0.945; cell 2 0.940 / 0.913, 0.927 / 0.906, 0.913 / 0.894; cell 3 0.851 /
0.859, 0.869 / 0.875, 0.875 / 0.877.  Our hickit runs (masked input, below) reach 0.949-0.959
per chain and 0.975-0.985 whole genome against the published Dip-C structure — **hickit agrees
with the published structures better than any of our methods** (it is the pipeline that produced
one of them, and its schedule / filters are close to Dip-C's), and the published structures are
far more reproducible between runs (0.24 vs 3-4 bead units RMSD to the ensemble mean): EMber's
finite-temperature sampling stage (frozen haploid parameter) keeps its ensembles broad.

**Held-out contacts on copy chains** (3 folds x 3 cells; ROC-AUC of the median distance;
strict = positives with both ends phased, ~100 per fold; cis-2 Mb = also one-end-phased cis reads
< 2 Mb, ~620 per fold):

| method | strict cis | strict trans | strict all | cis-2 Mb cis | cis-2 Mb all |
| --- | --- | --- | --- | --- | --- |
| nucdyn | 0.904 | 0.810 | 0.830 | 0.836 | 0.824 |
| ember (split) | 0.816 | 0.799 | 0.774 | 0.748 | 0.739 |
| ember_nosplit | 0.902 | 0.811 | 0.827 | 0.837 | 0.824 |
| ember_nosplit_prior | 0.903 | 0.813 | 0.830 | 0.837 | 0.825 |
| ember_nbr | 0.905 | 0.811 | 0.830 | 0.836 | 0.824 |
| hickit | 0.843 | 0.810 | 0.798 | 0.744 | 0.739 |

**Phase hold-back** (10 % of the phased ends unphased, seed 1; accuracy of the inferred
haplotype of the masked ends; mean over cells):

| method | all | cis < 10 Mb | cis >= 10 Mb | trans | fraction with p >= 0.75 (its accuracy) |
| --- | --- | --- | --- | --- | --- |
| nucdyn (closest candidate) | 0.803 | 0.711 | 0.965 | 0.975 | 1.00 (0.803) |
| ember (split) | 0.714 | 0.642 | 0.820 | 0.896 | 0.41 (0.939) |
| ember_nosplit | 0.800 | 0.703 | 0.975 | 0.988 | 0.54 (0.989) |
| hickit (2-D imputation) | 0.853 | 0.812 | 0.929 | 0.909 | 0.72 (0.965) |
| ember_nosplit_prior | 0.888 | 0.838 | 0.975 | 0.991 | 0.80 (0.973) |
| **ember_nbr** | **0.888** | **0.838** | **0.974** | **0.991** | 0.80 (0.974) |

The structure resolves distant (cis >= 10 Mb, trans) phases better than hickit's 2-D imputation
(0.97-0.99 vs 0.91-0.93); close cis phases (both homologs fold alike at 100 kb) need the
neighbourhood votes — combining both is best.

## 3. Phase prior (2026-10-03; `robust_dip_nbr_prior` registered in PREREG §6 before any run)

Native 2-D neighbourhood prior (`diploid::neighbour_prior`, hickit's `hk_impute` with hickit's
settings) — check against hickit itself on GM12878 cell 1 (1 Mb plumbing run, 10 % masked):
masked-end accuracy 0.855 (native) vs 0.855 (`hickit -u`), per stratum identical to 0.002, 3 s
vs 38 s.

Imaging truths, all 96 development tables (now incl. 10 % phased ends, job 46446007), paired vs
`ember_nosplit` (95 % CI over the 4 truth cells):

| metric | ember_nbr | ember_nosplit_prior (hickit) |
| --- | --- | --- |
| Spearman cis | −0.000 [−0.001, +0.001] | −0.001 [−0.003, +0.002] |
| Spearman whole | +0.003 [−0.002, +0.008] | −0.004 [−0.012, +0.004] |
| homolog Spearman | +0.012 [−0.000, +0.025] | +0.002 [−0.006, +0.011] |
| swap fraction | −0.000 | +0.003 |
| phase accuracy | **+0.058 [+0.041, +0.075]** | +0.026 [+0.019, +0.033] |

Worst `ember_nbr − ember_nosplit` stratum (dataset, phased fraction, eps, depth, rc): −0.004
(whole-genome, 10 % phased); phase accuracy gains +0.03 to +0.08 in every stratum.  At 10 %
phased ends: phase accuracy ember_nbr 0.886, hickit 0.846, nucdyn 0.852, ember_nosplit 0.834.

GM12878 (§2): phase hold-back +0.088 (0.888 vs 0.800; hickit 0.853); held-out AUCs within
0.003; agreement with the published structures −0.003 per chain / −0.001 whole genome on
average — cell 2 is −0.013 per chain, inside that cell's seed-to-seed spread (0.021-0.027 for
every method).

**Decision**: `robust_dip_nbr_prior = true` becomes the EMber default (no hickit dependency;
best phases on both kinds of data; no structure metric worse beyond run-to-run noise; the cell-2
per-chain −0.013 is the one number past 0.01 and is reported as such).  The hickit prior is not
adopted (same real-data phases, worse on the simulations, needs hickit).

## 4. Frozen diploid configuration (to be tagged before the test)

EMber haploid parameters = tag `robust-frozen`; diploid: `diploid_cis_sep` 10 Mb (not tuned),
`robust_dip_split` false, `robust_dip_nbr_prior` true (hickit's settings), no external phase
prior.  The NucDynamics-2017 diploid baseline and hickit are untouched.
