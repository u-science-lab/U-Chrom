# U-Chrom web browser — HTTP API

Contract between the Python server (`uchrom.browser.web.server`) and the
React/Three.js frontend (`uchrom/browser/web/frontend`).  All endpoints are
under `/api`; the built frontend is served from `/`.

The server is a *local* tool (`python -m uchrom.browser --web data.chromdata.zarr`):
paths are local filesystem paths on the machine running the server.

`.chromdata.zarr` / `.cdz` stores are opened **backed**: loading reads only
the small tables and the store's `index/`; the summary, trace and cell lists
come from the index, and a geometry request that names cells, traces or
chromosomes reads just those spots.  `.csv` files are loaded into memory
(the responses are the same either way).  A legacy `.h5cd` is refused
(`400`; convert it with `python -m uchrom.io.upgrade`).

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
    "path": "/abs/path/cell1.chromdata.zarr",
    "n_spots": 105700,
    "n_bins": 2600,                 // cd.bins (ChromData format 2.0 locus axis)
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
A dataset without spots (spatial Hi-C, scHi-C) lists the chromosomes of
its `bins` (with `n_spots: 0`), so the genome views can show its contact
maps and cell × bin tracks.

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
    {"key": "rna_umap", "method": "umap", "source": "rna", "modality": "RNA",
     "label": "RNA UMAP", "n_dims": 2},
    {"key": "atac_lsi", "method": "lsi", "source": "atac", "modality": "ATAC",
     "label": "ATAC LSI", "n_dims": 29}
  ],
  "point_sets": [
    {"name": "rna", "n_points": 3334, "label_field": "gene",
     "labels": [{"value": "Auts2", "count": 157}],
     "value_fields": ["peak_intensity"]}
  ]
}
```

`embeddings` are the 2-D-or-more arrays in `cd.cellm` (rows aligned to
`cd.cells`); metadata from `uns["embeddings"][key]` when present
(`uchrom.emb.embed_cells` writes it).  `method` is `pca`, `lsi`, `tsne`,
`umap` (or `null`), taken from the metadata or else from the key suffix
(`atac_umap` → `umap`).  `modality` is the display group the Embedding
view uses: the recorded `modality`, else from `source` / the key prefix
(`rna` → `RNA`, `if` → `Histone/IF`, `atac` → `ATAC`, `hic` → `Hi-C`),
`Published` for `paper_*` keys or a `…metadata` source, else `Other`.
`cell_fields` are the columns of `cd.cells` usable for colouring:
`kind: "numeric"` (with `min`/`max`) or `kind: "category"` — string
columns with 2–60 values that are not per-cell ids (e.g. `cell_type`), with
`categories: [{"value", "count"}]` in natural order; `group` is the prefix
before the first `.` (`rna.Nanog` → `rna`) or `cell`, and `label` the rest.
`point_sets` describe `cd.points` (non-genomic 3D points in the same frame
as `coords`, e.g. nascent RNA spots); `labels` are sorted by count.

### `POST /api/datasets`

Body `{"path": "/abs/path/data.chromdata.zarr"}` (a `.chromdata.zarr`
directory, `.cdz` or reconstruction `.csv`).
Loads the file and returns its summary (same shape as a list item above).
`400` with `{"detail": "..."}` if the file is missing or unreadable.

### `GET /api/files?path=&hidden=false`

One directory on the server, for the Open dataset dialog (default: the server's working directory):

```json
{"path": "/data/spatial", "parent": "/data", "sep": "/", "truncated": false,
 "entries": [{"name": "raw", "path": "/data/spatial/raw", "kind": "dir", "format": null, "size": null, "mtime": 1790712482.5},
             {"name": "brain.chromdata.zarr", "path": "…", "kind": "dataset", "format": "chromdata.zarr",
              "size": 1342177, "mtime": 1790712482.5}]}
