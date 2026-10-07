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
