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

* **2026-10-03 — diploid (homolog-resolved) extension: development set fixed before any diploid
  run on benchmark data.**  EMber is extended to phased diploid input (`native/nucdyn/src/diploid.rs`:
  one chain per chromosome copy; the copy pair of a contact with an unphased end is a latent
  variable of the same mixture model).  This is a *new* analysis, not part of the haploid test of
  §3-§5, whose result (§8) is unchanged.  Rules:
  * **Frozen**: every haploid parameter of EMber (the `robust_*` defaults of tag `robust-frozen`)
    stays as frozen; the haploid code path is pinned by `native/nucdyn/tests/regression.rs`.
  * **Diploid parameters that may be tuned, on the development units below only**:
    `robust_dip_split` (each candidate copy pair its own restraint vs one ambiguous restraint
    weighted by P(true)), the use of a prior over candidate copy pairs (none / hickit's imputed
    `phase_prob`), and — only if the development numbers call for it — the same-homolog rule for
    close unphased cis ends (`diploid_cis_sep`, 10 Mb from hickit's imputation prior, not tuned
    unless reported here).  Every tuned value and the development numbers behind it go to
    `diploid_devlog.md`.
    *Added 2026-10-03, before any run with it*: `robust_dip_nbr_prior` — a 2-D neighbourhood
    phase prior computed inside EMber (phased contacts within hickit's imputation radius vote for
    the copy pair of a contact with an unphased end; hickit's neighbour count, weights,
    pseudo-count and radius are taken as they are, not tuned): on / off, decided on the
    development units only, adopted only if phase accuracy improves without any structure metric
    or stratum getting worse by more than 0.01.  The hickit-imputation prior is re-evaluated on
    the same terms.  The NucDynamics-2017 diploid baseline (ambiguous restraints) and
    hickit (Dip-C schedule, `-u` imputation, `-S` split at 0.75) are not tuned.
  * **Development units**: imaging-truth simulations — Su 2020 genome-scale IMR90 (1,041 loci,
    homologs resolved experimentally) and Takei 2021 1 Mb mESC (homologs split by the screcon
    heuristic), diploid truth cells 1-2 of each (cells drawn with seed 1 by
    `diploid_sim.py truth`), all conditions; Dip-C GM12878 (Tan et al. 2018, GSE117876) cells
    1-4 (GSM3271347-GSM3271350), all checks (held-out phased contacts, agreement with the
    published Dip-C structures, run-to-run precision).
    *Amended 2026-10-03, before any real-data run*: the input is the authors' hickit
    re-processing (GSM3314359+, phased pairs), which GEO lacks for cells 4, 8 and 16 (cell 8 has
    no structure at all), so the GM12878 development cells are 1-3.
  * **Held back (one-shot test, after freezing the diploid parameters with a tag)**: truth cells
    3-5 of both simulation datasets; Dip-C GM12878 cells 5-7, 9-15 and 17 (11 cells); Uni-C GM12878 (Gao et al. 2025,
    GSE267873, 11 cells) entirely — its split (proposed: cells sorted by GSM, first 3 for a
    resolution / runtime pilot that does not set parameters, remaining 8 test) is fixed in this
    file before any Uni-C reconstruction.

