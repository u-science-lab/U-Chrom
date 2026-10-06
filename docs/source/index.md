# U-Chrom

**U**niversal **Chrom**atin: one toolkit for 3-D genome data from sequencing and imaging.

Single-cell Hi-C, spatial Hi-C, bulk Hi-C, chromatin tracing and DNA seqFISH+ all describe the
same thing — where loci sit relative to each other, cell by cell — yet each comes with its own
formats and tools.  U-Chrom puts them in one data model, `ChromData` (cells › traces › spots on a
shared locus axis, with contact maps, RNA, chromatin marks and cell positions linked per cell), and
builds the analyses on it: import, 3-D reconstruction, structure calling, per-locus features,
single-cell embeddings, an interactive web browser and an open data atlas.

```python
import uchrom as uc
from chromdata import ChromData

cd = ChromData.from_fofct("4DNFIHF3JCBY.csv")          # chromatin tracing (4DN FOF-CT)
tads = uc.tl.call_tads(cd, chrom="chr3")                # TADs from 3-D distances
cd.write("takei2021.chromdata.zarr")                    # one store, read in parts later
```

```bash
python -m uchrom_browser takei2021.chromdata.zarr       # look at it in the web browser
```

## The chapters

Each chapter introduces one part of the toolkit and shows it at work in tutorials on real data.

| Chapter | What it covers | Package / module |
|---------|----------------|------------------|
| [Data model & storage](data/index) | `ChromData`, the `.chromdata.zarr` store, backed and remote reads, linked and embedded modalities | `chromdata` |
| [Importing data](io/index) | 4DN FOF-CT, PyHiM, seqFISH+ multi-omics, Hi-C contacts (`.pairs`, `.cool`, `.scool`, `.hic`) | `uchrom.io` |
| [Imaging: tracing & imputation](imaging/index) | spot-to-trace alignment, filling missing loci | `uchrom.im` |
| [3-D reconstruction](recon/index) | single-cell NucDynamics and EMber, bulk MDS, IGM population models, GEM-FISH | `uchrom.recon`, `uchrom-recon` |
| [Structure calling](structures/index) | loops, TADs, domains per allele, A/B compartments | `uchrom.strc` |
| [Per-locus features](features/index) | distance maps, variance features, peaks, interval projections | `uchrom.fea` |
| [Cells & embeddings](cells/index) | embeddings and clusters from RNA, chromatin marks and contacts | `uchrom.emb` |
| [Visualisation](viz/index) | the web browser, the data atlas, plots | `uchrom-browser`, `uchrom.pl` |
| [Auto-discovery](discovery/index) | LLM agents that propose, run and check analyses on a `ChromData` | `uchrom-discovery` |

New here?  Start with [installation](start/install), the [quick start](start/quickstart) and the
[concepts](start/concepts) behind the data model.

```{toctree}
:caption: Getting started
:maxdepth: 1
:hidden:

start/install
start/quickstart
start/concepts
start/datasets
```

```{toctree}
:caption: Chapters
:maxdepth: 2
:hidden:

data/index
io/index
imaging/index
recon/index
structures/index
features/index
cells/index
viz/index
discovery/index
```

```{toctree}
:caption: Reference
:maxdepth: 1
:hidden:

reference/api/index
reference/format_spec
reference/data_sources
reference/design_2_0
reference/development
reference/changelog
reference/license
```
