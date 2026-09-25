# Interactive 3D browser

`python -m uchrom.browser` launches a PyVista + PyQt5 GUI for exploring
chromatin 3D structures.

```bash
python -m uchrom.browser out.h5cd       # ChromData
python -m uchrom.browser out.csv        # legacy CSV
python -m uchrom.browser                 # no args — shows welcome page
```

## Web version

The same browser also runs in a web page — no Qt required:

```bash
pip install "u-chrom[web]"
python -m uchrom.browser --web out.h5cd            # opens http://127.0.0.1:8765/
python -m uchrom.browser --web a.h5cd b.csv --port=9000 --noopen_browser
```

A local FastAPI server loads the files and streams coordinates to a
Three.js viewer in binary, one layer at a time, so only what is on screen
is transferred.  More files can be opened from the page (paths on the
machine running the server).  The HTTP API is documented in
`uchrom/browser/web/API.md`.

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

### Left sidebar vs right sidebar (inspector)

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

### Which cells a view shows

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

### Cell groups

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

### Themes

The ◐ menu at the right of the top bar switches the interface theme:
**System** (default; follows the OS light / dark setting), **Dark**,
**Light**, or **Paper** (light, with white views — for figures).  The
choice is remembered in the browser.  Canvases and the 3-D view follow the
theme: text, axes, grid, context cells, missing values and the PNG
background all switch.  Data colormaps (viridis, rainbow, the category
palettes) don't change; on light themes, dots and swatches get a thin
outline so pale colours stay visible.

### Matrix colour scales

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

### Saving a view as an image

The camera button in every pane header saves that pane's content as a PNG.
The file is `uchrom_<dataset>_<view>_<scope or locus>_<time>.png`, and the
header and hover tips are left out.

### Genome-coordinate views

Besides *3D* and *Embedding*, panes can show views along the genome.  They
share a **locus** (chromosome + range) set in the workspace bar — type
`chr7:20M-40M`, zoom with ± or *full*, or drag / zoom inside a view:

- **Genome** — a HiGlass-style stack of rows on one genomic axis (drag
  to pan, wheel to zoom, crosshair across rows):
  - *matrix rows*: a contact map or the 3-D distance matrix drawn as the
    upper triangle rotated 45° (adjustable height / max distance, flip);
    stack several to compare, e.g. two cell types' pseudo-bulk Hi-C, or a
    cell's contacts above its 3-D distances;
  - *track rows*: `cd.tracks` (e.g. Takei 2025's 59 per-spot IF channels:
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

### What each kind of data looks like

| Data | Example | Opens as |
|------|---------|----------|
| Imaging traces, many cells | Takei 2021 / 2025 (`example-data/takei2025_fov0/`) | 3D \| Embedding or 3D \| Genome |
| One simulated / reconstructed cell | `example-data/sim_cell1/` (NucDynamics + its contacts) | 3D \| Genome — its contacts above its 3-D distances |
| Single-cell multi-omics without 3-D | scHiCAR (`example-data/schicar_mop/`) | Matrix \| Embedding; the 3D pane says there are no coordinates |

Trace statistics, multi-canvas and sessions are desktop-only for now.

## Main areas

| Area | Purpose |
|------|---------|
| **Canvas** | 3D viewport, trackball rotation / pan / zoom |
| **Layers** panel | Per-canvas list of loaded structures; eye / rename / delete |
| **Operations tabs** | Chromosome / Region / Trace — subset into child layers |
| **Properties** | Style / colour / opacity / labels / Trace Statistics |

## Layers and subsetting

Loading a file creates a "root" layer.  Subsetting never mutates the
root — it spawns a **child layer** that remembers its parent.  You can
delete children freely without losing the original.

- **Chromosome Management** — shown when the root spans > 1 chromosome.
  Select a chromosome, pick a colour, "Create Subset".
- **Region Management** — always available when spots have `start`/`end`.
  Enter `start-end` within the displayed valid range for the chromosome.
- **Trace Management** — shown when `n_traces > n_chroms` (imaging
  data).  Select a single trace, a range `1-50`, or comma-separated IDs.

## Rendering

| Style | Notes |
|-------|-------|
| `line` | Fastest |
| `tube` | Best quality.  Enable "High quality" for 10× interpolation + 20-side tubes |
| `points` | Lightweight cloud |

Colour modes:

- `Rainbow` — per-chromosome colour (multi-chrom) or along-the-polymer
  rainbow (single chrom)
- `Custom` — single user colour
- `Per Trace` — each trace gets a distinct colour from `tab20`, useful
  for disentangling imaging data with many overlaid traces

Click a rendered trace to see its metadata (`trace_id`, `n_spots`,
chromosome, genomic region) in a small overlay label.

## Trace statistics

When Trace Management is visible, a `Trace Statistics` group appears
in the Properties panel:

- **Distance Matrix** — median pairwise distance across all traces on
  the current layer (`uchrom.fea.mean_distance_matrix` + Matplotlib
  heatmap).
- **Contact Map** — `uchrom.fea.contact_frequency` at a user-set
  distance threshold.
- **Rg Histogram** — per-trace radius of gyration distribution.
- **Split by Trace (N)** — tiles the first *N* traces into a
  roughly-square grid of canvases; cameras are synced so you can
  compare individual polymer shapes side by side.

## Multi-canvas mode

Menu → **Canvas → Add canvas (right/below)**.  Link cameras with
**Canvas → Link canvases** so they rotate together.

## Session save / load

**File → Save Session** writes a JSON capturing layer states, colour
maps, and camera positions.  **File → Load Session** restores them.
Imaging data paths are re-resolved if still valid; if not, the embedded
records are used.

## Known issues

- Some macOS builds of PyVista/VTK show spurious `IMKCFRunLoopWakeUp`
  warnings; they are cosmetic.
- The VisPy backend (historic) has been removed — PyVista is the only
  renderer.
