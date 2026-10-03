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

Pending (job 46440437, after this decision, reported as an addition): the same grid at 10 %
phased ends — Dip-C GM12878 has only 8 % of the ends phased (0.7 % of the contacts at both
ends), well below the 20-40 % assumed at the outset.

## 2. Dip-C GM12878, cell 1 (100 kb, 10 models)

See §3 for all three development cells; first numbers (cell 1, before the default change, so
`ember` = split): agreement with the published Dip-C structure (median distance-matrix r per
copy chain / whole genome): ember (split) 0.56 / 0.44, **ember_nosplit 0.945 / 0.962**,
nucdyn 0.940 / 0.939 (published hickit structure vs published Dip-C: see §3).  Wall time on one
RTX 2080 Ti: EMber 103-115 s, NucDynamics 2017 ~1,055 s.
