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
| `.h5cd` (ChromData) | `read_particles`, `ChromData.read` | DataFrame / `ChromData` |
| FOF-CT core CSV | `ChromData.from_fofct` | `ChromData` |

## Reconstruction output: `save_particles`

All reconstruction modules write through
`uchrom.io.save_particles(df, path)`:

- `path` ending in `.csv` → CSV (legacy)
- `path` ending in `.h5cd` or anything else → `ChromData` HDF5 (default)

```python
from uchrom.io import save_particles
save_particles(df, "out.h5cd")   # ChromData
save_particles(df, "out.csv")    # plain CSV
```

`read_particles` auto-detects the format by extension so downstream code
(browser, analysis) does not care which format is on disk.

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

## .h5cd format versioning

The on-disk `.h5cd` layout is versioned with two root attributes:

| Attribute | Example |
|-----------|---------|
| `uchrom_format_version` | `"1.0"` |
| `uchrom_version` | `"0.2.0"` |

Read semantics:

- Same MAJOR → read (higher MINOR warns, unknown fields ignored)
- Different MAJOR → `ValueError` with upgrade guidance
- Missing attribute → assume legacy 1.0 with a warning

New MAJOR versions add a `_read_vN(cls, f)` function in
`uchrom/core/cdata.py` plus any migration helper needed; the dispatch in
`ChromData.read` is the single place that maps version to reader.
