# File formats

What U-Chrom reads and writes, in one table; the chapters show each in use.

## Readers and writers

| Data | Read | Write |
|------|------|-------|
| `.chromdata.zarr` / `.cdz` (ChromData; spec: [format specification](format_spec)) | `ChromData.read(path, backed=, columns=, original_order=)`, also over HTTP / S3 | `cd.write(path)`, `ChromData.writer(path)` (streaming) |
| 4DN FISH Omics Format, chromatin tracing (FOF-CT) + cell and RNA tables | `ChromData.from_fofct(core, cell_table=, rna_table=, out=)` ([guide](../tracing/fofct)) | `cd.to_fofct`, `uchrom.io.write_fofct` |
| PyHiM ECSV traces | `ChromData.from_pyhim_trace` | — |
| Bintu et al. 2018 tracing CSV | `uchrom.io.read_bintu_tracing` | — |
| DNA seqFISH+ multi-omics (Takei et al. 2025) | `uchrom.io.read_seqfish_multiomics`, `load_takei2025_cerebellum`, `load_seqfish_multiomics_linked` | — |
| contacts: `.pairs` / `.pairs.gz`, phased pairs | `uchrom.io.read_pairs`, `read_phased_pairs` | `uchrom.io.write_higashi_inputs` (Higashi) |
| contact maps: `.cool` / `.mcool`, `.hic` | `uchrom.io.load_cool`, `load_hic`, `load_hic_inter`, `load_hic_genome` | — |
| per-cell maps (`.scool`), bulk / pseudo-bulk maps, RNA / ATAC (`.h5ad`, `.h5mu`), SpatialData | linked: `cd.link_scool`, `cd.link_cool`, `cd.link_anndata`, `cd.link_mudata`, `cd.link_spatialdata` | embedded copies: `python -m chromdata.embedded STORE`; export: `chromdata.embedded.export_scool` / `export_cool` / `export_mcool` |
| structures: `.3dg`, particle CSV | `uchrom.io.read_3dg`, `read_particles` | `uchrom.io.save_particles` |
| structures as PDB | — | `uchrom.io.particles_to_pdb`, `python -m uchrom.io particles_to_pdb` |
| legacy `.h5cd` (format 1.x / 2.0) | convert once: `python -m uchrom.io.upgrade old.h5cd` | — |

## Particles: `save_particles` / `read_particles`

The reconstruction modules can write a particle table through `uchrom.io.save_particles(df, path)`:
a path ending in `.csv` writes a plain CSV, `.chromdata.zarr` / `.cdz` a `ChromData` store (other
suffixes raise).  `read_particles` picks the format by the suffix, so code that reads structures does
not care which one is on disk.

```python
from uchrom.io import save_particles
save_particles(df, "out.chromdata.zarr")   # ChromData
save_particles(df, "out.csv")              # plain CSV
```

## Store versions

`cd.write(path)` / `ChromData.read(path)` pick the container from the path: `.chromdata.zarr` (Zarr v3 +
Parquet) or `.cdz` (the same store in one zip file).  The HDF5 `.h5cd` container of format 1.x / 2.0 is
no longer read or written; convert such files once with `python -m uchrom.io.upgrade old.h5cd`
(→ `old.chromdata.zarr`) or `uchrom.io.upgrade_h5cd(src, dst)`.

Every store records two attributes in its root `zarr.json`:

| Attribute | Example |
|-----------|---------|
| `uchrom_format_version` | `"2.3"` (`chromdata.zarrcd.ZARR_FORMAT_VERSION`) |
| `uchrom_version` | the version of the package that wrote it |

Reading: the same MAJOR is read (a higher MINOR warns; unknown fields are ignored); another MAJOR raises a
`ValueError` naming the converter.  Formats 2.0–2.2 are read as they are.
