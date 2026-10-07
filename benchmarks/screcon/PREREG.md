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

## 13. A spot reconstructed as one cell: dominant-cell recovery and spot QC — registered 2026-10-05, before any run of it

**Why.**  §12 found that few-cell pools are not deconvolved without an external cue.  A spatial Hi-C
spot (10-50 µm; a few cells or partial nuclei) is often dominated by one cell.  This section asks the
simpler question behind the "single-spot 3-D structure" claims of the 2026 spatial Hi-C papers
(`paper/plans/spatial_hic_deconvolution.md`): if a spot is reconstructed **as if it were one cell**, how
much of the **dominant** cell's structure comes back, as a function of the dominant cell's share f of
the contacts, and can spot-intrinsic metrics tell single-cell-like spots from mixed ones?
**Nothing is tuned**: the methods are the frozen ones; only a QC threshold is chosen, on development
units only.  Code: `dominant.py` (cells, designs, tables, runs, scoring, aggregation), jobs
`sherlock/dom_*.sbatch`; development record `dominant_devlog.md`.

* **Questions.**  **Q1** E1(f): agreement of the mixture's EMber structure with the dominant cell's own
  structure; at which f does it fall below the pure-cell control by more than 0.05?  **Q2** Does EMber's
  noise model help here (EMber − NucDynamics)?  **Q3** Spot QC: do spot-intrinsic metrics classify
  f >= 0.8 vs f <= 0.6, and at which threshold?
* **Data and split (fixed now).**
  * **Nagano 2017 serum haploid mESC**: development = the development half of §6 (201 cells,
    `robust_matched_split.py`); held back = the held-back half (202 cells).  Cell tables =
    `matched/nagano/serum` (mm10).
  * **Stevens 2017 haploid mESC**: development = cells 1-4, held back = cells 5-8 (GEO tables).
  * **Tan 2021 adult cortex Dip-C (diploid, phased hickit contacts)**: development = the §12.1
    development pool cells (role `dev` of `mix_type.split_table()`: P 40, O 18, A 7, M 9 = 74 cells);
    held back = the §12.1 held-back pool cells (role `test`, 77).  §12.1 reference cells are not used.
    Chromosomes chr1-19, X, Y; phases as given; ploidy `male` (Tan 2021 mice are males: X and Y one copy).
  * cis = same chromosome with separation >= 1 kb; n_cis(cell) = its number of cis contacts.
* **Dominants (fixed rule; the lists are materialised by `dominant.py designs` before any run and
  appended below).**  Nagano: development cells with n_cis >= 100,000, sorted by name, permuted with
  `numpy.random.default_rng(20261013)`, first 12.  Stevens: cells 1, 2, 3, 4.  Tan: per type in the order
  P, O, A, M (type index t = 0..3), the development cells of that type sorted by GSM, permuted with
  `default_rng(20261013 + t)`, first 2 (8 dominants).  Held back: the same rules on the held-back cells
  with base seed 20261014 (Stevens: cells 5-8).
* **Designs (minor cells).**  m = number of minor cells, 1 or 2.  Nagano: per dominant (index i) and m,
  m minors drawn without replacement (`default_rng(130_000 + 10 i + m)`; held back + 500,000) from the
  other cells of the same set with n_cis >= n_cis(D) / (2 m) (f = 0.5 feasible at full depth; if no such
  cell, from all).  Stevens: m = 1: each of the 3 other cells of the set; m = 2: each of the 3 pairs of
  other cells (6 designs per dominant).  Tan: m = 1: one cell of a different type; m = 2: one cell of
  the same type + one of a different type (`default_rng(131_000 + 10 i + m)`, held back + 500,000; same
  depth rule, falling back to all candidates).
