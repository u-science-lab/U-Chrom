# EMber-pop development log (`PREREG_POP.md` section 8)

Development units only: Su 2020 genome-scale `dev_bulk` (447 cells) → bulk inputs C1-C3 →
reconstructions scored against `dev_truth` (447 cells); the IGM demo (fit, runtime).  No held-back
unit has been simulated or run (the real IMR90 input is being built; no method has run on it).

## 1. Development inputs

`forward.py truth --split-set dev_bulk / dev_truth`, `forward.py bulk` (PREREG §3).

| | value |
| --- | --- |
| bulk cells: R_rg = sqrt(5/3) median Rg | 7,411 nm (IGM-sphere radius) |
| bulk cells: gyration semi-axes sqrt(5) σ_k | 11,361 / 5,549 / 1,429 nm (σ3 / σ1 = 0.13: **flat nuclei**) |
| IGM bead radius (occupancy 0.2), rc = 2 (r_i + r_j) | 348 nm, 1,392 nm |
| C1 mean row sum (oracle target) | 31.6 contacts per bin; 489,740 of 541,320 pairs ≥ 0.01 |
| C3 vs exact (preprocessed, 1.08·10⁸ reads, ε 0.1) | Pearson 0.86, Spearman 0.69; cis compressed (slope 0.33), trans inflated (slope 1.51) |
| real IMR90 target (exact C1 row sum of the 894 Su development cells) | 32.885 |

The imaged IMR90 nuclei are flat (median sqrt(λ3/λ1) = 0.13) and much denser than IGM's sphere of
radius R_rg: the uniform ellipsoid with the median gyration tensor has 22 % of that sphere's volume.

## 2. Screening (C1, S = 100, schedule × 0.1, seed 1, laptop M5 Pro GPU)

P1 = mean per-locus W1 of the elliptical radius ρ; P2 = mean per-pair distance W1 (units of the median
consecutive-locus distance, 1,086 nm), cis / trans parts; P3 = fit MAE; ρSp = Spearman of per-locus
mean ρ; medSp / cvSp = Spearman of per-pair median distance / coefficient of variation; cvR = ratio of
median CVs (R / T); terrSp = territory-neighbourhood Spearman; cf1 = contact-frequency MAE at rc vs the
truth; r31 = median sqrt(λ3/λ1); lamSp = Spearman of per-locus mean (1 − ρ) vs the measured lamina
distance; scale = global factor applied to R.  Ceiling = the bulk cells scored against the truth cells.
Lower is better for P1, P2, P3, cf1.

