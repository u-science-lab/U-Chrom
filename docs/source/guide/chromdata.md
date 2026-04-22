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
| `results` | dict | analysis outputs (loops, TADs, …) |
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

All children (coords, spots, tracks, layers, cellm) are filtered
consistently; traces and cells that become empty are dropped.

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
| 4DN FOF-CT core table | `ChromData.from_fofct` |
| `.h5cd` (HDF5) | `ChromData.read` |

```python
cd.write("data.h5cd")
cd2 = ChromData.read("data.h5cd")
```

The `.h5cd` format has a version stamp and gracefully handles legacy
files.  See [Concepts — On-disk format](../concepts.md) for details.

## Why not AnnData?

AnnData observations are flat (one row = one cell).  Chromatin tracing
has an extra hierarchy (Cell → Trace → Spot), and the natural "sample
axis" differs per operation — a distance matrix is per-trace, cell-type
embeddings are per-cell, TAD calls are per-locus.  `ChromData` exposes
that hierarchy directly while reusing the AnnData-like `obsm`/`uns`
conventions where they apply (`cellm`, `uns`).
