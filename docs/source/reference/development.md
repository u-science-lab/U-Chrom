# Contributing

U-Chrom wants to be common ground for 3-D genome analysis: one data model for chromatin tracing, imaging
multi-omics, single-cell, spatial and bulk Hi-C, with the field's methods built on it.  A method written once on a
`ChromData` runs on every dataset of the [atlas](../datasets/index.md), on disk or over HTTP, and its results show in
the web browser — so one contribution reaches every assay the method applies to.  Methods, readers for new formats,
datasets, tutorials, browser views, agent skills and bug reports are all welcome.

This page says what we look for, which methods exist and which are wanted, where code goes, and how it is tested
and reviewed.

## Ways to contribute

| You want to… | Start with |
|---|---|
| report a bug or ask a question | an [issue](https://github.com/u-science-lab/U-Chrom/issues) with a minimal example; a dataset of `uchrom.datasets` (e.g. `ds.load("takei2021_mesc")`) lets anyone reproduce it |
| add a method | a [method proposal](https://github.com/u-science-lab/U-Chrom/issues/new?template=method.md) naming the paper, its benchmark data, the authors' code and its licence; we agree on the module and on how it will be checked before you write the code |
| read or write a format | a reader in `uchrom.io` that returns a `ChromData`, tested on a small real file |
| add a dataset to the atlas | a recipe in `apps/atlas/recipes/` and its entry in the recipes' README (source, licence, size) |
| write a tutorial | a notebook in `tutorials/` that runs end to end on real data |
| improve the web browser | `packages/uchrom-browser` (FastAPI server, React / Three.js front end) |
| teach agents a workflow | a skill in `skills/` |

Small fixes — typos, docs, a failing edge case — can go straight to a pull request.

## What we look for

1. **A method takes a `ChromData`.**  It reads what it needs from the object — coordinates, the contact maps linked
   to it (`cd.linked_scool_path`, `uchrom.fea.read_band`), the cell table — and stores its result there with
   provenance (`cd.results`, `cd.intervals`, `cd.bin_tracks`).  No file paths in, no private containers out.  If the
   data model lacks something a method needs, the change goes into `chromdata`; open an issue first, since the store
   format is versioned.
2. **A re-implementation gives the authors' results.**  It is checked against the authors' code on the data of their
   paper, and the numbers go into the pull request: identical calls, the largest relative difference, the run time.
   Where it departs from that code on purpose (a bug, a faster formulation), the docstring says so and the pull
   request measures the difference.  The callers marked ✓ below were checked this way.
3. **Real data, registered.**  Synthetic tests check correctness; the paper's benchmark data check the port, and
   both are needed.  Every dataset a test, tutorial or check uses is registered (`uchrom.datasets`,
   `apps/atlas/recipes/`) and documented in the same pull request.  Nothing downloads silently, no input is
   fabricated to make a pipeline run, and no data are committed except the small fixtures of the tests.
4. **One question, every assay.**  Where the biology allows, a method runs on traces and on contact maps: a domain
   caller on 3-D distances and on a Hi-C map, a per-cell feature from contacts and from coordinates
   (`uchrom.fea.separation_profile` does both).  Reuse the shared building blocks — distance maps, banded reads,
   pseudo-bulk maps, imputation — rather than writing another.
5. **It scales.**  Stores open backed, also over HTTP: read one cell, trace or chromosome at a time (`iter_cells`,
   `get_chrom`, `read_band`), stay within `uchrom.settings.memory_budget`, and never build a dense genome-wide
   matrix.  Tight loops of many cheap steps go to the Rust crates (`uchrom-maps`, `uchrom-recon`); the NumPy code
   stays as the reference they are tested against and the fallback when they are not installed.
6. **Licences are respected.**  The core is MIT: implement from the paper rather than copying GPL or unlicensed
   code, wrap an external tool as an optional extra instead of vendoring it, and add the source to the
   [license notes](license.md).
7. **Dependencies stay light.**  `chromdata` needs NumPy, pandas, Zarr and PyArrow only.  Anything heavier is an
   extra, imported lazily, with tests that skip without it.

## Methods: what exists and what is wanted

✓ = checked against the authors' code (or the reference tool) on their data: Supplementary Table 3 of the U-Chrom
paper, with the scripts in
[uchrom-reproducibility/supp_table3](https://github.com/u-science-lab/uchrom-reproducibility/tree/main/supp_table3).
The *Wanted* column lists gaps we know of, not a limit: other methods are welcome — open a proposal.

**Imaging: chromatin tracing, DNA seqFISH+**

| Step | In U-Chrom | Wanted |
|---|---|---|
| Read / write | FOF-CT (both ways), PyHiM, SnapFISH, Bintu et al. 2018, Su et al. 2020, DNA seqFISH+ detections and multi-omics tables (`uchrom.io`) | outputs of other tracing pipelines that are not FOF-CT |
| Images → spots | — (U-Chrom starts from spot tables) | spot detection and fitting, drift and chromatic-aberration correction, or readers of the tools that do them |
| Spots → traces | Jie aligner (`uc.pp.align_spots`; checked against the deposited homolog assignment of Takei et al. 2021) | other aligners; homolog separation in densely labelled genome-wide data |
| Missing loci | linear, grid, SnapFISH-IMPUTE (`uc.pp.impute`) | model-based imputation |
| Domains | ArcFISH ✓, FISHnet per allele (`uc.tl.call_tads`) | single-trace domain boundaries (Bintu et al. 2018), hierarchical domains |
| Loops | ArcFISH axis-wise F test ✓ (`uc.tl.call_loops`) | SnapFISH loop calling |
| Compartments | ArcFISH axes PC ✓ (`uc.tl.call_compartments`) | — |
| Conformations | — | clustering of single traces into states, trace embeddings |

**Single-cell and spatial Hi-C**

| Step | In U-Chrom | Wanted |
|---|---|---|
| Contacts | `.pairs` → per-cell `.scool` (`uchrom.io.pairs_to_scool`); phased contacts (hickit `.pairs`, Dip-C `.con`); per-cell statistics: P(s), cis / trans, short / long ratio ✓ | haplotype imputation (as `hickit -u`) |
| Imputation | random walk with restart and z-scores as SnapHiC computes them ✓ (`uchrom.fea.impute_maps`, with a Rust kernel); scHiCluster's ✓ (`uchrom.emb.hic`) | Higashi's hypergraph imputation |
| Embeddings | scHiCluster ✓, FastHigashi (wrapped) (`uc.tl.embed_contacts`, `embed_higashi`) | BandNorm, scVI-3D |
| Structures in single cells | scA/B compartments ✓, boundaries of imputed maps, SnapHiC loops ✓ (`uc.tl.single_cell_compartments`, `single_cell_boundaries`, `call_loops(method="snaphic")`); pseudo-bulk maps per group | differential loops between cell types (SnapHiC-D) |
| 3-D structures | NucDynamics ✓ and EMber on the native engine (`uc.tl.reconstruct_sc`); Dip-C `.3dg` structures read | hickit / Dip-C reconstruction; other single-cell methods, compared on the same cells |
| In the tissue | neighbour graphs, Moran's I and Geary's C ✓, SPARK-X ✓, destriping of DBiT arrays, spatially variable 3-D features (`uchrom.spatial`) | deconvolution of spot maps into cell types; spatial domains from 3-D features |
| With RNA and other modalities | highly variable genes, RNA / ATAC / mark embeddings, clustering (`uc.tl.embed_cells`, `cluster_cells`) | label transfer between single-cell Hi-C and scRNA-seq; joint embeddings |

**Bulk Hi-C**

| Step | In U-Chrom | Wanted |
|---|---|---|
| Maps | ICE, observed / expected, cis expected, banded reads, rebinning, depth thinning, pileups (APA) (`uchrom.fea`) | — |
| Compartments | cis eigenvector ✓, saddle strength ✓, PC1 on uneven loci (`uc.tl.call_compartments`) | sub-compartments (Calder, SNIPER) |
| TADs | insulation ✓, directionality index (`uc.tl.call_tads`) | Arrowhead, TopDom, hierarchical callers (OnTAD) |
| Loops | HiCCUPS ✓, Mustache ✓, both with Rust kernels (`uc.tl.call_loops`) | Peakachu, Chromosight (also stripes) |
| Differential | — | contacts, boundaries and loops between conditions with replicates (e.g. multiHiCcompare, CHESS, diffHic) |
| 3-D structures | MDS, IGM populations, GEM-FISH with imaging (`uc.tl.reconstruct_bulk`, `uchrom.recon.bulk.deconv`) | other consensus and population methods (PASTIS, Chrom3D) |

**Across assays**

| Step | In U-Chrom | Wanted |
|---|---|---|
| Features | 3-D distance maps, radius of gyration, radial position, separation profiles from contacts and distances alike, per-cell strength of known boundaries and loops, GC / CpG, GTF annotation, MACS-style peaks (`uchrom.fea`) | — |
| Comparisons | structures against imaging and contacts (distance correlation, RMSD, contact agreement); boundary and loop agreement (`uchrom.fea.compare`, `uchrom.strc`) | group comparisons with the cell as the unit in the library (today a script of `skills/compare-groups`) |
| Plots | contact maps, distance matrices, tissue sections, 3-D tubes (`uchrom.pl`); every view of the web browser | — |

## Where code goes

```
packages/
├── chromdata/          the data model and the store (cdata.py, zarrcd.py; layout in spec.md)
├── uchrom/             the analysis library u-chrom (uchrom/, tests/)
├── uchrom-browser/     the web browser (uchrom_browser/ with frontend/ and the built static/, tests/)
├── uchrom-recon/       the native reconstruction engine (Rust: src/, tests/; Python: python/uchrom_recon)
├── uchrom-maps/        native kernels of the Hi-C map callers (Rust)
└── uchrom-discovery/   auto-discovery (uchrom_discovery/, tests/)
apps/
├── atlas/              the atlas page, thumbnails, publishing; recipes/ builds every dataset from its sources
└── hosted-browser/     the public web browser (Cloudflare Worker + container)
tutorials/              the tutorial notebooks (executed; docs/source/tutorials links to them)
skills/                 agent skills
docs/                   this documentation (Sphinx + MyST)
```

| You add… | It goes to | And also |
|---|---|---|
| a field of the data model, a change to the store | `packages/chromdata` | an issue first; `spec.md`; a format version bump |
| a reader or writer | `uchrom/io/` | a fixture and a test; [file formats](formats.md) |
| imaging preprocessing | `uchrom/im/` | an alias in `uc.pp` |
| a structure caller | `uchrom/strc/{tad,loop,comp}/<method>.py` | a `method=` entry of `uc.tl.call_tads` / `call_loops` / `call_compartments` |
| a feature or a map operation | `uchrom/fea/` | |
| an embedding, clustering or metric | `uchrom/emb/` | |
| a 3-D reconstruction | `uchrom/recon/{sc,bulk,fish}/` | a `method=` entry of `uc.tl.reconstruct_sc` / `reconstruct_bulk` |
| spatial statistics | `uchrom/spatial/` | |
| a plot | `uchrom/pl/` | |
| a native kernel | `packages/uchrom-maps` (map callers) or `packages/uchrom-recon` (reconstruction) | the NumPy reference, a test that both give the same results, a lazy import with fallback |
| a view of the web browser | `packages/uchrom-browser` | `API.md`, the rebuilt `static/` |
| a dataset | `uchrom/datasets/_sources.py` (original files) or a loader `_load_<area>.py`; atlas stores by a recipe | `apps/atlas/recipes/README.md` |
| an agent workflow | `skills/<name>/` | a test in `packages/uchrom/tests/skills/` |

Dependencies point one way: `chromdata` ← `uchrom-browser`; `chromdata` ← `uchrom` ← `uchrom-discovery`.
`chromdata` and `uchrom-browser` never import `uchrom` (their `tests/test_standalone.py` check it), `uchrom` never
imports `uchrom-discovery`, and the native crates never import `uchrom`.

## Anatomy of a method

Every analysis function follows one calling convention (`uchrom/convention.py`), so the same keywords work across
the library and `uc.tl` can dispatch on `method=`:

```python
"""<Method>: <what it calls>.

<Authors> <year>, *Journal* <volume>:<page> (doi:...), as <the authors' package, version> computes it.
What differs from that code, and why.
"""

from dataclasses import dataclass

from uchrom.convention import merge_tables, resolve_chroms, select_spots, selection_inputs, store_and_return


@dataclass
class MethodParams:
    window_bp: int = 100_000        # the paper's defaults


def call_tads_method(cd, *, chrom=None, trace_ids=None, cells=None, params=None,
                     key_added="tads.method", copy=False):
    """<One line>.  Parameters / Returns in numpydoc."""
    params = params or MethodParams()
    work = select_spots(cd, trace_ids=trace_ids, cells=cells)
    chroms = resolve_chroms(work, chrom)                       # chrom=None: every chromosome
    table = merge_tables([_one_chrom(work, c, params) for c in chroms], _empty_table())
    return store_and_return(                                   # copy=False: the table; True: a new ChromData
        cd, table, key_added=key_added, copy=copy, kind="intervals", interval_kind="domain",
        function="uchrom.strc.tad.call_tads_method", params=params,
        inputs=selection_inputs(work, chroms, trace_ids, cells))
```

- `chrom=None` runs every chromosome and merges the results into one table under one key.
- `key_added` is `"<what>.<method>"` (`tads.insulation`, `loops.hiccups`); `None` stores nothing.
- A method on contact maps takes `contacts=<key of the linked map>` instead of reading a path.
- The docstring cites the paper and the code the method follows; `docs/source/reference/api/<module>.rst` lists the
  function, and the module's docs chapter gets a sentence and, for a new kind of analysis, a tutorial.

## Install for development

```bash
git clone https://github.com/u-science-lab/U-Chrom.git && cd U-Chrom
uv pip install -e "packages/uchrom[web,recon]" -e packages/uchrom-discovery   # uv finds the siblings itself
# or with pip:
pip install -e "packages/chromdata[all]" -e "packages/uchrom-browser[test]" -e packages/uchrom \
            -e packages/uchrom-discovery
pip install ./packages/uchrom-recon          # Rust toolchain; or: cd packages/uchrom-recon && maturin develop --release
pip install ./packages/uchrom-maps           # optional: the native map kernels
```

## Tests

Each package has its own `tests` package; run each from its folder:

```bash
(cd packages/uchrom && pytest tests)
(cd packages/chromdata && pytest tests)
(cd packages/uchrom-browser && pytest tests)
(cd packages/uchrom-discovery && pytest tests)
(cd apps/atlas && pytest tests)
(cd packages/uchrom-recon && cargo test --release)               # add --features gpu for the GPU backend
(cd packages/uchrom-maps && cargo test --release)
(cd packages/uchrom-browser/uchrom_browser/frontend && npm test)  # the front end (vitest)
```

A test goes to the package whose code it tests, next to the module (`tests/strc/test_insulation.py` for
`uchrom/strc/tad/insulation.py`).  A new method brings:

- **known answers** on small synthetic inputs, with the edge cases: an empty chromosome, missing loci, one trace,
  one cell;
- **the reference** on a small real fixture: the output of the authors' code, computed once and written into the
  test, so it runs without that code installed (`test_real_map_matches_cooltools` in `tests/strc/test_insulation.py`
  does this);
- **the convention**: `chrom=None` equals the chromosomes one by one, `copy=True` leaves `cd` unchanged, the result
  is stored with its parameters, and a backed store gives what the in-memory object gives.

Fixtures are small real files in the package's `tests/fixtures/` (a few hundred kB, at most about 1 MB), each with
its source and licence in `fixtures/README.md`.  Shared fixtures (an object with every attribute, a store with
linked and embedded maps, a folder atlas, an HTTP server with range requests, store comparisons) are in
`chromdata.testing`.  Each suite's `tests/__init__.py` defines `FIXTURES`, `DATA_DIR` (the data directory) and
`REPO`; a test that needs a large dataset reads it from `DATA_DIR`, is marked `slow` and skips without it.  Optional
dependencies are `pytest.importorskip`-ed; `gpu` marks tests that need CUDA or MPS.  CI runs
`pytest -m "not slow and not gpu"` on Python 3.11 and 3.12, the native engine's tests on Linux and macOS and the
front end's tests, and checks that the committed `static/` matches a fresh build.

The full comparison with the authors' code on their paper's data is usually too heavy for a unit test: run it
outside the repository and put the script's numbers in the pull request.

## Pull requests

- Branch from `main`; one topic per pull request.
- Commit messages start with the package or area: `chromdata: …`, `strc: …`, `browser: …`, `docs: …`.
- Add a line to the *Unreleased* section of the [changelog](changelog.md); say "(behaviour change)" when results of
  an existing function change.
- The description says what changed, how it was checked and the real-data numbers, also when they disappoint.
- Tests pass locally and in CI; a changed tutorial is re-executed; the docs build without new warnings.

## The web browser's front end

The React / Three.js app is `packages/uchrom-browser/uchrom_browser/frontend`; it is built into
`uchrom_browser/static`, which is committed (users need no Node):

```bash
cd packages/uchrom-browser/uchrom_browser/frontend
npm install && npm test && npm run build
```

Keep `uchrom_browser/API.md` in sync with `server.py` / `data.py`.

## Tutorials and docs

Tutorials are Jupyter notebooks in `tutorials/`, committed **executed**: they run end to end on real data (from the
atlas or fetched with `uchrom.datasets`; see [datasets](../datasets/index.md)), and the docs build only renders them.
After changing a tutorial, re-run it from the repository root:

```bash
jupyter nbconvert --to notebook --execute --inplace tutorials/<name>.ipynb
```

A new tutorial gets a link in `docs/source/tutorials/`, an entry in its chapter's `index.md` and a card in the
gallery (`docs/source/gallery.md`).  Build the docs:

```bash
pip install -r docs/requirements.txt
sphinx-build -b html docs/source docs/build/html
```

## Data

Every dataset a tutorial, test or check uses is registered in `uchrom.datasets`
(`packages/uchrom/uchrom/datasets/_sources.py`: source URL, md5) or built by a recipe in `apps/atlas/recipes/`, and
documented in `apps/atlas/recipes/README.md` (size, source, licence, users).  Original files come from their
sources — never re-host someone else's raw data — and are cached in the data directory (`$UCHROM_DATA`, default
`~/.cache/uchrom`).  Analyses and tutorials start from `uchrom.datasets.load(name)`.
