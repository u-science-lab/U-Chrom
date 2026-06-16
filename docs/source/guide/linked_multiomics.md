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
└── provenance / links      mapping matrices and coordinate semantics
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
    mapping_matrix={
        "modality": "tangram_mapping",
        "shape": "merfish_cells x schicar_cells",
        "semantics": "projection weights from scHiCAR cells to MERFISH cells",
    },
)
cd.write("data.linked.h5cd")
```

The MuData file remains external.  U-Chrom records only link metadata under
`cd.uns["linked_mudata"]`.

## Store the Mapping Matrix

The Tangram mapping matrix is the core evidence for projecting scHiCAR data
into MERFISH space.  Store it in MuData, not only in notes or plots.

Recommended layout:

```text
mdata["schicar_rna"]              scHiCAR cells x genes
mdata["schicar_hic_features"]     scHiCAR cells x Hi-C-derived features
mdata["merfish"]                  MERFISH cells x genes or cell metadata
mdata["tangram_mapping"].X        MERFISH cells x scHiCAR cells
mdata.uns["tangram_mapping"]      method, source files, normalization, axis names
```

With the orientation above, MERFISH-space projection is:

```python
merfish_feature = mdata["tangram_mapping"].X @ schicar_feature
```

If your Tangram output uses the opposite orientation, record that explicitly
in `mdata.uns["tangram_mapping"]` and transpose before projection.

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

When `spots` rows are synthetic `cell x genome_bin` feature rows rather than
optical FISH spots, mark this explicitly:

```python
cd.uns["spot_semantics"] = "cell_by_genomic_bin_feature_rows"
```

## Store Cell-Level Spatial Coordinates

Tangram maps cells to tissue-space positions.  Those positions describe
cells, not genomic bins, so store them in `cells` and record provenance under
`uns["cell_spatial"]`.

```python
cd.set_cell_spatial_coordinates(
    xy,  # shape: n_cells x 2
    key="tangram_merfish",
    cell_ids=schicar_cell_ids,
    source="MERFISH centroid",
    method="Tangram map_cells_to_space",
    coordinate_system="micron",
    inferred=True,
)
```

Use this only when `cd.cells` is on the same cell axis as `cell_ids`.  If
`cd.cells` contains MERFISH cells but `xy` contains scHiCAR cells, keep the
scHiCAR coordinates in the linked MuData/AnnData object instead and record
that link from `ChromData`.

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
