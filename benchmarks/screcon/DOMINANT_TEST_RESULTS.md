# A spot reconstructed as one cell — held-back test results (PREREG §13, §13.2)

Run once, 2026-10-06 to 2026-10-08, with the methods frozen as in §13 (EMber haploid = tag `robust-frozen`; EMber
deep diploid = tag `ember-deep-frozen`; NucDynamics 2017) and the spot QC rule frozen in §13.2 (tag
`ember-spotqc-frozen`, `data/spotqc_frozen.json`) before any held-back table was built.  Engine build
`dom-4181d07` (the development build), **CPU (f64) path** instead of the GPU path of the development runs (PREREG
§13 note, user-approved before any held-back result was seen).  Nothing was changed after the results were seen.

Numbers: `results/dominant_test/dominant_dev.json` / `.md` (`dominant.py aggregate`; the file name is the
aggregator's) and `results/dominant_test/test_statements.json` (`dominant.py test --frozen`).

## Units

| dataset | dominants (n_cis) | designs | levels | mixtures + controls |
| --- | --- | --- | --- | --- |
| Nagano 2017 serum, held-back half | NST_576, 554, 66, 343, 651, 25, 895, 206, 954, 777, 732, 836 (117-227 k) | 24 | 10 k, 30 k, 100 k, full | 480 + 48 pure + 240 D-only |
| Stevens 2017 cells 5-8 | cell5 (62 k), cell6 (67 k), cell7 (45 k), cell8 (36 k) | 24 | 10 k, 30 k, full | 360 + 12 + 60 |
| Tan 2021 cortex, §12.1 held-back pool cells (phased, EMber deep) | cb_191, cb_137, cb_188, cb_020, cb_130, bc_122, cb_247, cb_062 (183-439 k) | 16 | 10 k, 30 k, 100 k, full | 320 + 32 + 160 |

All 1,712 tables scored (no missing runs).  Mean CPU wall time per run: EMber 15-37 s, NucDynamics 231-847 s.

## E1 — dominant-cell recovery (per-copy r vs the dominant's own EMber structure; mean over designs)

| dataset | level | pure | f 0.9 | 0.8 | 0.7 | 0.6 | 0.5 | f_drop (all / m = 1 / m = 2) | at f = 0.5: mixing / depth effect |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Nagano | 10 k | 0.571 | 0.559 | 0.536 | 0.516 | 0.499 | 0.473 | 0.7 / 0.7 / 0.7 | −0.024 / −0.073 |
| Nagano | 30 k | 0.765 | 0.753 | 0.716 | 0.683 | 0.644 | 0.586 | 0.7 / 0.8 / 0.7 | −0.071 / −0.109 |
| Nagano | 100 k | 0.895 | 0.874 | 0.823 | 0.758 | 0.700 | 0.653 | 0.8 / 0.8 / 0.8 | −0.172 / −0.070 |
| Nagano | full | 0.953 | 0.893 | 0.826 | 0.770 | 0.716 | 0.662 | 0.9 / 0.9 / 0.9 | −0.224 / −0.067 |
| Stevens | 10 k | 0.696 | 0.647 | 0.591 | 0.530 | 0.500 | 0.460 | 0.8 / 0.9 / 0.8 | −0.030 / −0.205 |
| Stevens | 30 k | 0.943 | 0.890 | 0.809 | 0.713 | 0.620 | 0.548 | 0.9 / 0.9 / 0.8 | −0.260 / −0.135 |
| Stevens | full | 0.978 | 0.934 | 0.857 | 0.762 | 0.669 | 0.589 | 0.8 / 0.9 / 0.8 | −0.324 / −0.066 |
| Tan | 10 k | 0.483 | 0.453 | 0.420 | 0.390 | 0.357 | 0.347 | 0.8 / 0.8 / 0.8 | −0.011 / −0.124 |
| Tan | 30 k | 0.816 | 0.776 | 0.710 | 0.617 | 0.522 | 0.433 | 0.8 / 0.8 / 0.8 | −0.179 / −0.204 |
| Tan | 100 k | 0.955 | 0.923 | 0.849 | 0.747 | 0.633 | 0.512 | 0.8 / 0.8 / 0.8 | −0.392 / −0.051 |
| Tan | full | 0.986 | 0.937 | 0.847 | 0.741 | 0.628 | 0.524 | 0.8 / 0.9 / 0.8 | −0.436 / −0.026 |

(f_drop = largest f < 1 whose mean ΔE1 vs the pure control is < −0.05; 0.8 = within 0.05 only at f = 0.9; 0.9 =
not even there.  95 % CIs over dominants in `results/dominant_test/dominant_dev.md`.)

**Statement (registered form)**: EMber recovers the dominant's structure within 0.05 of the pure control down to f = 0.9 only (f_drop 0.8) in 7 of 11 dataset × level cells; down to f = 0.8 (f_drop 0.7) in 2 (Nagano 10 k / 30 k, where the pure cell itself is poor, 0.57 / 0.77); not even at f = 0.9 (f_drop 0.9) in 2 (Nagano full −0.060, Stevens 30 k −0.053).  At >= 100 k cis the loss at f = 0.5 is 0.24-0.46 and is mostly mixing (the D-only control loses 0.03-0.07).  Same picture as the development set (`dominant_devlog.md` §2).

## E2 — EMber − NucDynamics (per-copy r vs the dominant's EMber reference, all f < 1 mixtures)

| | E2 [95 % CI over dominants] |
| --- | --- |
| all datasets | **+0.0053 [+0.0027, +0.0077]** |
| Nagano | +0.0047 [+0.0006, +0.0080] |
| Stevens | +0.0055 [+0.0046, +0.0065] |
| Tan (EMber deep vs NucDynamics diploid) | +0.0059 [−0.0007, +0.0122] |

By level: Nagano +0.020 at 10 k, ≈ 0 at 30 k / 100 k / full; Stevens +0.010 at 10 k, +0.001 / +0.005; Tan −0.009
(10 k) and −0.006 (30 k), +0.013 (100 k), +0.026 (full).  **Statement**: "EMber is better than NucDynamics on
dominant-cell mixtures" — the registered criterion (pooled CI above 0) **is met**, but the gain is ~0.005 per-copy
r, an order of magnitude below the mixing loss, and EMber deep is worse than NucDynamics on sparse (10-30 k)
diploid mixtures, as on development.

## E3 — spot QC with the frozen rule (Q3 >= development threshold of dataset and level → flagged as mixed)

Single-cell-like = f ∈ {1.0, 0.9, 0.8}, mixed = f ∈ {0.6, 0.5}.

| dataset | Q3 AUC, mean over levels [95 % CI] | sensitivity at the frozen thresholds | specificity | **QC works?** (CI lower > 0.75 and spec >= 0.8) |
| --- | --- | --- | --- | --- |
| Nagano | 0.825 [0.764, 0.915] | 0.91 | **0.51** | **no** (specificity) |
| Stevens | 0.980 [0.973, 0.994] | **0.47** | 1.00 | yes |
| Tan | 0.979 [0.964, 0.998] | 0.90 | 0.96 | yes |

Per level (sensitivity / specificity): Nagano 0.88/0.50, 0.90/0.48, 0.92/0.63, 0.96/0.43; Stevens 0.06/1.00 (10 k),
0.44/1.00 (30 k), 0.90/1.00 (full); Tan 0.69/0.88, 0.94/1.00, 0.97/1.00, 1.00/0.95.

Reported alongside, Q7 (partner conflict) at its frozen development thresholds: AUC 0.900 [0.840, 0.966] / 0.970
[0.961, 0.998] / 0.907 [0.830, 0.997], sensitivity 0.89 / 0.52 / 0.95, specificity 0.75 / 1.00 / 0.78 (Nagano /
Stevens / Tan).  All metrics, mean held-back AUC over datasets: Q3 0.928, Q7 0.925, Q2 0.890, Q6 0.816, Q5 0.789,
Q4 0.756, Q1 (ε) 0.509; logistic combination (leave one dominant out) 0.935 / 0.995 / 0.947.

**Statements**: the ranking metrics transfer to new cells (AUC 0.83-0.98, every CI lower bound above 0.75), but the
frozen **thresholds** do not transfer within a dataset as well as hoped: on Nagano they flag half of the
single-cell-like spots (specificity 0.51, as development already suggested at 0.70), on Stevens they miss half of
the mixed ones (sensitivity 0.47; the held-back Stevens cells 5-8 have lower violation rates than cells 1-4).  By
the registered rule the spot QC works for Stevens and Tan and **not for Nagano**.  The threshold is cell-population
dependent even within one protocol; the Chen application (`dominant_devlog.md` §7) shows it does not carry across
protocols either.

## Deviations

* CPU (f64) instead of GPU (f32) runs (PREREG §13 note, before any held-back result).
* The stored file name `results/dominant_test/dominant_dev.json` is the aggregator's default name; the content is
  the held-back set.
