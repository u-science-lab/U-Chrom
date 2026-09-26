---
name: show-in-browser
description: Read what the researcher selected in the U-Chrom web browser and show results there — select or focus cells, set the genomic locus, open Genome / Stats / Embedding / 3D / Matrix views scoped to groups, arrange and capture them. Use whenever a U-Chrom browser is open (python -m uchrom.browser --web) and a result should be seen, or the question refers to "these cells", "my selection", "what I'm looking at".
---

# Show results in the researcher's browser

The browser is visualization only; analysis stays in Python (`uchrom`). Drive the open page with
the Python client (or, for an agent inside the browser, the same actions as WebMCP tools
`uchrom_*`):

```python
import uchrom.browser as ub
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
| `capture(pane, path)` | save a PNG of a view; returns `{"path", "width", "height", "bytes"}` (never print image bytes) |

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
