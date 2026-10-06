# EMber-mix (few-cell deconvolution) — development log

PREREG §12 (registered 2026-10-05 before any benchmark run).  Development units only: Takei 2021
1 Mb and Su 2020 genome-scale development truth cells, Stevens 2017 cells 1-4, the development half
of the Nagano 2017 serum cells.  No test pool has been generated or run.

Metrics (`mix_score.py`): **M2** = mean over the pool's cells of the Hungarian-matched whole-genome
Spearman r of distances (sims: vs the truth; real: vs the cell's own frozen-EMber reconstruction, so
the oracle is 1 by construction); **M1** = contact-to-cell assignment accuracy of every pooled row
under that matching (strata: trans, cis > 20 Mb, 2-20 Mb, < 2 Mb).  "naive" = frozen EMber on the
pool as one cell (every true cell scored against the one structure).  ll0 = mixture log-likelihood
per contact with a uniform cell prior.

## 1. Engine (as built)

* `native/nucdyn/src/mix.rs` — protocol `robust` with `mix_cells = k`: EMber's mixture with the
  cell as a latent variable; k cells x n replicate models of one particle system annealed in one
  batched engine call (per-model restraint weights; CPU and GPU); E-step per restart group; λ
  (mixing weights) learned; final E-step over every input contact (`cell_probs`, P(true)).
  Knobs: `mix_seed` (patch / random / uniform / tri / group), `mix_restarts` + selection, prior modes
  (`mix_seed_keep`, `mix_prior_mode` uniform / posterior, temperature, floor), 2-D neighbourhood
  smoothing, staged commitment, trans-triangle coupling (`mix_tri_prior`), must-link groups with a
  group E-step (`mix_group_radius`, `mix_group_tri_min`), assignment kernel (`mix_assign_d0`).
* `dynamics.rs` / GPU: shape-free soft density cap `κ/2 Σ_i (ρ_i − ρ_max)₊²`, ρ_i = Σ_j (1 − d²/R²)²
  (`System::density`; finite-difference test; GPU = CPU to 3e-5 after 10 steps).  Opt-in in
  `robust.rs` too (`mix_density_rho`, default 0 = frozen EMber unchanged).
* `src/mixseed.rs` — structure-free seeds: triangle-consistency mean-field Potts; trans-triangle links;
  must-link groups (2-D single linkage + trans-triangle merge).
* `uchrom_nucdyn.deconvolve_passes` — multi-pass driver: trans groups (2-D single linkage within 5 Mb
  per chromosome pair, merged by trans-triangle links); pass 1 seeds the largest group to cell 0;
  after every pass each group (>= 10 rows) takes, as a whole, the cell its rows prefer (mean
  `cell_probs`); one more cell is seeded per pass with the largest group the seeded cells explain worst.
* Existing protocols bit-identical: `tests/regression.rs` now also pins the diploid protocols
  (NucDynamics-2017 diploid, frozen EMber diploid, EMber deep), hashes recorded with origin/main
  c7c7d0f on macOS and on Sherlock; this branch reproduces all seven hashes on both platforms.

## 2. Findings on the development pools (laptop, Takei k = 2 / 3, Stevens k = 2-4)

**The information is there.**  With the true labels the mixture recovers the cells (Takei k2_p1 d40:
M2 0.68-0.80, M1 0.78-0.80, closest-structure M1 0.86 ≈ the per-cell oracle 0.86), and the true
partition has a clearly higher marginal likelihood than every partition found otherwise (ll0 2.57-2.61
vs ≤ 2.52 for 12 random restarts, density cap on).

**The problem is symmetry breaking, not the objective.**

