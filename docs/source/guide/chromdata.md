# ChromData

`uchrom.ChromData` is the central container.  It is conceptually similar
to [AnnData](https://anndata.readthedocs.io/) but organises the data
around the chromatin-tracing hierarchy *Cell → Trace → Spot*.

## Construction

```python
import numpy as np
import pandas as pd
from uchrom import ChromData

coords = np.asarray([[1.0, 2.0, 3.0], [1.5, 2.3, 2.9]])
spots = pd.DataFrame({
    "chrom":    ["chr1", "chr1"],
    "start":    [0, 100_000],
    "end":      [100_000, 200_000],
    "trace_id": [0, 0],
})
cd = ChromData(coords, spots, uns={"genome_assembly": "GRCh38"})
```

### Required spot columns

| Column | Type | Required | FOF-CT field |
|--------|------|----------|--------------|
| `chrom` | str (category) | yes | `Chrom` |
| `start` | int | yes | `Chrom_Start` |
| `end` | int | yes | `Chrom_End` |
| `trace_id` | int/str (category) | yes | `Trace_ID` |
| `cell_id` | int/str (category) | no | `Cell_ID` |
| `spot_id` | int/str | no | `Spot_ID` |

String columns are auto-converted to `pd.Categorical` for ~10× memory
savings on large datasets.

## Attributes

| Attribute | Shape | Purpose |
|-----------|-------|---------|
| `coords` | `(n_spots, 3)` | x, y, z for each spot |
| `spots` | `(n_spots, ≥4)` | per-spot metadata |
| `cells` | `(n_cells, ?)` | per-cell metadata |
| `cellm` | dict | multi-dim cell annotations (embeddings, UMAP) |
| `tracks` | `(n_spots, n_tracks)` | epigenomic signals aligned to spots |
| `traces` | `(n_traces, ?)` | per-trace metadata |
| `layers` | dict | alternative coordinate sets |
| `points` | dict of DataFrames | non-genomic 3-D points in the same frame (nascent RNA spots, IF puncta): `x, y, z`, `cell_id`, `gene`, … |
| `results` | `ResultsStore` | analysis outputs with provenance (loops, TADs, …) — see [Results](#results) |
| `uns` | dict | unstructured metadata |

Properties: `cd.n_spots`, `cd.n_traces`, `cd.n_cells`, `cd.chroms`.

## Subsetting

Subset operations return **new** `ChromData` instances — they never
mutate the original.

```python
cd.get_chrom("chr1")           # all spots on chr1
cd.get_trace(5)                # only trace 5
cd.get_cell("cell_0")          # only cell "cell_0"
cd[cd.spots["chrom"] == "chr1"]  # boolean mask
cd[:100]                       # first 100 spots
```

All children (coords, spots, tracks, layers, cellm, and `points` via
their `cell_id`) are filtered consistently; traces and cells that become empty are dropped.

## Results

`cd.results` is a `ResultsStore` — a dict-like mapping from a key to a
`ResultRecord` (value + provenance).  Indexing returns the value, so it
reads like a dict; analysis functions store their output with
provenance:

```python
from uchrom.strc.tad import call_tads_by_pval

tads = call_tads_by_pval(cd)              # chrom=None → all chromosomes, one table
cd.results["tads.arcfish"] is tads        # True
rec = cd.results.record("tads.arcfish")
rec.kind, rec.function, rec.params, rec.inputs, rec.uchrom_version, rec.created_utc

cd.results["my_table"] = df               # plain assignment: no provenance
cd.results.set("my_table", df, function="my.fn", params={"k": 3})
```

| kind | value |
|------|-------|
| `table` | `DataFrame` / `Series` |
| `intervals` | `DataFrame` of genomic intervals (TADs, loops, domains) |
| `array` | `ndarray` (not object dtype) |
| `mapping` | nested `dict` of the value types here |
| `scalar` | JSON-compatible scalar / list / tuple |

A value that cannot be written to `.h5cd` raises `TypeError` **when it
is assigned**.  Values and provenance round-trip through `.h5cd`
(format 1.4).  Files from older versions read unchanged, with records
that carry no provenance.

Analysis functions share one calling convention (`cd` first; then
keyword-only `chrom=None`, `trace_ids`, `cells`, `params`, `device`,
`key_added="<what>.<method>"`, `copy=False`) — see
[Structure identification](structure.md#calling-convention).  The
`uc.tl` / `uc.pp` namespaces are flat aliases:

```python
import uchrom as uc
uc.tl.call_tads(cd, method="arcfish")     # strc.tad.call_tads_by_pval
uc.tl.call_loops(cd)                      # strc.loop.call_loops_axiswise_f
uc.tl.call_compartments(cd)               # strc.comp.call_compartments_axes_pc
uc.pp.impute(cd, method="linear")         # im.impute.impute_coordinates
```

## On-demand distance matrix

Global `(n_spots, n_spots)` matrices are not stored — they are
meaningless across cells and scale poorly.  Compute per-trace on demand:

```python
D = cd.compute_distances(trace_id=0)  # (n_spots_in_trace, n_spots_in_trace)
```

## I/O

| Input | Method |
|-------|--------|
| Reconstruction CSV (chrom, start, end, x, y, z) | `ChromData.from_dataframe` |
| 4DN FOF-CT core table (+ cell / RNA tables) | `ChromData.from_fofct` |
| `.h5cd` (HDF5) | `ChromData.read` |

```python
cd.write("data.h5cd")
cd2 = ChromData.read("data.h5cd")
```

### Multi-omics FOF-CT: cell table and RNA spots

4DN FOF-CT data sets can ship companion tables next to the core DNA
table.  Pass them to `from_fofct` to keep everything in one `.h5cd`:

```python
cd = ChromData.from_fofct(
    "4DNFIHF3JCBY.csv",                 # DNA spots / traces (core)
    cell_table="4DNFIFINA2U9.csv",      # per-cell: area, centroid, RNA counts
    rna_table="4DNFIJ52NVDV.csv",       # nascent RNA spots
)
cd.cells[["nucleus_area_um2", "rna.Nanog"]]   # genes are prefixed "rna."
cd.points["rna"].head()                        # x, y, z, gene, cell_id, …
cd.get_cell("0_2").points["rna"]               # RNA spots of one cell
cd.write("takei2021_multiomics.h5cd")          # format 1.3
```

Cell embeddings from the RNA counts (stored in `cd.cellm`, parameters in
`cd.uns["embeddings"]`):

```python
from uchrom.emb import embed_cells

embed_cells(cd)          # rna_pca (10 PCs), rna_tsne, rna_umap (needs umap-learn)
cd.cellm["rna_umap"]     # (n_cells, 2), rows follow cd.cells
```

Counts are `log1p`-transformed and z-scored per gene.  Library-size
normalisation is **off** by default (`library_size=True` to enable): in
small targeted panels one housekeeping gene can dominate the total (Eef2
is ~16 % of all counts in Takei 2021), and dividing by it makes PC1 "Eef2
vs everything else".  Without it, PC1 on Takei 2021 is overall expression
level and PC2 separates naive (Nanog, Esrrb, Tfcp2l1, Tbx3) from primed /
formative (Otx2, Lin28a/b, Dnmt3a) pluripotency markers.

### Embeddings from other modalities

`embed_cells(cd, source=…)` embeds any `cd.cells` prefix group, or an
explicit cells × features matrix (`matrix=`, dense or `scipy.sparse`), with
a normalisation suited to the data (`normalization="auto"` picks it from
`source`; recorded in `uns["embeddings"][key]["normalization"]`):

| `source` | normalisation | linear step | keys |
|---|---|---|---|
| `rna` (and unknown) | `counts`: `log1p` + z-score (optionally library size) | PCA | `rna_pca`, `rna_tsne`, `rna_umap` |
| `if`, `protein` | `zscore` (`log=True` adds `log1p`) | PCA | `if_pca`, … |
| `atac` | `tfidf`: TF-IDF + truncated SVD (LSI); component 1 dropped if \|r\| with log depth > 0.5 | LSI | `atac_lsi`, `atac_tsne`, `atac_umap` |
| `hic` | `none` (features used as given) | PCA | `hic_pca`, … |

Each entry also records `modality` ("RNA", "Histone/IF", "ATAC", "Hi-C"),
which the web browser uses to group the Embedding picker.

Imaging data carry per-spot signals in `cd.tracks`.
`aggregate_tracks` turns them into per-cell features:

```python
from uchrom.emb import aggregate_tracks, embed_cells
from uchrom.io.seqfish_multiomics import IF_COLUMNS   # 48 antibody channels

aggregate_tracks(cd, IF_COLUMNS, prefix="if")                  # cells["if.H3K27ac"], … (mean)
aggregate_tracks(cd, IF_COLUMNS, by="chrom", write=False)      # if.H3K27ac@chr1, …
aggregate_tracks(cd, IF_COLUMNS, by=10_000_000, write=False)   # if.H3K27ac@chr1:3 (10 Mb bins)
corr = aggregate_tracks(cd, IF_COLUMNS, stat="corr", write=False)  # if.H3K27ac~H3K9me3, …
embed_cells(cd, source="if", matrix=corr.to_numpy(), normalization="zscore")
```

On Takei 2025 cerebellum (47 cells, `example-data/takei2025_fov0/`) the
per-spot IF z-scores are already close to per-cell normalised (the spread
of per-cell means is ~0.1 of the within-cell SD), so per-cell means carry
little cell-type signal.  The within-cell mark–mark correlations (how marks
co-occur on the same loci) separated the cell types best — kNN-5 purity
0.61 vs 0.44 for means, 0.39 for mark × chromosome, ~0.5 for mark × 10 Mb;
chance ≈ 0.28 — and are what `build_takei2025_fov0.py` uses for
`if_pca / if_tsne / if_umap` (the per-cell means stay as `if.*` for
colouring).  With 47 cells these numbers are indicative only.

Single-cell contact maps (`.scool`) give a Hi-C embedding with the
scHiCluster recipe (convolution → random walk with restart → top-20 %
binarisation → per-chromosome PCA):

```python
from uchrom.emb import scool_cell_features

feats, cols, n_contacts = scool_cell_features("cells_1Mb.scool", cd.cells.index)
embed_cells(cd, source="hic", matrix=feats, normalization="none", n_pcs=20)
```

`example-data/build_schicar_mop.py` builds the scHiCAR dataset this way:
RNA (`rna_*`), ATAC (100 kb bins → LSI, `atac_*`; gene activity of the RNA
HVGs as `atac.<gene>`), Hi-C (`hic_*`) and the paper's UMAP.

The web browser (`python -m uchrom.browser --web`) can colour cells by any
of these cell fields, draw the RNA spots with the chromatin traces, and
show the embeddings as a 2-D view linked to the 3-D one.

The `.h5cd` format has a version stamp and gracefully handles legacy
files.  See [Concepts — On-disk format](../concepts.md) for details.

## Why not AnnData?

AnnData observations are flat (one row = one cell).  Chromatin tracing
has an extra hierarchy (Cell → Trace → Spot), and the natural "sample
axis" differs per operation — a distance matrix is per-trace, cell-type
embeddings are per-cell, TAD calls are per-locus.  `ChromData` exposes
that hierarchy directly while reusing the AnnData-like `obsm`/`uns`
conventions where they apply (`cellm`, `uns`).
