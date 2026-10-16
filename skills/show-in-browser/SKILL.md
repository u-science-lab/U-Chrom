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
| `select_cells(cells=[...], name=None)` | register + focus a group (like a lasso); returns `{"group": ref}` |
| `focus(cell=…)` / `focus(group=ref)` / `focus()` | focus / release |
| `set_locus(chrom, start, end)` | genomic window of Genome / Matrix / Stats views |
| `open_view(type, cells=…, rows=[…], stats=…, compare_groups=[…], field_x, field_y, embedding)` | new view; returns `{"pane": id}` |
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
stats = ws.open_view("stats", stats="rg", compare_groups=[g, "field:cell_type=Granule"])
ws.arrange(layout="grid")
```

## Checks
- Show what the answer claims: the views must use the same groups and locus as the numbers.
- Don't close or rearrange the researcher's existing views unless asked; add views.
- Name the pane ids in the answer so the researcher can find them.
- No browser open (`BrowserError: 409`/connection refused) → give the result without views and say so.