| development experiment (Takei k=2, d40, ε 0.05) | M2 | M1 | note |
| --- | --- | --- | --- |
| naive EMber (pool as one cell) | 0.39-0.49 | — | |
| oracle EMber per cell | 0.68-0.74 | 0.83-0.86 | closest-structure rule |
| IGM S = k (sphere), k2_p1 | 0.435 | 0.499 | at chance |
| mix, random patch seed (default EM) | 0.43-0.45 | 0.52 | seed partition locks in, then converges to two consensus folds |
| seed released after stage 1 (uniform prior) | 0.45-0.47 | 0.49-0.53 | even the true seed decays: coarse structures do not tell the cells apart |
| posterior accumulation (prior = previous posterior), from a 60 % / 75 % / 85 % correct seed, density cap ρ 20 | 0.55 / 0.58 / 0.65 | 0.67 / 0.73 / 0.77 | **basin**: partially correct seeds are amplified |
| same, from 12 random patch seeds (k2_p2) | 0.35-0.49 | 0.47-0.58 | all chimeric / consensus; ll0 2.48-2.52 < truth 2.61 |
| triangle mean-field seed (tri) + posterior + cap ("A") | 0.66 on k2_p1, 0.32-0.46 elsewhere | 0.67 / ≈ 0.5 | seed accuracy 0.50-0.60 (mean 0.53) |
| A over all 32 Takei k = 2 / 3 development pools | 0.39 / 0.32 (naive 0.38 / 0.35) | 0.53 / 0.34 | no gain |

* Single structures absorb the union: the naive fold satisfies 96 % of the long-range contacts within
  4 radii; per-particle density (neighbours within 2 radii) 138 vs 56 for single cells; chimeric mix
  solutions 95.  The density cap at single-cell density (ρ_max 20, R = 2) enlarges the likelihood
  margin of the true partition (ll0 +0.25) but does not by itself break chimeras.  The no-contact term
  (`robust_nc_scale`) does not either.
* Structure-free cues: triangle closure of long-range partner pairs is 2.4x enriched within cells
  (66 % vs 28 %), but a pairwise Potts energy on it prefers genomically local labellings over the
  truth (annealed / spectral solutions reach lower energy than the truth with accuracy 0.50-0.70);
  ego-network clustering (local 0.72) does not synchronise globally (0.50-0.59).  **Trans triangles
  on three chromosomes** are far more specific: closure 12 % vs 1.9 % (sims, d40), 11 % vs 0.7 % (d10),
  **18 % vs 0.3 % in Stevens pools**; 2-D trans blobs are 98-99 % pure; joined by trans-triangle links
  the largest group of a Stevens k = 2 pool holds 38 % of the trans rows at 91 % purity.
* Trans labels are the lever on real data: with the true labels of the trans contacts only (cis
  uniform), k = 2 Stevens pools reach M2 0.92-0.94 (85 %-correct trans labels: 0.79-0.90).

**Real pools (Stevens 2017 cells 1-4, 200 kb, development)**

| method | k = 2 (6 pools) M2 | M1 | M1 trans | k = 3 (4) M2 | k = 4 (1) M2 |
| --- | --- | --- | --- | --- | --- |
| naive EMber | 0.400 | — | — | 0.296 | 0.229 |
| tri seed + posterior | 0.412 | 0.570 | 0.580 | — | — |
| largest trans group seed, 1 pass | 0.500 | 0.627 | 0.698 | — | — |
| + group re-seeding, pass 2 / pass 3 (Python prototype) | 0.546 / 0.592 | 0.67 / 0.62 | 0.76 / 0.84 | — | — |
| `deconvolve_passes` 3 passes ("P3") | **0.624** | 0.637 | 0.84 | 0.334 | 0.273 |
| `deconvolve_passes` k+3 passes, sequential cell seeding ("Q") | 0.540 | 0.643 | 0.735 | 0.367 | 0.270 |

k = 2: five of six pools clearly deconvolved (M2 0.51-0.79 vs naive 0.33-0.49; trans assignment
0.76-0.91); the pool with cells 2 + 4 (p5) is not (its largest trans group holds 239 rows).  k >= 3: no
useful gain yet — the sequential seeding of further cells is the open problem.  Run-to-run variation is
large (P3 vs Q differ by up to 0.3 on one pool).