* **2026-10-04 — diploid configuration frozen (tag `ember-diploid-frozen`) and the diploid test
  pre-registered, before any test run.**
  * **Frozen method** ("EMber diploid"): protocol `"robust"` of `native/nucdyn` at the tagged
    commit with its engine defaults — the haploid parameters of tag `robust-frozen` unchanged, and
    `diploid_cis_sep` = 10 Mb, `robust_dip_split` = false, `robust_dip_nbr_prior` = true, no external
    phase prior, ploidy `"auto"`.  Development record: `diploid_devlog.md`.  No parameter or code
    change to the method after this line.
  * **Comparators** (not tuned): NucDynamics 2017 protocol with diploid ambiguous restraints
    (`run_diploid.py --method nucdyn`), hickit 0.1.1 Dip-C pipeline (`run_hickit.py --diploid`).
  * **Test units** (never run before this entry): imaging-truth simulation truth cells 3-5 of
    `su2020_genome` and `takei2021_1mb`, all 24 conditions (depth 20 / 80, rc 0.5 / 1.0, eps 0.05 / 0.2,
    phased ends 0.1 / 0.2 / 0.4; 144 tables), 1 Mb, 5 models, seed 1 (`dip_sim_run.sbatch SET=test`);
    Dip-C GM12878 cells 5-7, 9-15, 17 (11 cells; hickit phased pairs), 100 kb, 10 models, seed 1
    (`dip_real.sbatch`: references, all contacts with seeds 1 and 2, phase hold-back 10 % seed 1,
    held-out 3 folds x 10 % seed 1).
  * **Primary endpoints** (paired differences, 95 % percentile bootstrap, `diploid_test.py`, written
    before the test):
    **D1** simulation within-chain Spearman, EMber − NucDynamics, unit = truth cell (6);
    **D2** GM12878 strict held-out cis ROC-AUC (positives with both ends phased), EMber − NucDynamics,
    unit = cell x fold (33);
    **D3** GM12878 masked-phase accuracy, EMber − hickit, unit = cell (11).
  * **Secondary** (reported in full): simulation within-chain / whole-genome / homolog Spearman and
    swapped homologs per dataset, depth, rc, eps and phased fraction; held-out strict trans / all and
    cis-2 Mb cis / trans / all AUC; masked-phase accuracy cis < 10 Mb / cis >= 10 Mb / trans (vs
    hickit).  **Descriptive only**: agreement with the published Dip-C / hickit structures (those are
    hickit's / Dip-C's own outputs, so agreement measures closeness to those pipelines, not accuracy),
    ensemble precision (EMber samples a finite-temperature ensemble; its spread is reported as a
    number, not as an error), run-to-run agreement, wall time.
  * **Decision rule**: EMber diploid is called **better than NucDynamics-diploid and hickit on this
    test** only if the D1 and D3 CIs are above 0, the D2 CI lower bound is above −0.01
    (non-inferiority), and no secondary stratum is worse by more than 0.01 with a CI excluding 0.
    Otherwise reported as it is ("better on X, equal on Y, worse on Z").
  * **Not part of this test**: Uni-C GM12878 (GSE267873) — its pairs carry no phases; it needs
    read-level phasing (re-alignment with GM12878 trio-phased SNPs) and gets its own
    pre-registration later.  Resolutions finer than 100 kb.

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

## 8. Test results (2026-10-02)

Run once with the frozen method (tag `robust-frozen`); full tables in `TEST_RESULTS.md`.
P1 = +0.0028 [+0.0025, +0.0031], P2 = +0.0367 [+0.0291, +0.0448]; no §4 stratum worse by more
than 0.01 (largest losses: simulation eps 0, -0.0045; held-out PR-AUC cis, -0.0031); H100 wall
time 0.2x NucDynamics.  By §5: **better than NucDynamics.**  Not thresholded by §5 but reported:
real-data ensemble precision is worse (RMSD to mean 3.0 vs 1.1 bead units, cells 5-8 full
tables) and the agreement with the published models slightly lower (r 0.950 vs 0.963).

## 9. Name (2026-10-03)

The frozen method "robust" is published in U-Chrom as **EMber** (`uchrom.recon.sc.reconstruct_ember`,
engine protocol `"robust"` with the alias `"ember"`).  Naming only: the method, its frozen
parameters and the results of §8 are unchanged.

## 10. Diploid test results (2026-10-04)

Run once with the frozen diploid configuration (tag `ember-diploid-frozen`); full tables in
`DIPLOID_TEST_RESULTS.md`, numbers in `results/diploid_test.json`.  D1 = +0.027 [+0.013, +0.040],
D2 = +0.000 [−0.002, +0.002] (non-inferiority bound −0.01 met), D3 = +0.025 [+0.022, +0.028]; no
secondary stratum worse by more than 0.01.  By the pre-registered rule: **EMber diploid is better
than NucDynamics-diploid and hickit on this test.**  Descriptive: closer to NucDynamics than to
hickit in agreement with the published (hickit / Dip-C) structures; broader ensembles (sampling);
8.6x faster than NucDynamics-diploid.

## 11. Deep low-phasing diploid extension (2026-10-04, registered before any run of it; written as §10 on its branch — the tag message of `ember-deep-frozen` says §10 — and renumbered when merged after the diploid test results)

**Why.**  A demonstration of the frozen diploid EMber (tag `ember-diploid-frozen`, §6) on scMicro-C
GM12878 (Wu et al. 2025, GEO GSE192759; 2.2-3.0 M contacts per cell, 5.6 % of the ends phased,
hickit `impute.pairs`) gave structures that do not reproduce between seeds (cell 035: per-copy
distance r 0.58 at 100 kb, 0.54 at 20 kb, 0.47 at 5 kb; the authors' five hickit runs agree at
0.98-0.99, our own hickit run at 0.96), and the NucDynamics-2017 diploid protocol of the same engine
does no better (0.59).  On Dip-C GM12878 (§6 development cells, ~1 M contacts, 8 % phased) the same
scorer gives 0.98.  This section registers a development cycle for a fix.  **The frozen diploid
configuration of §6 and its test are untouched**: every new setting below defaults to off, the
frozen code path stays pinned by `tests/regression.rs`, and the §6 test results are reported as
they are.

