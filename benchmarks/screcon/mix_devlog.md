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
