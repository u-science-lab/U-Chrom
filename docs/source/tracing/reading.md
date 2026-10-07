# Reading tracing data

| Data | Reader |
|------|--------|
| 4DN FISH Omics Format, chromatin tracing (FOF-CT), with its cell and RNA tables | `ChromData.from_fofct(core, cell_table=, rna_table=, out=)`; back with `cd.to_fofct` |
| PyHiM ECSV traces | `ChromData.from_pyhim_trace`; write one with `uchrom.io.write_pyhim_trace` |
| the tables of Bintu et al. 2018 | `uchrom.io.read_bintu_tracing` |
| the tables of Su et al. 2020 (chromosome- and genome-scale DNA-MERFISH), with the authors' binned Hi-C | `uchrom.io.read_su2020_tracing`, `read_su2020_hic`; a locus × locus map as a `.cool`: `write_locus_cool` |
| SnapFISH / SnapFISH-IMPUTE coordinate + annotation tables | `uchrom.io.read_snapfish(coor, ann)` |
| raw DNA seqFISH+ detections (not yet traced) | `uchrom.io.read_seqfish_detections` → [from detections to traces](traces) |
| several spots of one trace on one locus | `uchrom.im.merge_duplicate_spots` (`uc.pp.merge_duplicate_spots`) |
| published datasets, ready as `ChromData` | `uchrom.datasets.load("takei2021_mesc")`, `load("bintu_imr90")`, ... ([datasets](../start/datasets)) |

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/import_fofct
/tutorials/import_pyhim_ecsv
```

## The 4DN FISH Omics Format (FOF-CT)

FOF-CT is the 4DN Nucleome format for chromatin tracing: a core table of spots (`Spot_ID`, `Trace_ID`,
`X`, `Y`, `Z`, `Chrom`, `Chrom_Start`, `Chrom_End`, optional `Cell_ID` and extra columns) under `##`
header lines, with optional companion tables of cells and of RNA spots.

### Reading: `ChromData.from_fofct`

```python
from chromdata import ChromData

cd = ChromData.from_fofct("core.csv", cell_table="cells.csv", rna_table="rna.csv")
```

Columns map as `Spot_ID` → `spot_id`, `Trace_ID` → `trace_id`, `X/Y/Z` → `coords`, `Chrom`,
`Chrom_Start`, `Chrom_End` → the locus (`bins`), `Cell_ID` → `cell_id`.  The cell table becomes
`cd.cells` (gene counts as `rna.<gene>`; centroids `Cent_ROI_x/y[/z]` or `cell_center_*_global` are
registered as cell positions), the RNA spot table `cd.points["rna"]`.  `out="x.chromdata.zarr"` streams
a large table into a store chunk by chunk instead of building it in memory.

`from_fofct` handles the quirks of real files:

- `##Columns=(…)` declared case-insensitively (some writers use lower case);
- the CSV header row repeated after the `##Columns=` line;
- header lines wrapped in double quotes and padded with trailing commas;
- extra columns (e.g. `Readout`) kept as spot columns;
- `##XYZ_Unit` and `##Genome_Assembly` promoted to `uns["xyz_unit"]` / `uns["genome_assembly"]`; all
  header lines kept in `uns["fofct_header"]`.

FOF-CT files are usually in µm; to use other units, scale `cd.coords` and set `uns["xyz_unit"]` so
that plots are labelled correctly.

### Writing: `cd.to_fofct`

`cd.to_fofct(path, cell_table=None, rna_table=None)` (or `uchrom.io.write_fofct(cd, path, …)`) is the
inverse of `from_fofct`:

- the core table: `##FOF-CT_version`, `##Table_namespace`, `##genome_assembly`, `##XYZ_unit` and the
  `#key: value` lines — from `uns["fofct_header"]` when the data came from FOF-CT, else from `uns` —
  then `##columns=(Spot_ID, Trace_ID, X, Y, Z, Chrom, Chrom_Start, Chrom_End, [Cell_ID,
  Sub_Cell_ROI_ID, Extra_Cell_ROI_ID], …extra spot columns, spot tracks)`, one row per spot;
- `cell_table=`: `cd.cells` as a `4dn_FOF-CT_cell` table (`Cell_ID` first; `centroid_*` →
  `Cent_ROI_*`, `nucleus_area_um2` → `area(um2)`, the `rna.` prefix removed);
- `rna_table=`: `points["rna"]` as a `4dn_FOF-CT_rna` table.

Coordinates are written with full precision and read back exactly, so `from_fofct(to_fofct(cd))` gives
back the same coordinates, ids, loci, extra columns, cell table and RNA spots.  Spot tracks come back
as spot columns; `bin_tracks=True` also writes the per-locus tracks, broadcast to spots.  FOF-CT has no
place for `cellm`, `binm`, `layers`, `intervals`, `results` or other `uns` keys.

```python
cd.to_fofct("out_core.csv", cell_table="out_cell.csv", rna_table="out_rna.csv",
            header={"lab_name": "My lab"})
```

The tutorial [Importing FOF-CT chromatin-tracing data](../tutorials/import_fofct) does both on the Takei
et al. 2021 tables.