* **Mixtures.**  f ∈ {1.0, 0.9, 0.8, 0.7, 0.6, 0.5} = the dominant's share of the mixture's cis
  contacts.  Depth levels N (cis contacts of the mixture) ∈ {10,000; 30,000; 100,000; full = n_cis(D)}
  (2026 spatial Hi-C spots: Chen et al. 10 µm cortex median ~9 k pairs per spot, p90 ~30 k; Guo et al.
  20 µm ~136 k cis); a level is used for a dominant only when
  n_cis(D) >= N.  Cell j contributes t_j cis contacts — t_D = round(f N), every minor round((1 − f) N / m)
  — and its other rows (trans, cis < 1 kb) at the same rate (each cell keeps its own trans / cis ratio).
  Sampling is nested: each cell's cis rows and other rows are permuted once (dominant
  `default_rng(140_000 + i)`; a minor `default_rng(150_000 + 100 design + rank)`) and the first rows are
  taken, so the dominant's rows at f are a subset of its rows at any larger f.  If a minor has too few
  contacts, N of that design is lowered to the largest feasible value for every f (recorded; its f = 1.0
  control is made at that N).  Rows of a mixture are shuffled (`default_rng(7)`); the cell of origin is
  stored next to the table.  Haploid tables: GEO 4 columns; Tan: hickit phased pairs.
* **Controls.**  **pure** (f = 1.0): the dominant alone at N (separates mixing from depth); shared by
  the designs of a dominant at that N.  **D-only**: exactly the dominant rows of an f < 1 mixture, without
  the minors (separates the minors' effect from the dominant's depth loss).
* **Methods (frozen).**  Nagano / Stevens: EMber haploid (protocol `robust`, `run_robust.ROBUST_DEFAULTS`
  = tag `robust-frozen`).  Tan: EMber deep diploid (tag `ember-deep-frozen`: `ROBUST_DEFAULTS` +
  `robust_dip_commit` 0.75, `robust_dip_commit_drop`, `robust_dip_readmit_stage` 4; at 200 kb stage 4 is
  the 200 kb stage and the structure commitment happens at the refinement stage).  Baseline:
  NucDynamics, protocol `nuc_dynamics_2017` (no noise model; diploid: ambiguous restraints).
  200 kb (schedule 8, 4, 2, 0.4, 0.2 Mb), 2 models per run, GPU, the engine build of this branch (its
  regression hashes of the frozen protocols checked in the setup job).  Seeds: references 1; mixture and
  pure runs: EMber 2 and 3, NucDynamics 2; D-only: EMber 2.
* **References.**  Every cell used (dominants and minors): EMber on its full table, seed 1.  Dominants
  also NucDynamics on the full table, seed 1 (secondary reference of E2).
