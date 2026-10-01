# `robust` development log (milestone M2, development set only)

Method: `PREREG.md` §7; engine `native/nucdyn/src/robust.rs` (protocol `"robust"`); runner
`run_robust.py`; jobs `sherlock/robust_*.sbatch` (`_env_robust.sh` enforces the development set:
simulation truth cells 1-2, held-out cells 1-4); comparison `robust_compare.py` (paired vs the
existing `nucdyn_gpu` runs, which are not re-run); noise diagnostics `robust_diag.py`.

**No test-set unit (truth cells 3-5, held-out / real cells 5-8) has been run or read.**

Conventions: P2-dev = mean over the 72 development simulations (2 datasets x 2 truth cells x 18
conditions) of robust - nucdyn_gpu in median-over-models cis Spearman r; CI = 95 % bootstrap over
units ("cluster" = dataset x truth cell, only 4 clusters).  P1-dev = mean over 12 (cell, fold) of
the mean of the five cis-band ROC-AUCs (median-distance score), CI by resampling cells.  Baseline
dev means (from the existing runs): Spearman cis nucdyn_gpu 0.758 (su 0.709, takei 0.807);
held-out bands mean (median score) 0.846, frac score 0.687.

## Entries

