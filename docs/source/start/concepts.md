# Concepts

## One table of positions

Every 3-D genome measurement ends in the same table: a genomic locus and where it is.

| chrom | start | end | x | y | z |
|-------|-------|-----|---|---|---|
| chr3 | 34,600,000 | 34,625,000 | 1.82 | 0.44 | −0.91 |
| chr3 | 34,625,000 | 34,650,000 | 1.79 | 0.47 | −0.88 |

Chromatin tracing and DNA seqFISH+ measure the positions directly; Hi-C measures contacts, from
which [3-D reconstruction](../recon/index) computes them.  Everything downstream — distances,
structures, features, embeddings, the browser — works on this table, whatever produced it.

## Cells, traces, spots — and bins

- A **spot** is one locus observed in 3-D: a row of the table.
- A **trace** is an ordered chain of spots along one chromatin fibre — one copy of a chromosome
  region (two per diploid cell, or one per haplotype after phasing).
- A **cell** holds traces (and, for sequencing data, contact maps and other modalities).
- A **bin** is a locus of the *locus axis* shared by all cells: `chrom`, `start`, `end`.  Every
  spot points at one bin (`spots.bin_id`), so signals that belong to a locus (bulk ATAC, GC
  content, a compartment score) are stored once per bin, not once per spot.

## `ChromData`

`ChromData` (package `chromdata`) holds all of it, the way AnnData holds a single-cell matrix:

```
ChromData
├── bins         loci (n_bins): chrom, start, end, [name, resolution]
├── bin_tracks   per-locus signals (n_bins)
├── binm         per-locus multi-dimensional arrays
├── intervals    typed tables of structures: TADs, loops, peaks, segments
├── coords       (n_spots, 3) x, y, z
├── spots        per spot: bin_id, trace_id, [cell_id]   (chrom / start / end derived from bins)
├── spot_tracks  per-spot signals (IF intensity, RNA z-scores, ...)
├── layers       alternative coordinates (n_spots, 3): imputed, models of an ensemble, ...
├── cells        per cell: type, position, counts, ...
├── cellm        per-cell multi-dimensional arrays: embeddings, UMAP, ...
├── traces       per trace
├── cell_shapes  cell outlines (GeoParquet)
├── points       non-genomic 3-D points: RNA spots, IF puncta
├── results      analysis outputs, each with its provenance (function, parameters, version, time)
└── uns          metadata: genome assembly, units, linked files, ...
```

All spots of all cells are stored flat; `cd.get_cell(id)`, `cd.get_trace(id)` and
`cd.get_chrom(name)` return the part you need as a new `ChromData`.  Pairwise distance matrices are
never stored — `cd.compute_distances(trace_id=...)` computes one when needed.

## Linked and embedded modalities

Single-cell Hi-C contact maps (`.scool`), pseudo-bulk maps (`.cool` / `.mcool`), RNA or ATAC
matrices (`.h5ad`, `.h5mu`), SpatialData stores and section images stay in their own files: a
`ChromData` records *links* to them with the mapping between their cells and its cells
(`cd.link_scool`, `cd.link_cool`, `cd.link_anndata`, `cd.link_mudata`, `cd.link_spatialdata`).
To share a dataset as one self-contained store, the linked files are *embedded* into it
(`python -m chromdata.embedded STORE`): contact maps partitioned by chromosome and sharded for
range reads, AnnData as Zarr.

## The store: `.chromdata.zarr`

`cd.write("x.chromdata.zarr")` writes a Zarr v3 group with Parquet tables (`.cdz` is the same tree in
one zip file).  Coordinates are partitioned by chromosome and sorted by cell; other per-spot columns
sit in cell-sorted tables; an index maps cells, traces and chromosomes to row ranges.  So a store
opens *backed* — `ChromData.read(path, backed=True)` reads the small tables and the index, and a
cell, a trace or a chromosome is read when asked for — on a laptop, on a cluster, or over HTTP from
object storage (that is how the [data atlas](../viz/atlas) works).  Large data are written by
streaming (`ChromData.writer`) and analysed chunk by chunk (`cd.iter_cells()`), within a memory budget
(`uchrom.settings.memory_budget`).  The layout is specified in the
[format specification](../reference/format_spec).

## Analyses

Analysis functions follow one calling convention:

```python
result = fn(cd, *, chrom=None, params=..., device="auto", key_added="<what>.<method>", copy=False)
```

`chrom=None` runs every chromosome; the result is returned and stored in `cd.results[key_added]`
(structures also in `cd.intervals`, per-locus values in `cd.bin_tracks`) together with the function,
its parameters and the U-Chrom version, so a store remembers how its results were made.
`uchrom.tl` and `uchrom.pp` give short names: `uc.tl.call_tads(cd)`, `uc.tl.call_loops(cd)`,
`uc.tl.call_compartments(cd)`, `uc.tl.reconstruct_sc(contacts)`, `uc.pp.impute(cd)`.

## Where things live

| You want to | Look in |
|-------------|---------|
| hold, subset, save or share data | [`chromdata`](../data/index) |
| read a file format | [`uchrom.io`](../io/index) |
| turn spots into traces, fill gaps | [`uchrom.im`](../imaging/index) |
| compute structures from Hi-C | [`uchrom.recon`](../recon/index) |
| call loops, TADs, compartments | [`uchrom.strc`](../structures/index) |
| compute per-locus features | [`uchrom.fea`](../features/index) |
| compare cells | [`uchrom.emb`](../cells/index) |
| look at it | [`uchrom-browser`, `uchrom.pl`](../viz/index) |
| let agents explore it | [`uchrom-discovery`](../discovery/index) |