* **Scoring** (`dominant.py score`).  Structures compared on the particles both have, matched by
  (chain, position) at 200 kb; a run's distances = mean over its 2 models; chains = chromosomes
  (haploid) or copy chains (diploid).
  * **E1 (primary)**: per-copy r — Pearson r of all within-chain particle distances, mixture EMber run
    (seed 2) vs the dominant's EMber reference, median over chains with >= 50 matched particles.
    Secondary: whole-genome r (Pearson; 200,000 random particle pairs, trans included, seed 0), Spearman
    per-copy, per separation band (< 2, 2-20, > 20 Mb), and the per-copy r vs each minor's reference.
    Summary per dataset × level × m × f: ΔE1 = E1(mixture) − E1(pure control of the same dominant and N),
    mean with a 95 % percentile bootstrap over dominants (2,000 resamples, seed 0); **f_drop** = the
    largest f < 1 whose mean ΔE1 < −0.05 (else "none down to 0.5"); decomposition: depth effect
    E1(D-only) − E1(pure), mixing effect E1(mixture) − E1(D-only).
  * **E2**: E1(EMber) − E1(NucDynamics) per mixture (both vs the dominant's EMber reference), per
    dataset × level × f and over f < 1, bootstrap over dominants.  Secondary (removes the reference's
    method): NucDynamics vs the dominant's NucDynamics reference, EMber vs its EMber reference.
  * **E3 QC** — spot-intrinsic metrics (the mixture table and its own EMber runs only), each with its
    direction fixed now (+: larger = more mixed): **Q1** ε of EMber's last EM update (+); **Q2** fraction
    of the input contacts with EMber weight P(true) < 0.5, filtered contacts counted (+); **Q3** restraint
    violation rate: input contacts >= 400 kb apart (or trans) whose model-mean distance exceeds 2 bead
    units (diploid: closest copy pair consistent with the phased ends) (+); **Q4** seed-to-seed per-copy
    r, EMber seed 2 vs 3 (−); **Q5** long-range transitivity: graph of 1 Mb bins joined by >= 1 contact
    with cis separation >= 2 Mb or trans, closed fraction of wedges (−); **Q6** trans-triangle closure:
    wedges of two trans edges at a bin whose partners lie on two other, different chromosomes, closed
    fraction (−); **Q7** partner conflict: pairs of long-range contacts (cis >= 2 Mb or trans) with an
    end within 10 kb of each other whose other ends are on different chromosomes or > 5 Mb apart,
    fraction (+).  Classes: single-cell-like = f ∈ {1.0, 0.9, 0.8}, mixed = f ∈ {0.6, 0.5}; f = 0.7
    excluded.  ROC-AUC with the registered direction per dataset × level (a spot's depth is known) and
    per dataset (mean over levels), 95 % bootstrap over dominants.  Secondary: Spearman of each metric
    with E1; a logistic combination of Q1-Q7 + log N, leave-one-dominant-out within dataset.
  * **QC threshold (development only)**: the metric with the highest per-dataset AUC averaged over the
    three datasets (ties: fewer runs needed, i.e. Q5-Q7 before Q1-Q3 before Q4); threshold per level =
    Youden's J on the development units; its sensitivity / specificity are reported.
* **Held back (not run until the user approves).**  The same pipeline on the held-back dominants with
  the QC metric and thresholds frozen.  Statements: "EMber recovers the dominant's structure within
  0.05 of the pure control down to f = X" (f_drop per dataset × level); "EMber is better than
  NucDynamics on dominant-cell mixtures" only if the E2 95 % CI over all f < 1 mixtures is above 0;
  "the spot QC works" only if the held-back AUC (per dataset, mean over levels) has a 95 % CI lower
  bound above 0.75 and the specificity at the frozen thresholds is >= 0.8.  Otherwise reported as it is.
* **Materialised development designs** (`dominant.py designs`, 2026-10-06, before any reconstruction;
  n_cis in parentheses; full lists in `runs/dominant/<dataset>/dev/designs.json`):
  * Nagano dominants: NST_637 (103,371), NST_755 (168,397), NST_304 (112,519), NST_274 (126,094),
    NST_674 (109,021), NST_763 (174,763), NST_344 (202,214), NST_333 (180,994), NST_722 (110,073),
    NST_844 (110,791), NST_982 (208,039), NST_395 (111,446); 24 designs (one m = 1, one m = 2 per dominant).
  * Stevens dominants: cells 1 (98,028), 2 (72,204), 3 (24,739), 4 (81,946); 24 designs.  No Stevens cell
    reaches 100 k cis (levels 10 k, 30 k, full; cell 3: 10 k and full).
  * Tan dominants: cortex-p056-cb_043 (P), cortex-p309-bc_103 (P), cortex-p309-bc_165 (O),
    cortex-p056-cb_112 (O), cortex-p056-cb_129 (A), cortex-p056-cb_284 (A), cortex-p056-cb_134 (M),
    cortex-p056-cb_100 (M) (173-858 k cis); 16 designs.  The cells come from reciprocal crosses (cb / bc);
    phase labels are kept as given (the mixture's copy labels of the dominant are its own).
* **Expected cost** (development): ~4,100 runs (Nagano ~1,900, Stevens ~1,000, Tan ~1,200), haploid
  ~10-20 s per run, diploid 10 s - 5 min; ~20 GPU hours.

### 13.1 Development results (2026-10-06; development units only, `dominant_devlog.md`)

Nothing of the held-back sets has been built or run.  E1: the dominant's structure stays within 0.05 of the
pure control only at f = 0.9 (f_drop = 0.8 for most dataset × level cells, 0.9 for Stevens 30 k and Tan
30 k / full); at f = 0.5 the per-copy r falls by 0.12-0.47 and the structure agrees as much with the minor
cell as with the dominant.  E2: EMber − NucDynamics +0.004 to +0.020 on haploid mixtures; diploid (EMber
deep) −0.010 / −0.012 at 10 k / 30 k and +0.015 / +0.025 at 100 k / full.  E3: mean AUC Q3 violation rate
0.91, Q7 partner conflict 0.89, Q2 0.87, Q5 / Q6 0.75, Q4 0.71, Q1 ε 0.51 (ε at its lower bound).
**Proposed QC rule (registered selection rule; not frozen until the user approves the held-back test)**:
Q3 with the per-dataset, per-level Youden thresholds of `dominant_devlog.md` §4; Q7 reported alongside.
The thresholds are protocol-specific and are not to be applied to other datasets without calibration.

### 13.2 Freeze of the spot QC rule and the held-back test — 2026-10-06, before any held-back table is built or run

User approval received 2026-10-06.  **Frozen QC rule** (`data/spotqc_frozen.json`, tag `ember-spotqc-frozen`):
flag a spot as mixed when its **Q3** (fraction of the input contacts >= 400 kb apart or trans whose
model-mean distance in its EMber run, seed 2, exceeds 2 bead units) is >= the development Youden threshold of
its dataset and depth level:

| dataset | 10 k | 30 k | 100 k | full |
| --- | --- | --- | --- | --- |
| Nagano | 0.3638 | 0.3783 | 0.4240 | 0.4227 |
| Stevens | 0.2947 | 0.2685 | (full's) | 0.2528 |
| Tan (phased, EMber deep) | 0.5319 | 0.4109 | 0.3880 | 0.3752 |

A level without a development threshold (Stevens 100 k) takes the dataset's `full` threshold.  Q7 (partner
conflict) is reported alongside with its own development thresholds (same file), not part of the rule.
Already known on development (`dominant.py test` on the development scores, before the held-back run):
Nagano Q3 specificity at these thresholds is 0.70 (< 0.8), Stevens 0.88, Tan 0.85.

**Held-back test** (run once with the registered §13 pipeline, engine `dom-4181d07` = the build of the
development runs, methods frozen as before): `dom_prepare.sbatch SET=test APPROVED=1` (Nagano held-back half,
dominants by seed 20261014; Stevens cells 5-8; Tan §12.1 held-back pool cells, seeds 20261014 + t), then
`dom_run.sbatch` per dominant.  Scoring: `dominant.py aggregate` (E1 / E2 / E3 tables, f_drop) and
`dominant.py test --frozen data/spotqc_frozen.json` (the statements of §13: f_drop per dataset × level; E2 over
all f < 1 mixtures with a 95 % CI over dominants, per dataset and pooled; held-back AUC of Q3 per dataset =
mean over levels with a 95 % bootstrap CI over dominants; sensitivity / specificity at the frozen thresholds
pooled over the dataset's levels; "the spot QC works" for a dataset only if the AUC CI lower bound > 0.75 and
the pooled specificity >= 0.8).  Results go to `DOMINANT_TEST_RESULTS.md` and §13.4; nothing is changed after
they are seen.

### 13.3 Addition 2026-10-06 — unphased diploid calibration and the Chen et al. 2026 application (registered before any run of either)

**Why.**  Spatial Hi-C of inbred mouse brain cannot be phased; §13 tested phased diploid cells only.

* **Handling (fixed now): pseudo-haploid.**  Unphased diploid input is reconstructed with haploid EMber
  (tag `robust-frozen`; both homologs on one chain per chromosome), as §12.1 did.  Not diploid-unphased: with
  no phased ends every contact has four candidate copy pairs, the frozen deep configuration commits only
  prior-phased contacts (none) and drops the rest until the 200 kb stage, and at 2-30 k contacts per spot the
  copy assignment is not identifiable.
* **Calibration (development only; Tan §13 development designs, unchanged)**: dataset `tanu` = the same Tan
  development cells, designs, levels, f and sampled rows as `tan`, phases dropped (GEO tables), every run
  pseudo-haploid (EMber haploid seeds 2 / 3, NucDynamics haploid seed 2, D-only EMber seed 2; references =
  each cell's own phase-dropped table, EMber haploid seed 1, NucDynamics seed 1).  Scored with
  `dominant.py score` / `aggregate` (E1 per chromosome chain, E2, Q1-Q7).  Q3 and Q7 thresholds for unphased
  diploid input = Youden on these units per level (the §13 rule applied to `tanu`); reported as `tanu` in
  `dominant_devlog.md` §6.  No held-back `tanu` run (the Tan held-back cells are used by §13.2).
* **Chen et al. 2026 application** (`chen_spots.py`): sections cortex adult 10 µm (GSA run CRR1829219,
  Adult16_HiC) and hippocampus adult 10 µm (CRR1829220, Adult22_HiC); per-spot deduplicated pairs read-only
  from `$OAK/uchrom/spatial_hic_chen2026/<run>/<run>.dedup.pairs.gz` (reprocessed from CRA016676, see the
  catalog); spots = barcode pairs linked to the published spots (`data/chen2026_*_spots.tsv.gz`, 7,795 /
  8,185).
  * Depth: n_cis = cis pairs (>= 1 kb) of the spot.  Spots with n_cis < 10,000 are **not assessable** (below
    the calibrated range; counted, not reconstructed).  Level of a spot: 10 k for 10-30 k, 30 k for 30-100 k,
    100 k for >= 100 k cis.
  * Per assessable spot: EMber haploid (`robust-frozen`), 200 kb, 2 models, seed 2 (GEO table of the spot's
    pairs); Q2, Q3, Q7.  **Pass** = Q3 < the `tanu` Q3 threshold of its level (the frozen rule, unphased
    calibration); Q7 with the `tanu` Q7 threshold reported alongside.
  * Reported: per section and level the number and fraction of spots that pass (also over all linked spots,
    not-assessable counted as not passing); spatial maps (grid) of n_cis, assessable / pass / fail, Q3, Q7;
    pass fraction per published region / cluster; for passing spots simple structural features — genome
    radius of gyration and median chromosome radius of gyration (bead units), intermingling (fraction of
    particles with a particle of another chromosome within 2 bead units), contact trans fraction — and their
    maps and per-region medians.
  * Secondary, descriptive (no threshold): per section 200 in-silico 50:50 mixtures of two random assessable
    spots and 200 single assessable spots, all subsampled to 10,000 cis (`default_rng(20261015)`), same
    EMber run and Q3 / Q7 — where real spots sit between "one spot" and "two spots" of the same protocol.
  * Caveats stated up front: the thresholds come from Dip-C cells, not from this protocol (§13 showed they do
    not transfer exactly); a 10 µm spot that passes is "not detectably mixed at the level f <= 0.6", not shown
    to be one cell; there is no reference structure for a spot, so no E1.

**Note 2026-10-06 (user-approved, before any held-back result has been seen; no held-back reconstruction had
started):** because no GPUs were being scheduled, the held-back runs of §13.2, the unphased Tan calibration
of §13.3 and the remaining Chen cortex tasks run on the **CPU (f64) path of the same frozen engine build**
(`dom-4181d07`, `device="cpu"`) instead of the GPU (f32) path used for the development runs.  The method,
its parameters, seeds, inputs and scoring are unchanged; the CPU and GPU paths implement the same protocol
(the engine's GPU tests check them against each other), but individual runs are not bit-identical across
devices.  Chen hippocampus (all tasks) and cortex tasks 1, 2 and 4 (and part of task 3) already ran on GPU;
their outputs are kept and only the missing runs are made on CPU.