| run | P1 | P2 | cis | trans | P3 | ρSp | medSp | cvSp | cvR | terrSp | cf1 | r31 | lamSp | scale | s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ceiling (bulk cells) | 0.011 | 0.170 | 0.075 | 0.175 | 0.002 | 0.99 | 0.95 | 0.58 | 1.01 | 0.72 | 0.005 | 0.13 (T) | 0.94 | 0.99 | |
| **IGM sphere** | 0.055 | 1.044 | 0.580 | 1.068 | 0.006 | 0.88 | 0.62 | 0.25 | 0.68 | −0.14 | 0.022 | 0.93 | 0.90 | 1.49 | 71 |
| **IGM ellipsoid** (imaging semi-axes) | 0.068 | 0.450 | 0.285 | 0.459 | 0.011 | 0.25 | 0.54 | 0.09 | 0.96 | 0.20 | 0.012 | 0.12 | 0.17 | 0.97 | 35 |
| IGM sphere, p = f (no iterative correction) | 0.057 | 1.028 | 0.483 | 1.056 | 0.011 | 0.90 | 0.64 | 0.25 | 0.68 | −0.03 | 0.022 | 0.92 | 0.90 | 1.58 | 54 |
| no envelope, nothing else | 0.285 | 2.155 | 0.355 | 2.248 | 0.005 | 0.28 | 0.68 | 0.15 | 1.61 | 0.24 | 0.016 | 0.48 | 0.36 | 1.27 | 282 |
| no envelope + non-contact (nc) k 1 from σ index 0 | 0.244 | 0.912 | 1.081 | 0.904 | 0.011 | 0.27 | 0.38 | 0.14 | 1.16 | 0.48 | 0.084 | 0.62 | 0.28 | 0.47 | 219 |
| no envelope + nc k 0.1 from σ 0 | 0.321 | 1.776 | 0.747 | 1.829 | 0.005 | −0.03 | 0.21 | 0.10 | 1.40 | 0.48 | 0.071 | 0.58 | 0.07 | 0.61 | 445 |
| no envelope + nc k 1 at the last σ | 0.297 | 2.311 | **0.223** | 2.419 | 0.005 | 0.14 | 0.51 | 0.18 | 1.50 | 0.39 | **0.009** | 0.50 | 0.20 | 1.11 | 318 |
| Rg cap (imaging Rg) | 0.059 | 0.995 | 0.600 | 1.015 | 0.006 | 0.91 | 0.73 | 0.37 | 0.69 | 0.39 | 0.022 | 0.89 | 0.85 | 1.50 | 75 |
| Rg cap + nc last σ, k 1 | 0.067 | 0.959 | 0.498 | 0.982 | 0.006 | 0.90 | 0.74 | 0.35 | 0.70 | 0.37 | 0.021 | 0.88 | 0.84 | 1.46 | 143 |
| Rg cap + nc last σ, k 0.3 | 0.070 | 0.948 | 0.507 | 0.971 | 0.007 | 0.90 | 0.74 | 0.36 | 0.71 | 0.36 | 0.021 | 0.86 | 0.84 | 1.48 | 138 |
| Rg cap + nc last σ + IGM A-step (iterative correction) | 0.055 | 0.998 | 0.527 | 1.022 | 0.006 | 0.92 | 0.73 | 0.28 | 0.69 | 0.48 | 0.022 | 0.88 | 0.87 | 1.37 | 123 |
| Rg cap + soft (β 4 → 32) | 0.140 | 1.124 | 0.386 | 1.162 | 0.071 | 0.67 | 0.71 | 0.19 | 1.11 | 0.61 | 0.020 | 0.61 | 0.60 | 2.18 | 57 |
| Rg cap + nc last σ + soft | 0.105 | 0.974 | 0.447 | 1.001 | 0.007 | 0.73 | 0.75 | 0.23 | 0.98 | 0.58 | 0.020 | 0.68 | 0.65 | 1.45 | 168 |
| two-sided Rg prior | 0.178 | 1.092 | 0.530 | 1.121 | 0.005 | 0.70 | 0.73 | −0.04 | 1.38 | 0.45 | 0.016 | 0.32 | 0.73 | 1.27 | 218 |
| two-sided Rg prior + nc last σ | 0.183 | 1.066 | 0.364 | 1.102 | 0.005 | 0.77 | 0.71 | 0.03 | 1.41 | 0.43 | 0.015 | 0.35 | 0.79 | 1.25 | 273 |
| **gyration prior** (imaging σ1-σ3, k 1) | **0.054** | 0.347 | 0.206 | 0.354 | 0.007 | **0.93** | **0.81** | 0.32 | 0.97 | **0.61** | 0.008 | 0.13 | 0.91 | 0.99 | 96 |
| gyration prior + nc last σ (IGM A-step) | **0.052** | 0.346 | **0.188** | 0.354 | 0.006 | 0.91 | 0.79 | 0.29 | 0.96 | **0.61** | **0.007** | 0.14 | 0.89 | 1.00 | 183 |
| gyration prior + nc last σ, p = f | 0.077 | **0.324** | 0.236 | **0.329** | 0.006 | 0.89 | 0.80 | 0.22 | 1.01 | 0.41 | **0.007** | 0.13 | 0.92 | 1.02 | 204 |

