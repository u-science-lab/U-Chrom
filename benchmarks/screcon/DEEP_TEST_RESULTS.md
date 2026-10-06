# EMber deep — test results (PREREG §11, 2026-10-04)

Run once with the frozen configuration (tag `ember-deep-frozen`: frozen diploid EMber + `robust_dip_commit`
0.75, `robust_dip_commit_drop` true, `robust_dip_readmit_stage` 4), engine built from the tag
(`highres_setup.sbatch`, ENGINE=deep-frozen), `sherlock/deep_dev.sbatch` with
`data/deep_test_variants.txt`; evaluated with `deep_diploid.py test` → `data/deep_test.json`.
Nothing was changed after the results were seen.

**Test units**: scMicro-C GM12878 (Wu et al. 2025, GSE192759) cells 047, 028, 017, 049, 032, 027, 014;
100 kb and 20 kb, 10 models, seeds 1 and 2; GPUs: RTX 2080 Ti / TITAN Xp / P100 (Sherlock `gpu` /
`owners`; reproducibility does not depend on the device type, wall times are not comparable to H100).

## Endpoints

| | value | criterion | result |
| --- | --- | --- | --- |
| **C1** run-to-run per-copy r at 20 kb, median over 7 cells | **0.983** (min 0.969) | median ≥ 0.90, each ≥ 0.85 | **met** |
| **C2** strict held-out cis ROC-AUC, EMber deep − NucDynamics-diploid, mean over 7 cells | **+0.0117** | ≥ −0.01 | **met** |

**C1 met, C2 met.**

## Per cell

| cell | r 100 kb (whole) | r 20 kb (whole) | r 20 kb < 2 / 2-20 / > 20 Mb | vs authors' hickit, 20 kb | held-out cis AUC deep / NucDyn (Δ) | strict positives | contacts used (phase coverage) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 047 | 0.983 (0.990) | 0.994 (0.998) | 0.97 / 0.99 / 0.99 | 0.85 | 0.854 / 0.850 (+0.004) | 37 | 45 % |
| 028 | 0.936 (0.972) | 0.983 (0.995) | 0.94 / 0.97 / 0.98 | 0.82 | 0.670 / 0.612 (+0.058) | 50 | 36 % |
| 017 | 0.986 (0.989) | 0.991 (0.996) | 0.95 / 0.98 / 0.99 | 0.86 | 0.819 / 0.804 (+0.015) | 39 | 37 % |
| 049 | 0.951 (0.968) | 0.981 (0.970) | 0.90 / 0.95 / 0.96 | 0.91 | 0.711 / 0.691 (+0.020) | 35 | 38 % |
| 032 | 0.945 (0.969) | 0.984 (0.994) | 0.95 / 0.97 / 0.99 | 0.84 | 0.742 / 0.763 (−0.021) | 43 | 39 % |
| 027 | 0.936 (0.826) | 0.969 (0.809) | 0.88 / 0.92 / 0.94 | 0.85 | 0.749 / 0.750 (−0.001) | 30 | 37 % |
| 014 | 0.978 (0.985) | 0.991 (0.996) | 0.95 / 0.98 / 0.98 | – | 0.856 / 0.850 (+0.006) | 28 | 38 % |

Secondary (not thresholded): held-out trans AUC deep / NucDynamics per cell in `data/deep_test.json`
(EMber deep higher in all 7 cells); cis < 2 Mb same-homolog held-out AUC is *lower* for EMber deep than for
NucDynamics in 6 of 7 cells (mean −0.016): the contacts it leaves out (not phased) are mostly close cis
ones.  "vs authors' hickit" at 100 kb is missing for 032, 027, 014 and at 20 kb for 014 (their
reference structures were built in parallel and were not ready when those runs were scored;
descriptive only).

## Accepted costs (registered before the test)

* **Phase coverage**: EMber deep uses only the contacts committed to a copy pair (by the prior, or by
  the structure after re-admission at 200 kb): 36-45 % of the input contacts on the test cells.
  On the Dip-C development cells the masked phase ends that receive a phase fall from 0.94 to 0.73,
  the correct fraction over all masked ends from 0.83 to 0.71 (`diploid_devlog.md` §6).
* **Held-out per cell**: C2 holds on the mean; 2 of 7 test cells are below NucDynamics-diploid
  (032 −0.021, 027 −0.001).  Only 28-50 strict positives (both ends phased) per cell, so per-cell
  AUCs are noisy.
