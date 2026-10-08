# Browsing the atlas

The U-Chrom atlas is a public collection of 3-D genome datasets — single-cell Hi-C, spatial Hi-C, imaging —
each converted to one self-contained `.chromdata.zarr` store and served from object storage
(`https://uchrom-atlas-r2.u-science.org`).  A store opens without downloading it: only what you look at or
analyse is read.

## On the web

- **The atlas page**, [uchrom-atlas.u-science.org](https://uchrom-atlas.u-science.org): every dataset
  with its study, organism, tissue, number of cells, modalities and a thumbnail, grouped by study; each card
  links to the paper, the source data and the one-file download.
- **The hosted web browser**, [uchrom-browser.u-science.org](https://uchrom-browser.u-science.org): open a
  dataset from the *Open* dialog → *Atlas* and look at it — cells in their tissue, structures in 3-D, contact
  maps, embeddings — with nothing installed.  The same dialog lists the atlas in your own browser
  (`python -m uchrom_browser`, see [the web browser](../viz/browser)).

## From Python

`ds.list_atlas()` reads the atlas catalog (`catalog.json`) and returns one row per store:

```python
import uchrom.datasets as ds

atlas = ds.list_atlas()
atlas[["title", "organism", "n_cells", "modalities", "size_mb", "downloaded"]]
atlas[atlas["modalities"].map(lambda m: "3-D coordinates" in m)]      # stores with 3-D structures
```

| Column | Meaning |
|--------|---------|
| `title`, `study`, `organism`, `tissue`, `assembly` | what the dataset is (the study's citation and source accession are in `catalog.json`) |
| `n_cells`, `modalities` | cells (spots for spatial data) and what the store holds: `Hi-C per cell`, `Hi-C per spot`, `Hi-C bulk`, `RNA`, `ATAC per cell`, `3-D coordinates`, `signals per spot`, `images`, `embeddings`, ... |
| `size_mb`, `download_mb` | the store, and its one-file copy (`.cdz`) |
| `downloaded` | the `.cdz` is already in your data directory ([fetching](fetch.md)) |
| `url` | the address `ds.load` and the web browser open |

The full catalog — descriptions, papers, DOIs, licences, studies — is `chromdata.catalog.fetch_catalog(url)`
(a dict); `python -m uchrom.datasets atlas` prints the short table.

## Another atlas

An atlas is any folder or bucket of stores with a `catalog.json`: `ds.list_atlas(root)` and
`ds.atlas(id, root=root)` read another one, `python -m uchrom_browser --atlas URL_OR_FOLDER` (or
`UCHROM_ATLAS`) lists it in the web browser.  How a dataset is added to the public atlas — recipes, embedded
copies, the catalog, the page — is described in [the data atlas](../viz/atlas).
