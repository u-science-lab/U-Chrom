# Linked Multi-Omics

U-Chrom keeps `ChromData` focused on chromatin structure while allowing
external modality files to be linked explicitly.

Use this pattern when a dataset contains cell-level matrices, raw
single-cell Hi-C contacts, or inferred spatial coordinates that should not be
forced into `coords` / `spots`.

```text
UChromProject
├── ChromData (.chromdata.zarr)   measured or reconstructed 3D structure
├── MuData (.h5mu)               multi-modal single-cell matrices
├── scool (.scool)               raw single-cell Hi-C contact matrices
└── provenance / links           mapping matrices and coordinate semantics
```

## Link MuData

```python
from uchrom import ChromData

cd = ChromData.read("data.chromdata.zarr")
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
cd.write("data.linked.chromdata.zarr")
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
cells, not genomic bins, so store them in `cells` (columns
`<key>_centroid_x` / `_y`) with a record under `uns["cell_spatial"]`
(schema in `packages/chromdata/spec.md`):

```python
cd.set_cell_positions(
    xy,  # shape: n_cells x 2 (or x 3)
    key="tangram_merfish",
    cell_ids=schicar_cell_ids,
    unit="um",
    frame="tissue",
    status="inferred",                  # inferred positions need a source
    source="MERFISH centroid",
    method="Tangram map_cells_to_space",
)
cd.cell_positions("tangram_merfish")    # x, y indexed by cell_id
```

Use this only when `cd.cells` is on the same cell axis as `cell_ids`.  If
`cd.cells` contains MERFISH cells but `xy` contains scHiCAR cells, keep the
scHiCAR coordinates in the linked MuData/AnnData object instead and record
that link from `ChromData`.  (`set_cell_spatial_coordinates()` is the
deprecated form of this call.)

## Link SpatialData

Imaging data sets often come with a SpatialData store (images, segmentation
labels, cell shapes, tables).  Link it rather than copying it:

```python
cd.link_spatialdata("sample.sdata.zarr")             # table / region / instance_key from the store
cd.link_spatialdata("sample.sdata.zarr", key="seg",  # explicit cell map
                    table="table", region="cell_boundaries",
                    region_key="region", instance_key="cell_id",
                    cell_col="sdata_cell")           # when the ids differ: a cells column
sdata = cd.load_linked_spatialdata(cells=["c1", "c2"])   # subset to two cells
cd.validate_links()                                  # path, table, instance key, matched cells
```

`cd.to_spatialdata()` goes the other way: spots as 3-D points, cell
centroids, outlines (`cd.cell_shapes`) and the cell table.

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
- linked SpatialData stores have the recorded table and instance key, and
  the cell map finds the ChromData cells
- cell-position records name existing `cells` columns and have a valid
  status (inferred ones a source)
- linked metadata records have expected formats

## Project Wrapper

For workflows with several linked files, use `UChromProject`:

```python
from uchrom import UChromProject

project = UChromProject.from_chromdata("data.linked.chromdata.zarr")
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
