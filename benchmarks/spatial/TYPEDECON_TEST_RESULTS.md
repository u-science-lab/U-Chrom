# Type deconvolution — held-back test results (PREREG §14.6 / §14.10)

Run once, 2026-10-07, with the frozen method (tag `typedecon-frozen`: TD* = `fit_td(shrink=0.2,
prior_mean="pooled_ps")`) on the 16 held-back in-silico tissues (Tan 2021 POOL-test cells, reps 0-7 x low / high;
no contact reused in any tissue; 8.2-8.5 M contacts / 600 spots (low), 10.7-11.5 M / 150 spots (high)).  Sherlock CPU
jobs 46943868 (tissues), 46943871 (fits, 16 tasks, 22-33 min each), 46943902 (aggregate).  Outputs:
`$SCRATCH/uchrom-nd/runs/spatial/typedecon/{tissues,scores/test,tables/test}`.  Nothing was changed after the results
were seen.

**Result: H1, H2 and H3 are met and the stratum check passes, so by the registered rule composition-weighted
deconvolution recovers type-specific contact profiles better than cluster pseudo-bulk (dominant-type pooling) and
NNLS on this in-silico test.**  The margins are small in absolute terms (P1 +0.014 over NNLS, +0.031 over dominant
pooling) and every method sits near the truth's own split-half ceiling (P1 0.223, P2 0.486 at 1 Mb): read the
numbers as "TD* gets 82-93 % of the way to the true-origin oracle, the baselines less", not as high absolute
agreement.

## Primary test (1 Mb, moderate composition noise, both regimes, 16 tissues; paired, 95 % bootstrap)

| hypothesis | P1 contrast_r | P2 comp_r | met |
|---|---|---|---|
| H1 TD* − dominant | +0.0309 [+0.0242, +0.0384] | +0.0583 [+0.0449, +0.0730] | yes |
| H2 TD* − NNLS | +0.0143 [+0.0123, +0.0166] | +0.0427 [+0.0382, +0.0475] | yes |
| H3 TD* − shuffled | +0.2330 [+0.2211, +0.2441] | +0.5086 [+0.4746, +0.5412] | yes |

## Stratum check (1 Mb; TD* − dominant per regime x noise, 8 tissues; fails if < −0.01 with CI excluding 0)

| regime | noise | P1 | P2 | worse? |
|---|---|---|---|---|
| low | exact | +0.0166 [+0.0144, +0.0190] | +0.0276 [+0.0248, +0.0304] | no |
| low | moderate | +0.0190 [+0.0171, +0.0212] | +0.0334 [+0.0306, +0.0362] | no |
| low | heavy | +0.0181 [+0.0161, +0.0200] | +0.0345 [+0.0298, +0.0389] | no |
| high | exact | +0.0408 [+0.0370, +0.0444] | +0.0810 [+0.0722, +0.0899] | no |
| high | moderate | +0.0428 [+0.0347, +0.0521] | +0.0833 [+0.0681, +0.0997] | no |
| high | heavy | +0.0334 [+0.0278, +0.0384] | +0.0740 [+0.0593, +0.0864] | no |

**Decision (§14.6)**: H1 met, H2 met, H3 met, stratum check passed → "composition-weighted deconvolution recovers type-specific contact profiles better than cluster pseudo-bulk and NNLS".

## All strata, 1 Mb — P1 / P2, mean of 8 tissues

| regime | noise | TD-ps0.2 | dominant | nnls | random | oracle |
|---|---|---|---|---|---|---|
| low | exact | 0.242 / 0.522 | 0.226 / 0.495 | 0.232 / 0.490 | -0.005 / 0.002 | 0.251 / 0.528 |
| low | moderate | 0.240 / 0.518 | 0.221 / 0.485 | 0.229 / 0.484 | -0.003 / 0.004 | 0.251 / 0.528 |
| low | heavy | 0.228 / 0.499 | 0.210 / 0.465 | 0.217 / 0.464 | -0.002 / -0.003 | 0.251 / 0.528 |
| high | exact | 0.225 / 0.494 | 0.184 / 0.413 | 0.206 / 0.445 | -0.005 / -0.010 | 0.252 / 0.524 |
| high | moderate | 0.216 / 0.480 | 0.174 / 0.397 | 0.198 / 0.429 | -0.007 / -0.022 | 0.252 / 0.524 |
| high | heavy | 0.185 / 0.422 | 0.152 / 0.348 | 0.170 / 0.372 | -0.000 / -0.000 | 0.252 / 0.524 |

