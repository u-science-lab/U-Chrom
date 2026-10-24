---
name: show-in-browser
description: Only when a U-Chrom web browser is running or the user asks to show results in it — read the researcher's selection, open / arrange / capture views. Not for computing answers.
---

# Show results in the researcher's browser

The browser is visualization only; analysis stays in Python (`uchrom`). Drive the open page with
the Python client (or, for an agent inside the browser, the same actions as WebMCP tools
`uchrom_*`):

```python
import uchrom_browser as ub
ws = ub.connect()                    # finds the running server; ub.connect("http://127.0.0.1:8765")
ws.describe()                        # dataset (path, cell fields, tracks, maps), views, focus, selection
cells = ws.selected_cells()          # what the researcher lassoed / focused ([] if nothing)
cd = ws.dataset()                    # the same ChromData, for analysis
```

## Actions (all via `ws.<name>(**args)`; full schema: `ws.tools()`)
| action | use |
|---|---|
| `select_cells(cells=[...], name=None)` | register + focus a group (like a lasso); returns the canonical server-accepted cell ids, group ref, and counts |
| `focus(cell=…)` / `focus(group=ref)` / `focus()` | focus / release |
| `set_locus(chrom, start, end)` | genomic window of Genome / Matrix / Stats views |
| `open_view(type, cells=…, rows=[…], stats=…, chrom_scope="all"|"locus", compare_groups=[…], field_x, field_y, embedding)` | new view; returns `{"pane": id}` |
| `arrange(layout="grid")`, `show_view(pane)`, `close_view(pane)` | layout |
| `color_by(field)` | colour cells by a field |
| `capture(pane, path, format=None)` | save a view as PNG, SVG or PDF (format from the suffix of `path`, else `format`, else PNG; SVG / PDF are editable vectors); returns `{"path", "format", "width", "height", "bytes", "notes"}` (never print image bytes) |

Group references: the `group` returned by `select_cells`, `field:<column>=<value>`, or `all`.
Genome rows: `{"kind": "track", "track": "H3K27ac", "cells": ref}`, `{"kind": "distance", "cells": ref}`,
`{"kind": "contacts", "source": key, "cells": ref}`, `{"kind": "intervals", "key": "tads"}`.

## Recipe: show a two-group comparison
```python
g = ws.select_cells(cells=cells)["group"]
ws.set_locus(chrom="chr15", start=3_000_000, end=33_000_000)
genome = ws.open_view("genome", cells=g, rows=[{"kind": "track", "track": "H3K27ac"},
                                              {"kind": "distance", "cells": g},
                                              {"kind": "distance", "cells": "field:cell_type=Granule"}])
stats = ws.open_view("stats", stats="rg", chrom_scope="locus", compare_groups=[g, "field:cell_type=Granule"])
ws.arrange(layout="grid")
```

## Checks
- `chrom_scope="locus"` makes Rg / scaling use the current locus chromosome; it still summarizes that whole chromosome, not just the locus start/end interval. The default `"all"` includes every chromosome.
- Show what the answer claims: the views must use the same groups and chromosome scope as the numbers.
- Don't close or rearrange the researcher's existing views unless asked; add views.
- Name the pane ids in the answer so the researcher can find them.
- No browser open (`BrowserError: 409`/connection refused) → give the result without views and say so.

## Local agent loop

When the browser is running locally, an agent may read and propose UI changes while the researcher
keeps approval in the WebUI:

```python
import uchrom_browser as ub

ws = ub.connect()
page = ws.agent_pages()[0]["page"]       # choose and pin explicitly
snapshot = ws.agent_snapshot(page=page)   # page canonical state + state_revision
plan = ws.propose_ui_changes(
    [
        {"name": "set_locus", "args": {"chrom": "chr15", "start": 0, "end": 200_000_000}},
        {"name": "open_view", "args": {"type": "stats", "stats": "rg", "chrom_scope": "locus"}},
    ],
    page=page,
    expected_revision=snapshot["state_revision"],
)
print(plan["plan_id"], plan["status"])  # pending; the user applies/rejects in the Agent panel
```

Before running this flow, pin the selected page with the **Pin** button in the WebUI Agent panel.
The plan is bound to the explicit page and revision. If the researcher changes the page first, the
plan becomes stale and must be proposed again from a fresh `agent_snapshot`. `capture()` remains a
read-only page action and does not create or apply an agent plan. This loop is local and process
scoped; only the local WebUI Apply/Reject buttons are the supported approval path. Agents should not
call the `/api/agent/plans/{plan_id}/approve`, `/reject` or `/apply` endpoints directly. The test
suite uses those endpoints only to simulate the WebUI buttons in a deterministic API-level test;
it does not automate or verify the rendered UI. This feature does not provide hosted handoff or
arbitrary code execution. A reproducible real-data check is:

```bash
uv pip install -e packages/chromdata -e packages/uchrom-browser -e "packages/uchrom[web]"
python -m uchrom_browser packages/uchrom-browser/tests/fixtures/sim_cell1/sim_cell1.cdz
cd packages/uchrom-browser && pytest tests/test_agent_e2e.py -q
```
