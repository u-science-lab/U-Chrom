# The web browser

The web browser is the package `uchrom-browser` (`import uchrom_browser`).  It needs only the data
model, `chromdata`, not the analysis library; `u-chrom`'s `web` extra installs it.

```bash
pip install -e packages/chromdata -e packages/uchrom-browser   # from the repository (or: u-chrom[web])
python -m uchrom_browser out.chromdata.zarr                     # opens http://127.0.0.1:8765/
python -m uchrom_browser a.chromdata.zarr b.cdz --port=9000 --noopen_browser
uchrom-browser out.chromdata.zarr                               # the same, as a command
```

A local FastAPI server loads the files and streams coordinates to a
Three.js viewer in binary, one layer at a time, so only what is on screen
is transferred.  More files can be opened from the page (paths on the
machine running the server).  The HTTP API is documented in
`packages/uchrom-browser/uchrom_browser/API.md`.

Navigating imaging data with many cells:

- **Cells** (left) lists every cell.  Click one — or click a nucleus in
  the view — to focus it: the camera flies there, the cell is drawn in
  full (tubes by default) and the other cells fade into context.  `←` /
  `→` step through cells, `Esc` returns to all cells, and the *others*
  slider in the focus bar sets how faint the context is.
- **Chromosomes** (3-D inspector, right) is a legend and a visibility filter: click to
  show / hide, double-click to show only one.  Colours match the
  rainbow mode.
- Clicking a trace of the focused cell shows its trace, cell and bin.
- **Subset layer** (collapsed, 3-D inspector) still creates region / trace
  layers when you want to compare or keep a selection.

Multi-omics data (e.g. `ChromData.from_fofct(core, cell_table=…,
rna_table=…)`, see the ChromData guide):

- **Colour · all cells → Gene / Property** colours every cell by a
  numeric `cd.cells` column — **Gene** for RNA counts (`rna.Nanog`, …),
  **Property** for morphology (nuclear area, centroid, …), and one button
  per any other column prefix (`if.*` → *IF* for per-cell immunofluorescence /
  histone means, `atac.*` → *ATAC* for gene activity).  Pick the column in the
  search box (type to filter).  Colours use viridis with a colour bar
  (capped at the 99th percentile; grey = missing).
  The cell list then shows each cell's value and can sort by it.
- A focused cell shows a **Cell** panel: morphology and its RNA counts as
  bars; click a gene to colour all cells by it.
- **Points** draws `cd.points` sets (nascent RNA spots) as markers
  coloured by gene, with a legend to show / hide genes (double-click to
  show one) and a marker-size slider.  Other cells' points follow the
  *others* opacity; clicking a point shows its gene, cell and intensity.
- **Views are equal panes.**  The centre area is a workspace of views —
  *3D* and *Embedding* (2-D view of `cd.cellm` embeddings such as
  `rna_umap`, `rna_tsne`, `rna_pca` from `uchrom.emb.embed_cells`; any two
  PCs for PCA / LSI).  The Embedding picker groups them by modality —
  *RNA · UMAP*, *Histone/IF · UMAP*, *ATAC · UMAP* / *ATAC · LSI*,
  *Hi-C · UMAP*, *Published · UMAP* — from `uns["embeddings"][key]["modality"]`
  (or the key prefix).  Each pane's header picks its view type; its settings are in the
  inspector (right); **+ View** adds panes (e.g. two 3-D cameras, or UMAP next to
  PCA) and the workspace bar switches the layout: **Tabs**, **Columns**,
  **Rows** or **Grid** (drag the dividers; the arrangement is remembered
  in the browser).  Datasets with embeddings open as 3D | Embedding.
  Selection is shared: clicking a dot or a nucleus focuses that cell in
  every pane, and the focus bar (◀ cell ▶, *others* opacity) and colour
  scale are shared (focus bar, left sidebar), not in any one view.