* **Already seen (before this entry)**: frozen-EMber runs of cells 035, 024, 320, 047, 028 at
  100 / 20 / 10 / 5 kb (seeds 1, 2); scores looked at for 035 and 024 only (and the hickit-replicate
  agreement of 320); for 035 also 2 / 1 kb runs, a held-out split at 10 kb, NucDynamics-diploid,
  EMber with hickit's phase prior and our hickit run at 100 kb (`highres_*.sbatch`,
  `paper/fig3/results/highres/summary.json`).  The frozen-EMber scores of 047 and 028 exist on disk
  but were not inspected and are not used for any decision.
* **Development cells** (fixed now): GSM5764669 cell 035, GSM5764658 cell 024, GSM5764954 cell 320.
  Plus the §6 Dip-C GM12878 development cells 1-3 (non-regression only).
* **Held back** (one-shot test after a freeze with a new tag): scMicro-C cells with the authors'
  structures among the downloaded ones — 047, 028, 017, 049, 032, 027, 014 (GSM5764681, GSM5764662,
  GSM5764651, GSM5764683, GSM5764666, GSM5764661, GSM5764648).  Cells 026 and 051 (no authors'
  structures, 33 % / 12 % cis) are excluded.
* **Diagnostics** (development cells only; descriptive, they set no parameter): reproducibility of
  frozen EMber after down-sampling cell 035 to Dip-C depth (1.0 M contacts) and after removing cis
  contacts < 20 kb; the noise estimate ε per stage; ambiguous restraints per stage; agreement per
  separation band (< 2 / 2-20 / > 20 Mb).
* **New tunables** (engine parameters, default = off = the frozen behaviour; values tried only on the
  development cells, every value and number recorded in `diploid_devlog.md`):
  1. `robust_dip_commit` τ (0 = off; tried 0.75 = hickit's `-S` threshold, and 0.9): a contact whose
     phase prior (neighbourhood prior x external prior) gives one candidate copy pair probability
     >= τ becomes unambiguous on that pair (hard phasing, hickit-like);
     `robust_dip_commit_rest` = `keep` (the other ambiguous contacts stay ambiguous) or `drop`
     (they are not used, as hickit `-S`).
  2. `robust_dip_commit_stage` (staged commitment; -1 = off; tried: after the 2 Mb stage and after the
     400 kb stage): from that stage on, contacts are committed by the EM posterior P(c | true) of the
     current structure times the prior, with the same τ and rest rule.
  3. `dip_isolation_nei` / `dip_isolation_radius` (0 = off; tried hickit's `-r10m -c5`: a contact
     needs >= 5 other contacts with both ends within 10 Mb, Chebyshev; and `-r1m -c1`): an extra
     isolated-contact filter before stage 1.
  Combinations of 1-3 are allowed.  Nothing else of EMber is changed; if the development numbers
  call for any other change (e.g. ε bounds), it is added here, dated, before it is run.
* **Development criteria** (all must hold for a candidate to be adopted; fixed now):
  * **C1 reproducibility**: per-copy distance r between seed 1 and seed 2 (`highres.py score`,
    10 models each, median over model pairs and copy chains) at 20 kb: >= 0.90 in the median over
    the three scMicro-C development cells and >= 0.85 in each.
  * **C2 held-out contacts**: strict held-out cis ROC-AUC (`diploid_heldout.py split`, 10 % of the
    reads, fold 1 of seed 1, eval grid 100 kb, positives with both ends phased; `heldout.py score`
    median distance) at 100 kb, mean over the three development cells: candidate − NucDynamics-diploid
    (same split) >= −0.01.
  * **C3 no regression where diploid EMber works**: Dip-C GM12878 cells 1-3, 100 kb, the §6
    development checks (`dip_real.sbatch` steps full / mask / heldout): per-chain and whole-genome r
    vs the published Dip-C structure, strict held-out cis ROC-AUC (3 folds), masked-phase accuracy —
    each, mean over cells, not worse than the frozen EMber runs already on disk (`ember_nbr`) by more
    than 0.01.
  * Reported, not thresholded: agreement with the authors' hickit structures (descriptive: hickit's
    own output), whole-genome and per-band r, 5 kb reproducibility, wall time, GPU memory.
