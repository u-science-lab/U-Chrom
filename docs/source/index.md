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

cd = ds.load("takei2021_mesc")                          # chromatin tracing (4DN FOF-CT), built once
tads = uc.tl.call_tads(cd, chrom="chr3")                # TADs from 3-D distances
cd.write("takei2021.chromdata.zarr")                    # one store, read in parts later
```

```bash
python -m uchrom_browser takei2021.chromdata.zarr       # look at it in the web browser
```

New here?  Start with [installation](start/install), the [quick start](start/quickstart) and the
[concepts](start/concepts) behind the data model — or browse every tutorial in the [gallery](gallery).

## By data type

Each chapter takes one kind of data from its files to a `ChromData` and through the analyses made for it,
step by step, with tutorials on real data.

| Data | Steps |
|------|-------|
| [Chromatin tracing](tracing/index) | [reading tracing data](tracing/reading) · [from detections to traces](tracing/traces) · [filling missing loci](tracing/imputation) · [calling structures](tracing/structures): loops, TADs, domains, compartments |
| [Imaging multi-omics: DNA seqFISH+](seqfish/index) | [reading the data](seqfish/reading) · [marks, cells and tissue](seqfish/marks) |
| [Single-cell and spatial Hi-C](schic/index) | [contact maps per cell](schic/contacts) · [pseudo-bulk maps](schic/pseudobulk) · [structures from single cells](schic/structures) · [3-D structures of single cells](schic/reconstruction) · [cell embeddings](schic/embeddings) |
| [Bulk Hi-C](bulk/index) | [calling structures from a map](bulk/structures): compartments, domains, loops, pileups · [structures from a bulk map](bulk/reconstruction): MDS, IGM · [Hi-C with imaging](bulk/gem_fish): GEM-FISH |

## Common to all data

| Chapter | What it covers | Package / module |
|---------|----------------|------------------|
| [Datasets & the atlas](datasets/index) | browsing the public atlas, loading a dataset as a `ChromData` (over HTTP or built from its sources), fetching files for offline work | `uchrom.datasets` |
| [Data model & storage](data/index) | `ChromData`, the `.chromdata.zarr` store, backed and remote reads, linked and embedded modalities | `chromdata` |
| [Per-locus features](features/index) | distance maps, variance features, signals and peaks along the genome, annotation | `uchrom.fea` |
| [Visualisation](viz/index) | the web browser, the data atlas, plots | `uchrom-browser`, `uchrom.pl` |

```{toctree}
:caption: Getting started
:maxdepth: 1
:hidden:

start/install
start/quickstart
gallery
start/concepts
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

datasets/index
data/index
features/index
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