- **Max bond** (Style) breaks polylines between consecutive spots farther
  apart than a threshold — by default 10× the median spacing.  Imaging
  traces contain duplicated loci and, in Takei 2021, per-chromosome
  "unassigned" traces (`…_-1`); without the cut these are drawn as long
  lines across the nucleus.  Isolated spots are still drawn.
- **Tubes vs lines.**  In the all-cells view a tube (≈0.1 µm across) is
  thinner than a pixel and thousands of traces exceed the tube budget, so
  the overview is always drawn with lines — the Style panel says so.
  Tubes (radius 0.35× the median spot spacing) appear once a cell is
  focused.

## Left sidebar vs right sidebar (inspector)

The two sidebars have fixed roles:

- **Left = shared by every open view** — the cell list (search, ↗),
  the focused cell's info (or the dataset summary) and *Colour · all
  cells* with its legend / colour bar.  Changing anything here affects
  all panes, in every layout (tabs, columns, rows, grid).
- **Right = inspector of the active pane** — click a pane to make it
  active (accent border); the inspector is titled after it
  (e.g. *Genome · pane 3*) and holds only that pane's settings:
  - *3D*: layers, subset layer, render style, chromosome legend, points;
  - *Genome*: one card per row (tracks, matrices, intervals) with all
    its settings;
  - *Matrix*, *Embedding*, *Stats*: their own controls.

Pane headers stay one line: view type, 📌 badge, maximise / close
(3-D views also have ⟲ reset camera).  The focus bar and locus navigator
above the panes are shared, like the left sidebar.

## Which cells a view shows

Every view has **one** *cells* setting at the top of the inspector.  Each
Genome row that depends on cells (tracks, the 3-D distance, per-cell
contact maps) has its own, next to the row's other settings.  The
setting always says what it shows *right now*, e.g. *Follow focus →
selection (10 cells)*, and every row's label on the canvas repeats it
(*All cells · 47*, *selection · 10 cells*, *cell 1_0_34*).

| Setting | Shows | Changes with focus / lasso? |
|---|---|---|
| **All cells** | every cell of the dataset | never |
| **Follow focus** (default for views) | the focused cell, else the focused group or lasso selection, else all cells | yes |
| **Cell…** | one cell (📌; a 3-D view draws only it) | no |
| **Group…** | a cell type, a saved group, or the current lasso selection | no |
| **Same as view** (default for rows) | whatever the view's setting shows | like the view |

When a lasso selection is picked as a group, it can be saved under a name
or **frozen** as an unnamed group, so that a new lasso doesn't change it.
When the cells are more than one, an **aggregate** control appears:
mean / median / max of the spots per bin for tracks, and median / mean
distance over the traces for the 3-D distance.  A per-cell contact map
over several cells is their pseudo-bulk (the sum of their maps).  Bulk
contact maps always hold all cells in the file.

Open a cell in a new view pinned to it with ↗ on its row in the cell list,
↗ *New view* in the focus bar, or the label shown when clicking a trace —
e.g. to compare two cells side by side while the overview stays.  Layouts
saved before this setting are migrated: a pinned cell or a group stays;
"focused cell only" unticked becomes *All cells*; ticked becomes *Same as
view*.

## Cell groups

Views can aggregate over a **group** of cells, not only over all cells or
one cell.  A group is either a category of a cell field (every
`cell_type`, cluster, … — one automatic group per value) or a cell list you
select yourself:

- **Groups** (left sidebar, shared by every view) lists the automatic
  groups, collapsed by field, and your saved groups.  Click a group to
  **focus** it — like focusing a cell.  Its cells are drawn in full in the
  3-D views and highlighted in the embeddings and the cell list, and the
  others fade.  Every view that follows the focus then aggregates over the
  group.  *All cells* / `Esc` releases it, and ↗ opens a new view scoped to
  it.
- **Lasso**: in an Embedding view, shift-drag (or turn on the ◌ lasso
  tool) around cells.  The selection is focused at once.  **Save as
  group** (in the view or the Groups panel) keeps it under a name, and you
  can rename (✎) or delete (×) it later.  Saved groups are remembered per
  dataset in the browser.
