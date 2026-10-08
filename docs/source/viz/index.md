# Visualisation

The **web browser** (package `uchrom-browser`) shows a `ChromData` the way the data were taken:
cells in their tissue, structures in 3-D, contact maps, genome tracks and embeddings — linked
through the cells you select.  It opens stores backed, from a disk or over HTTP, and can be driven
from Python (and by coding agents) with the same actions as its interface.  The **data atlas** is a
public collection of stores you can open in it without downloading anything.  `uchrom.pl` draws the
standard figures with matplotlib.

| Task | API |
|------|-----|
| open the web browser on stores | `python -m uchrom_browser x.chromdata.zarr` (or `uchrom-browser`) |
| drive it from Python | `uchrom_browser.connect()` → `Workspace` (`selected_cells`, `open_view`, `capture`, ...) |
| browse the atlas | the Open dialog; `https://uchrom-browser.u-science.org` (hosted); [datasets & the atlas](../datasets/browse) |
| plots | `uchrom.pl.plot_distance_matrix`, `plot_contact_map`, `plot_rg_histogram`, `plot_structure_3d` |

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/plotting_and_browser
```

## Guides

```{toctree}
:maxdepth: 1

browser
atlas
```

API: [uchrom-browser](../reference/api/browser), [uchrom.pl](../reference/api/pl).
