---
name: show-in-browser
description: Only when a U-Chrom web browser is running or the user asks to show results in it — read the researcher's selection, open / arrange / capture views. Not for computing answers.
---

# Show results in the researcher's browser

The browser is visualization only; analysis stays in Python (`uchrom`). Choose the control transport in this order:

1. **MCP tools (`uchrom_*`)** — when connected via `uchrom-browser-mcp` / `uchrom-browser mcp` / `uchrom-web mcp` (stdio: includes session tools `uchrom_status` / `uchrom_list_pages` / `uchrom_bind_page` / `uchrom_wait_for_page` / `uchrom_batch`, `uchrom://` resources including `uchrom://pages`, and file-backed `uchrom_capture_view(path=...)`), or when running inside a WebMCP browser tab (exposes `ui_tools.json` actions directly; `uchrom_capture_view` returns base64 rather than writing files).
2. **Control CLI (`uchrom-web`, or `uchrom-browser ctl`)** — in terminal coding agents (Claude Code, Codex) without MCP config. Zero setup, compact JSON on stdout/stderr, semantic exit codes (`0` ok, `2` bad args, `3` unreachable/no tab, `4` multi-tab conflict or disconnected tab, `5` action/file error).
3. **Python client (`uchrom_browser.connect()`)** — inside Python scripts that already compute on `chromdata`/`uchrom` (`ws = ub.connect()`; use `ws.capture(path=...)` for file-backed figure exports and `page=...` when multiple tabs are open).

```bash
# Terminal / CLI path (zero Python boilerplate, pure stdlib)
uchrom-web doctor
uchrom-web pages
uchrom-web bind <page_id>                  # required when 2+ browser tabs are open
uchrom-web selection                       # read researcher's lassoed / focused cells
uchrom-web locus chr15:3000000-33000000
uchrom-web open stats --stats rg --chrom-scope locus --compare g123,field:cell_type=Granule
uchrom-web arrange grid
uchrom-web batch --steps-json '[{"action":"arrange","args":{"layout":"grid"}},{"action":"capture_view","args":{"path":"overview.svg"}}]'
uchrom-web capture --out fig.svg
```

```python
import uchrom_browser as ub
ws = ub.connect()                    # finds the running server; ub.connect("http://127.0.0.1:8765")
ws.describe()                        # dataset (path, cell fields, tracks, maps), views, focus, selection
cells = ws.selected_cells()          # what the researcher lassoed / focused ([] if nothing)
cd = ws.dataset()                    # the same ChromData, for analysis
```

## Actions (via `uchrom_<name>`, `uchrom-web call <name> --json '{...}'`, or `ws.<name>(**args)`; schema: `uchrom-web tools --schema <name>` / `ws.tools()`)
| action | use |
|---|---|
| `select_cells(cells=[...], name=None)` | register + focus a group (like a lasso); returns the canonical server-accepted cell ids, group ref, and counts |
| `focus(cell=…)` / `focus(group=ref)` / `focus()` | focus / release |
| `set_locus(chrom, start, end)` | genomic window of Genome / Matrix / Stats views |
| `open_view(type, cells=…, rows=[…], stats=…, chrom_scope="all"|"locus", compare_groups=[…], field_x, field_y, embedding)` | new view; returns `{"pane": id}` |
| `arrange(layout="grid")`, `show_view(pane)`, `close_view(pane)` | layout |
| `color_by(field)` | colour cells by a field |
| `capture_view` (`ws.capture(pane, path, format=None)`) | save PNG/SVG/PDF (`uchrom-browser-mcp` / `uchrom-web capture --out` refuse overwriting, `..`, and symlinks; `ws.capture` writes to `path` or a temp file directly; WebMCP returns base64) |

Group references: the `group` returned by `select_cells`, `field:<column>=<value>`, or `all`.
Genome rows: `{"kind": "track", "track": "H3K27ac", "cells": ref}`, `{"kind": "distance", "cells": ref}`,
`{"kind": "contacts", "source": key, "cells": ref}`, `{"kind": "intervals", "key": "tads"}`.

## Multi-tab & readiness checks
- If 2+ browser tabs are connected, NEVER guess: pass explicit `page` / `--page` or bind once (`uchrom_bind_page` / `uchrom-web bind <page_id>`). If a bound tab closes, rebind or unbind explicitly instead of silently falling back to another tab.
- When you just started `uchrom-browser`, call `uchrom_wait_for_page` / `uchrom-web wait` to wait for the browser tab to attach.

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
- No browser open (`BrowserError: 409`, exit code `3`, or `uchrom_status` empty `pages`) → give the result without views and say so.
