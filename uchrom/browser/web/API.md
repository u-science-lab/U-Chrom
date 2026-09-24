# U-Chrom web browser — HTTP API

Contract between the Python server (`uchrom.browser.web.server`) and the
React/Three.js frontend (`uchrom/browser/web/frontend`).  All endpoints are
under `/api`; the built frontend is served from `/`.

The server is a *local* tool (`python -m uchrom.browser --web data.h5cd`):
paths are local filesystem paths on the machine running the server.

## Datasets

### `GET /api/health`

`{"status": "ok", "version": "<uchrom version>", "bundle": "index-<hash>.js" | null}`

`bundle` is the frontend build the server saw in `static/` when it started.
The page compares it with its own script and warns when they differ: the
page was rebuilt after the server started, so the server may lack routes
the page uses — restart the server.

### `GET /api/datasets`

List loaded datasets.

```json
[
  {
    "id": "d1",
    "name": "cell1",
    "path": "/abs/path/cell1.h5cd",
    "n_spots": 105700,
    "n_traces": 20,
    "n_cells": 1,
    "xyz_unit": "um",              // from uns, may be null
    "trace_mode": false,            // n_traces > n_chroms → imaging-style data
    "chroms": [
      {"name": "chr1", "start": 3000000, "end": 195000000,
       "n_spots": 9500, "n_traces": 1}
    ]
  }
]
```

`chroms` is ordered naturally (`chr1, chr2, …, chr10, …, chrX, chrY, chrM`).

Multi-omics fields (empty lists when the dataset has none):

```json
{
  "cell_fields": [
    {"name": "nucleus_area_um2", "group": "cell", "label": "nucleus_area_um2",
     "min": 81.2, "max": 402.7, "n_valid": 201},
    {"name": "rna.Nanog", "group": "rna", "label": "Nanog",
     "min": 0, "max": 52, "n_valid": 201}
  ],
  "embeddings": [
    {"key": "rna_umap", "method": "umap", "source": "rna", "label": "RNA UMAP",
     "n_dims": 2}
  ],
  "point_sets": [
    {"name": "rna", "n_points": 3334, "label_field": "gene",
     "labels": [{"value": "Auts2", "count": 157}],
     "value_fields": ["peak_intensity"]}
  ]
}
```

`embeddings` are the 2-D-or-more arrays in `cd.cellm` (rows aligned to
`cd.cells`); metadata from `uns["embeddings"][key]` when present.
`cell_fields` are the columns of `cd.cells` usable for colouring:
`kind: "numeric"` (with `min`/`max`) or `kind: "category"` — string
columns with 2–60 values that are not per-cell ids (e.g. `cell_type`), with
`categories: [{"value", "count"}]` in natural order; `group` is the prefix
before the first `.` (`rna.Nanog` → `rna`) or `cell`, and `label` the rest.
`point_sets` describe `cd.points` (non-genomic 3D points in the same frame
as `coords`, e.g. nascent RNA spots); `labels` are sorted by count.

### `POST /api/datasets`

Body `{"path": "/abs/path/data.h5cd"}` (`.h5cd` or reconstruction `.csv`).
Loads the file and returns its summary (same shape as a list item above).
`400` with `{"detail": "..."}` if the file is missing or unreadable.

### `DELETE /api/datasets/{id}`

Unload a dataset.  `204`.

## Traces

### `GET /api/datasets/{id}/traces?chrom=chr1&offset=0&limit=500`

Trace table (optionally restricted to one chromosome), ordered by
chromosome then trace id.

```json
{
  "total": 1231,
  "traces": [
    {"trace_id": "t12", "chrom": "chr21", "cell_id": "c3",
     "n_spots": 65, "start": 28000000, "end": 30000000}
  ]
}
```

`trace_id` / `cell_id` are always strings; `cell_id` may be `null`.

## Cells

### `GET /api/datasets/{id}/cells?offset=0&limit=500`

Cell table in natural id order (`cell_2` before `cell_10`); `total` is 0
when the dataset has no `cell_id` column.

```json
{
  "total": 201,
  "cells": [
    {"cell_id": "0_1", "n_spots": 1548, "n_traces": 41, "n_chroms": 20}
  ]
}
```

### `GET /api/datasets/{id}/cell_values?field=rna.Nanog`

One numeric cell field for every cell (for colouring the overview):

```json
{"field": "rna.Nanog", "kind": "numeric", "cell_ids": ["0_1", "0_2"], "values": [0, 13]}
```

Categorical fields return strings (`"kind": "category"`).  Missing values
are `null`.  `404` unknown field.

### `GET /api/datasets/{id}/cell_info?cell_id=0_2`

All `cd.cells` columns of one cell (numbers stay numbers, NaN → `null`):

```json
{"cell_id": "0_2", "fields": {"nucleus_area_um2": 158.7, "rna.Zfp42": 95}}
```

