# Datasets

U-Chrom keeps no data in its repository.  Every dataset it knows comes as a `ChromData` in one call:

```python
import uchrom.datasets as ds

cd = ds.load("kim2020_scihic")            # built once from the original files, then read from the data directory
cd = ds.load("takei2021_mesc")            # chromatin tracing, with its cell and RNA tables
cd = ds.load("takei2025_cerebellum")      # a store of the atlas, opened over HTTP (backed)
ds.list_datasets()                        # what there is; column `load`: available as a ChromData
ds.list_atlas()                           # the atlas: id, title, cells, modalities, size
```

**Built from the original files** — a dataset with a loader is downloaded once from its source (4DN, GEO,
Zenodo, GitHub, UCSC; md5-checked), turned into a `.chromdata.zarr` store with its contact maps linked
next to it, and read from there afterwards (in memory; `backed=True` reads it in parts).

**The atlas** — public datasets as stores that open over HTTP without downloading them: only the small
tables are read at first, and a cell or a chromosome when you ask for it
(`cd.get_cell(cd.cells.index[0])`).  Contact maps and RNA are embedded in the store and read the same way.

**The original files themselves** — `ds.fetch(name)` returns the downloaded files, for reading a raw
format yourself (the [file formats](../reference/formats) and the import tutorials do) or for reference
files that are not a `ChromData` (a genome sequence, a gene annotation):

```python
path = ds.fetch("takei")                  # Takei 2021 FOF-CT core table, 22 MB, 4DN
```

```bash
python -m uchrom.datasets list
python -m uchrom.datasets load kim2020_scihic takei2021_mesc     # build the ChromData stores
python -m uchrom.datasets fetch --default                        # every file the tutorials use (~0.9 GB)
python -m uchrom.datasets path takei
```

The data directory is `$UCHROM_DATA`, else `~/.cache/uchrom` (`ds.data_dir()`); set `UCHROM_DATA` to put
large data elsewhere, or to reuse a folder of earlier downloads.

**Your own data** — read with the readers of [`uchrom.io`](../reference/formats) and saved as a store
([data model & storage](../data/index)).

Where every dataset comes from — the study, accession, licence, how it is fetched or built (the
recipes of the atlas stores and the benchmark inputs), and who uses it — is listed in
[data sources](../reference/data_sources).
