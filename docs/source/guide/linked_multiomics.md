# Linked Multi-Omics

U-Chrom keeps `ChromData` focused on chromatin structure while allowing
external modality files to be linked explicitly.

Use this pattern when a dataset contains cell-level matrices, raw
single-cell Hi-C contacts, or inferred spatial coordinates that should not be
forced into `coords` / `spots`.

```text
UChromProject
├── ChromData (.h5cd)       measured or reconstructed 3D structure
├── MuData (.h5mu)          multi-modal single-cell matrices
├── scool (.scool)          raw single-cell Hi-C contact matrices
└── provenance / links      cell mappings and coordinate semantics
```

## Link MuData

```python
from uchrom import ChromData

cd = ChromData.read("data.h5cd")
cd.link_mudata(
    "schicar_mop.h5mu",
    key="schicar_mop",
    modalities=["rna", "atac", "hic_features", "spatial"],
    cell_axis="RNAbarcode",
    spatial_source="Tangram-inferred MERFISH coordinate",
    not_measured_spatial=True,
)
cd.write("data.linked.h5cd")
```

The MuData file remains external.  U-Chrom records only link metadata under
`cd.uns["linked_mudata"]`.

## Link scool

```python
cd.link_scool(
    "GSE305439_DNA_1Mb_MOp_RNAbarcode.scool",
    key="schicar_contacts",
    cell_name="RNAbarcode",
    barcode_source="DNAbarcode",
    genome_assembly="mm10",
    bin_size=1_000_000,
)
```

Raw scHi-C / scHiCAR contacts are contact matrices, not `x/y/z` coordinates.
Only measured or reconstructed coordinates should be stored in
`ChromData.coords`.

## Validate Links

```python
issues = cd.validate_links()
if issues:
    print("\n".join(issues))
```

Validation checks:

- all-NaN coordinates have explicit coordinate-status metadata
- linked file paths exist
- linked scool files can be recognized by `cooler`
- linked metadata records have expected formats

## Project Wrapper

For workflows with several linked files, use `UChromProject`:

```python
from uchrom import UChromProject

project = UChromProject.from_chromdata("data.linked.h5cd")
project.link_mudata("schicar_mop.h5mu", key="schicar_mop")
project.link_scool("GSE305439_DNA_1Mb.scool", key="schicar_contacts")
project.validate()
project.describe()
```

The wrapper does not duplicate data.  It centralizes links and validation.

## Coordinate Semantics

Tangram or similar mapping methods can give single-cell assays inferred
tissue-space positions.  Mark these as inferred:

```text
Tangram-inferred spatial coordinate
```

Do not label them as measured spatial coordinates unless the assay directly
measured the cell position.
