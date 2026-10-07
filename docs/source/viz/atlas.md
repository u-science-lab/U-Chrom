# The data atlas

The U-Chrom atlas is a public collection of 3-D genome datasets — single-cell Hi-C, spatial Hi-C,
imaging — each converted to one self-contained `.chromdata.zarr` store (contact maps, RNA / ATAC
and section images embedded) and served from object storage.

- **Browse**: [uchrom-atlas.u-science.org](https://uchrom-atlas.u-science.org) lists the datasets
  with their studies and thumbnails.
- **Look**: open a dataset in the hosted web browser,
  [uchrom-browser.u-science.org](https://uchrom-browser.u-science.org), or in your own
  (`python -m uchrom_browser`, *Open* dialog → *Atlas*).  Nothing is downloaded up front; views read
  the parts they show.
- **Analyse**: `uchrom.datasets.load(id)` opens a store from Python, backed, without downloading it;
  `uchrom.datasets.fetch(id)` downloads its one-file copy (`.cdz`) for offline work — see
  [datasets & the atlas](../datasets/index).

## How a dataset gets into the atlas

The datasets are built by the recipes in `apps/atlas/recipes/` (one `build_*.py` per study, from the
original files `uchrom.datasets` fetches; documented in [data sources](../reference/data_sources)), then

1. `python -m chromdata.embedded STORE.chromdata.zarr` copies the linked contact maps (`.cool`,
   `.mcool`, `.scool`), AnnData and images into the store (chunked and sharded for range requests);
2. the store is uploaded to the bucket;
3. `python -m chromdata.catalog build apps/atlas/datasets.json --root $UCHROM_DATA` writes `catalog.json` — the
   descriptions come from `apps/atlas/datasets.json`, the counts and modalities from the stores;
4. `python apps/atlas/build.py figures|site` draws the thumbnails and the static page.

The full procedure is `apps/atlas/PUBLISH.md`; the deployment of the page and the hosted browser is
`apps/README.md`.  Your own folder of stores plus a `catalog.json` is an atlas too:
`python -m uchrom_browser --atlas /path/to/folder`.
