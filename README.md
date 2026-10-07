<p align="center"><img src="docs/source/_static/logo.svg" alt="U-Chrom" width="120"></p>

# U-Chrom

**Universal Chromatin** — one toolkit for 3-D genome data from sequencing and imaging.

Single-cell Hi-C, spatial Hi-C, bulk Hi-C, chromatin tracing and DNA seqFISH+ all describe where loci
sit relative to each other, cell by cell, but each comes with its own formats and tools.  U-Chrom
puts them in one data model and builds the analyses on it:

- **`ChromData` and the `.chromdata.zarr` store** — cells › traces › spots on a shared locus axis,
  with contact maps, RNA, chromatin marks, cell positions and outlines linked per cell; a store
  opens *backed*, from disk or over HTTP, and is read one cell or chromosome at a time.
- **Import** — 4DN FOF-CT, PyHiM, seqFISH+ multi-omics, `.pairs` / `.cool` / `.scool` / `.hic`.
- **Imaging** — spot-to-trace alignment and coordinate imputation.
- **3-D reconstruction** — NucDynamics and EMber (single cell), MDS and IGM population models
  (bulk), GEM-FISH (Hi-C + imaging), on a native engine (Rust; multi-core CPU and GPU).
- **Structures** — loops, TADs, per-allele domains and A/B compartments called from 3-D distances.
- **Features and embeddings** — distance maps, variance features, peaks; embeddings and clusters of
  cells from RNA, chromatin marks, accessibility and contact maps.
- **The web browser** — cells in their tissue, structures in 3-D, contact maps, tracks and
  embeddings, linked through the cells you select; scriptable from Python and by agents.
- **The data atlas** — public datasets as stores you open without downloading:
  [uchrom-atlas.u-science.org](https://uchrom-atlas.u-science.org), in the browser at
  [uchrom-browser.u-science.org](https://uchrom-browser.u-science.org).
- **Auto-discovery** — LLM agents that propose, run and check analyses on a dataset.

## Install

Python ≥ 3.11.  The packages are installed from this repository (not on PyPI yet):

```bash
git clone https://github.com/Nanguage/U-Chrom.git && cd U-Chrom
pip install -e packages/chromdata -e packages/uchrom      # data model + analysis library
pip install -e packages/uchrom-browser                     # web browser
pip install ./packages/uchrom-recon                         # native reconstruction engine (needs Rust)
```

or, with [uv](https://docs.astral.sh/uv/): `uv pip install -e "packages/uchrom[web,recon]"`.

## Quick start

```python
import uchrom as uc
import uchrom.datasets as ds

# a dataset of the atlas, read over HTTP: ~2 s to open 1,799 cells, then one cell on demand
cd = ds.load("takei2025_cerebellum")
cell = cd.get_cell(cd.cells.index[0])

# chromatin tracing (Takei 2021): TADs from 3-D distances
cd = ds.load("takei2021_mesc")                              # built once from the 4DN files
tads = uc.tl.call_tads(cd, chrom="chr3")
cd.write("takei2021.chromdata.zarr")

# single-cell Hi-C: embed cells by their contact maps (FastHigashi)
cd = ds.load("kim2020_scihic")                              # 1,931 cells, per-cell maps linked
uc.tl.embed_higashi(cd)                                     # -> cd.cellm["higashi"] (extra u-chrom[emb])

# single-cell Hi-C -> an ensemble of 3-D structures (EMber, native engine)
s = uc.tl.reconstruct_sc(ds.fetch("stevens2017") / "GSM2219497_Cell_1_contact_pairs.txt.gz", n_models=4)
```

```bash
python -m uchrom_browser takei2021.chromdata.zarr        # look at it
```

## Documentation

The documentation has a chapter per kind of data — chromatin tracing (reading, traces, imputation, structure
calling), imaging multi-omics (DNA seqFISH+), single-cell and spatial Hi-C (contact maps, 3-D structures, cell
embeddings), bulk Hi-C (MDS, IGM, GEM-FISH) — and chapters common to all data — data model & storage,
per-locus features, visualisation — each with tutorials on real data
(`docs/`, notebooks in `tutorials/`); online at [u-chrom-docs.u-science.org](https://u-chrom-docs.u-science.org).
Data come from the atlas or from their original sources (`python -m uchrom.datasets`), never from the
repository; where each dataset comes from: [`apps/atlas/recipes/README.md`](apps/atlas/recipes/README.md).

## Repository layout

| Folder | Package (import) | What it is |
|--------|------------------|------------|
| `packages/chromdata/` | `chromdata` | the data model: `ChromData` and the `.chromdata.zarr` store (numpy / pandas / zarr / pyarrow only); format spec in `spec.md` |
| `packages/uchrom/` | `u-chrom` (`uchrom`) | the analysis library: I/O, imaging, reconstruction, structures, features, embeddings, plots |
| `packages/uchrom-browser/` | `uchrom-browser` (`uchrom_browser`) | the web browser (needs `chromdata`, not `uchrom`) |
| `packages/uchrom-recon/` | `uchrom-recon` (`uchrom_recon`) | the native reconstruction engine: NucDynamics, EMber, IGM (Rust; LGPL-3.0) |
| `packages/uchrom-discovery/` | `uchrom-discovery` (`uchrom_discovery`) | LLM-driven auto-discovery on top of `uchrom` |
| `apps/` | — | the atlas (page, publishing, `recipes/` that build every dataset) and the hosted web browser |
| `benchmarks/`, `tutorials/`, `docs/` | — | figure benchmarks, tutorials, documentation |

Each package has its own tests (`cd packages/<package> && pytest tests`); see
`docs/source/reference/development.md`.

## License

See [`docs/source/reference/license.md`](docs/source/reference/license.md) (including third-party code).