```

- `kind`: `dir`, `dataset` or `file`.  A dataset is something `POST /api/datasets` opens: a
  `*.chromdata.zarr` directory (listed as a dataset, not entered), `.cdz`, `.csv`, `.csv.gz`.
- Order: directories, datasets, other files; by name within each.
- `size` is in bytes (the total of the files of a store directory).
- Hidden entries appear only with `hidden=true`.  At most 5,000 entries (`truncated`).
- Errors: `404` no such directory / not a directory, `403` permission denied.  Only names and `stat`
  are read.

### `GET /api/files/places`

Starting points of the dialog: `[{"label": "Server folder", "path": …}, {"label": "Home", "path": …},
…]` — the server's working directory, the home directory, then the folder of each loaded dataset
(each folder once).

### `GET /api/atlas?refresh=false`

The atlas the server lists (`--atlas URL`, `UCHROM_ATLAS`, default `https://uchrom-atlas-r2.u-science.org`; an empty
value turns it off): `{"root": <URL or folder>, "catalog": {"title", "description", "updated", "datasets": [...]}}`.
Every dataset carries `url` (what `POST /api/datasets` opens: a `.chromdata.zarr` read over HTTP / S3 on demand),
`title`, `paper`, `doi`, `source_url`, `license`, `organism`, `assembly`, `tissue`, `n_cells`, `sections`,
`modalities`, `contact_maps`, `images`, `size_mb`.  Fetched by the server (the page needs no CORS) and cached 5
minutes (`refresh=true` re-reads).  `{"root": null, "catalog": null}` when no atlas is configured; `502` when the
catalog cannot be read.  Format and builder: `uchrom/core/atlas.py` (`python -m uchrom.core.atlas build`).

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

## Cell positions and images

### `GET /api/datasets/{id}/spatial/{key}?region=`

The cells of one region (section / FOV) of a cell-position set
(`cd.cell_positions(key)`), with the region's image:

```json
{"key": "image", "region": "E14_5_HiC", "unit": "px", "y_axis": "down",
 "cell_ids": ["E14_5_HiC:1x15", …], "x": [1063.1, …], "y": [1074.4, …],
 "image": {"name": "E14_5_HiC", "extent": [0, 1080, 0, 1080], "kind": "bright-field"}}
```

Without `region`, every cell with a position, plus `"regions"` (the region of
each cell, or `null` without a `region_col`) and `"images"` (region → image,
as above) so a client can switch regions without another request.  Sets are listed in the
dataset summary:

```json
"spatial": [{"key": "image", "unit": "px", "frame": "tissue", "y_axis": "down",
             "status": "measured", "source": "…", "n_images": 6,
             "regions": [{"name": "E14_5_HiC", "n_cells": 5426, "image": "E14_5_HiC"}]}]
```

one per `uns["cell_spatial"]` record, sets with images first; `regions`
are the values of the record's `region_col`.  `y_axis` is the record's
(`"down"` for image pixels / grid rows; default `"down"` for units `px`
and `spot`, else `"up"`).  Images are `uns["linked_images"][name]` records
(`path` relative to the dataset, `positions` = the key whose units they are
in, `region`, `extent` [x0, x1, y0, y1] with the image's first row at y0,
optional `kind`).  `404` unknown key / region.

### `GET /api/datasets/{id}/images/{name}`

The image file of a `linked_images` record (e.g. PNG).  `404` unknown name
or missing file.

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

**Whole genome.**  `chrom=*` asks for every chromosome end to end in
*genome coordinates* (a chromosome's positions plus its `offset` in the
summary's `genome` list: natural order, `length` = the largest extent of its
bins / spots and of any contact map).  `start` / `end` are ignored — the whole
genome comes back at once.  `tracks` pools k consecutive bins of a chromosome
beyond 4,000 bins; `contacts` takes an `.mcool` at the finest resolution with at
most 1,000 bins over the genome, else pools k × k bins within each chromosome
(`note` says so); `intervals` returns every row with `start` / `end` shifted;
`distance` answers `400` (3-D distances are per chromosome).

The dataset summary gains:

```json
{
  "has_coords": true,                    // false → no 3-D spots (hide/grey 3-D views)
  "tracks": [{"name": "ATAC", "level": "bin", "grid": "spots"},     // numeric cd.bin_tracks columns (per locus)
             {"name": "H3K27ac", "level": "spot", "grid": "spots"}, // numeric cd.spot_tracks columns (per spot)
             {"name": "ssAB@500kb", "level": "cell_bin", "grid": "ssAB@500kb",
              "label": "ssA/B 500 kb", "resolution": 500000, "n_cells": 17204}],
      // cell_bin: a linked cell × bin matrix, one track per resolution (see /tracks)
  "contact_maps": [
    {"key": "bulk", "kind": "cool",      // cool | mcool | scool
     "label": "IMR90 Hi-C", "resolutions": [30000],
     "chroms": [{"name": "chr21", "length": 46709983}],
     "per_cell": false, "n_cells": 0}
  ],
  "genome": [{"name": "chr1", "offset": 0, "length": 195471971},     // the whole-genome layout (chrom=*)
             {"name": "chr2", "offset": 195471971, "length": 182113224}],
  "intervals": [{"key": "tads.arcfish", "n": 120, "kind": "domain"}]
      // cd.intervals tables (kind: domain | segment | peak) first, then other
      // cd.results DataFrames with chrom/start/end (kind: null)
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

### `GET /api/datasets/{id}/store`

The on-disk structure of a `.chromdata.zarr` / `.cdz` store, for the Store tab
(`422` for in-memory / CSV datasets).  A nested node:

```json
{"name": "x.chromdata.zarr", "path": "", "kind": "group", "bytes": 2935369563,
 "container": "zarr",                          // root only: zarr (directory) | cdz (zip)
 "attrs": {"uchrom": "{\"format_version\":\"2.3\",…}"},   // key → JSON preview (≤160 chars)
 "children": [
   {"name": "umap", "path": "cellm/umap", "kind": "array", "bytes": 27827,
    "shape": [1799, 2], "dtype": "float64", "chunk_shape": [1799, 2], "n_chunks": 1},
   {"name": "bins.parquet", "path": "tables/bins.parquet", "kind": "table", "bytes": 1203,
    "rows": 41, "columns": ["chrom", "start", "end"], "row_groups": 1}
 ]}
