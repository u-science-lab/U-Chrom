# Figure 1

Final figure: `fig1_final.pdf` / `fig1_final.png` (170 × 187 mm), legend in `legend.md`
(also used by `../manuscript/captions/fig1.tex`).

Rebuild:

    PYTHONPATH=<repo> python paper/fig1/make_fig1_final.py

Inputs:
- `_cache/` — small data extracts: the Takei 2025 cell `1_0_34` traces and IF, and the scHiCAR contact
  windows. Re-extract them from `example-data/` with `python paper/fig1/make_fig1.py --refresh`;
  the datasets are catalogued in `example-data/README.md`.
- `art3/a_flat_1.png` — the AI-generated conceptual illustration in panel a (`gen_image.py`, OpenRouter).
  Its Hi-C wall and floor tracks are repainted with real data by the script.
- `logos_ext/` — third-party logos with sources and usage terms in `SOURCES.md`;
  `_cache/logos/` holds their trimmed rasters.
- `logos/` — U-Chrom and ChromData logos (vector; `export_logos.py`).
- `refs/DESIGN_NOTES.md` — design survey of framework-paper figures; the reference images are not
  redistributed.

`make_fig1.py` is the first draft and provides `--refresh` for the data caches.
