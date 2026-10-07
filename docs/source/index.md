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
import uchrom.datasets as ds
from chromdata import ChromData

cd = ChromData.from_fofct(ds.fetch("takei"))           # chromatin tracing (4DN FOF-CT), fetched once
tads = uc.tl.call_tads(cd, chrom="chr3")                # TADs from 3-D distances
cd.write("takei2021.chromdata.zarr")                    # one store, read in parts later
```

```bash
python -m uchrom_browser takei2021.chromdata.zarr       # look at it in the web browser
```

New here?  Start with [installation](start/install), the [quick start](start/quickstart) and the
[concepts](start/concepts) behind the data model.

## By data type

Each chapter takes one kind of data from its files to a `ChromData` and through what is specific to
it, with tutorials on real data.

| Data | What the chapter covers |
|------|-------------------------|
| [Chromatin tracing](tracing/index) | FOF-CT, PyHiM and other tables; raw detections into traces; filling missing loci |
| [Imaging multi-omics: DNA seqFISH+](seqfish/index) | DNA positions with chromatin marks, RNA and cell positions in the same cells |
| [Single-cell and spatial Hi-C](schic/index) | contacts per cell, linked contact maps, 3-D structures of single cells (NucDynamics, EMber), embeddings from contacts |
| [Bulk Hi-C](bulk/index) | contact maps to 3-D: one consensus structure (MDS), a population of structures (IGM), Hi-C with tracing (GEM-FISH) |

## Common to all data

| Chapter | What it covers | Package / module |
|---------|----------------|------------------|
| [Data model & storage](data/index) | `ChromData`, the `.chromdata.zarr` store, backed and remote reads, linked and embedded modalities | `chromdata` |
| [Structure calling](structures/index) | loops, TADs, domains per allele, A/B compartments from 3-D distances | `uchrom.strc` |
| [Per-locus features](features/index) | distance maps, variance features, signals and peaks along the genome | `uchrom.fea` |
| [Cells & embeddings](cells/index) | embeddings and clusters of cells from RNA, chromatin marks, accessibility and contacts | `uchrom.emb` |
| [Visualisation](viz/index) | the web browser, the data atlas, plots | `uchrom-browser`, `uchrom.pl` |

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
:caption: By data type
:maxdepth: 2
:hidden:

tracing/index
seqfish/index
schic/index
bulk/index
```

```{toctree}
:caption: Common to all data
:maxdepth: 2
:hidden:

data/index
structures/index
features/index
cells/index
viz/index
```

```{toctree}
:caption: Reference
:maxdepth: 1
:hidden:

reference/api/index
reference/formats
reference/format_spec
reference/data_sources
reference/design_2_0
reference/development
reference/changelog
reference/license
```