```

`kind`: `group` (Zarr group), `dir` (a plain folder, e.g. `chrom=chr1`),
`array` (its chunk files are folded in: `n_chunks`), `table` (Parquet),
`file`.  At most 400 children per node (`more` counts the rest).

### `GET /api/datasets/{id}/tracks?names=H3K27ac,H3K9me3&chrom=chr7&start=&end=&cell_id=&agg=mean&group=`

Per-genomic-bin aggregate of tracks over the spots of the selection (all
cells, one `cell_id`, or a `group` — see *Cell groups*), for a
genome-browser track view.  Bin-level tracks are broadcast to their spots
first, so `n_spots` and empty-bin omission behave the same for both levels:

```json
{"chrom": "chr7", "bin_starts": [...], "bin_ends": [...],
 "n_spots": [12, 9, …],
 "values": {"H3K27ac": [0.3, -0.1, …], "H3K9me3": […]}}
```

`agg`: `mean` (default) | `median` | `max`.  Empty bins are omitted.

`cell_bin` tracks come from `uns["linked_bin_matrices"][key]`: an
AnnData file (path relative to the dataset) of cells × bins, `obs` index =
cell ids, `var["bin_id"]` = rows of `cd.bins` (`var["resolution"]` splits it
into one track per bin size, named `<key>@<size>`, e.g. `ssAB@500kb`).  The
value of a bin is the `agg` over the cells in scope that have one (all
cells, one cell, a group); `n_spots` counts those cells; every bin of the
window is returned (`null` = no value; a cell not in the matrix gets all
`null`).  Tracks reported on different bins (`grid`) must be requested
separately: mixing them is a `422`.

### `GET /api/datasets/{id}/intervals/{key}?chrom=chr7&start=&end=`

Rows of an interval table (TADs, loops, peaks; `cd.intervals[key]`, else
`cd.results[key]`):
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
- a registered id `g<12 hex>` — an explicit cell list (a lasso selection);
- `all` — every cell of the dataset (reserved; on a per-cell `.scool` map it
  gives the all-cell pseudo-bulk — the client's "All cells" setting).

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

## Control (drive the open page from code and agents)

The page stays the owner of what is on screen.  A caller posts an action; the server forwards it
to the active page over Server-Sent Events; the page runs it with the same functions as its GUI
(`frontend/src/actions.ts`) and posts the result back.  Actions are defined once in
`ui_tools.json` (name, description, JSON-schema input), which the page also registers as WebMCP
tools (`frontend/src/webmcp.ts`, feature-detected, experimental).  Python:
`uchrom.browser.connect()` (`uchrom/browser/client.py`).

### `GET /api/control/tools`

`ui_tools.json`: `{"version": 1, "tools": [{"name", "description", "inputSchema", "annotations"?}]}`.

### `POST /api/control/actions`

Body `{"name": "open_view", "args": {...}, "timeout": 30, "page": null}` → `{"ok": true, "result": …}`
(the page's return value).  `404` unknown action; `409` no page is connected; `422` the page
reported an error (`detail` is its message); `504` the page did not answer within `timeout` s.
Without `page`, the most recently active page (last focused, else last connected) runs it.

### `GET /api/control/events?page=<id>` (page side)

`text/event-stream`: `event: hello` once, then `event: action` with
`{"id", "name", "args"}` per action; a `: keepalive` comment every 15 s.

### `POST /api/control/results/{action_id}` (page side)

Body `{"ok": true, "result": …}` or `{"ok": false, "error": "…"}` → `{"accepted": bool}`.

### `POST /api/control/active?page=<id>` · `GET /api/control/pages`

The page marks itself active on window focus; `pages` lists connected pages, active first.

`python -m uchrom.browser --web` records its URL in `~/.cache/uchrom/browser.json` (removed on
exit) so that `connect()` finds a server that moved to another port.
