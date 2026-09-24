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
- **Chromosomes** (right) is a legend and a visibility filter: click to
  show / hide, double-click to show only one.  Colours match the
  rainbow mode.
- Clicking a trace of the focused cell shows its trace, cell and bin.
- **Subset layer** (collapsed, bottom left) still creates region / trace
  layers when you want to compare or keep a selection.

Multi-omics data (e.g. `ChromData.from_fofct(core, cell_table=…,
rna_table=…)`, see the ChromData guide):

- **Colour · all cells → Gene / Property** colours every cell by a
  numeric `cd.cells` column — **Gene** for RNA counts (`rna.Nanog`, …),
  **Property** for morphology (nuclear area, centroid, …), and one button
  per any other column prefix (e.g. `if.*` → *IF*).  Pick the column in the
  search box (type to filter).  Colours use viridis with a colour bar
  (capped at the 99th percentile; grey = missing).
  The cell list then shows each cell's value and can sort by it.
- A focused cell shows a **Cell** panel: morphology and its RNA counts as
  bars; click a gene to colour all cells by it.
- **Points** draws `cd.points` sets (nascent RNA spots) as markers
  coloured by gene, with a legend to show / hide genes (double-click to
  show one) and a marker-size slider.  Other cells' points follow the
  *others* opacity; clicking a point shows its gene, cell and intensity.
- **Embedding** (viewport toolbar) opens a 2-D view of `cd.cellm`
  embeddings (e.g. `rna_umap`, `rna_tsne`, `rna_pca` from
  `uchrom.emb.embed_cells`; any two PCs for PCA).  Dots use the same
  colouring as the 3-D overview, the focused cell is ringed, and clicking
  a dot focuses that cell in 3-D.  The header switches the layout — **Float** (window over the 3-D view),
  **Tab** (full-size tab next to *3D*) or **Split** (side by side, drag the
  divider); the choice is remembered in the browser.
- **Max bond** (Style) breaks polylines between consecutive spots farther
  apart than a threshold — by default 10× the median spacing.  Imaging
  traces contain duplicated loci and, in Takei 2021, per-chromosome
  "unassigned" traces (`…_-1`); without the cut these are drawn as long
  lines across the nucleus.  Isolated spots are still drawn.

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
