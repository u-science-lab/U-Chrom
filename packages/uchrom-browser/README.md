# uchrom-browser

The U-Chrom web browser: open a `.chromdata.zarr` / `.cdz` store (on disk or over HTTP) and explore its cells in
linked views -- the tissue, embeddings, 3-D structures and chromatin traces, contact and distance maps, tracks.  A
selection made in one view (a lasso, a cell type) re-scopes every view.

```bash
pip install -e packages/chromdata -e packages/uchrom-browser   # from a clone of the repository (not on PyPI yet)
uchrom-browser data.chromdata.zarr                 # or: python -m uchrom_browser data.chromdata.zarr
uchrom-browser --atlas https://uchrom-atlas-r2.u-science.org      # the Open dialog lists an atlas
```

Python and coding agents drive an open browser with the same actions as the page (`ui_tools.json`):

```python
import uchrom_browser as ub
ws = ub.connect()
cells = ws.get_selection()["cells"]
ws.open_view(type="genome", rows=[{"kind": "contacts", "source": "per_cell"}], cells=cells)
```

It needs only the data model, [`chromdata`](../chromdata); the analysis library (`u-chrom`) is not required.  The
server's API is [`uchrom_browser/API.md`](uchrom_browser/API.md); the front end (`uchrom_browser/frontend`, React +
Three.js) is built with `npm run build` into `uchrom_browser/static`, which is committed.
