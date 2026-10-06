# chromdata

The data model of U-Chrom: one object and one store for single-cell Hi-C, spatial Hi-C and chromatin tracing.

- **`ChromData`**: cells › traces › spots on a shared locus axis (`bins`); per-locus, per-spot and per-cell tables;
  contact maps linked per cell (`.cool` / `.scool`), not copied; tissue positions and outlines; analysis results
  with provenance.
- **`.chromdata.zarr`**: Zarr v3 + Parquet, coordinates partitioned by chromosome and sorted by cell, read in parts
  (a cell, a chromosome) from disk or over HTTP (`.cdz` = the same tree in one zip file).  The specification is
  [`spec.md`](spec.md).

```bash
pip install chromdata            # numpy, pandas, zarr, pyarrow
pip install "chromdata[all]"     # + linked contact maps, AnnData / MuData, remote stores, cell outlines
```

```python
from chromdata import ChromData

cd = ChromData.read("x.chromdata.zarr", backed=True)     # or an https:// / s3:// URL
cell = cd.get_cell(cd.cells.index[0])                    # one cell, read alone
```

Part of [U-Chrom](https://github.com/u-science-lab/U-Chrom): the analysis library is `u-chrom` (`import uchrom`),
the web browser `uchrom-browser`.  Atlases of stores: `python -m chromdata.catalog`.