`404` unknown cell.

### `GET /api/datasets/{id}/embedding/{key}?dims=0,1`

Two components of a cell embedding for a 2-D scatter view:

```json
{"key": "rna_umap", "label": "RNA UMAP", "cell_ids": ["0_1", "0_2"],
 "x": [1.2, -0.4], "y": [3.3, 0.8], "axis_labels": ["UMAP1", "UMAP2"]}
```

`dims` defaults to `0,1` (e.g. `2,3` for PC3/PC4).  Non-finite values →
`null`.  `404` unknown key, `422` bad dims.

## Point sets

### `POST /api/datasets/{id}/points/{name}`

Body (optional filters, AND-ed): `{"cell_ids": ["0_2"], "labels": ["Nanog"]}`.
Small point sets, so the response is JSON:

```json
{
  "n": 2,
  "positions": [x0, y0, z0, x1, y1, z1],
  "cell_ids": ["0_2", "0_2"],
  "labels": ["Nanog", "Sox2"],
  "values": {"peak_intensity": [1234, 980]}
}
```

`cell_ids` entries may be `null`; NaN values → `null`.  `404` unknown set.

## Geometry (binary)

### `POST /api/datasets/{id}/geometry`

Body — a **layer filter**; all fields optional and combined with AND:

```json
{
  "chroms": ["chr1", "chr2"],
  "region": {"chrom": "chr1", "start": 10000000, "end": 20000000},
  "trace_ids": ["t1", "t2"],
  "cell_ids": ["c1"],
  "max_points": 2000000
}
```

Region selection keeps spots whose `[start, end)` overlaps the region.
`max_points` (default 5,000,000) caps the response; when the selection is
larger the server keeps whole segments in order until the cap and sets
`truncated: true`.

Response: `application/octet-stream`, little-endian:

| Offset | Type | Content |
|--------|------|---------|
| 0 | `uint32` | `H` = header byte length (multiple of 4) |
| 4 | `H` bytes | UTF-8 JSON header, right-padded with spaces |
| 4+H | `float32[3·N]` | positions `x0,y0,z0,x1,…` |
| … | `uint32[N]` | genomic `start` of each point's bin |
| … | `uint32[S+1]` | segment offsets into the point arrays |

Header:

```json
{
  "n_points": 1234,                 // N
  "n_segments": 3,                  // S
  "total_points": 1234,             // before truncation
  "truncated": false,
  "segments": [
    {"trace_id": "t1", "chrom": "chr1", "cell_id": null,
     "n_points": 400, "start": 3000000, "end": 12000000}
  ],
  "bbox": {"min": [x, y, z], "max": [x, y, z]},
  "chrom_extent": {"chr1": [3000000, 195000000]}
}
```

A **segment** is a maximal run of consecutive spots (sorted by `start`) of one
trace on one chromosome with finite coordinates.  Spots with NaN coordinates
are dropped and split the run, so a polyline is never drawn across a missing
spot.  Points of segment `i` are `offsets[i] … offsets[i+1]-1`.

`chrom_extent` gives each chromosome's full `[min start, max end]` in the
dataset (not just the selection), so the frontend can colour a sub-region on
the same rainbow scale as its parent.

Errors: `404` unknown dataset, `422` invalid filter.

## Genome-coordinate views (tracks, contact and distance matrices, stats)

These views are **peers** of the 3-D view and also work for datasets without
3-D coordinates (e.g. single-cell Hi-C / RNA: `n_spots == 0`).  All share a
*locus* `chrom, start, end` chosen in the client.

The dataset summary gains:

```json
{
  "has_coords": true,                    // false → no 3-D spots (hide/grey 3-D views)
  "tracks": [{"name": "H3K27ac"}],       // numeric cd.tracks columns (per spot)
  "contact_maps": [
    {"key": "bulk", "kind": "cool",      // cool | mcool | scool
     "label": "IMR90 Hi-C", "resolutions": [30000],
     "chroms": [{"name": "chr21", "length": 46709983}],
     "per_cell": false, "n_cells": 0}
  ],
  "intervals": [{"key": "tads", "n": 120}]   // cd.results DataFrames with chrom/start/end
}
```

`contact_maps` come from `uns["linked_cool"]` (`ChromData.link_cool`) and
`uns["linked_scool"]` (`ChromData.link_scool`); files must exist on the
server.

### Binary matrix payload

`/contacts/…` and `/distance` return `application/octet-stream`, little-endian:
`uint32 H` | `H` bytes JSON header (space-padded to a multiple of 4) |
`float32[n_rows × n_cols]` row-major (`NaN` = missing).  Header:

```json
{"chrom": "chr21", "start": 18000000, "end": 21000000,
 "n_rows": 100, "n_cols": 100, "bin_starts": [...], "bin_ends": [...],
 "resolution": 30000, "value": "count|balanced|distance|contact_frequency",
 "unit": "um", "n_traces": 42, "note": "…"}
```