## All strata, 250 kb — P1 / P2, mean of 8 tissues (insulation contrast r)

| regime | noise | TD-ps0.2 | dominant | nnls | random | oracle |
|---|---|---|---|---|---|---|
| low | exact | 0.180 / 0.497 (0.53) | 0.159 / 0.456 (0.50) | 0.174 / 0.463 (0.52) | 0.002 / 0.022 (0.01) | 0.200 / 0.517 (0.56) |
| low | moderate | 0.176 / 0.488 (0.52) | 0.153 / 0.444 (0.49) | 0.170 / 0.452 (0.51) | 0.002 / 0.016 (0.01) | 0.200 / 0.517 (0.56) |
| low | heavy | 0.161 / 0.461 (0.48) | 0.141 / 0.418 (0.46) | 0.156 / 0.424 (0.47) | 0.001 / 0.006 (0.00) | 0.200 / 0.517 (0.56) |
| high | exact | 0.165 / 0.471 (0.49) | 0.128 / 0.382 (0.42) | 0.158 / 0.429 (0.47) | -0.001 / 0.013 (-0.01) | 0.207 / 0.525 (0.57) |
| high | moderate | 0.155 / 0.452 (0.47) | 0.120 / 0.358 (0.40) | 0.149 / 0.407 (0.45) | -0.002 / -0.001 (-0.02) | 0.207 / 0.525 (0.57) |
| high | heavy | 0.128 / 0.386 (0.40) | 0.104 / 0.311 (0.34) | 0.124 / 0.346 (0.38) | 0.002 / 0.013 (-0.01) | 0.207 / 0.525 (0.57) |

## Paired differences, every noise level and resolution (both regimes, 16 tissues)

| res | noise | − dominant P1 | P2 | − NNLS P1 | P2 | − shuffled P1 | P2 | − oracle P1 | P2 |
|---|---|---|---|---|---|---|---|---|---|
| 1 Mb | exact | +0.029 [+0.023, +0.035] | +0.054 [+0.041, +0.068] | +0.014 [+0.012, +0.017] | +0.041 [+0.036, +0.046] | +0.238 [+0.228, +0.248] | +0.513 [+0.485, +0.539] | -0.018 [-0.023, -0.014] | -0.018 [-0.024, -0.011] |
| 1 Mb | moderate | +0.031 [+0.024, +0.038] | +0.058 [+0.045, +0.073] | +0.014 [+0.012, +0.017] | +0.043 [+0.038, +0.048] | +0.233 [+0.221, +0.244] | +0.509 [+0.475, +0.541] | -0.024 [-0.030, -0.018] | -0.027 [-0.036, -0.018] |
| 1 Mb | heavy | +0.026 [+0.021, +0.030] | +0.054 [+0.043, +0.067] | +0.013 [+0.012, +0.015] | +0.042 [+0.038, +0.048] | +0.208 [+0.191, +0.222] | +0.462 [+0.423, +0.494] | -0.045 [-0.057, -0.034] | -0.065 [-0.085, -0.047] |
| 250 kb | exact | +0.029 [+0.026, +0.033] | +0.065 [+0.052, +0.078] | +0.007 [+0.006, +0.007] | +0.038 [+0.035, +0.041] | +0.173 [+0.166, +0.179] | +0.466 [+0.444, +0.487] | -0.031 [-0.036, -0.025] | -0.037 [-0.046, -0.028] |
| 250 kb | moderate | +0.029 [+0.025, +0.033] | +0.069 [+0.054, +0.086] | +0.006 [+0.005, +0.006] | +0.040 [+0.037, +0.043] | +0.166 [+0.157, +0.173] | +0.463 [+0.436, +0.487] | -0.038 [-0.045, -0.031] | -0.051 [-0.063, -0.040] |
| 250 kb | heavy | +0.022 [+0.020, +0.024] | +0.058 [+0.049, +0.069] | +0.005 [+0.004, +0.006] | +0.038 [+0.035, +0.043] | +0.143 [+0.131, +0.153] | +0.414 [+0.380, +0.442] | -0.059 [-0.069, -0.049] | -0.097 [-0.120, -0.077] |

