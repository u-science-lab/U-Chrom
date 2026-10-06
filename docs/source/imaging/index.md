# Imaging: tracing & imputation

Chromatin tracing produces 3-D spots per locus; `uchrom.im` turns raw detections into traces and
fills the loci a trace missed.

| Task | API |
|------|-----|
| assign detected spots to chromatin fibres (traces), with ploidy | `uchrom.im.trace.align_spots` (the *jie* aligner) |
| fill missing coordinates: linear, cubic spline, SnapFISH-IMPUTE | `uchrom.im.impute.impute_coordinates(cd, method=...)`, `uc.pp.impute` |

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/jie_aligner
/tutorials/fish_imputation
```

## Guide

```{toctree}
:maxdepth: 1

tracing
```

API: [uchrom.im](../reference/api/im).