Findings of the screening:

1. **The global nuclear shape dominates the pair-distance distributions** (P2): with the imaging
   semi-axes as a hard ellipsoid, IGM's P2 falls from 1.04 to 0.45 — but its radial organisation is lost
   (ρ Spearman 0.25, lamina 0.17): the flat ellipsoid of the imaging size holds IGM's beads at occupancy
   0.9, so nothing can sort.
2. **The contacts do not determine the shape.** Every shape-free variant (no envelope; non-contact
   restraints; radius-of-gyration cap or two-sided prior) gives round or cigar-like structures
   (sqrt(λ3/λ1) 0.32-0.94 vs 0.13 in the truth).  The contacts do set the density: with the Rg cap the
   structures shrink to about the truth's volume (scale 1.46-1.50) but stay round.  Without any global
   term chromosomes drift apart (trans W1 2.2-2.4).
3. Two-sided assignment (non-contact restraints, at the last σ only: from σ index 0 the early structures
   swell and never recover) improves the cis distances and the contact frequencies (cf1 0.009 vs 0.022)
   but needs a global term.
4. Soft assignment with a low β (4) over-compacts (p = f for every candidate pair gives every structure a
   weak pull) and loses the radial order; not pursued at β 4.
5. **An orientation-free, wall-free gyration-shape prior** (the imaging standard deviations along each
   structure's own principal axes, the same three numbers as the IGM ellipsoid) gives the best P1 and P2
   at once: radial order kept (ρ Spearman 0.93, lamina 0.91), pair distances P2 0.35, cell-to-cell
   variability at the truth's level (cvR 0.97 vs IGM 0.68), territory neighbourhoods (0.61 vs −0.14).

**Consequence for the design (decision point for the user):** the purely shape-free EMber-pop (one
imaging scalar, as IGM-sphere) is only slightly better than IGM-sphere on P2 and equal on P1; the large
gains need the imaging shape statistics (three scalars, as IGM-ellipsoid) in the soft prior.  The method
going forward is "IGM A/M + no envelope + gyration-shape prior (+ non-contact restraints at the last σ)";
since it uses the same imaging information as IGM-ellipsoid, the freeze proposal adds IGM-ellipsoid as a
co-primary comparator (PREREG §10, before any test run).

## 3. Tuning the gyration-prior method (C1, S = 100, schedule × 0.1, laptop GPU)

Seed-to-seed spread at this size is small (sd over 3-4 seeds: P1 ≤ 0.001, P2 ≤ 0.013, P3 < 0.0001), so
differences ≥ 0.005 in P1 and ≥ 0.03 in P2 are above the noise; "(n)" = seeds.

| variant | P1 | P2 | cis | trans | P3 | ρSp | terrSp | cvR | s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IGM sphere (4) | 0.055 | 1.043 | 0.581 | 1.067 | 0.0060 | 0.88 | −0.05 | 0.68 | 76 |
| IGM ellipsoid (3) | 0.067 | 0.439 | 0.289 | 0.447 | 0.0112 | 0.26 | 0.13 | 0.96 | 31 |
| gyration k 1 (3) | 0.054 | 0.347 | 0.206 | 0.354 | 0.0073 | 0.93 | 0.62 | 0.97 | 93 |
| gyration k 10 | 0.055 | 0.346 | 0.202 | 0.353 | 0.0073 | 0.94 | 0.64 | 0.97 | 95 |
| gyration k 0.1 (2) | **0.050** | 0.342 | 0.217 | 0.348 | 0.0071 | 0.93 | 0.56 | 0.97 | 97 |
| gyration k 0.03 | **0.048** | 0.341 | 0.226 | 0.347 | 0.0070 | 0.93 | 0.59 | 0.97 | 94 |
| gyration k 0.01 | 0.053 | 0.348 | 0.267 | 0.352 | 0.0055 | 0.91 | 0.55 | 0.98 | 111 |
| gyration k 1, one imaged cell per structure | 0.066 | 0.385 | 0.186 | 0.395 | 0.0055 | 0.90 | 0.64 | 1.05 | 157 |
| gyration k 1 + nc last σ (3) | 0.053 | 0.350 | 0.188 | 0.359 | 0.0057 | 0.91 | 0.62 | 0.96 | 176 |
| gyration k 1 + nc last σ, p = f | 0.077 | 0.324 | 0.236 | 0.329 | 0.0058 | 0.89 | 0.41 | 1.01 | 204 |
| gyration k 1 + soft (β 8 → 32) + nc | 0.080 | 0.348 | 0.300 | 0.350 | 0.0059 | 0.89 | 0.47 | 1.02 | 167 |
| gyration k 0.1 + nc last σ k 1 (2) | 0.050 | 0.345 | 0.205 | 0.353 | 0.0057 | 0.90 | 0.57 | 0.96 | 192 |
| gyration k 0.1 + nc k 0.3 | 0.054 | 0.327 | 0.201 | 0.334 | 0.0055 | 0.91 | 0.56 | 0.98 | 211 |
| gyration k 0.1 + nc k 1, range 1.5 (2) | 0.055 | 0.333 | 0.193 | 0.340 | 0.0053 | 0.91 | 0.55 | 0.99 | 218 |
| gyration k 0.1 + nc k 1, range 1.25 | 0.058 | 0.326 | 0.193 | 0.333 | 0.0053 | 0.91 | 0.56 | 0.99 | 223 |
| **B5** = gyration k 0.1 + nc k 1 last σ + ≤ 5 iterations / σ (3) | **0.051** | 0.345 | 0.207 | 0.355 | 0.0060 | 0.90 | 0.59 | 0.96 | **95-108** |
| B5 with nc k 0.3 | 0.054 | 0.337 | 0.204 | 0.344 | 0.0057 | 0.89 | 0.57 | 0.97 | 108 |
| B5 with nc range 1.5 | 0.054 | 0.330 | 0.196 | 0.337 | 0.0053 | 0.90 | 0.56 | 0.98 | 103 |
| B5 with gyration k 1 | 0.052 | 0.349 | 0.195 | 0.357 | 0.0060 | 0.89 | 0.63 | 0.96 | 110 |

* A weaker gyration spring (0.03-0.1) gives the best radial positions; the gyration prior alone fits the
  input slightly worse than IGM (P3 0.0071 vs 0.0060, at the edge of the registered 20 % margin).
* The non-contact restraints at the last σ bring P3 back to IGM's level (0.0057-0.0060) and improve the cis
  distances; with IGM's iteration rule they keep the violation score above 1 % and use all 10 iterations of
  the last σ (2.5-2.9 × IGM's wall time); **≤ 5 iterations per σ** (`max_iterations` 5 + advance) keeps P1 /
  P2 / P3 and cuts the wall time to 1.3-1.4 × IGM.
* Not adopted: soft assignment (P1 0.080), p = f (P1 0.077), per-structure shapes of single imaged cells
  (P1 0.066: a structure forced into an arbitrary cell's size and shape fits its contacts worse; the cell
  variability is reproduced anyway, cvR 0.96-0.97 with the median shape), shorter non-contact range.
* **Candidate B5** = no envelope + gyration prior k 0.1 (imaging median σ1-σ3) + non-contact restraints k 1
  at the last σ (IGM A-step with iterative correction) + ≤ 5 iterations per σ.

Dev preview of the decision rule (`pop_test.py`, su_dev C1 only, 1,000 bootstrap replicates; this is one
development unit, not the test):

| B5 vs | P1 diff [95 % CI] | P2 diff | P3 diff | wall time |
| --- | --- | --- | --- | --- |
| IGM sphere | +0.0043 [+0.0019, +0.0064] | +0.70 [+0.59, +0.79] | −0.0001 [−0.0003, +0.0003] | 1.65 × |
| IGM ellipsoid | +0.0167 [+0.0112, +0.0224] | +0.097 [+0.056, +0.139] | +0.0052 [+0.0049, +0.0058] | 3.6 × |

## 4. Other conditions (S = 100, schedule × 0.1, seed 1)

| | C2 (Gaussian kernel) P1 / P2 / cis / P3 | C3 (finite depth + noise) P1 / P2 / cis / P3 |
| --- | --- | --- |
| IGM sphere | 0.058 / 1.035 / 0.669 / 0.0066 | 0.077 / 1.020 / 1.065 / 0.018 |
| IGM ellipsoid | 0.067 / 0.444 / 0.290 / 0.0104 | **0.068** / 0.446 / **0.288** / 0.026 |
| gyration k 0.1 (no nc) | **0.053** / **0.311** / 0.242 / 0.0071 | 0.086 / 0.420 / 0.514 / 0.015 |
| **B5** | 0.054 / 0.326 / 0.267 / **0.0060** | 0.072 / **0.382** / 0.831 / **0.013** |

**C3 is the weak spot.**  The IGM preprocessing of the noisy finite-depth matrix compresses the cis
probabilities 3× and inflates trans 1.5× (§1); every contact-driven model then puts cis loci too far apart
and loses part of the radial order (IGM sphere: ρ Spearman 0.46, lamina 0.23; B5: 0.76 / 0.57).  The IGM
ellipsoid is insensitive (its flat wall at occupancy 0.9 packs the loci whatever the contacts say) and is
better than B5 on C3 for P1 (0.068 vs 0.072) and for the cis distances (0.29 vs 0.83).  The non-contact
restraints help B5's radial order on C3 (P1 0.072 vs 0.086 without) but cost cis distances (they enforce
the compressed cis frequencies).  No noise model was adopted: the distortion is multiplicative and
class-dependent, not a floor, and nothing in the development data identifies the scale without the truth.

## 5. Full annealing schedule (S = 200; the test runs the full schedule)

The screening used the schedule × 0.1.  With the full IGM schedule IGM-sphere's radial positions improve
markedly (P1 0.055 → 0.047; the radial slope of the per-locus means R vs T 0.57 → 0.72), and further with S
(S = 500: 0.046, S = 1,000: 0.045; Sherlock, TITAN Xp), while B5's do not (0.051 → 0.049): **at the test's
scale B5 is not better than IGM-sphere on P1**.  Its P2 advantage stays large (0.44 vs 1.04).  Adding a soft
wall in each structure's own principal frame (B6) recovers P1 (0.043).

| run (C1, S = 200, full schedule) | P1 | P2 | cis | trans | P3 | ρSp | terrSp | cvR | wall s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IGM sphere (laptop M5 Pro, seed 2) | 0.047 | 1.035 | 0.523 | 1.061 | 0.005 | 0.93 | 0.32 | 0.67 | 1,057 |
| IGM sphere (Sherlock TITAN Xp, seed 1; S = 500 / 1,000) | 0.047 (0.046 / 0.045) | 1.036 (1.033 / 1.031) | 0.52 | 1.06 | 0.005 | 0.93 | 0.30 | 0.67 | 1,291 (2,447 / 4,580) |
| B5 (laptop, seed 2) | 0.049 | 0.444 | 0.204 | 0.457 | 0.005 | 0.91 | 0.57 | 0.94 | 2,345 |
| B5 with 10 iterations / σ (Sherlock, seed 1) | 0.049 | 0.425 | 0.199 | 0.437 | 0.005 | 0.91 | 0.63 | 0.94 | 4,040 |
| **B6** = B5 + principal-frame wall 1.15 (laptop, seed 2) | **0.043** | **0.436** | 0.201 | 0.448 | 0.005 | 0.91 | 0.65 | 0.94 | 2,172 |

Principal-frame wall (`gyration_wall`: IGM's envelope in each structure's own principal frame, semi-axes
1.15 × sqrt(5) σ_k; screening at S = 100, × 0.1): C1 P1 0.047 / P2 0.338 (B5 0.051 / 0.351); C3 P1 **0.064**
/ P2 0.352 / cis 0.73 (B5 0.072 / 0.382 / 0.83; IGM ellipsoid 0.068 / 0.446 / 0.29); wall 1.0 is too tight
(territory Spearman −0.10, P2 0.52).  At the full schedule B6 is the only candidate better than IGM-sphere
on P1 (0.043 vs 0.047, one seed each; not yet replicated — the Sherlock replicates were cut off, below).

## 6. IGM demo (WTC11 2 Mb, no truth): fit and runtime

Native IGM on the demo input, S = 1,000, Sherlock TITAN Xp: wall time 6,121 s, Pearson of the population's
contact probabilities vs the input on the restrained pairs 0.933 (the H100 runs of `design.md`: 0.933 in 782 s).
The EMber-pop runs on the demo had not finished when Sherlock access was lost (below): **no demo comparison
yet**.

## 7. Runtime

Same device, same S, full schedule: B5 / B6 take 2.0-2.2 × IGM-sphere's wall time (laptop GPU, S = 200:
2,172-2,345 s vs 1,057 s) — inside the registered 3 × bound, mostly the non-contact restraints (wider
neighbour grid) and more iterations at the last σ.  At S = 100 × 0.1 the ratio was 1.3-1.65 ×.  IGM-sphere's
wall time scales linearly in S (1,291 / 2,447 / 4,580 s at S = 200 / 500 / 1,000 on a TITAN Xp).