**Simulated pools (Takei 1 Mb)**: the trans-group driver does not deconvolve them (k = 2, 8 pools:
M2 0.20-0.48, M1 0.50-0.57): the simulated 1 Mb maps are dense (80 % of the reads ≥ 5 Mb apart, ~150
long-range partners per locus), trans triangles are far less specific (15 % cross-cell links) and 5 Mb
blobs percolate across cells.  The simulations of §12 are much harder than the real pools for every
cue tried.

## 3. Development round 2 on Sherlock (2026-10-05, engine `dev-b34a9c4`)

Jobs `mix_dev.sbatch` (one GPU each), all development pools of Stevens (11), Nagano k = 2 / 3 / 5
(12), Takei and Su k = 2 / 3 / 5, pools 1-2, all four conditions (24 each).  Variants:
`mix_variants/real_r2.json`, `sim_r2.json`.  Rows: `data/mix_dev_r2.tsv` (`mix_aggregate.py`).
"Q" / "Qdc" = `deconvolve_passes` (k + 3 passes; Qdc with the density cap ρ 20); "A" = triangle
seed + posterior accumulation + cap; `diag_*` are diagnostics that use the true origin (not methods).

Mean M2 (matched whole-genome Spearman) by k:

| dataset | k | naive | IGM S=k | Q / Qdc | A | diag: 75 % seed | diag: true trans labels / true labels | oracle |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stevens | 2 | 0.400 | 0.359 | **0.545** | — | 0.801 | 0.933 | 1 |
| Stevens | 3 | 0.294 | 0.281 | 0.340 | — | 0.682 | 0.914 | 1 |
| Stevens | 4 | 0.229 | 0.269 | 0.278 | — | 0.640 | 0.905 | 1 |
| Nagano | 2 | 0.491 | — | 0.476 | — | 0.749 | 0.742 | 1 |
| Nagano | 3 | 0.384 | — | 0.336 | — | 0.607 | 0.684 | 1 |
| Nagano | 5 | 0.324 | — | 0.314 | — | 0.516 | 0.688 | 1 |
| Takei 1 Mb | 2 | 0.420 | 0.413 | 0.415 | 0.420 | 0.592 | 0.683 | 0.685 |
| Takei 1 Mb | 3 | 0.349 | 0.343 | 0.310 | 0.329 | 0.521 | 0.631 | 0.600 |
| Takei 1 Mb | 5 | 0.195 | 0.172 | 0.217 | 0.207 | 0.445 | 0.677 | 0.686 |
| Su genome | 2 | 0.462 | 0.407 | 0.438 | 0.482 | 0.680 | 0.846 | 0.862 |
| Su genome | 3 | 0.372 | 0.317 | 0.361 | 0.359 | 0.712 | 0.881 | 0.918 |
| Su genome | 5 | 0.291 | 0.223 | 0.261 | 0.259 | 0.628 | 0.845 | 0.895 |

Paired differences (95 % bootstrap over pools): Stevens Q − naive M2 +0.100 [+0.058, +0.146],
Q − IGM M2 +0.124 [+0.069, +0.187], Q − IGM M1 −0.009 [−0.094, +0.054]; Nagano Q − naive M2
−0.024 [−0.045, −0.002]; Takei Qdc − IGM M2 +0.005 [−0.022, +0.031]; Su Qdc − IGM M2 +0.038
[+0.029, +0.048] (Qdc − naive −0.022).  IGM with S = k is at chance in M1 everywhere (0.20-0.52 =
1/k) and below naive EMber in M2 on three of four datasets.

**Reading.**  (1) The observation model and the engine are right: with the true labels (sims) the
mixture reaches the per-cell oracle (Takei 0.68 vs 0.69, Su 0.85 vs 0.86-0.92 by k), and a 75 %-correct
seed is amplified to M2 0.45-0.80 on every dataset and k — far above naive and IGM.  On real pools the
true labels of the *trans* contacts alone give 0.68-0.93.  (2) What is missing is a reliable
structure-free source of that partial labelling.  The trans-triangle group seeding works only for
two-cell Stevens pools (5 of 6 deconvolved); it fails on Nagano pools (deeper, unequal cells: the
trans groups percolate into one 80 %-pure group — an adaptive threshold, `group_tri_min="auto"`,
did not fix it on the 4 Nagano k = 2 pools: M2 0.40-0.56 vs naive 0.40-0.55), on k >= 3 everywhere
(sequential seeding of further cells; seeding the k largest groups at once; stricter merging — all
tried on Stevens k = 3 / 4, no gain), and on the dense simulated pools.

