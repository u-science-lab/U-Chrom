# U-Chrom

**U**niversal **Chrom**atin structure data analysis toolkit.

U-Chrom provides a unified framework for 3D chromatin structure analysis.
The core data structure is a **structure table** — genomic bins mapped to
3D coordinates `(chrom, start, end, x, y, z)` — which can be obtained from
either sequencing-based data (Hi-C, Dip-C) via 3D reconstruction, or
imaging-based data (ORCA, MERFISH, DNA seqFISH+) via chromatin tracing.

On top of this common interface, U-Chrom implements:

- **Reconstruction** from sparse Hi-C contacts (Nuc Dynamics, GEM, MDS/SMACOF)
- **Structure identification** — loops (ArcFISH-style per-axis F-test),
  TADs (directionality index), compartments (placeholder)
- **Geometric features** — distance matrices, contact frequency, radius
  of gyration
- **Interactive 3D browser** built on PyVista + PyQt5
- **Population-level aggregation plots** (median distance matrix, contact
  map, Rg histogram)

## Quick start

```bash
pip install u-chrom
```

```python
from uchrom import ChromData

# Import FOF-CT imaging data
cd = ChromData.from_fofct("example-data/core.csv")

# ArcFISH-style loop calling (GPU-accelerated)
from uchrom.strc.loop import call_loops_axiswise_f
loops = call_loops_axiswise_f(cd, chrom="chr17", device="auto")

# Persist
cd.write("data.chromdata.zarr")
```

Launch the interactive 3D browser:

```bash
python -m uchrom.browser --web data.chromdata.zarr
```

```{toctree}
:caption: Getting started
:maxdepth: 1

install
concepts
example_data
```

```{toctree}
:caption: Tutorials — Core & I/O
:maxdepth: 1

tutorials/chromdata_basics
tutorials/import_fofct
tutorials/import_pyhim_ecsv
tutorials/takei2025_walkthrough
tutorials/takei2025_auto_discovery
tutorials/takei2025_iterative_auto_discovery
```

```{toctree}
:caption: Tutorials — Reconstruction (recon)
:maxdepth: 1

tutorials/reconstruction
tutorials/gem_fish_reconstruction
```

```{toctree}
:caption: Tutorials — Imaging & tracing (im)
:maxdepth: 1

tutorials/jie_aligner
```

```{toctree}
:caption: Tutorials — Structure identification (strc)
:maxdepth: 1

tutorials/loop_calling
tutorials/tad_calling
tutorials/fishnet_domains
tutorials/compartment
```

```{toctree}
:caption: Tutorials — Embedding (emb)
:maxdepth: 1

tutorials/higashi_embedding
```

```{toctree}
:caption: User guide
:maxdepth: 2

guide/chromdata
guide/io
guide/tracing
guide/reconstruction
guide/structure
guide/auto_discovery
guide/iterative_auto_discovery
guide/data_enrichment_for_discovery
guide/linked_multiomics
guide/chromdata_2_0_design
guide/browser
```

```{toctree}
:caption: API reference
:maxdepth: 1

api/index
```

```{toctree}
:caption: Project
:maxdepth: 1

changelog
license
```
