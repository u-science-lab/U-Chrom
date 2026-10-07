# Type deconvolution (PREREG §14) — development log

Development units only (POOL-dev tissues).  Every variant tried and every number goes here, dated.

## 2026-10-07 — setup

* Code and tests written; synthetic toys only (three toy types with flipped compartments: TD, NNLS and
  dominant pooling all recover them; the random-composition control does not).  Not evidence on data.
* Composition-noise levels calibrated on the composition generator (PREREG §14.3).
* Timing with fake contacts of the real size (600 / 150 spots, 8.5 / 11.6 M contacts): 1 Mb TD 0.2 s per EM
  iteration, NNLS 2 s; 250 kb TD 0.65 s per iteration, NNLS 66 s (laptop).
* No run on data: Sherlock access was denied at registration (needs a new login).

## 2026-10-07 — development runs (POOL-dev tissues; jobs 46912975 prepare, 46912976 fit 1-8, 46912977 aggregate)

Sherlock CPU (normal / owners), venv-main; one fit task per tissue (all res x noise), 42 min - 2.5 h each, peak RSS
~1 GB at 1 Mb.  Outputs: `$SCRATCH/uchrom-nd/runs/spatial/typedecon/{split.tsv,cells,truth,tissues,scores/dev,tables/dev}`.

* **Cells**: cis contacts (>= 1 kb, chr1-19) per cell, median 191 k (O dev) - 395 k (L6 dev); TRUTH totals P 28.2 M,
  L6 9.6 M, I 8.7 M, O 9.1 M, A 3.6 M, M 3.9 M.  Tissues: low 8.1-8.5 M contacts / 600 spots, high 11.1-11.7 M / 150
  spots; **no contact reused** in any development tissue.
* **Composition given** (realised): moderate MAE 0.045 / 0.053, r 0.96 / 0.94 (low / high); heavy MAE 0.081 / 0.095,
  r 0.86 / 0.80.
* **Truth reliability (noise ceiling)**: TRUTH half A vs half B, 1 Mb: P1 0.223, P2 0.486 (per type P1 P .21, L6 .14,
  I .12, O .31, A .16, M .38); 250 kb: 0.195 / 0.501.  The type contrasts at these resolutions are small against
  sampling noise: every number below is bounded by this, and the oracle (0.25 / 0.54) sits only just above it.

**1 Mb** — P1 contrast_r / P2 comp_r, mean of 4 tissues

| regime | noise | TD-ps0.2 | TD | dominant | nnls | random | oracle |
|---|---|---|---|---|---|---|---|
| low | exact | 0.244 / 0.532 | 0.239 / 0.516 | 0.229 / 0.507 | 0.234 / 0.499 | 0.010 / 0.018 | 0.253 / 0.535 |
| low | moderate | 0.241 / 0.529 | 0.237 / 0.511 | 0.224 / 0.500 | 0.229 / 0.491 | 0.011 / 0.023 | 0.253 / 0.535 |
| low | heavy | 0.229 / 0.511 | 0.225 / 0.495 | 0.211 / 0.479 | 0.216 / 0.471 | 0.010 / 0.020 | 0.253 / 0.535 |
| high | exact | 0.231 / 0.509 | 0.226 / 0.484 | 0.188 / 0.432 | 0.216 / 0.459 | 0.001 / 0.007 | 0.255 / 0.540 |
| high | moderate | 0.223 / 0.495 | 0.219 / 0.470 | 0.176 / 0.402 | 0.208 / 0.440 | 0.004 / 0.006 | 0.255 / 0.540 |
| high | heavy | 0.204 / 0.460 | 0.200 / 0.440 | 0.171 / 0.398 | 0.189 / 0.411 | 0.007 / 0.024 | 0.255 / 0.540 |

**250 kb** — P1 contrast_r / P2 comp_r, mean of 4 tissues (insulation contrast r in parentheses)

| regime | noise | TD-ps0.2 | TD | dominant | nnls | random | oracle |
|---|---|---|---|---|---|---|---|
| low | exact | 0.186 / 0.503 (0.54) | 0.177 / 0.482 (0.16) | 0.164 / 0.467 (0.52) | 0.178 / 0.469 (0.53) | 0.007 / 0.029 (0.00) | 0.206 / 0.518 (0.57) |
| low | moderate | 0.180 / 0.494 (0.53) | 0.172 / 0.472 (0.06) | 0.159 / 0.454 (0.51) | 0.173 / 0.458 (0.52) | 0.007 / 0.028 (-0.00) | 0.206 / 0.518 (0.57) |
| low | heavy | 0.164 / 0.468 (0.50) | 0.156 / 0.447 (0.04) | 0.145 / 0.430 (0.48) | 0.157 / 0.430 (0.48) | 0.008 / 0.018 (-0.00) | 0.206 / 0.518 (0.57) |
| high | exact | 0.175 / 0.489 (0.51) | 0.166 / 0.461 (0.12) | 0.137 / 0.403 (0.44) | 0.168 / 0.443 (0.49) | 0.003 / 0.026 (0.00) | 0.217 / 0.535 (0.58) |
| high | moderate | 0.164 / 0.466 (0.49) | 0.156 / 0.440 (0.07) | 0.125 / 0.367 (0.40) | 0.157 / 0.419 (0.46) | 0.002 / 0.017 (0.01) | 0.217 / 0.535 (0.58) |
| high | heavy | 0.144 / 0.420 (0.44) | 0.136 / 0.396 (0.04) | 0.120 / 0.358 (0.39) | 0.139 / 0.375 (0.42) | 0.005 / 0.024 (0.01) | 0.217 / 0.535 (0.58) |

**Selection rule** (1 Mb, mean (P1 + P2) / 2 over the 24 development units; worst (regime, noise, res) stratum vs plain TD):