## 4. Recommendation (no freeze yet)

No configuration meets the §12 development criterion (M1 and M2 improving on the development pools
with no stratum worse by more than 0.01): the best candidate (Q, trans-group passes) improves M2 on
Stevens k = 2 only and is worse than naive EMber on Nagano and on the simulations.  I recommend **not**
freezing and **not** running the §12 test.  The registered test as written would fail T1-T4 by these
numbers.  Possible next steps, each to be registered in §12 before it is run: (a) a reference- or
annotation-assisted route (the "Tangram-like" route of the plan): any external partial labelling at
the 75 % level — reference structures of the cell type, RNA-defined cell identity in spatial data,
phased SNPs in F1 hybrids — is amplified by the existing engine (diagnostic rows above); (b) a
better structure-free seed for k >= 3 and for deep cells (the trans-triangle signal is strong — 12-18 %
vs 0.3-1.9 % closure — but its groups merge across cells once a pool is deep); (c) fragment-end
exclusivity on real data with restriction-fragment coordinates (not available in the GEO tables used
here).

## 5. Cue 1 — cell-type prior from reference Dip-C (PREREG §12.1), development, pseudo-haploid (2026-10-05)

Tan 2021 adult cortex, registered split (reference P 80 / O 37 / A 15 / M 18 cells), 28 development
pools (7 compositions x 4), 200 kb, phases ignored everywhere (references included), laptop (Sherlock
access was denied for part of the day).  Prior: per-type 1 Mb pseudo-bulk (cells weighted 1 / depth),
smoothed (3 x 3 bins), pseudo-count 0.1 x mean, per-contact log-propensity, cell proportions by EM.
Rows: `data/mix_type_dev_r1.tsv`.

**The cue is weak per contact.**  ROC-AUC of the per-contact type log-likelihood ratio between the two
cells of a pool: 0.55-0.62 overall (cis 2-20 Mb 0.60-0.68, trans 0.50-0.55), the same at 500 kb and with
more smoothing.  Prior-only assignment is close to the cells' depth shares.  Aggregating the evidence over
the contacts of a 2-D blob or over a neighbourhood of bins does not help: contacts of one blob share their
bin pair, so their evidence is not independent (and aggregating over all rows of a bin pair mixes cells).