## 8. What was not done or not adopted, and why

* **Shape-free confinement** (the original design intent): every variant without an imaging shape —
  no envelope, the non-contact restraints alone, an Rg cap, a two-sided Rg prior — left the structures round
  or cigar-like; Hi-C contacts at this resolution do not identify the flat nuclear shape (§2).  The shape
  must come from imaging (three numbers: the gyration standard deviations).
* **Shape-free soft density cap (EMber-mix port)**: not ported.  With the non-contact restraints the
  local density within the contact distance is set by the assigned contacts (data-driven), which is what the
  cap was meant to bound; without them the gyration prior bounds the volume.
* **EMber observation model, soft responsibilities with staged commitment**: implemented (contact weight π
  = 1 / (1 + (d / d_act)^β), β schedule, commitment, 9-bit weights on the GPU) and tested; it over-compacts
  at low β and loses the radial order (P1 0.080-0.140); not adopted.
* **Bulk noise mixture**: not implemented.  The development noise condition (C3) is dominated by the IGM
  preprocessing's class-dependent rescaling (cis × 0.33, trans × 1.5), not by an additive ligation floor;
  nothing on the development data identifies that rescaling without the truth.  C3 remains the weak spot
  (§4).
* **Per-structure shapes of single imaged cells**: implemented (`gyration_targets`), worse than the median
  shape (P1 0.066).
* Held back, not run: Su 2020 test half, Takei 2021, real IMR90 (its input is built).

## 9. State at the stop (2026-10-07) and what is still needed before a freeze

* Sherlock access was refused (`Permission denied`) during the full-schedule replicates; the queued / running
  development jobs (B6 at S = 200 on C1 seeds 1 and 3, C2, C3; IGM baselines on C2 / C3 at the full schedule;
  the size sweep with B5; the demo comparison) were not collected.  Laptop runs were interrupted too.
* Before a freeze: replicate B6 vs IGM-sphere vs IGM-ellipsoid at the full schedule on C1-C3 (≥ 2 seeds), the
  WTC11 demo fit / runtime with B6, then fix B5 or B6 in `PREREG_POP.md` §10 (the draft there names B6 as the
  leading candidate) and wait for the user's approval.  No held-back unit has been run.
