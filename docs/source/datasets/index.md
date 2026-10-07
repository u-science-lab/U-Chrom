# Datasets and the atlas

U-Chrom keeps no data in its repository.  Every dataset it knows reaches you in one call, as a `ChromData`
or as its original files, from three places:

| Where | What it is | Browse | Get it |
|-------|------------|--------|--------|
| **The atlas** | public 3-D genome datasets, each one `.chromdata.zarr` store in object storage (contact maps, RNA, ATAC, images embedded) | [the atlas page](https://uchrom-atlas.u-science.org), the web browser, `ds.list_atlas()` | `ds.load(id)` opens it over HTTP; `ds.fetch(id)` downloads it (`.cdz`) |
| **Datasets with a loader** | published datasets built into a store from their original files the first time you load them | `ds.list_datasets()` (column `load`) | `ds.load(name)` |
| **Original files** | the files as their source publishes them (4DN, GEO, Zenodo, GitHub, UCSC): raw formats, reference genomes, annotations | `ds.list_datasets()` | `ds.fetch(name)` |

```python
import uchrom.datasets as ds

ds.list_atlas()                           # the atlas: id, title, study, organism, cells, modalities, sizes
cd = ds.load("stevens2017_mesc")          # an atlas store, opened over HTTP (backed: read in parts)
cd = ds.load("takei2021_mesc")            # a dataset with a loader: built once, then read from disk
path = ds.fetch("takei")                  # an original file: Takei 2021 FOF-CT core table (22 MB, 4DN)
```

Which one?  **Analyse a dataset** → `ds.load` (atlas id or loader name: the same call).  **Work offline or
read a whole atlas store many times** → `ds.fetch(id)` once, then `ds.load(id)` reads the local copy.
**Read a raw format yourself, or need a genome / annotation file** → `ds.fetch(name)`.  **Your own data**
→ the readers of [`uchrom.io`](../reference/formats), saved as a store ([data model & storage](../data/index)).

Everything downloaded or built goes to the **data directory**: `$UCHROM_DATA`, else `~/.cache/uchrom`
(`ds.data_dir()`).  Set `UCHROM_DATA` to keep large data elsewhere or to share a folder of downloads.

| Step | Page | API |
|------|------|-----|
| find a dataset: the atlas page, the web browser, the catalog from Python | [Browsing the atlas](browse.md) | `ds.list_atlas`, `chromdata.catalog` |
| a dataset as a `ChromData`: over HTTP, from a local copy, built by a loader | [Loading datasets](load.md) | `ds.load`, `ds.atlas`, `ChromData.read(..., backed=True)` |
| files on disk: atlas stores for offline work, original files, reference files | [Fetching files](fetch.md) | `ds.fetch`, `ds.path`, `ds.list_datasets`, `python -m uchrom.datasets` |

Where every dataset comes from — study, accession, licence, size, how it is fetched or built, who uses it —
is listed in [data sources](../reference/data_sources).

## Tutorial

```{toctree}
:maxdepth: 1

/tutorials/datasets_atlas
```

## Guides

```{toctree}
:maxdepth: 1

browse
load
fetch
```

API: [uchrom.datasets](../reference/api/datasets).
