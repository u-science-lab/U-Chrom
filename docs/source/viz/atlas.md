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
- **Analyse**: read a store from Python, backed, without downloading it:

```python
from chromdata import ChromData, catalog

cat = catalog.fetch_catalog(catalog.DEFAULT_ATLAS)      # https://uchrom-atlas-r2.u-science.org
[(d["id"], d["n_cells"], d["modalities"]) for d in cat["datasets"]][:3]

cd = ChromData.read(cat["datasets"][0]["url"], backed=True)
```

  Each dataset also has a one-file download (`.cdz`) for offline work.

## How a dataset gets into the atlas

The datasets are built by the scripts in `example-data/` (one `build_*.py` per study, documented in
the [example-data catalog](../start/example_data)), then

1. `python -m chromdata.embedded STORE.chromdata.zarr` copies the linked contact maps (`.cool`,
   `.mcool`, `.scool`), AnnData and images into the store (chunked and sharded for range requests);
2. the store is uploaded to the bucket;
3. `python -m chromdata.catalog build apps/atlas/datasets.json` writes `catalog.json` — the
   descriptions come from `apps/atlas/datasets.json`, the counts and modalities from the stores;
4. `python apps/atlas/build.py figures|site` draws the thumbnails and the static page.

The full procedure is `apps/atlas/PUBLISH.md`; the deployment of the page and the hosted browser is
`apps/README.md`.  Your own folder of stores plus a `catalog.json` is an atlas too:
`python -m uchrom_browser --atlas /path/to/folder`.
