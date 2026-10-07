# Loading datasets

`ds.load(name)` gives a dataset as a `ChromData`, whatever it is:

```python
import uchrom.datasets as ds

cd = ds.load("stevens2017_mesc")          # an atlas id: the store over HTTP (or its local copy)
cd = ds.load("kim2020_scihic")            # a loader: built once from the original files, then read from disk
```

## Atlas stores: read in parts

An atlas store is opened **backed**: the small tables (`cells`, `traces`, `bins`, `uns`, embeddings) are
read at once — a second or two — and everything else when you ask for it, with HTTP range requests:

| You ask for | What is read |
|-------------|--------------|
| `cd.cells`, `cd.bins`, `cd.cellm["..."]`, `cd.uns` | already there |
| `cd.get_cell(id)`, `cd.get_trace(id)`, `cd.get_chrom(name)`, `cd[rows]` | that cell's / trace's / chromosome's rows only → an in-memory `ChromData` |
| `cd.iter_cells(batch)`, `cd.iter_traces(batch)` | the store in batches, for a pass over everything |
| a contact map: `uchrom.fea.open_map(cd, "bulk", resolution=1_000_000)`, `cd.load_linked_cool("bulk", resolution=)` | that level of the embedded map, exported once per session |
| per-cell maps: `cd.load_linked_scool(key=, cell=)`, `cd.linked_scool_path(key, cells=[...])`, `uchrom.fea.pseudobulk(cd, "cell_type")` | the cells asked for (pseudo-bulk: every cell, streamed) |
| RNA / ATAC: `cd.linked_adata` | the embedded AnnData |
| `cd.to_memory()` | everything (as large as `size_mb`) |

The analyses take such a `ChromData` directly (`uc.tl.pseudobulk(cd, "cell_type")`,
`uc.tl.call_compartments(cd, method="eig", contacts="bulk", resolution=1_000_000)`, ...).  `backed=False`
reads the whole store into memory; `columns=` / `tracks=` read only some columns.

**Faster and offline: a local copy.**  `ds.fetch(id)` downloads the store's one-file copy (`.cdz`) into
the data directory; from then on `ds.load(id)` opens that copy — the same object, read from disk
([fetching](fetch.md)).  `ds.atlas(id, local=False)` still reads the remote store, `local=True` insists on the
copy.

**Without `uchrom`.**  The stores are plain `.chromdata.zarr`: `chromdata.ChromData.read(url, backed=True)`
opens one (only `chromdata` and `aiohttp` needed), `s3://` / `gs://` URLs too (`s3fs` / `gcsfs`; options in
`UCHROM_STORAGE_OPTIONS`).

## Datasets with a loader

`ds.list_datasets()` marks them in the column `load`: published datasets that are not in the atlas (chromatin
tracing, bulk Hi-C slices, single-cell Hi-C for the tutorials).  The first `ds.load(name)` fetches the
original files, builds the `ChromData` (contact maps linked next to it) and writes it to
`<data directory>/<dataset>/<dataset>.chromdata.zarr`; afterwards it is read from there — in memory, or
`backed=True`.  A new version of a loader rebuilds it once; `rebuild=True` forces it.

```bash
python -m uchrom.datasets load kim2020_scihic takei2021_mesc     # build ahead of time
```

| Loader | What it gives |
|--------|---------------|
| `takei2021_mesc`, `takei2021_mesc_detections` | DNA seqFISH+ mESC tracing with its cell and RNA tables; the raw detections |
| `bintu_imr90`, `bintu_imr90_hg19`, `su2020_chr21`, `huang2021_sox2` | chromatin tracing (IMR90 chr21, mESC Sox2) |
| `rao2014_imr90_chr21` | bulk Hi-C, IMR90 chr21 at 5 kb, linked |
| `kim2020_scihic`, `tan2018_gm12878`, `wu2025_scmicroc` | single-cell Hi-C with per-cell maps linked |

The full list, with sizes and sources, is `ds.list_datasets()` and [data sources](../reference/data_sources).
