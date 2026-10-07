# Chromatin tracing

Multiplexed DNA FISH — ORCA, Hi-M, DNA-MERFISH, chromatin tracing in general — images one locus after
another and gives each locus a position in 3-D.  Its data arrive as a table of spots: one row per locus of
one chromatin fibre, with `x, y, z`.  That is a `ChromData` almost as it stands; this chapter follows the
data from the files to the structures they show.

| Step | Page | API |
|------|------|-----|
| read FOF-CT, PyHiM and other tracing tables; write FOF-CT | [Reading tracing data](reading) | `ChromData.from_fofct`, `ChromData.from_pyhim_trace`, `uchrom.io` readers, `uchrom.datasets.load` |
| link raw detections into traces, with ploidy | [From detections to traces](traces) | `uchrom.im.trace.align_spots` |
| fill the loci a trace missed | [Filling missing loci](imputation) | `uchrom.im.impute.impute_coordinates`, `uc.pp.impute` |
| loops, TADs, domains per allele, A/B compartments from 3-D distances | [Calling structures](structures) | `uchrom.strc`, `uc.tl.call_loops` / `call_tads` / `call_compartments` |

The coordinates are then measured like any others — distance maps, contact frequencies, variances
([per-locus features](../features/index)) — and shown in the [web browser](../viz/index).  Imaging and Hi-C
of the same cell type meet in [GEM-FISH](../bulk/gem_fish).

```{toctree}
:maxdepth: 2
:hidden:

reading
traces
imputation
structures
```