* **Decision**: among candidates meeting C1-C3 the one with the fewest new settings is adopted (ties:
  higher C1), frozen with a tag and tested once on the held-back cells with C1 and C2 per cell and
  in the median; C3 is re-checked on Dip-C cells 5-7, 9-15, 17 with the §6 test protocol only if the
  frozen §6 defaults would change (they do not: new settings off by default).  If no candidate meets
  C1-C3 the extension is reported as not working on deep low-phasing data, with the numbers, and
  Fig. 3 gets no scMicro-C panel.
* *Added 2026-10-04, after the first development numbers (`diploid_devlog.md` §6), before any run
  with it*: tunable 4, `robust_dip_readmit_stage` (-1 = off; tried 3 = 400 kb and 4 = 200 kb):
  with `robust_dip_commit` by the prior and `drop`, the contacts the prior could not phase are
  re-admitted at that stage as ambiguous restraints and committed at the next stage by the EM
  posterior of the structure (>= the same τ) or dropped.  Reason: commitment by the prior with
  `drop` reproduces (C1) but loses held-out AUC (C2 / C3) with two thirds of the contacts unused;
  `keep` uses them but does not reproduce.  Criteria unchanged.
* **2026-10-04 — deep configuration frozen (tag `ember-deep-frozen`) and the deep test registered,
  before any held-back run.**
  * **Frozen method** ("EMber deep"): the frozen diploid EMber of §6 plus `robust_dip_commit` = 0.75,
    `robust_dip_commit_drop` = true, `robust_dip_readmit_stage` = 4 (n75r4 in `diploid_devlog.md` §6);
    `robust_dip_commit_stage` = -1, `dip_isolation_nei` = 0.  These are passed as parameters; the engine
    defaults (= the §6 configuration) are unchanged, so §6 and its test are unaffected and the C3
    re-check on the §6 Dip-C test cells is not run (rule above).
  * **Accepted costs, reported in full**: lower phase coverage (Dip-C development cells: masked ends with
    an assigned phase 0.94 → 0.73; correct over all masked ends 0.83 → 0.71) and C2 met on the mean only
    (per cell −0.005 / −0.027 / +0.041 on the development cells).
  * **Test units** (never run with any configuration except the frozen-EMber ladder runs of 047 / 028,
    whose scores were not inspected): scMicro-C cells 047, 028, 017, 049, 032, 027, 014.
  * **Protocol** (`sherlock/deep_dev.sbatch` with the frozen build of the tag, variants
    `engine:deep:{"robust_dip_commit":0.75,"robust_dip_readmit_stage":4}` and `nucdyn`): 100 kb and 20 kb,
    10 models, seeds 1 and 2; `highres.py score` (50,000 random pairs per chain); held-out split
    `diploid_heldout.py split --folds 1 --seed 1 --eval-res 100000 --cis-same-homolog 2000000`, EMber deep
    and NucDynamics-diploid (engine defaults, 2017 protocol) at 100 kb seed 1 on the training table,
    `heldout.py score` strict cis ROC-AUC.
  * **Endpoints**: **C1** median over the 7 cells of seed-1-vs-2 per-copy r at 20 kb >= 0.90 and every
    cell >= 0.85; **C2** mean over the 7 cells of (EMber deep − NucDynamics-diploid) strict held-out cis
    ROC-AUC >= −0.01.  Reported, not thresholded: per-cell values, 100 kb r, whole-genome and per-band r,
    r vs the authors' hickit structures, held-out trans / cis < 2 Mb, fraction of input contacts with an
    assigned copy pair (phase coverage), wall time.  **Result statement**: "C1 met / not met, C2 met /
    not met", with the numbers; no change to the method after the test is run.
* **2026-10-04 — deep test result** (run once, tag `ember-deep-frozen`; `DEEP_TEST_RESULTS.md`):
  **C1 met** (run-to-run per-copy r at 20 kb: median 0.983 over the 7 held-back cells, min 0.969);
  **C2 met** (strict held-out cis ROC-AUC, EMber deep − NucDynamics-diploid: mean +0.0117; per cell
  +0.004 / +0.058 / +0.015 / +0.020 / −0.021 / −0.001 / +0.006 for 047 / 028 / 017 / 049 / 032 / 027 / 014,
  28-50 strict positives per cell).  Accepted costs as registered: 36-45 % of the input contacts carry
  a copy pair and are used; cis < 2 Mb same-homolog held-out AUC lower than NucDynamics in 6 of 7 cells
  (mean −0.016, secondary).  No change to the method after the test.

## 12. Few-cell deconvolution, "EMber-mix" (working name) — registered 2026-10-05, before any run of it on benchmark data

**Question.**  Given the pooled contacts of k haploid single cells (k = 2-20; the first step of
`paper/plans/spatial_hic_deconvolution.md`), does EMber-mix recover the k individual structures and
the cell of origin of each contact better than IGM run with S = k structures (native engine, protocol
`igm`, its spherical nucleus)?  EMber-mix has **no nuclear shape prior**.