- **A view on a group** (*cells → Group…*, see above) shows its group
  whatever is focused, which makes side-by-side comparisons possible:
  - *3D*: the group's cells in full, the others faint;
  - *Genome* / *Matrix*: tracks and the 3-D distance matrix aggregated
    over the group's traces; a per-cell contact map (`.scool`) becomes the
    group's **pseudo-bulk** (the sum of its cells' maps);
  - *Stats*: Rg and distance-vs-separation over the group.
- **Per-row cells** (Genome inspector): each track, distance or per-cell
  matrix row can have its own setting.  Stack e.g. *Bergmann* above
  *Granule* on one axis, or keep an *All cells* row above a *Follow
  focus* row to see a selection against the whole population.
- **Compare groups** (Stats inspector): overlay several groups on the Rg
  histogram (as fractions of traces) or on the scaling curve, each in its
  colour.

On Takei 2025 cerebellum FOV 0, for example, the median trace Rg follows
nuclear size: Granule 1.16 µm (22 cells) < Bergmann 1.47 µm (8) < Purkinje
1.86 µm (3).  On scHiCAR MOp the pseudo-bulk of a subclass is identical
to that subclass's own `.cool` (coarsened to the same 1 Mb bins).

## Driving the browser from Python (and agents)

The open page can be driven from code with the same actions as its GUI — read what the researcher
selected, open and arrange views, capture a view:

```python
import uchrom_browser as ub

ws = ub.connect()                        # the running `python -m uchrom_browser …`
cells = ws.selected_cells()              # the researcher's lasso (or focused group / cell)
cd = ws.dataset()                        # the ChromData the browser has open
g = ws.select_cells(cells=cells)["group"]
ws.set_locus(chrom="chr15", start=3_000_000, end=33_000_000)
ws.open_view("genome", cells=g, rows=[{"kind": "track", "track": "H3K27ac"},
                                      {"kind": "distance", "cells": g},
                                      {"kind": "distance", "cells": "field:cell_type=Granule"}])
ws.open_view("stats", stats="rg", compare_groups=[g, "field:cell_type=Granule"])
ws.capture(path="rg.png")              # or rg.svg / rg.pdf: editable vectors (format= to override)
```

`ws.tools()` lists the actions (`describe_workspace`, `get_selection`, `select_cells`,
`list_groups`, `focus`, `set_locus`, `open_view`, `show_view`, `close_view`, `arrange`, `color_by`,
`capture_view`); they are defined in `packages/uchrom-browser/uchrom_browser/ui_tools.json`.  Coding agents use the
same client.  In browsers that support WebMCP (a W3C Community Group draft; Chrome behind a flag),
the page also registers these actions as tools (`uchrom_open_view`, …) for agents running in the
browser.  The HTTP side is documented under *Control* in `packages/uchrom-browser/uchrom_browser/API.md`.

## Themes

The ◐ menu at the right of the top bar switches the interface theme:
**System** (default; follows the OS light / dark setting), **Dark**,
**Light**, or **Paper** (light, with white views — for figures).  The
choice is remembered in the browser.  Canvases and the 3-D view follow the
theme: text, axes, grid, context cells, missing values and the PNG
background all switch.  Data colormaps (viridis, rainbow, the category
palettes) don't change; on light themes, dots and swatches get a thin
outline so pale colours stay visible.

## Matrix colour scales

Every matrix — each Genome matrix row, and the Matrix view — has its own
colour scale in the inspector:

- **Colormap**: fall (HiGlass; the default for contact maps), viridis
  (the default for distances), magma, inferno, Reds, YlOrRd, greys, or
  RdBu_r (diverging, for signed data).
- **Reverse**: distances are reversed by default, so near is bright.
- **Scale**: log (the default for contacts) or linear.
- **Range**: empty means automatic (99th-percentile clip, shown as the
  placeholder), or enter a min / max.

