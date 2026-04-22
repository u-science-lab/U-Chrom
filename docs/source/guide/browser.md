# Interactive 3D browser

`python -m uchrom.browser` launches a PyVista + PyQt5 GUI for exploring
chromatin 3D structures.

```bash
python -m uchrom.browser out.h5cd       # ChromData
python -m uchrom.browser out.csv        # legacy CSV
python -m uchrom.browser                 # no args — shows welcome page
```

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
