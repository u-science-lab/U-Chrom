# U-Chrom web browser — HTTP API

Contract between the Python server (`uchrom.browser.web.server`) and the
React/Three.js frontend (`uchrom/browser/web/frontend`).  All endpoints are
under `/api`; the built frontend is served from `/`.

The server is a *local* tool (`python -m uchrom.browser --web data.h5cd`):
paths are local filesystem paths on the machine running the server.

## Datasets

### `GET /api/health`

`{"status": "ok", "version": "<uchrom version>"}`

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
  "point_sets": [
    {"name": "rna", "n_points": 3334, "label_field": "gene",
     "labels": [{"value": "Auts2", "count": 157}],
     "value_fields": ["peak_intensity"]}
  ]
}
```

`cell_fields` are the numeric columns of `cd.cells`; `group` is the prefix
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
{"field": "rna.Nanog", "cell_ids": ["0_1", "0_2"], "values": [0, 13]}
```

Missing values are `null`.  `404` unknown field.

### `GET /api/datasets/{id}/cell_info?cell_id=0_2`

All `cd.cells` columns of one cell (numbers stay numbers, NaN → `null`):

```json
{"cell_id": "0_2", "fields": {"nucleus_area_um2": 158.7, "rna.Zfp42": 95}}
```

`404` unknown cell.

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
