# Structure calling

`uchrom.strc` calls chromatin structures from the 3-D data itself — from the distances between
loci in many traces, not from a contact map: loops (a per-axis F-test, ArcFISH), TADs (ArcFISH
p-values, the directionality index), domains per allele (FISHnet) and A/B compartments.  Every
caller follows one calling convention: `fn(cd, *, chrom=None, params=..., device="auto",
key_added=..., copy=False)`; `chrom=None` runs every chromosome, results go to `cd.intervals` /
`cd.results` with their provenance, and on a backed store the callers stream.

| Structure | API |
|-----------|-----|
| loops | `uchrom.strc.loop.call_loops_axiswise_f`, `uc.tl.call_loops` |
| TADs | `uchrom.strc.tad.call_tads_by_pval`, `call_tads_di`, `uc.tl.call_tads` |
| domains per trace / allele | `uchrom.strc.tad.call_domains_fishnet` |
| A/B compartments | `uchrom.strc.comp.call_compartments_axes_pc`, `uc.tl.call_compartments` |
| all of them, projected onto bins / spots | `uchrom.strc.call_structures_multi`, `add_structural_features` |

The callers run on PyTorch (`device="auto"`: CUDA, Apple MPS or CPU).

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/loop_calling
/tutorials/tad_calling
/tutorials/fishnet_domains
/tutorials/compartment
```

## Guide

```{toctree}
:maxdepth: 1

methods
```

API: [loops](../reference/api/strc_loop), [TADs](../reference/api/strc_tad),
[compartments](../reference/api/strc_comp), [enrichment](../reference/api/strc_enrichment).