Matrices are capped at 1,000 × 1,000 bins: larger requests are sum-pooled
(contacts) / median-pooled (distances) and the header says so in `note`.

### `GET /api/datasets/{id}/tracks?names=H3K27ac,H3K9me3&chrom=chr7&start=&end=&cell_id=&agg=mean&group=`

Per-genomic-bin aggregate of spot tracks over the selection (all cells,
one `cell_id`, or a `group` — see *Cell groups*), for a genome-browser
track view:

```json
{"chrom": "chr7", "bin_starts": [...], "bin_ends": [...],
 "n_spots": [12, 9, …],
 "values": {"H3K27ac": [0.3, -0.1, …], "H3K9me3": […]}}
```

`agg`: `mean` (default) | `median` | `max`.  Empty bins are omitted.

### `GET /api/datasets/{id}/intervals/{key}?chrom=chr7&start=&end=`

Rows of an interval table (TADs, loops, peaks):
`{"columns": [...], "rows": [[…], …]}` with `chrom, start, end` (and for
loops `chrom2, start2, end2`) plus any score columns.

### `GET /api/datasets/{id}/contacts/{key}?chrom=chr21&start=&end=&resolution=&balance=false&cell=&group=`

Contact matrix from a linked cool / mcool / scool.  `resolution` picks an
mcool level (default: the finest that fits 1,000 bins); `cell` selects a
cell of an scool (neither `cell` nor `group` → `422`).  Binary payload above.

`group` (scool only) → **pseudo-bulk**: the sum of the raw counts of the
group's cells that have a map (read straight from the HDF5 pixels, so a few
hundred cells take ~0.2 s; at most 20,000 cells, a random subset beyond
that is noted).  Header adds `"group"`, `"n_cells"` (maps summed) and
`"n_contacts"` (upper-triangle total in the region); `value` is `count`
(no balancing).  The last 16 results are cached.  `group` on a cool /
mcool (not per-cell) → `422`; `cell` and `group` together → `422`.

### `GET /api/datasets/{id}/distance?chrom=&start=&end=&cell_id=&trace_id=&stat=median&threshold=&group=`

Pairwise 3-D distances between genomic bins from `coords`:

- `trace_id` → that trace's matrix;
- `cell_id` (no trace) → per-bin-pair median over that cell's traces;
- `group` → statistic over the traces of the group's cells;
- none → population statistic over all traces on `chrom`.

The header adds `"group"` and `"n_cells"` (cells contributing traces).

`stat`: `median` (default) | `mean` | `contact` (fraction of traces with
distance < `threshold`, default 0.5 × dataset unit… or `threshold`).
Binary payload above (`value`: `distance` or `contact_frequency`).

### `GET /api/datasets/{id}/stats/rg?chrom=&cell_id=&group=`

Radius of gyration per trace: `{"trace_ids": [...], "cell_ids": [...],
"chroms": [...], "rg": [...], "n_spots": [...], "unit": "um",
"group": null, "n_cells": 47}`.

### `GET /api/datasets/{id}/stats/scaling?chrom=&cell_id=&group=`

Distance vs genomic separation (log-spaced separation bins):
`{"sep_bp": [...], "median": [...], "q25": [...], "q75": [...], "n_pairs": [...],
"unit": "um", "group": null, "n_cells": 47}`.

## Cell groups

Views can aggregate over a **group** of cells instead of all cells or one
cell.  Every endpoint above that takes `cell_id` / `cell` also takes
`group=<ref>` (exclusive with the cell; both → `422`).  A reference is

- `field:<column>=<value>` — every cell whose `cd.cells[column]` equals
  `value` (e.g. `field:cell_type=Bergmann`; URL-encode it, values may
  contain `+`), usable without registering; or
- a registered id `g<12 hex>` — an explicit cell list (a lasso selection).

An unknown field or id → `404`; a group with no cells → `422`.

### `POST /api/datasets/{id}/groups`

Body `{"cells": ["1_0_25", "1_0_34"], "name": "lasso 1"}` →
`{"id": "g3f1c…", "name": "lasso 1", "n_cells": 2, "n_unknown": 0}`.
The id is a hash of the sorted known cells, so registering the same cells
again (another tab, after a server restart) returns the same id; unknown
cell ids are dropped (`n_unknown`); none known → `422`.  Groups live in the
server's memory: clients keep their own list and re-register on use.

### `GET /api/datasets/{id}/groups`

Registered groups: `[{"id": "g3f1c…", "name": "lasso 1", "n_cells": 2}]`.

### `GET /api/datasets/{id}/group_cells?group=<ref>`

`{"group": "<ref>", "name": "Bergmann", "n_cells": 8, "cells": [...]}`
(natural cell order for registered groups, `cd.cells` order for fields).