**Method under development** (`native/nucdyn/src/mix.rs`; protocol `robust` with `mix_cells` = k;
everything frozen in EMber's §6-§11 configurations stays as it is — the new code path is entered only
with `mix_cells` >= 2, and the existing protocols stay pinned by `tests/regression.rs`).  EMber's
mixture observation model with the cell as a further latent variable: a contact is false (rate ε) or
true and generated by cell s with probability λ_s ν_cs (λ: learned mixing weights, ν: per-contact
prior), landing on particle pair b with probability f(d_sb) / G_s; responsibilities P(true, s) weight
the restraints of cell s (per-model weights; all cells annealed in one batched engine call); k cells
x n replicate models.  Development may change the method; the knobs below are the registered space.

* **Already seen before this entry**: only synthetic toy pools of random-walk "cells" (unit tests in
  `mix.rs`): the E-step on the true structures assigns 99 % of the long-range contacts correctly;
  annealed from random-patch seeds the structures are fair but the assignment is near chance (0.58 on
  long-range contacts) while the true-origin seed reaches 0.885 with a clearly higher mixture
  likelihood (1.57 vs 1.30) — an optimisation (local optimum / symmetry-breaking) problem, not an
  unidentifiable one.  No benchmark data (imaging truths, Nagano, Stevens) has been pooled or run.
* **Development set** (tuning allowed; every variant and number recorded in a new `mix_devlog.md`):
  * Imaging-truth mixtures, **takei2021_1mb** haploid truths (`truth.takei1mb_cells`, min_detect 0.6,
    min_sep 1 Rg; eligible = all 20 chromosomes accepted: 61 cells): eligible cell ids sorted as
    strings, permuted with `numpy.random.default_rng(20261005)`, first 30 = development, remaining 31
    = test.  **su2020_genome** pseudo-haploid truths (one copy per chromosome: experimental homolog 1;
    eligible = detection of that copy >= 0.85, 1,041 loci): eligible cells sorted by (experiment, cell),
    permuted with the same seed, first 100 = development, next 100 = test.
  * Pools: for each dataset and k in {2, 3, 5, 10, 20}: 4 development pools (cells drawn without
    replacement within a pool from the development cells; `numpy.random.default_rng(1000 k + pool)`),
    6 test pools from the test cells (`default_rng(2000 + 1000 k + pool)`).  Conditions per pool:
    depth 10 / 40 reads per Mb of the haploid span per cell, ε = 0.05 / 0.2, Gaussian kernel, rc = 1.0 x
    the median consecutive-locus distance (`simulate.simulate_reads`, per cell seed = 100 pool + cell
    index); the pooled table is the concatenation of the cells' reads in random order, with the cell of
    origin and the noise flag stored next to it.  Development: 2 x 5 x 4 x 4 = 160 tables; test 240.
    Resolution 1 Mb (schedule 8, 4, 2, 1 Mb).
  * Real single-cell mixtures (haploid): **Nagano 2017 serum** (`matched/nagano/serum` tables): pools
    drawn from the development half of `robust_matched_split.py` (201 cells) for development, from the
    held-back half (202) for test; k in {2, 3, 5, 10, 20}, 4 development / 6 test pools per k (same
    seeds as above + 50,000).  **Stevens 2017**: cells 1-4 for development (all 6 pairs, all 4 triples,
    the 4-cell pool), cells 5-8 for test (the same 11 pools).  Resolution 200 kb (schedule 8, 4, 2, 0.4,
    0.2 Mb).  Reference of every real cell = frozen EMber (tag `robust-frozen` defaults) on the cell's
    own contacts, 2 models, seed 1, same schedule (also the "oracle" upper bound).
