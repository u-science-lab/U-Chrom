# Data model & storage

Everything in U-Chrom is a `ChromData` (package `chromdata`, also `uchrom.ChromData`): cells ›
traces › spots, every spot pointing at one locus of a shared locus axis (`bins`).  Coordinates
live in `coords`, per-spot signals in `spot_tracks`, per-locus signals in `bin_tracks`, cell
metadata and embeddings in `cells` / `cellm`, called structures in `intervals`, analysis outputs
with their provenance in `results`.  Contact maps, RNA and other matrices stay in their own files
and are *linked* per cell — or *embedded* into the store when it is shared.

A `ChromData` is saved as a `.chromdata.zarr` store (Zarr v3 + Parquet; `.cdz` is the same tree
in one zip file).  A store opens *backed*: only the small tables are read, and a cell, a trace or
a chromosome is read when it is needed — from a local disk or over HTTP from object storage.
`chromdata` needs only numpy, pandas, zarr and pyarrow; the analysis library and the web browser
build on it.

| Task | API |
|------|-----|
| build from a spot table / a reconstruction CSV | `ChromData(coords, spots, ...)`, `ChromData.from_dataframe` |
| subset | `cd.get_cell`, `cd.get_trace`, `cd.get_chrom`, `cd[rows]` |
| per-locus vs per-spot data | `cd.bins`, `cd.bin_tracks`, `cd.spot_tracks`, `cd.spots_with_loci()` |
| structures and results | `cd.intervals` (typed tables), `cd.results` (`ResultsStore`, provenance) |
| distances on demand | `cd.compute_distances(trace_id=...)` |
| cell positions and outlines | `cd.set_cell_positions`, `cd.cell_positions`, `cd.set_cell_shapes` |
| write / read | `cd.write("x.chromdata.zarr")`, `ChromData.read(path, backed=True, columns=...)` |
| stream large data | `ChromData.writer(path)`, `cd.iter_cells()`, `cd.iter_traces()` |
| linked modalities | `cd.link_cool`, `cd.link_scool`, `cd.link_anndata`, `cd.link_mudata`, `cd.link_spatialdata`, `cd.validate_links()` |
| embedded copies (atlas) | `python -m chromdata.embedded STORE`, `chromdata.embedded` |
| catalogs of stores | `chromdata.catalog` (`python -m chromdata.catalog build`) |

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/chromdata_basics
/tutorials/chromdata_stores
```

## Guides

```{toctree}
:maxdepth: 1

chromdata
linked_modalities
```

The store layout is specified in the [format specification](../reference/format_spec); the API is
under [chromdata](../reference/api/core).
