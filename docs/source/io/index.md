# Importing data

`uchrom.io` reads the formats of the field into `ChromData` (and writes some back).  Imaging data
become spots with coordinates; sequencing data are linked as contact maps per cell, or turned into
coordinates by [3-D reconstruction](../recon/index).

| Data | Reader |
|------|--------|
| 4DN FISH Omics Format, chromatin tracing (FOF-CT) with cell and RNA tables | `ChromData.from_fofct(core, cell_table=, rna_table=, out=)`; back with `cd.to_fofct` |
| PyHiM ECSV traces | `ChromData.from_pyhim_trace` |
| DNA seqFISH+ multi-omics (Takei et al.) | `uchrom.io.read_seqfish_multiomics`, `load_takei2025_cerebellum` |
| Bintu et al. tracing tables | `uchrom.io.read_bintu_tracing` |
| Hi-C contacts: `.pairs`, phased pairs, `.cool` / `.mcool`, `.hic` | `read_pairs`, `read_phased_pairs`, `load_cool`, `load_hic` |
| per-cell contact maps (`.scool`) and pseudo-bulk maps | `cd.link_scool`, `cd.link_cool`; `uchrom.io.count_contacts` |
| structures: `.3dg`, particle CSV, PDB | `read_3dg`, `read_particles`, `save_particles`, `particles_to_pdb` |
| ChromData from older versions (`.h5cd`) | `python -m uchrom.io.upgrade old.h5cd` |

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/import_fofct
/tutorials/import_pyhim_ecsv
/tutorials/import_seqfish_multiomics
```

## Guide

```{toctree}
:maxdepth: 1

formats
```

API: [uchrom.io](../reference/api/io).