## Per type (1 Mb, moderate; P1 / P2, mean of 16 tissues)

| method | P | L6 | I | O | A | M |
|---|---|---|---|---|---|---|
| TD-ps0.2 | 0.23 / 0.57 | 0.15 / 0.42 | 0.12 / 0.41 | 0.35 / 0.64 | 0.15 / 0.31 | 0.37 / 0.65 |
| dominant | 0.21 / 0.51 | 0.14 / 0.38 | 0.10 / 0.34 | 0.31 / 0.61 | 0.12 / 0.25 | 0.30 / 0.55 |
| nnls | 0.21 / 0.52 | 0.14 / 0.39 | 0.11 / 0.34 | 0.33 / 0.61 | 0.14 / 0.28 | 0.34 / 0.60 |
| random | -0.01 / -0.02 | -0.00 / -0.01 | -0.01 / -0.02 | 0.01 / -0.01 | -0.00 / 0.01 | -0.01 / -0.00 |
| oracle | 0.24 / 0.57 | 0.17 / 0.45 | 0.14 / 0.43 | 0.35 / 0.65 | 0.18 / 0.34 | 0.43 / 0.71 |

Oracle fraction of P1 (1 Mb): exact 0.93, moderate 0.91, heavy 0.82; type identification accuracy (1 Mb, moderate) 0.990 (dominant 0.958).
Robustness, exact − heavy (1 Mb): P1 +0.027, P2 +0.048.

## S1 (secondary; 1 Mb, mean over tissues and noise levels)

| method | low | high |
|---|---|---|
| TD-groups(shrink=0.0) | 0.038 | 0.036 |
| TD-groups(shrink=0.1) | 0.038 | 0.036 |
| TD-groups(shrink=1.0) | 0.038 | 0.034 |
| dominant-groups | 0.036 | 0.031 |
| oracle(P vs L6 by origin) | 0.053 | 0.055 |

Composition given (realised): high heavy MAE 0.096 r 0.80; high moderate MAE 0.056 r 0.93; low heavy MAE 0.080 r 0.86; low moderate MAE 0.045 r 0.96

## Caveats

* **Noise ceiling**: the truth profiles (pseudo-bulk of 15-80 TRUTH cells per type) reproduce themselves only at
  P1 0.223 / P2 0.486 (half vs half); the absolute levels above are bounded by this, not by the method.
* **In-silico only**: the spots pool real Dip-C cells, but compositions are exact contact shares perturbed by a
  Dirichlet / RNA-content model (moderate: MAE 0.045-0.056, r 0.93-0.96; heavy: MAE 0.080-0.096, r 0.80-0.86).  Real
  RNA deconvolution errors (missing types, platform effects, cell-size differences in RNA) may behave differently;
  partial nuclei are modelled as uniform subsamples, not spatial sections of a nucleus.
* **Types** are the authors' structure clusters (defined from the cells' chromatin), so they differ in contacts by
  construction.
* Replicate tissues re-draw the same POOL-test cells; the CIs cover tissue construction, not cell sampling.
* **S1 (spatially varying profiles) remains uninformative**: the L2-5 vs L6 difference is at the noise level even
  for the oracle (r 0.05).
* Not run: per-type 3-D (§14.7, parameters not yet registered) and real data (§14.8, needs separate approval).
