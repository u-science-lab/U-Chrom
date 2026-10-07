# Filling missing loci

Chromatin tracing misses loci: a probe that did not hybridise, a spot that was not detected, a locus
dropped by the aligner.  A trace then has gaps — rows with no coordinates — and every distance that
involves them is missing.  `uchrom.im.impute` fills them, either from the trace itself or from the other
traces of the population.

| Method | `impute_coordinates(cd, method=...)` | What it uses |
|--------|--------------------------------------|--------------|
| linear interpolation | `"linear"` | the neighbouring loci of the same trace |
| cubic spline | `"cubic"` | the same trace, a smooth curve through its loci |
| SnapFISH-IMPUTE (Yu et al.) | `"snapfish"` | traces of the population whose conformation is similar |

```python
from uchrom.im.impute import impute_coordinates

filled = impute_coordinates(cd, method="snapfish")       # also: uc.pp.impute(cd, method="snapfish")
```

The result is a new `ChromData` with the same spots and a spot column `imputed` marking the filled ones; a
locus a method cannot fill stays missing (SnapFISH-IMPUTE, for instance, leaves a locus that no similar trace
observed).  Imputed coordinates are estimates: `evaluate_imputation` hides observed loci, fills them with each
method and measures the error, as the tutorial does on Bintu et al. 2018 traces:

```python
from uchrom.im.impute import evaluate_imputation

holdout = evaluate_imputation(cd, methods=("linear", "cubic", "snapfish"), frac=0.1, seed=0)
holdout.summary                                          # median error per method
```

## Tutorial

```{toctree}
:maxdepth: 1

/tutorials/fish_imputation
```

API: [uchrom.im](../reference/api/im).
