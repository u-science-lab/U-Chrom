# Pre-registration: EMber-pop (shape-free population deconvolution of bulk Hi-C) vs IGM

Written **2026-10-07, before any code of the new method exists and before any run on the data below**.
Changes to this file after the held-back test set has been looked at must be listed in §10 with the
date and the reason; additions before that go to §10 as well, dated, before they are used.

## 1. Question

Does the new population method (working name **EMber-pop**: IGM-style population of S diploid
structures, but EMber's likelihood observation model and no nuclear envelope, §9) reconstruct the
*population* of genome structures behind a bulk Hi-C matrix better than IGM as implemented in U-Chrom
(native engine, protocol `igm`, IGM 1.0 defaults, spherical nucleus; validated against the original
IGM in `design.md` §7(d), `igm_demo_compare.py`)?  "Better" is measured against imaged populations
that were **not** used to make the bulk input (§2).

## 2. Data, cell split and held-back units (fixed now)

The split is `data/pop_split.tsv`, written by `pop_split.py` (seed 20261007) and committed with this
file, before any simulation of it exists.

| dataset | cells | development (tuning allowed) | held back (one-shot test) |
| --- | --- | --- | --- |
| Su 2020 genome-scale IMR90 DNA-MERFISH (`truths.su2020_genome`; 1,041 loci, homologs resolved, lamina distances) | 1,787 | bulk from `dev_bulk` (447 cells), truth `dev_truth` (447) | bulk from `test_bulk` (447), truth `test_truth` (446) |
| Takei 2021 mESC DNA seqFISH+ 1 Mb (`truths.takei2021_1mb`; 2,460 loci, homologs split heuristically) | 201 | — (never run before the freeze) | bulk from `test_bulk` (100), truth `test_truth` (101) |
| real bulk: Rao 2014 IMR90 Hi-C (4DN `4DNFIR1JDZH7`) vs Su 2020 imaging | — | — (input may be built, no method run on it before the freeze) | truth = all 893 Su test-half cells (`test_bulk` + `test_truth`) |
| IGM demo WTC11 2 Mb (`WTC11_HiC_2Mb.hcs`, no truth) | — | fit to input, runtime | — |

* No parameter or design choice of EMber-pop is made on held-back units.  The comparators (§4) are
  not tuned at all; their configuration is fixed here.
* Development runs may use smaller populations (S ≥ 100) and shortened schedules to iterate; the
  frozen method is evaluated at the registered sizes (§4).

## 3. Simulated bulk inputs (`forward.py bulk`, written before any run)

For each truth split, the bulk is made **only from the `*_bulk` cells**:

* model bins: Su — 3 Mb centred on every locus (`centered:3000000`); Takei — 1 Mb centred
  (`centered:1000000`);
* contact distance `rc` = IGM's `2 (r_i + r_j)` with IGM bead radii at occupancy 0.2 in a sphere of
  radius `R_rg` = median over the bulk cells of `sqrt(5/3) Rg` (`forward.resolve_rc`, `--rc igm`);
* three conditions per split:
  * **C1** `step` kernel (IGM's own contact definition), infinite depth (exact IGM-pooled
    probabilities);
  * **C2** `gauss` kernel exp(−(d/rc)²) (mismatched with every model), infinite depth;
  * **C3** `step` kernel, finite depth: reads = 200 × L(L−1)/2 (Su 1.08·10⁸, Takei 6.05·10⁸), random
    ligation noise ε = 0.1, log-normal visibility bias sd 0.2, 10 fine bins per model bin, the IGM
    preprocessing (`deconv.preprocess`, KR) onto the model bins with the oracle target (mean row sum of
    the exact C1 matrix of the same bulk cells), seed 1.
* Real IMR90: `real_inputs.py preprocess` of the 4DN mcool (fine 20 kb from the 10 kb level, KR, IGM SI
  protocol) onto the Su 3 Mb centred bins, target = mean row sum of the exact C1 matrix of the 894 Su
  **development** cells (no test-half cell informs the input).

## 4. Methods compared (configurations fixed now)

* **EMber-pop** — the candidate, configuration frozen with tag `ember-pop-frozen` (§8).
* **IGM-sphere** (primary comparator) — `deconvolve(method="igm")`, engine defaults (IGM 1.0 demo
  annealing schedule, σ lists 1 → 0.01, `max_iterations` 10, occupancy 0.2), `nucleus_radius` = `R_rg`
  of the bulk cells (real IMR90: of the Su development cells); nothing else set.
* **IGM-ellipsoid** (secondary comparator) — as IGM-sphere with `nucleus_shape="ellipsoid"`,
  semi-axes = `sqrt(5) ×` the median gyration standard deviations (σ1 ≥ σ2 ≥ σ3) of the bulk cells,
  bead radii identical to IGM-sphere (`occupancy_total_bp` scaled by V_ellipsoid / V_sphere).
* **Baselines** (`bulk_baselines.py`, same input): HIPPS and the contact-matched Gaussian
  (pairwise-only), random confined polymer (floor); **ceiling**: the bulk cells themselves scored
  against the truth cells (a perfect deconvolution of the input).
* **Ablations of EMber-pop** (reported, not part of the decision): with IGM's sphere, with the
  imaging-calibrated ellipsoid, with a radius-of-gyration prior instead of the density cap, and with
  IGM's hard assignment (each new ingredient switched off one at a time).
* Sizes: S = 1,000 structures, seeds 1, 2, 3 for every method and unit; population-size sweep
  S ∈ {200, 500, 1,000, 2,000}, seed 1, Su test C1, both methods.  Same device and build for both
  methods (GPU when available, else CPU).

## 5. Metrics (`pop_metrics.py` + the existing `bulk_metrics.py`)

Reconstructions are mapped onto the truth loci by bin midpoint; copy labels are arbitrary (cis
samples pool same-copy combinations, trans samples all combinations; `bulk_metrics.pair_samples`).

* **Elliptical radial position ρ** (shape-aware, scale-free): per structure, centroid `c` and
  gyration tensor of all its non-missing loci (both copies), eigenpairs (λ_k, v_k);
  `ρ = |(V^T (x − c)) / sqrt(5 λ)|` (= 1 on the surface of the uniform ellipsoid with that gyration
  tensor).  Uses each structure's own (imaged or modelled) shape.
* **Pair distance W1**: per locus pair, W1 between the R and T distance samples (100 quantiles),
  R rescaled by one global factor (least squares on per-pair medians, `bulk_metrics.global_scale`),
  lengths in the truth's median consecutive-locus distance.
* **Fit to input**: per pair with input f ≥ 0.01 (|i − j| > 1 within a chromosome, all trans pairs),
  `|cf_R − f|`, cf_R = fraction of R's samples within the model's own contact distance
  `2 (r_i + r_j)` (model units, no rescaling).
* Secondary metrics: contact frequency at 0.5 rc and 2 rc vs truth (MAE); cell-to-cell variability
  (per-pair coefficient of variation of distances: Spearman R vs T and ratio of medians); chromosome
  territory neighbourhood frequencies (per chromosome pair, the fraction of structures × copy
  combinations whose two chromosome copies have any locus pair within rc: MAE and Spearman over
  chromosome pairs); nuclear shape (per structure gyration ratios sqrt(λ2/λ1), sqrt(λ3/λ1) and
  Rg after the global scale: W1 R vs T); per-locus mean ρ Spearman; centroid radial W1 (`bulk_metrics`);
  lamina (Su: Spearman of per-locus mean lamina distance vs the per-locus mean of 1 − ρ);
  three-body, clusters, C2ST, nearest-cell RMSD (`bulk_metrics.score_population`); wall time.

## 6. Primary endpoints (held-back units)

Simulation test units: (Su test, Takei) × (C1, C2, C3) = 6 units.  For every unit and method the
metric is averaged over the three seeds; Δ = IGM-sphere − EMber-pop for losses (positive = EMber-pop
better).  95 % CIs: percentile bootstrap, 2,000 replicates (seed 0), resampling **chromosomes** as
blocks (pairs weighted by the product of their two chromosomes' multiplicities), jointly over the
units of a dataset; the pooled statistic is the mean over the six units.

* **P1 — radial position**: mean over loci of the per-locus W1 of ρ (50 quantiles, copies pooled).
* **P2 — pair-distance distributions**: mean over 50,000 locus pairs (`bulk_metrics.all_pairs`, seed 0;
  cis and trans) of the per-pair W1.
* **P3 — fit to input (non-inferiority)**: mean |cf_R − f| over the pairs of §5.

## 7. Decision rule

EMber-pop is called **better than IGM** only if

1. P1 and P2 are both > 0 with 95 % CIs excluding 0 (pooled over the six simulation units), **and**
2. P3: the lower CI bound of Δ3 is above −0.2 × IGM-sphere's P3 value (EMber-pop's misfit at most
   20 % larger), **and**
3. real IMR90 vs Su test-half imaging: neither Δ1 nor Δ2 has a 95 % CI entirely below 0, **and**
4. no secondary stratum — P1 / P2 / P3 per unit, P2 per cis separation band (0–1, 1–2, 2–5, 5–10, 10–20,
   20–50, > 50 Mb) and trans (pooled over units) — is worse by more than 5 % of IGM-sphere's value of
   that stratum with a CI upper bound below 0, **and**
5. EMber-pop's wall time at S = 1,000 (median of the three seeds, Su test C1) is at most 3 × IGM-sphere's.

Otherwise the result is reported as it is: "better on X, equal on Y, worse on Z".  Every endpoint of
§5-§6, the comparison with IGM-ellipsoid, the ablations and the S sweep are reported whatever the
outcome.

## 8. Development protocol

* Development units: Su `dev_bulk` → `dev_truth`, conditions C1-C3; the WTC11 demo (fit and runtime);
  synthetic unit tests.  Development scores use the same metrics; every candidate and its numbers go to
  `POP_DEVLOG.md`.
* Existing protocols stay bit-identical: `packages/uchrom-recon/tests/regression.rs` and
  `src/igm/regression_tests.rs` (IGM hashes) must pass unchanged; EMber-pop options default to off in
  the `igm` protocol.
* Freeze: the method and its parameters are fixed in one commit tagged `ember-pop-frozen`, recorded in
  §10 with the test protocol (build, commands, seeds), **before** any held-back run.  The held-back
  test is run once, after the user approves the freeze.

## 9. The method being developed (design as of this date)

* **Population and engine**: IGM's diploid bead layout, radii, polymer bonds, soft-cosine excluded
  volume, annealing MD + CG on the native engine (CPU f64 / GPU f32, structures batched).
* **Assignment = EM over latent contacts**: per candidate pair (input f ≥ σ) and structure s, a
  latent contact indicator with prior q_s = κ(d_s), κ a logistic kernel in log distance around the
  contact distance; conditioned on the population frequency (f S contacts), the posterior inclusion
  probabilities are the exponentially tilted q_s (π_s = 1 / (1 + (d_s / d_λ)^β), d_λ solved per pair so
  that Σ π_s = f S — IGM's activation distance is the β → ∞ limit).  Soft responsibilities weight
  the contact restraints; β grows over the iterations and confident assignments are committed first
  (EMber deep: ambiguous assignments destabilise).
* **Two-sided**: structures whose current contact is not supported (π_s small, d_s < rc) get a
  lower-bound restraint, so over-represented contacts are corrected (IGM only adds contacts).
* **Bulk noise**: the input is a mixture of true contact frequency and a ligation-noise floor
  (estimated from the data); the A-step targets the denoised frequency.
* **No envelope**: a shape-free soft density cap (local density ≤ ρ_max on the neighbour grid,
  `κ/2 Σ_i (ρ_i − ρ_max)₊²`, ported from EMber-mix) and, if needed, a weak isotropic compaction
  (radius-of-gyration upper bound); trans contacts and excluded volume set the nuclear shape.
* Each ingredient is adopted only if it improves the development endpoints (P1, P2) without failing
  P3 / the strata; anything not adopted is reported in `POP_DEVLOG.md`.

## 10. Changes and additions

No held-back unit has been run with any method (the real IMR90 input was built, 2026-10-07, no method
run on it).

### 2026-10-07 — DRAFT of the freeze proposal (not approved, not frozen, no tag; development not finished)

Development record: `POP_DEVLOG.md` (§9: what is still needed).  The candidate below is B5; the leading
alternative is **B6 = B5 + `gyration_wall` 1.15** (a soft wall in each structure's own principal frame), the
only candidate better than IGM-sphere on P1 at the full schedule in one development seed; the choice between
B5 and B6 is made on the replicated development runs before the proposal is submitted.  If approved, the
commit that adds the approval date here is tagged `ember-pop-frozen` and the test below is run once.

* **Method ("EMber-pop", development candidate B5; B6 adds `gyration_wall` 1.15).**  Protocol `igm` of `packages/uchrom-recon`
  at the tagged commit, IGM 1.0 defaults (σ lists 1 → 0.01, demo annealing schedule, occupancy 0.2,
  bead radii from `nucleus_radius` = R_rg, iterative correction, contact range 2) plus:
  `nucleus_shape = "none"` (no envelope; the sphere of R_rg only sets the bead volumes);
  `gyration_prior` = the bulk cells' median gyration standard deviations σ1 ≥ σ2 ≥ σ3 (the imaging
  calibration of IGM-ellipsoid, whose semi-axes are sqrt(5) σ_k), `gyration_kspring` 0.1;
  `noncontact_kspring` 1.0 from the last σ (`noncontact_from_sigma` 5), range = the contact range;
  `max_iterations` 5 with `advance_on_max_iterations`.  = `pop_run.py --method ember_pop` (`EMBER_POP`),
  `deconvolve(method="ember_pop", nucleus=...)` with its defaults.  Not adopted (development evidence in
  `POP_DEVLOG.md`): the soft assignment (β 4-8: radial order lost), a noise floor (the C3 distortion is
  multiplicative — cis × 0.33, trans × 1.5 after the preprocessing — not a floor), the density cap (the
  non-contact restraints at rc already set the local density from the data), per-structure shapes of
  single imaged cells (worse than the median shape), a two-sided Rg prior (cigar-like structures).
* **Deviation from §9 / §1 (stated, not hidden): the method is not shape-free.**  On the development data
  the contacts did not determine the nuclear shape (every shape-free variant gave round or cigar-like
  structures); the large gains come from the imaging-calibrated, orientation-free, wall-free gyration
  prior.  It uses three imaging numbers (σ1-σ3) where IGM-sphere uses one (R_rg).
* **Comparators (addition):** IGM-ellipsoid uses the same three numbers and becomes a **co-primary**
  comparator: items 1-4 of §7 are evaluated against IGM-sphere and against IGM-ellipsoid, and EMber-pop is
  called better than IGM only if both pass; item 5 (wall time ≤ 3×) against IGM-sphere as registered (the
  ellipsoid wall time is reported).  Ablations replace those of §4: EMber-pop without the non-contact
  restraints; with IGM's sphere instead of the gyration prior; with the radius-of-gyration cap (one imaging
  scalar, the information of IGM-sphere) instead of the gyration prior; with gyration spring 1.
* **Implementation details fixed now:** IGM-ellipsoid radii equal to IGM-sphere's through the occupancy
  scaled by V_sphere / V_ellipsoid (the engine refuses `occupancy_total_bp` below the modelled genome); if
  that occupancy would reach 1, one bead radius for all beads = the median IGM-sphere radius
  (`pop_run.method_params`).  Ploidy: Su and IMR90 `diploid`, Takei `male` (chrX, chrY one copy).
  Real IMR90: calibration (R_rg, σ1-σ3, scale target 32.885) from the 894 Su development cells
  (`forward.py truth --split-set dev_bulk dev_truth`), truth = the 893 test-half cells, the model's own
  contact distance for scoring.  The bootstrap counts a cis pair once per resampled chromosome
  (`pop_test.py`).
* **Test protocol:** build of the tag (`pop_setup.sbatch`); inputs `pop_prepare.sbatch` (su_test:
  `su2020_genome`, test_bulk / test_truth, `centered:3000000`; takei_test: `takei2021_1mb`, test_bulk /
  test_truth, `centered:1000000`); real_imr90: `input_3mb.npz` → `real.npz`, `bulk_cells.npz` = the Su
  development cells, `truth.npz` = the test-half cells; runs `pop_pair.sbatch` with the tables of
  `pop_test_tables.py` (`test_main`: 18 lines × 3 methods, S = 1,000, seeds 1-3, full schedule, the three
  methods back to back on one GPU; `test_real`; `test_sweep`; `test_ablation`); scoring in the same job
  (`pop_score.py score`); endpoints and decision `pop_test.py --units su_test takei_test --b ember_pop
  --a igm_sphere igm_ellipsoid --real real_imr90 --runtime-unit su_test/C1`.  Results are reported
  whatever they are; no change to the method after the test.
