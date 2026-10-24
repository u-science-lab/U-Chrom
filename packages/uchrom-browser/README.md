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

## Local agent loop

The local browser includes a process-local agent control layer. A Claude or Codex process can pin a
connected page, read its canonical state, and propose a revision-bound plan through the Python
client. The user reviews that plan in the local WebUI Agent panel and clicks Apply or Reject; the
server then executes the approved actions over the same SSE channel used by the page and reads the
canonical state back. The agent cannot apply a mutation without that local approval.

Run the real-data smoke test with the committed fixture:

```bash
uv pip install -e packages/chromdata -e packages/uchrom-browser -e "packages/uchrom[web]"
python -m uchrom_browser packages/uchrom-browser/tests/fixtures/sim_cell1/sim_cell1.cdz
```

For an offline deterministic check (no Chrome, hosted Worker, or network), run:

```bash
cd packages/uchrom-browser
pytest tests/test_agent_e2e.py -q
```

The API-level test adapter uses the real `.cdz` store and a small SSE page handler, then verifies selection,
chromosome-clamped locus, Stats `chrom_scope="locus"`, Genome panes, revision readback and a
read-only capture. It does not automate the rendered Agent panel; Apply/Reject approval remains a
local WebUI action. See [`uchrom_browser/API.md`](uchrom_browser/API.md) for endpoint contracts.
