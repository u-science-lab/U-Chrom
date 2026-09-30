---
name: load-data
description: START HERE for any U-Chrom data question (.chromdata.zarr, .cdz), even simple counts — how many cells / traces / spots / IF channels / genes, contact-map resolution (.scool/.mcool), units, distance between consecutive loci / particles, traces per chromosome per cell (ploidy), spots per trace by cell type. QC script; routes to the analysis skills.
---

# Load and inspect a U-Chrom dataset

## When to use
First step on any ChromData store — `.chromdata.zarr`, `.cdz` (the same store zipped; a legacy `.h5cd` must first be converted with `python -m uchrom.io.upgrade old.h5cd`) (ChromData: chromatin tracing, DNA seqFISH+, ORCA/Hi-M, simulated structures,
scHi-C/scHiCAR with linked `.scool/.mcool/.cool`, RNA/ATAC, embeddings), and for questions about the data
itself: counts, channels, genes, cell types, contact-map resolution and coverage, units, consecutive-locus
distance, traces per chromosome per cell (ploidy), spots per trace by group, duplicate / missing loci.

## Route: load the skill for your question too (Skill tool), right after step 1
| the question… | also load |
|---|---|
| compares groups of cells ("do X cells have more/larger Rg / nuclei / … than Y", "what is different about these cells", "still there at equal spots per trace?") | `compare-groups` |
| asks for distances vs separation, Rg per chromosome, P(s) slope, TADs, compartments, loops (P(s) per cell type: this one) | `call-structures` |
| asks whether two things correlate / are associated (IF, RNA, ATAC, nuclear size vs structure or radial position; ATAC vs RNA; cell-type separation / kNN purity in embeddings) | `associate-modalities` |
| only asks what is in the data / QC | this skill is enough |

Load the routed skill with the Skill tool *before* writing your own analysis code — its script and checks
are what the answer is judged on.

## Steps
1. **One call summary.** Run the script (it prints JSON; ~1–2 s even on 400k spots):
   ```bash
   python <skill dir>/scripts/inspect_data.py data.chromdata.zarr [--group cell_type]
   ```
   or `from inspect_data import summarize; s = summarize(ChromData.read(path))`.
   It reports `counts`, `uns` (assembly, `xyz_unit`, `coordinate_status`), `cells` columns grouped by
   prefix, categorical columns with counts, `spot_tracks` / `bin_tracks`, `traces` columns, `cellm` embeddings with their
   recipe, `linked` contact maps (existence, resolutions, number of cells in a `.scool`), `qc`, `checks`.
2. **Answer "how many" from the right table** (don't guess from one place):
   | question | where |
   |---|---|
   | cells | `len(cd.cells)`; cells with 3-D data: `cd.spots.cell_id.nunique()` (can differ) |
   | traces / spots | `cd.n_traces`, `cd.n_spots` (a trace = one allele's copy of one chromosome/region) |
   | IF antibody channels, genes | count the `cells` columns with the prefix (`if.`, `rna.`, `atac.`); `spot_tracks` may also hold non-antibody signals (repeat FISH, RNA, spot intensity, radial scores) — list and exclude them |
   | embeddings | `cd.cellm[key]` (n_cells × d) + `cd.uns["embeddings"][key]` (modality, method, input) |
   | contact maps | `cd.uns["linked_scool"]` (per cell), `cd.uns["linked_cool"]` (pseudo-bulk / merged); open with `cooler` (`cooler.fileops.list_scool_cells`, `list_coolers` for `.mcool` levels) — the resolution is the cooler's `binsize` |
   | units | `cd.uns["xyz_unit"]` — "model units" (NucDynamics etc.) are *not* µm; never convert |
3. **Read `checks` and handle every item before analysis** (table below). Say in the answer which
   choice you made.
4. For analysis, continue with *call-structures* (distances, Rg, P(s), TADs, compartments),
   *compare-groups* (group differences) or *associate-modalities* (correlations).

## QC → what to do
| QC item (`qc` key) | why it matters | do |
|---|---|---|
| traces per (cell, chrom) `traces_per_cell_chrom` | diploid ⇒ ≤ 2 (≤ 4 after replication); more = over-split alleles, doublets, mis-assigned spots | report the distribution and the fraction > 2, **state the denominator** ((cell, chrom) pairs with ≥ 1 trace vs all cells × chroms); before comparing cells summarise per cell (median over its traces) or restrict to cells with ≤ 2 traces per chromosome; mention `uns['allele_col']` if alleles were assigned by clustering |
| duplicate loci `duplicate_loci` | two spots of one locus in one trace (sister chromatids, mis-assignment) | average per (trace, locus) before distance matrices and callers; statistics like Rg can keep them but say so |
| spots per trace `spots_per_trace.by_<group>` | Rg, span and P(s)-like statistics grow with the number and genomic spread of detected loci | compare groups per cell (median over a cell's traces, then median over cells); if groups differ > 1.3×, also compare at equal loci (*compare-groups* `equalize`) |
| detection `loci_per_chrom.median_detected_frac_per_trace` | sparse traces (few % of loci) make locus-level maps empty | bin to a coarser resolution before maps / TADs (*call-structures* `coverage`) |
| consecutive loci `consecutive_loci` | median 3-D step between consecutive detected loci, with its genomic gap and unit | quote with the unit and the gap; for simulated structures (one particle per bin) this is the bond length in model units |
| one `batch` / field of view | no biological replicate | say so in every comparison |
| `n_spots == 0`, `coordinate_status` | contacts-only data (scHi-C) | structure comes from the linked contact maps, not `coords` |

## Report
> *Dataset*: … cells (… with traces), … traces, … spots on … chromosomes; assembly …, coordinates in ….
> *Other data*: … IF channels (`if.*`), … genes (`rna.*`), embeddings …, contact maps … at … bp (… cells).
> *QC*: traces per chromosome per cell … (… % > 2 of … (cell, chrom) pairs); … duplicate loci; spots per
> trace median … (per cell; by group …); … → handled by ….
