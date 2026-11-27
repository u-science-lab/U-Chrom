# uchrom-browser

The U-Chrom web browser: open a `.chromdata.zarr` / `.cdz` store (on disk or over HTTP) and explore its cells in
linked views -- the tissue, embeddings, 3-D structures and chromatin traces, contact and distance maps, tracks.  A
selection made in one view (a lasso, a cell type) re-scopes every view.

```bash
pip install -e packages/chromdata -e packages/uchrom-browser   # from a clone of the repository (not on PyPI yet)
uchrom-browser data.chromdata.zarr                 # or: python -m uchrom_browser data.chromdata.zarr
uchrom-browser --atlas https://uchrom-atlas-r2.u-science.org      # the Open dialog lists an atlas
```

Coding agents and Python drive an open browser using the same actions (`ui_tools.json`) via three interfaces — all pure Python stdlib on the client side with no `u-chrom` dependency:

- **Stdio MCP server (`uchrom-browser-mcp` / `uchrom-browser mcp` / `uchrom-web mcp`)**:
  ```bash
  uchrom-browser-mcp --print-config claude   # or: claude-code, codex, cursor
  uchrom-browser-mcp --doctor                # check server health, connected tabs & proxy env
  ```
- **Control CLI (`uchrom-web`, or `uchrom-browser ctl`)** — strict JSON output and semantic exit codes for terminal agents:
  ```bash
  uchrom-web pages                           # connected tabs + active dataset summary
  uchrom-web bind <page_id>                  # when multiple tabs are open
  uchrom-web selection
  uchrom-web open stats --stats rg --compare field:cell_type=Purkinje,field:cell_type=Granule
  uchrom-web batch --steps-json '[{"action":"arrange","args":{"layout":"grid"}}]'
  uchrom-web capture --out rg.svg
  ```
- **Python client (`uchrom_browser.connect()`)**:
  ```python
  import uchrom_browser as ub
  ws = ub.connect()
  cells = ws.get_selection()["cells"]
  ws.open_view(type="genome", rows=[{"kind": "contacts", "source": "per_cell"}], cells=cells)
  ```

The server's HTTP, CLI, and MCP contracts live in [`uchrom_browser/API.md`](uchrom_browser/API.md); the front end (`uchrom_browser/frontend`, React + Three.js) is built with `npm run build` into `uchrom_browser/static`, which is committed.
