# Datasets

U-Chrom keeps no data in its repository.  There are three ways to data:

**The atlas** — public datasets as `.chromdata.zarr` stores, opened over HTTP without downloading
them (only what an analysis or a view reads is fetched):

```python
import uchrom.datasets as ds

ds.list_atlas()                                   # id, title, cells, modalities, size
cd = ds.atlas("takei2025_cerebellum")             # backed: cells, bins, index now; spots on demand
cell = cd.get_cell(cd.cells.index[0])
```

**Original files** — when a tutorial shows how a raw format is read (FOF-CT, `.pairs`, a `.cool`, raw
seqFISH+ detections), the file is fetched once from its source (4DN, GEO, Zenodo, GitHub, UCSC) into
the *data directory* and checked:

```python
path = ds.fetch("takei")                          # Takei 2021 FOF-CT core table, 22 MB, 4DN
ds.list_datasets()                                # every source U-Chrom knows
```

```bash
python -m uchrom.datasets list
python -m uchrom.datasets fetch takei stevens2017
python -m uchrom.datasets fetch --default        # everything the tutorials fetch (~0.9 GB)
python -m uchrom.datasets path takei
```

The data directory is `$UCHROM_DATA`, else `~/.cache/uchrom` (`ds.data_dir()`); set `UCHROM_DATA` to put
large data elsewhere, or to reuse a folder of earlier downloads.

**Your own data** — imported with [`uchrom.io`](../io/index) and saved as a store
([data model & storage](../data/index)).

Where every dataset comes from — the study, accession, licence, how it is fetched or built (the
recipes of the atlas stores and the benchmark inputs), and who uses it — is listed in
[data sources](../reference/data_sources).