The colour bar on the canvas, and the PNG export, follow these settings.

## Saving a view as an image

The camera button in every pane header saves that pane's content as
**PNG** (pixels, as on screen), **SVG** or **PDF**.  The file is
`uchrom_<dataset>_<view>_<scope or locus>_<time>.<png|svg|pdf>`, and the
header and hover tips are left out.

SVG and PDF are editable vector graphics for Illustrator / Inkscape: the
2-D views (Matrix, Genome rows, Stats, Embedding, Spatial) are written by
the same drawing code as the screen, so axes, ticks, bars, track bars and
dots are shapes and all labels stay text.  Recurring styles are grouped
(e.g. one `<g>` per colour of a scatter plot) so a whole category can be
selected and restyled at once.  What stays as pixels: contact / distance
heat maps and section images (embedded PNGs, as heat maps usually are in
figures).  The 3-D view is projected with its camera: lines and points
become paths and circles, painted far to near; **tubes are approximated**
by round-capped strokes as wide as the tube on screen — without lighting,
and with straight bonds instead of the smoothed curve.  The PDF is the SVG
converted in the page (96 px = 72 pt); its text uses Helvetica, and
characters outside Latin-1 (e.g. 📌) are left out of it (`≥`, `…` are
spelled `>=`, `...`).  What an export approximates is shown in the status
bar and written in the SVG's `<desc>`.

## Genome-coordinate views

Besides *3D* and *Embedding*, panes can show views along the genome.  They
share a **locus** (chromosome + range) set in the workspace bar — type
`chr7:20M-40M`, zoom with ± or *full*, or drag / zoom inside a view:

- **Genome** — a HiGlass-style stack of rows on one genomic axis (drag
  to pan, wheel to zoom, crosshair across rows):
  - *matrix rows*: a contact map or the 3-D distance matrix drawn as the
    upper triangle rotated 45° (adjustable height / max distance, flip);
    stack several to compare, e.g. two cell types' pseudo-bulk Hi-C, or a
    cell's contacts above its 3-D distances;
  - *track rows*: `cd.bin_tracks` (per locus) and `cd.spot_tracks` (per spot; e.g. Takei 2025's 59 per-spot IF channels:
    H3K27ac, H3K4me3, H3K9me3, LaminB1, …) aggregated per bin over all
    cells, one cell or a group (the row's *cells* setting);
  - *interval rows*: `cd.results` tables (TADs as boxes, loops as arcs),
    with their boundaries echoed as guides across the matrix rows.
  Add / remove / reorder rows in the inspector (right); rows are remembered.
- **Matrix** — the full square version: a contact map from a linked `.cool` / `.mcool` / `.scool`
  (`cd.link_cool`, `cd.link_scool`; a per-cell map shows the view's cells —
  one cell's map, or the sum over a group / all cells)
  or the **3-D distance** matrix computed from `coords` (one trace, the
  cells in scope: median / mean distance or contact frequency).
  Large regions are pooled to ≤ 1,000 bins; drag a square to zoom.
- **Stats** — radius of gyration per trace, distance vs genomic
  distance (population with IQR band, focused cell on top), a histogram
  of a cell field, or a scatter of two cell fields (click to focus).

Cells can be coloured by numeric fields (genes, morphology) or by
categorical ones such as `cell_type`, with a legend.

## What each kind of data looks like

| Data | Example | Opens as |
|------|---------|----------|
| Imaging traces, many cells | Takei 2021 / 2025 (atlas `takei2025_cerebellum`) | 3D \| Embedding or 3D \| Genome |
| One simulated / reconstructed cell | atlas `stevens2017_mesc` (structures + their contacts) | 3D \| Genome — its contacts above its 3-D distances |
| Single-cell multi-omics without 3-D | atlas `schicar_mouse_cortex` | Matrix \| Embedding; the 3D pane says there are no coordinates |