* **Comparators (not tuned)**: (a) naive EMber — frozen EMber on the pooled table as if one cell;
  (b) IGM with S = k (`uchrom.recon.bulk.deconv.deconvolve_igm` defaults: sphere radius 5 µm, occupancy
  0.2, demo annealing, haploid), input p_ij = min(1, n_ij / k) on the resolution grid (n_ij = pooled
  contacts of the bin pair; neighbours 1), each contact assigned to the structure in which its bin pair
  is closest; (c) oracle EMber per true cell (upper bound; sims: on the cell's own simulated reads).
* **Scoring** (`mix_score.py`, written before any test run): recovered cells are matched one to one to
  the true cells by the Hungarian algorithm on the Spearman r of distances (sims: vs the truth on the
  measured loci; real: vs the cell's reference on a 1 Mb grid of bin midpoints covered in both); a
  recovered cell's distances = mean over its replicate models.  **M1** contact-to-cell assignment
  accuracy (most probable cell of every input contact under that matching; every input contact counts,
  filtered ones included); **M2** mean over the pool's cells of the matched whole-genome Spearman r;
  **M3** (real mixtures only) held-out contacts of the pool: 10 % of the pooled reads held out
  (`heldout.py split --folds 1 --seed 1`, eval grid = the resolution), every method re-run on the
  training table, score of a pair = minus the smallest replicate-median distance over the recovered
  cells (bead units), cis ROC-AUC.  Secondary: M1 by separation (cis < 2 Mb / 2-20 Mb / > 20 Mb /
  trans) and on signal reads only; cis-only Spearman; ε and λ; wall time.
* **Development knobs** (engine parameters, default off where they exist; values tried only on the
  development units): symmetry breaking `mix_seed` (patch / random / uniform; patch size, minimum
  separation), restarts `mix_restarts` with selection stage `mix_select_stage`, learned mixing weights
  `mix_learn_pi`, 2-D neighbourhood smoothing of the cell posteriors `mix_nbr_prior` (exponent, radius,
  pseudo-count), staged commitment `mix_commit` / `mix_commit_stage` / `mix_commit_drop` /
  `mix_readmit_stage` (the deep-extension lesson), replicate models per cell, a structure-informed
  seed (e.g. splitting off the contacts a one-cell fit explains worst), the schedule (temperature / MD
  steps per stage), and the confinement term: none (EMber), a shape-free soft density cap (penalty on
  local particle density above ρ_max on the neighbour grid), weak isotropic compaction, an
  imaging-calibrated radius-of-gyration prior, an IGM-like sphere (control).  Anything else is added
  here, dated, before it is run.
* **Development criterion** for adopting a knob: development M1 and M2 (imaging-truth mixtures and
  Nagano / Stevens development pools) improve without any (dataset, k, depth, ε) stratum worse by more
  than 0.01; ties broken by fewer settings.
* **Freeze**: the chosen configuration is tagged (`ember-mix-frozen`) and recorded here before any test
  pool is run; **the test is run only after the parent / user approves the freeze.**
* **Test endpoints** (paired differences, 95 % percentile bootstrap over pools — sims: pools grouped
  across their 4 conditions): **T1** M1 EMber-mix − IGM (sims); **T2** M2 EMber-mix − IGM (sims);
  **T3** M1 EMber-mix − IGM (real: Nagano + Stevens test pools); **T4** M2 EMber-mix − IGM (real);
  **T5** M3 EMber-mix − IGM (real).  **Decision rule**: EMber-mix is called **better than IGM (S = k)**
  only if the T1-T4 CIs are above 0, the T5 CI lower bound is above −0.01, and no secondary stratum
  (dataset, k, depth, ε; real: dataset, k) is worse by more than 0.01 with a CI excluding 0.  Otherwise
  reported as it is.  **Breakdown k** (reported, not thresholded): per dataset, the smallest k at which
  the M2 gain of EMber-mix over naive EMber (each true cell scored against the single naive structure)
  has a 95 % CI that includes 0 or lies below it.  The oracle (per-cell EMber) gap is reported for every k.

### 12.1 Addition 2026-10-05 — externally assisted deconvolution, cue 1: cell-type prior from reference single-cell Hi-C (registered before any run of it)

**Why.**  §12 development (`mix_devlog.md` §1-§4) found that the engine recovers the cells from a
partially correct labelling (a 75 %-correct seed reaches M2 0.45-0.80 on every development set) but
that no structure-free seed provides one.  The user approved direction A: an *external* cue.  Cue 1 is
the spatial Hi-C-RNA use case: the cell types present in a pool are known (from RNA), and reference
single-cell Hi-C of those types gives type-specific contact propensities.  Nothing of the §12 test is
run; this addition has its own development / held-back split.

* **Data**: Tan et al. 2021 Dip-C, adult mouse cortex (GEO GSE146397; the 510 adult cells of
  `data/tan2021_adult_cortex_cells.tsv`, cell types from the GEO metadata), per-cell hickit contacts
  (`*.contacts.pairs.txt.gz`).  Types used: P = "Cortical L2–5 Pyramidal Cell" (160), O = "Mature
  Oligodendrocyte" (74), A = "Adult Astrocyte" (30), M = "Microglia Etc." (37).
* **Split (fixed now)**: per type, cells sorted by GSM and permuted with
  `numpy.random.default_rng(20261006)`: first floor(n/2) = REFERENCE, next floor((n − ref)/2) =
  development pool cells, the rest = held-back pool cells (P 80 / 40 / 40, O 37 / 18 / 19, A 15 / 7 / 8,
  M 18 / 9 / 10).  Reference cells are never pooled; pool cells never enter a reference.
* **Pools**: compositions PO, PA, PM, OM (k = 2, different types), PAM (k = 3, different types), PP
  (k = 2, same type — the hard case, reported as such), PPO (k = 3, mixed).  Development: 4 pools per
  composition from the development pool cells (`default_rng(60_000 + 100 composition index + pool)`,
  cells of a pool distinct); held-back: 6 pools per composition from the held-back cells
  (`default_rng(70_000 + 100 composition index + pool)`), run only after a freeze is approved.  A pool is
  the concatenation of its cells' contact rows in random order with the origin stored.
* **Ploidy (choice for this step)**: phases are ignored — every cell and every pool is reconstructed
  as haploid (one chain per chromosome; the two homologs' contacts on one chain), both in the pools and
  in the references.  This is a pseudo-haploid approximation (it does not model homologs) applied
  identically to every method, so the deconvolution itself is what is measured.  A diploid mix engine
  (cells × copies) is a later extension, compared on the development pools before any freeze if built.
* **Resolution**: 200 kb (schedule 8, 4, 2, 0.4, 0.2 Mb).  **Reference of every pool cell**: frozen EMber
  (tag `robust-frozen` defaults, phases ignored) on the cell's own contacts, 2 models, seed 1.
* **The prior**: per reference type t, a pseudo-bulk contact map at `R_ref` (every reference cell's
  contacts weighted 1 / its contact count), 2-D smoothed, plus a pseudo-count; L_t(c) = the normalised
  propensity of the bin pair of contact c.  For a pool with declared type composition (cell s has type
  t_s; the labels play the role of the RNA), the prior of contact c is
  ν_cs ∝ exp(γ Σ_{j ∈ N(c) ∪ {c}} w_cj ln L_{t_s}(j)) (N: 2-D neighbours as `mix_nbr_*`; cells of the
  same type get equal priors), used as the seed and the E-step prior of the mix engine (`mix_prior`),
  followed by EM refinement.
* **Methods compared** (development and test): **E** = EMber-mix with the type prior; **prior-only** =
  argmax ν (no 3-D); **prior-split** = frozen EMber on each cell's prior-assigned contacts (structures
  from the prior alone); **naive** = frozen EMber on the pool as one cell; **IGM** S = k (as §12);
  **oracle** = the references.  Scoring = `mix_score.py` (M1 assignment accuracy over every pooled row,
  Hungarian matching on structure r; M2 matched whole-genome Spearman r vs the references).
* **Development knobs** (development pools only, recorded in `mix_devlog.md`): `R_ref` (1 Mb / 500 kb /
  250 kb), smoothing, pseudo-count, γ, neighbourhood radius / weights, the EM configuration of the
  engine (prior keep, posterior accumulation, refinement passes, density cap).
* **Test endpoints** (held-back pools; paired differences, 95 % percentile bootstrap over pools):
  on the different-type pools (PO, PA, PM, OM, PAM; 30 pools): **U1** M1 E − prior-only > 0 (3-D adds to
  the prior); **U2** M2 E − naive > 0; **U3** M2 E − IGM > 0 and M1 E − IGM > 0; **U4** M2 E − prior-split
  ≥ −0.01 (non-inferior).  **Decision**: type-assisted EMber-mix is called **useful for different-type
  pools** only if U1-U3 CIs are above 0 and the U4 lower bound is above −0.01, with no composition worse
  than naive in M2 by more than 0.01 (CI excluding 0).  Same-type (PP) and mixed (PPO) pools are reported
  in full, every endpoint, without a threshold.
* **Cue 2** (genotype labels, GM12878 + PBMC Dip-C) and **cue 3** (reference-structure templates) get
  their own dated additions before any run.

### 12.2 Addition 2026-10-05 — externally assisted deconvolution, cue 2: genotype labels (GM12878 + PBMC Dip-C), registered before any run of it

**Why.**  The user decided to test a cue that labels contacts directly: when the pooled cells come from
different donors, a contact whose read covers a donor-distinguishing SNP carries its donor.  Only the
development pools below are run until a freeze is approved.

* **Data**: Tan et al. 2018 Dip-C (GEO GSE117876 / hickit re-processing GSE117874; SRA SRP149125, public):
  GM12878 cells with hickit pairs (cells 1-3, 5-7, 9-15, 17; 14 cells) and PBMC cells 1-18 (one donor,
  different from GM12878).  **Contact tables** = the authors' hickit phased pairs (as §6), haplotypes
  of each donor's own phasing.  **Donor labels** come only from re-aligned reads (below).
* **Split (fixed now)**: GM12878 cells (by number) permuted with `numpy.random.default_rng(20261007)`:
  first 6 = development pool cells, the other 8 = held-back.  PBMC cells 1-18 permuted with
  `default_rng(20261008)`: first 6 = GENOTYPING cells (their reads give the PBMC donor genotype; never
  pooled), next 6 = development pool cells, last 6 = held-back.
* **Donor-distinguishing sites**: GM12878 genotype = GIAB HG001 v3.3.2 GRCh37 high-confidence VCF and its
  high-confidence regions; PBMC genotype = `bcftools mpileup | call` on the pooled reads of the 6
  genotyping cells (re-aligned to hs37d5).  A site is used when it is a biallelic SNV inside the GIAB
  high-confidence regions and the two donors are homozygous for different alleles: GIAB 1/1 (or 1|1)
  with PBMC >= 4 reads all REF, or GIAB absent (hom-REF) with PBMC called 1/1 with >= 4 reads all ALT
  (QUAL >= 30).  Het sites are not used.
* **Labelling pipeline** (per pooled cell, Sherlock batch jobs; FASTQ / BAM deleted after use): SRA reads
  → `bwa mem -5SP` to hs37d5 → `hickit.js sam2seg -v <donor VCF>` (the sites written as phased
  hets, haplotype 0 = GM12878 allele, 1 = PBMC allele) → `chronly` → `hickit` pairs, whose phase
  columns are donor labels.  A contact of the authors' table gets the donor of the re-aligned contact
  with identical (chr1, pos1, chr2, pos2, strand1, strand2) when its labelled ends agree; otherwise it
  is unlabelled.  Reported: fraction of contacts labelled per cell and per-contact label accuracy
  (against the known cell).
* **Pools**: compositions GP (1 GM12878 + 1 PBMC), GGP (2 + 1: two same-donor cells, the hard part),
  GGPP (2 + 2); 6 development pools per composition from the development cells
  (`default_rng(80_000 + 100 composition + pool)`), 8 held-back pools per composition from the held-back
  cells (`default_rng(90_000 + 100 composition + pool)`).  Diploid (cells × copies, `src/mixdip.rs`),
  200 kb.  **Reference** of every pooled cell = frozen EMber diploid (tag `ember-diploid-frozen`
  defaults) on its own table, 2 models, seed 1.
* **Prior**: labelled contact → probability 1 − δ on the pool's cells of that donor (equally), δ on the
  others; unlabelled contacts get the donor distribution of their 2-D neighbours (hickit-style
  imputation of `mix_nbr_*`: nearest labelled contacts within the radius, weights 1 / (d / span + 0.001),
  pseudo-count), iterated; seed and E-step prior of the engine, then EM.
* **Methods**: E (genotype prior + EM); prior-only (argmax; cells of one donor tie); prior-split (EMber
  diploid on each cell's prior-assigned contacts); naive EMber diploid on the pool; IGM S = k
  (diploid); oracle (the references).  Scoring `mix_score.py` (copy chains).
* **Development knobs**: δ, the neighbour radius / count / pseudo-count / iterations of the spreading,
  the engine configuration (prior fixed vs posterior accumulation, refinement passes, density cap).
* **Test endpoints** (held-back pools, paired 95 % bootstrap over pools): **V1** M1 E − prior-only > 0;
  **V2** M2 E − naive > 0; **V3** M2 and M1 E − IGM > 0; **V4** M2 E − prior-split >= −0.01; decision as
  §12.1 (V1-V3 CIs above 0, V4 lower bound above −0.01, no composition worse than naive in M2 by > 0.01).
  The separation of the two same-donor cells (GGP, GGPP) is reported in full.

### 12.3 Note 2026-10-07 — outcome of §12, §12.1 and §12.2

**Held-back test not run by decision of 2026-10-07; development results reported as exploratory, no
claim of a frozen method.**  This applies to §12 (no freeze; `mix_devlog.md` §1-§4), §12.1 (cue 1,
cell-type prior: negative on the development pools in both ploidies, devlog §5-§6) and §12.2 (cue 2,
genotype labels, devlog §7).  No tag `ember-mix-frozen` exists; no held-back pool of §12, §12.1 or §12.2
was generated, aligned or run.  Exploratory finding of §12.2: splitting a pool by the genotype prior and
running frozen EMber diploid on each part recovered cells of distinct donors on the development GP pools
(M2 0.74 vs naive EMber 0.30), while the EMber-mix engine added nothing (M2 −0.17 vs that split) and two
cells of one donor (GGP, GGPP) were not separated.  The split was a registered baseline, not the method
under test, and it is not tested here.
