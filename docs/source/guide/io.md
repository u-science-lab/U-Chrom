# I/O and file formats

`uchrom.io` handles reading sequencing and imaging data, and saving
reconstruction output.

## Supported inputs

| Format | Reader | Returns |
|--------|--------|---------|
| `.pairs` / `.pairs.gz` | `read_pairs` | DataFrame (read-level pairs) |
| `.cool` / `.mcool` | `load_cool`, `load_hic_genome` | contact pixel DataFrame / bin+matrix |
| `.hic` | `load_hic`, `load_hic_inter`, `load_hic_genome` | bin+matrix |
| `.3dg` | `read_3dg` | DataFrame (chrom, start, x, y, z) |
| `.csv` (reconstruction) | `read_particles` | DataFrame |
| `.chromdata.zarr` / `.cdz` (ChromData) | `read_particles`, `ChromData.read` | DataFrame / `ChromData` |
| FOF-CT core CSV | `ChromData.from_fofct` | `ChromData` |

## Reconstruction output: `save_particles`

All reconstruction modules write through
`uchrom.io.save_particles(df, path)`:

- `path` ending in `.csv` → CSV (legacy)
- `.chromdata.zarr` / `.cdz` → `ChromData` store (other suffixes raise)

```python
from uchrom.io import save_particles
save_particles(df, "out.chromdata.zarr")   # ChromData
save_particles(df, "out.csv")              # plain CSV
```

`read_particles` auto-detects the format by extension so downstream code
(browser, analysis) does not care which format is on disk; ChromData
files come back in the row order they were saved in.

## FOF-CT import details

`ChromData.from_fofct(path)` handles several real-world FOF-CT quirks:

- `##Columns=(…)` declared case-insensitively (some writers use lower-case)
- CSV column header row repeated after the `##Columns=` metadata
- Header lines wrapped in double quotes and padded with trailing commas
- Optional extra columns (e.g. `Readout`) preserved in `spots`
- `##XYZ_Unit`, `##Genome_Assembly` promoted to top-level `uns` keys

Unit conversion: FOF-CT files are typically in µm; you can scale in place
by multiplying `cd.coords` yourself, or pass a custom unit label into
`uns['xyz_unit']` so downstream plots label correctly.

## FOF-CT export: `to_fofct`

`cd.to_fofct(path, cell_table=None, rna_table=None)` (or
`uchrom.io.write_fofct(cd, path, …)`) writes the inverse of `from_fofct`:

- the core table: `##FOF-CT_version`, `##Table_namespace`,
  `##genome_assembly`, `##XYZ_unit` and the `#key: value` lines — taken
  from `uns['fofct_header']` when the data came from FOF-CT, else from
  `uns` — then `##columns=(Spot_ID, Trace_ID, X, Y, Z, Chrom, Chrom_Start,
  Chrom_End, [Cell_ID, Sub_Cell_ROI_ID, Extra_Cell_ROI_ID], …extra spot
  columns, spot tracks)`, one row per spot;
- `cell_table=`: `cd.cells` as a `4dn_FOF-CT_cell` table (`Cell_ID` first;
  `centroid_*` → `Cent_ROI_*`, `nucleus_area_um2` → `area(um2)`, the
  `rna.` prefix removed);
- `rna_table=`: `points['rna']` as a `4dn_FOF-CT_rna` table.

Coordinates are written with full precision and `from_fofct` parses them
exactly (`float_precision="round_trip"`), so `from_fofct(to_fofct(cd))`
gives back the same coordinates, ids, loci, extra columns, cell table and
RNA spots.  Spot tracks come back as spot columns; `bin_tracks=True` also
writes the per-locus tracks, broadcast to spots.  FOF-CT has no place for
`cellm`, `binm`, `layers`, `intervals`, `results` or other `uns` keys.

```python
cd.to_fofct("out_core.csv", cell_table="out_cell.csv", rna_table="out_rna.csv",
            header={"lab_name": "My lab"})
```

## ChromData files and format versioning

`cd.write(path)` / `ChromData.read(path)` pick the container from the
path: `.chromdata.zarr` (Zarr v3 + Parquet, the default), `.cdz` (the
same store zipped into one file).  The HDF5 `.h5cd` container of format
1.x / 2.0 is no longer read or written; convert such files once with
`python -m uchrom.io.upgrade old.h5cd` (→ `old.chromdata.zarr`) or
`uchrom.io.upgrade_h5cd(src, dst)`.

Every container records two attributes:

| Attribute | Example |
|-----------|---------|
| `uchrom_format_version` | `"2.0"` |
| `uchrom_version` | `"0.2.0"` |

Read semantics:

- Same MAJOR → read (higher MINOR warns, unknown fields ignored)
- Different MAJOR → `ValueError` with upgrade guidance
- Missing attribute → assume legacy 1.0 with a warning

New MAJOR versions add a `_read_vN(cls, f)` function in
`uchrom/core/cdata.py` (HDF5) or a reader in `uchrom/core/zarrcd.py`
(zarr) plus any migration helper needed; the dispatch in
`ChromData.read` is the single place that maps path and version to
reader.