| variant | mean | worst ΔP1 | worst ΔP2 |
|---|---|---|---|
| TD | 0.3551 | +0.0000 | +0.0000 |
| TD-ps0.2 | 0.3674 | +0.0035 | +0.0165 |
| TD-r20 | 0.3626 | -0.0231 | -0.0390 |
| TD-s0.05 | 0.3602 | +0.0028 | +0.0041 |
| TD-s0.2 | 0.3635 | +0.0040 | +0.0079 |
| TD-s1 | 0.3647 | +0.0022 | +0.0098 |
| TD-y | 0.3570 | -0.0162 | -0.0185 |

**Paired differences of TD-ps0.2** (unit = tissue, both regimes, 8 per noise level; 95 % bootstrap):

| res | noise | − dominant P1 | P2 | − NNLS P1 | P2 | − shuffled P1 | P2 | − oracle P1 | P2 |
|---|---|---|---|---|---|---|---|---|---|
| 1 Mb | exact | +0.029 [+0.019, +0.039] | +0.051 [+0.033, +0.071] | +0.013 [+0.011, +0.015] | +0.042 [+0.035, +0.049] | +0.232 [+0.222, +0.242] | +0.508 [+0.490, +0.529] | -0.016 [-0.022, -0.010] | -0.017 [-0.027, -0.006] |
| 1 Mb | moderate | +0.032 [+0.021, +0.042] | +0.061 [+0.037, +0.084] | +0.014 [+0.012, +0.016] | +0.046 [+0.040, +0.052] | +0.225 [+0.212, +0.235] | +0.497 [+0.477, +0.516] | -0.022 [-0.029, -0.014] | -0.026 [-0.039, -0.012] |
| 1 Mb | heavy | +0.025 [+0.020, +0.031] | +0.047 [+0.036, +0.059] | +0.014 [+0.013, +0.015] | +0.045 [+0.038, +0.052] | +0.208 [+0.190, +0.224] | +0.464 [+0.431, +0.494] | -0.038 [-0.048, -0.027] | -0.052 [-0.071, -0.031] |
| 250 kb | exact | +0.030 [+0.024, +0.036] | +0.061 [+0.044, +0.080] | +0.008 [+0.007, +0.009] | +0.040 [+0.035, +0.045] | +0.176 [+0.169, +0.183] | +0.469 [+0.455, +0.483] | -0.031 [-0.038, -0.023] | -0.030 [-0.041, -0.019] |
| 250 kb | moderate | +0.030 [+0.024, +0.037] | +0.069 [+0.048, +0.091] | +0.007 [+0.006, +0.008] | +0.041 [+0.037, +0.045] | +0.168 [+0.159, +0.175] | +0.458 [+0.438, +0.475] | -0.039 [-0.048, -0.030] | -0.046 [-0.063, -0.030] |
| 250 kb | heavy | +0.022 [+0.019, +0.024] | +0.050 [+0.040, +0.060] | +0.006 [+0.004, +0.007] | +0.041 [+0.037, +0.046] | +0.148 [+0.135, +0.159] | +0.423 [+0.389, +0.453] | -0.057 [-0.068, -0.046] | -0.083 [-0.106, -0.060] |

**S1** (r of log O/E, E_upper − E_lower vs truth P − L6; 1 Mb, mean over tissues and noise levels):

| method | low | high |
|---|---|---|
| TD-groups(shrink=0.0) | 0.034 | 0.037 |
| TD-groups(shrink=0.1) | 0.034 | 0.037 |
| TD-groups(shrink=1.0) | 0.033 | 0.035 |
| dominant-groups | 0.027 | 0.033 |
| oracle(P vs L6 by origin) | 0.048 | 0.052 |

**Reading.**

* **Selection (§14.5 rule)**: **TD-ps0.2** (shrink 0.2 towards the pooled profile rescaled to each type's P(s)) has
  the highest development mean (0.367 vs plain TD 0.355) and no stratum worse than plain TD (worst +0.004 / +0.017).
  Learned yield (TD-y) and composition refinement (TD-r20) fail the rule (worse than TD by 0.016-0.039 in some
  strata; TD-r20 helps only under heavy noise in the high regime).  **Proposed, not frozen.**
* TD-ps0.2 beats dominant-type pooling and NNLS in every stratum, CIs above 0: vs dominant +0.025-0.032 (P1) /
  +0.047-0.061 (P2) at 1 Mb, larger in the high-depth (multi-cell) regime where spots are more mixed
  (high, moderate: 0.223 / 0.495 vs 0.176 / 0.402); vs NNLS small in P1 (+0.013-0.014), larger in P2 (+0.042-0.046).
* Shuffled compositions give ~0 (P1 0.00-0.01): the recovered contrasts come from the composition information.
* Distance to the oracle at 1 Mb: −0.016 / −0.017 (exact), −0.022 / −0.026 (moderate), −0.038 / −0.052 (heavy);
  TD-ps0.2 reaches 87-96 % of the oracle P1 with moderate noise.
* At 250 kb plain TD (no shrinkage) has **near-zero insulation-contrast r (0.04-0.16)** while every pooled method
  has ~0.4-0.55: the unshrunk mixture profiles are noisy at fine resolution; the shrinkage fixes it (0.44-0.54).
* **S1 is uninformative**: even origin-pooled P vs L6 correlates only 0.05 with the truth P − L6 difference (the
  noise level of 27 + 80 truth cells), so spatially varying profiles cannot be evaluated on this pair.
* Caveats: the absolute levels (P1 ~0.2, P2 ~0.5) are set by the truth's own noise, not by the method.  The types
  are the authors' structure clusters; real RNA-derived compositions may err differently from the Dirichlet model.