Mean M2 (matched whole-genome Spearman vs each cell's own EMber reconstruction) by composition:

| composition | naive | IGM S=k | prior-split | E (prior fixed) | E (posterior) | E + density cap | diag: 75 % seed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PO | 0.472 | 0.355 | 0.417 | 0.452 | 0.432 | 0.398 | 0.613 |
| PA | 0.424 | 0.331 | 0.376 | 0.415 | 0.393 | 0.375 | 0.562 |
| PM | 0.478 | 0.329 | 0.385 | 0.424 | 0.403 | 0.350 | 0.614 |
| OM | 0.467 | 0.368 | 0.459 | 0.424 | 0.443 | 0.389 | 0.624 |
| PAM | 0.420 | 0.349 | 0.329 | 0.386 | 0.377 | 0.325 | 0.570 |
| PP (same type) | 0.486 | 0.328 | 0.496 | 0.424 | 0.436 | 0.364 | 0.614 |
| PPO | 0.423 | 0.364 | 0.375 | 0.396 | 0.384 | 0.304 | 0.531 |

All 28 pools: E (prior fixed) − naive M2 −0.036 [−0.048, −0.023]; E − prior-split M2 +0.012
[−0.009, +0.033], M1 −0.052 [−0.094, −0.015]; E − IGM M2 +0.071 [+0.056, +0.086], M1 +0.001
[−0.035, +0.034].  Mean M1: E 0.51 / 0.33 (k = 2 / 3), prior-only 0.58 / 0.34, IGM 0.50 / 0.34, oracle
(closest of the true cells' structures) 0.69 / 0.53.

**Reading.**  Cue 1 does not work on these data: the type prior is too weak per contact (AUC ~0.6), and on
deep diploid cortex cells (300-500 k contacts each) even a 75 %-correct seed recovers less than on the
Stevens cells (M2 0.53-0.62 vs 0.80).  The 3-D EM adds nothing on top of the prior (M2 +0.01 vs prior-split,
M1 −0.05).  EMber-mix with the type prior is better than IGM S = k (M2 +0.07) but worse than naive EMber
on the pool (M2 −0.04) in every composition.  The density cap hurts (−0.06 more).  Under §12.1's
rule this would fail U1 and U2.  No further tuning (the §12.1 knobs left — reference resolution, smoothing,
γ — move the per-contact AUC by < 0.01 on the development pools).  The diploid (cells × copies) runs are
on Sherlock (§6 below when done).

## 6. Cue 1, diploid (cells × copies), development (2026-10-06, Sherlock jobs 46646505 + 46722984, engine `dev-ace6f8e`)

Same 28 development pools, phased (the authors' hickit pairs, both homologs), diploid mix engine
(`src/mixdip.rs`), oracle = frozen EMber diploid per cell; the same type prior as §5 (1 Mb pseudo-bulks,
phases ignored in the reference), on the diploid rows.  Variants `mix_variants/type_r1.json`.  Rows:
`data/mix_type_dev_d1.tsv`.  (The first batch failed at the `diag_seed75` step of 7 pools — the
oracle-prior path did not handle `.pairs.gz` pools; fixed in `run_mix.py` and those pools re-run with
the cached method runs.)

Mean M2 by composition (4 pools each):

| composition | naive | IGM S=k | prior-split | E (prior fixed) | E (posterior) | E + density cap | diag: 75 % seed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PO | 0.420 | 0.176 | 0.381 | 0.417 | 0.419 | 0.399 | 0.714 |
| PA | 0.432 | 0.161 | 0.408 | 0.456 | 0.438 | 0.412 | 0.785 |
| PM | 0.371 | 0.165 | 0.324 | 0.360 | 0.346 | 0.317 | 0.719 |
| OM | 0.379 | 0.172 | 0.390 | 0.381 | 0.376 | 0.371 | 0.697 |
| PAM | 0.298 | 0.204 | 0.258 | 0.305 | 0.284 | 0.283 | 0.641 |
| PP (same type) | 0.453 | 0.153 | 0.456 | 0.444 | 0.457 | 0.466 | 0.734 |
| PPO | 0.317 | 0.193 | 0.307 | 0.302 | 0.311 | 0.285 | 0.643 |

Mean M1 (k = 2 / 3): E (prior fixed) 0.51 / 0.32, E (posterior) 0.50 / 0.37, prior-only (argmax of the
prior, same-type ties at random) 0.58 / 0.39, prior-split 0.59 / 0.35, IGM 0.48 / 0.34, closest of the
true cells' structures 0.74 / 0.60.  Paired over all 28 pools (95 % bootstrap): E (prior fixed) − naive
M2 −0.000 [−0.018, +0.017]; E − prior-split M2 +0.020 [+0.000, +0.041], M1 −0.070 [−0.121, −0.022];
E − IGM M2 +0.206 [+0.173, +0.241], M1 +0.011 [−0.028, +0.052]; density cap − naive M2 −0.019
[−0.038, −0.000].

**Reading.**  Diploid modelling does not rescue cue 1.  The engine does better in the diploid setting —
a 75 %-correct seed reaches M2 0.64-0.79 (pseudo-haploid 0.53-0.62) — but the type prior is not a 75 %
labelling (prior-only M1 0.58 at k = 2, close to the depth share), and EM on top of it ties naive EMber in
M2 and loses 0.07 of M1 against prior-split.  §12.1 U1 (M1 E − prior-only > 0) and U2 (M2 E − naive > 0)
would fail in both ploidies.  **Cue 1 is closed as negative**; no further §12.1 knob was tried.  The
held-back cue-1 pools are not run.
