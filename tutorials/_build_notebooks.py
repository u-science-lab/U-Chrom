"""Regenerate the tutorial notebooks under ``tutorials/``.

Run once from the repo root::

    python tutorials/_build_notebooks.py

Notebooks are written with empty outputs and ``execution_count = null`` so
they diff cleanly.  Keep cell ``source`` as a list of strings (one line
each) for readability in ``git diff``.
"""

from __future__ import annotations

import json
from pathlib import Path


def md(text: str):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [line + "\n" for line in text.rstrip("\n").split("\n")],
    }


def code(text: str):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [line + "\n" for line in text.rstrip("\n").split("\n")],
    }


NB_META = {
    "kernelspec": {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    },
    "language_info": {
        "name": "python",
        "version": "3.11",
    },
}


def write_nb(path: Path, cells: list):
    nb = {
        "cells": cells,
        "metadata": NB_META,
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(nb, indent=1) + "\n")
    print(f"wrote {path}")


# ============================================================
# 1. ChromData basics
# ============================================================

nb1 = [
    md("""\
# 1. ChromData — the core data container

`uchrom.ChromData` is the central data structure for U-Chrom, analogous to
[AnnData](https://anndata.readthedocs.io/) for chromatin 3D structure data.
It holds genomic bins mapped to 3D coordinates, grouped in a
**Cell → Trace → Spot** hierarchy, and persists as `.h5cd` (HDF5) files.

This notebook covers:

- Creating a ChromData from scratch
- The three "core tables" (core / cell / chromatin) and auxiliary storage
- Subsetting by chromosome, trace, or cell
- Round-tripping to `.h5cd` with format versioning
- Importing from reconstruction CSV and FOF-CT"""),

    code("""\
import numpy as np
import pandas as pd
from uchrom import ChromData"""),

    md("## Minimal construction\n\n`ChromData` needs at least `coords (n_spots, 3)` and a `spots` DataFrame with `chrom / start / end / trace_id`."),

    code("""\
rng = np.random.default_rng(0)
coords = rng.normal(size=(60, 3))
spots = pd.DataFrame({
    'chrom':    ['chr1']*30 + ['chr2']*30,
    'start':    list(range(0, 30_000_000, 1_000_000)) * 2,
    'end':      list(range(1_000_000, 31_000_000, 1_000_000)) * 2,
    'trace_id': [0]*30 + [1]*30,
})

cd = ChromData(coords, spots, uns={'genome_assembly': 'GRCh38'})
cd"""),

    md("## Attributes"),

    code("""\
print('n_spots :', cd.n_spots)
print('n_traces:', cd.n_traces)
print('chroms  :', cd.chroms)
cd.spots.head()"""),

    md("`spots['chrom']` and `spots['trace_id']` are auto-converted to `pd.Categorical` for ~10× memory savings on large datasets."),

    code("""\
print(cd.spots['chrom'].dtype)
print(cd.spots['trace_id'].dtype)"""),

    md("## Subsetting\n\nAll subset operations return a **new** `ChromData` — never mutate the original."),

    code("""\
chr1 = cd.get_chrom('chr1')
print(chr1)"""),

    code("""\
trace0 = cd.get_trace(0)
print(trace0)

# Boolean indexing also works
first_ten = cd[np.arange(10)]
print(first_ten)"""),

    md("## On-demand distance matrix\n\nGlobal pairwise distance matrices are not stored (they'd be O(n²) and biologically meaningless across cells). Compute per-trace on demand:"),

    code("""\
d = cd.compute_distances(trace_id=0)
print('distance matrix shape:', d.shape)
print('diagonal is zero      :', np.allclose(np.diag(d), 0))"""),

    md("## Persistence — `.h5cd`\n\n`ChromData` serialises to HDF5 with a format version attribute so future releases can migrate old files."),

    code("""\
import tempfile, os
tmp = tempfile.mkdtemp()
path = os.path.join(tmp, 'demo.h5cd')

cd.write(path)
cd2 = ChromData.read(path)
print(cd2)
print('coords match:', np.allclose(cd.coords, cd2.coords))"""),

    md("""\
## Importing from existing formats

| Source | Method |
|--------|--------|
| Reconstruction CSV (chrom, start, end, x, y, z) | `ChromData.from_dataframe(df)` |
| 4DN FOF-CT core table | `ChromData.from_fofct(path)` |
| `.h5cd` | `ChromData.read(path)` |"""),

    code("""\
# Example: from a reconstruction output CSV (here we build a fake one)
recon = pd.DataFrame({
    'chrom': ['chr1']*10,
    'start': range(0, 10_000_000, 1_000_000),
    'end':   range(1_000_000, 11_000_000, 1_000_000),
    'x': rng.normal(size=10),
    'y': rng.normal(size=10),
    'z': rng.normal(size=10),
})
cd_recon = ChromData.from_dataframe(recon, cell_id='demo_cell')
cd_recon"""),

    md("## Where to go next\n\n- **Tutorial 2** — importing real FOF-CT imaging data and inspecting trace structure.\n- **Tutorial 3** — running 3D reconstruction from Hi-C `.pairs` files.\n- **Tutorial 4** — ArcFISH-style loop calling on FOF-CT data."),
]

write_nb(Path("tutorials") / "01_chromdata_basics.ipynb", nb1)


# ============================================================
# 2. FOF-CT imaging data
# ============================================================

nb2 = [
    md("""\
# 2. Importing FOF-CT imaging data

The [4DN FISH Omics Format — Chromatin Tracing](https://fish-omics-format.readthedocs.io/)
(FOF-CT) is the community standard for chromatin-tracing / multiplexed DNA
FISH experiments.  A FOF-CT *core table* is a CSV with a metadata header
(`##FOF-CT_Version=v1.0`, `##Columns=(…)`) followed by per-spot rows.

This notebook loads a real FOF-CT dataset with `ChromData.from_fofct` and
shows how to navigate the **Cell → Trace → Spot** hierarchy that imaging
data naturally exposes."""),

    code("""\
import numpy as np
import pandas as pd
from uchrom import ChromData

# Change this to a FOF-CT file you have locally
FOFCT = 'example-data/fofct_core.csv'  # or similar

# For this tutorial we build a synthetic example that looks like FOF-CT
# output in case you do not have a file handy.  Skip this cell if you
# downloaded a real file.
import io, os
if not os.path.exists(FOFCT):
    os.makedirs('example-data', exist_ok=True)
    rng = np.random.default_rng(0)
    header = '''##FOF-CT_Version=v1.0
##Table_Namespace=4dn_FOF-CT_core
##Genome_Assembly=GRCh38
##XYZ_Unit=micron
#Lab_Name: Demo
##Columns=(Spot_ID, Trace_ID, X, Y, Z, Chrom, Chrom_Start, Chrom_End, Cell_ID)
'''
    rows = []
    sid = 1
    for cell in range(20):
        for trace in range(2):          # 2 alleles per cell
            walk = np.cumsum(rng.normal(scale=0.12, size=(12, 3)), axis=0)
            for bin_i in range(12):      # 12 bins per trace
                x, y, z = walk[bin_i]
                start = 1_000_000 + bin_i * 10_000
                rows.append((sid, f'{cell}_{trace}', x, y, z,
                             'chr17', start, start + 10_000, cell))
                sid += 1
    with open(FOFCT, 'w') as f:
        f.write(header)
        for r in rows:
            f.write(','.join(str(x) for x in r) + '\\n')

FOFCT"""),

    md("## Load the file"),

    code("""\
cd = ChromData.from_fofct(FOFCT)
cd"""),

    md("## Inspect metadata\n\nThe FOF-CT header fields go into `cd.uns` so you can always trace the origin of a dataset."),

    code("""\
cd.uns['fofct_header']"""),

    code("""\
print('genome   :', cd.uns.get('genome_assembly'))
print('xyz_unit :', cd.uns.get('xyz_unit'))
print()
print(cd.spots.head())"""),

    md("## Traces per chromosome\n\nImaging data typically has many traces per chromosome (each trace = one allele observation)."),

    code("""\
summary = (
    cd.spots
      .groupby('chrom', observed=True)
      .agg(n_spots=('trace_id', 'size'),
           n_traces=('trace_id', 'nunique'))
)
summary"""),

    md("## Subsetting a single trace\n\nThis is the natural unit of analysis in chromatin tracing."),

    code("""\
first_trace_id = cd.spots['trace_id'].iloc[0]
trace = cd.get_trace(first_trace_id)
print(trace)
print()
print(trace.to_dataframe().head())"""),

    md("## Convert to ChromData-backed analysis format\n\nDownstream analysis modules in `uchrom.fea` and `uchrom.strc` operate directly on the flat DataFrame produced by `cd.to_dataframe()` or accept the `ChromData` itself."),

    code("""\
df = cd.to_dataframe()
print(df.columns.tolist())
df.head()"""),

    md("""\
## Writing your own FOF-CT-compatible data

If you produced tracing data with a tool that does not write FOF-CT, you
can create a ChromData directly (see Tutorial 1) and write `.h5cd`.  The
on-disk format is versioned so downstream tools can safely consume it."""),
]

write_nb(Path("tutorials") / "02_import_fofct.ipynb", nb2)


# ============================================================
# 3. 3D reconstruction from Hi-C
# ============================================================

nb3 = [
    md("""\
# 3. 3D reconstruction from Hi-C data

U-Chrom provides several 3D reconstruction algorithms:

| Module | Best for | Notes |
|--------|---------|-------|
| `uchrom.recon.sc.nucdyn` | Single-cell Hi-C / Dip-C | Molecular-dynamics, Taichi GPU |
| `uchrom.recon.sc.gem` | Single-cell, energy minimisation | Taichi autodiff |
| `uchrom.recon.bulk.mds` | Bulk Hi-C | SMACOF MDS, PyTorch GPU |

This notebook walks through a short single-cell reconstruction using Nuc
Dynamics on the example data shipped with the repo."""),

    md("## Locate the example data\n\nThe notebook looks for `example-data/cell1.pairs` in the repo; we walk up the directory tree to find the repo root so this runs from any cwd."),

    code("""\
from pathlib import Path

def find_repo_root(start: Path = Path.cwd()) -> Path:
    for p in [start, *start.parents]:
        if (p / 'example-data' / 'cell1.pairs').exists():
            return p
    raise FileNotFoundError('Could not locate example-data/cell1.pairs')

repo = find_repo_root()
pairs = repo / 'example-data' / 'cell1.pairs'
out_path = repo / 'tutorials' / '_out_tutorial3.h5cd'
print('pairs:', pairs)
print('out  :', out_path)"""),

    md("## Run Nuc Dynamics\n\nThe CLI is the simplest way; the main function is also importable."),

    code("""\
# From the shell (uncomment to run):
# !python -m uchrom.recon.sc.nucdyn example-data/cell1.pairs out.h5cd \\
#     --arch=cpu --dyns=30 --size_steps='[2, 0.4]'

from uchrom.recon.sc.nucdyn import main as nucdyn_main
nucdyn_main(
    str(pairs),
    str(out_path),
    arch='cpu',      # 'cuda' if you have an NVIDIA GPU
    dyns=30,         # fewer steps for the tutorial
    size_steps=[2, 0.4],  # only two resolution stages
)"""),

    md("## Load the reconstructed structure\n\nThe `.h5cd` output carries a `cell_id` derived from the filename and one trace per chromosome."),

    code("""\
from uchrom import ChromData
cd = ChromData.read(str(out_path))
cd"""),

    code("""\
print('chroms  :', cd.chroms)
print('n_spots :', cd.n_spots)
cd.spots.head()"""),

    md("## Compute a distance matrix for one chromosome"),

    code("""\
import matplotlib.pyplot as plt

trace_id = cd.spots['trace_id'].iloc[0]
D = cd.compute_distances(trace_id=trace_id)

fig, ax = plt.subplots(figsize=(5, 5))
im = ax.imshow(D, cmap='viridis_r', aspect='equal')
ax.set_title(f'Distance matrix — trace {trace_id}')
fig.colorbar(im, ax=ax, label='distance')"""),

    md("""\
## Using other reconstruction backends

`python -m uchrom.recon.sc.gem <in> <out.h5cd>` — energy-minimisation
variant (smoother, slower).

`python -m uchrom.recon.bulk.mds <contact.mcool> <out.h5cd> --resolution=100000`
— PyTorch SMACOF MDS on bulk Hi-C data.  Inter-chromosomal whole-genome
reconstruction via `--inter` with the additional `--resolution_inter` flag.

All three write the same `.h5cd` schema so downstream tools don't care
which reconstructor was used."""),
]

write_nb(Path("tutorials") / "03_reconstruction.ipynb", nb3)


# ============================================================
# 4. ArcFISH-style loop calling
# ============================================================

nb4 = [
    md("""\
# 4. ArcFISH-style loop calling on tracing data

`uchrom.strc.loop` provides a GPU-accelerated reimplementation of the
axis-wise F-test loop caller from Yu et al. 2025 (*ArcFISH*, bioRxiv
2025.11.26.690837).  Unlike Hi-C-style contact-frequency callers, the
axis-wise approach explicitly models the anisotropic per-axis measurement
error that is typical of DNA FISH images (Z usually noisier than X/Y),
and works with as few as ~30 traces per chromosome.

Pipeline, per chromosome:

1. **Per-axis variance cube** — for each `(i, j)` bin pair and each
   axis `c`, compute the variance of `x_c[j] - x_c[i]` across traces.
2. **Filter + normalise** — two LOWESS passes on log(genomic distance):
   first to NaN-out per-trace outliers at 4 σ, then to put the
   distance-stratified mean variance at 1.
3. **Per-axis F-test** — candidate `(i, j)` gets `F_c = norm_var / ring_mean`
   against a local background ring `[inner_cut, outer_cut]`.
4. **ACAT Cauchy combine** — aggregate the per-axis p-values with the
   median-trace-variance-inverse axis weights.
5. **BH-FDR**, cluster accepted candidates by 1D proximity, pick the
   lowest-p summit per cluster.
6. **Pseudo-contact-frequency filter** — only keep summits where the
   fraction of traces with `3D pdist < adjacent-bin cutoff` exceeds
   1/2 (singleton) or 1/3 (larger cluster).

Output is a BEDPE-style `DataFrame` stored under `cd.results['loops']`."""),

    code("""\
import pandas as pd
from uchrom import ChromData
from uchrom.strc.loop import call_loops_axiswise_f, LoopCallerParams"""),

    md("## Load a chromatin-tracing dataset\n\nWe use the same synthetic FOF-CT file produced by tutorial 2; re-run that one first if this cell fails.  In practice you would download a real dataset such as Takei et al. 2021 (4DN accession `4DNFIHF3JCBY`)."),

    code("""\
from pathlib import Path
import os

def find_fofct() -> str:
    # Walk up to find a tutorials/ next to example-data/
    here = Path.cwd()
    for p in [here, *here.parents]:
        cand = p / 'example-data' / 'fofct_core.csv'
        if cand.exists():
            return str(cand)
    # Fallback: synthesise a FOF-CT file with built-in loop structure so
    # the tutorial actually calls a loop.  Bin pair (5, 20) is drawn close
    # together across traces; other pairs are random.
    os.makedirs('example-data', exist_ok=True)
    import numpy as np
    rng = np.random.default_rng(0)
    header = '''##FOF-CT_Version=v1.0
##Table_Namespace=4dn_FOF-CT_core
##Genome_Assembly=GRCh38
##XYZ_Unit=micron
#Lab_Name: Demo
##Columns=(Spot_ID, Trace_ID, X, Y, Z, Chrom, Chrom_Start, Chrom_End, Cell_ID)
'''
    # Brownian-bridge polymer: bins 5 and 20 are always pinned close to
    # each other (the "loop"); the intervening bins form a random bridge
    # between the two anchors, and bins outside [5, 20] are independent
    # random walks.  This produces a clean contact map with one bright
    # spot at (5, 20) and a standard diagonal elsewhere.
    def synth_trace(rng, n_bins=30, loop_a=5, loop_b=20, step=0.20, anchor_noise=0.03):
        w = np.zeros((n_bins, 3))
        # Pre-loop bins 0..loop_a: plain random walk
        for i in range(1, loop_a + 1):
            w[i] = w[i - 1] + rng.normal(scale=step, size=3)
        # Loop anchor at bin b: near w[loop_a] with tiny noise
        w[loop_b] = w[loop_a] + rng.normal(scale=anchor_noise, size=3)
        # Interior bins loop_a+1 .. loop_b-1: Brownian bridge from w[loop_a] → w[loop_b]
        n_int = loop_b - loop_a - 1
        if n_int > 0:
            raw = np.cumsum(rng.normal(scale=step, size=(n_int, 3)), axis=0)
            # End-point drift to remove so we land at w[loop_b]
            end_drift = raw[-1] - (w[loop_b] - w[loop_a])
            for k, idx in enumerate(range(loop_a + 1, loop_b)):
                t = (k + 1) / (n_int + 1)
                w[idx] = w[loop_a] + raw[k] - t * end_drift
        # Post-loop bins loop_b+1 .. n_bins-1: random walk from w[loop_b]
        for i in range(loop_b + 1, n_bins):
            w[i] = w[i - 1] + rng.normal(scale=step, size=3)
        return w

    rows = []
    sid = 1
    for cell in range(300):
        for trace in range(2):
            walk = synth_trace(rng)
            for bin_i in range(30):
                x, y, z = walk[bin_i]
                s = 1_000_000 + bin_i * 25_000
                rows.append((sid, f'{cell}_{trace}', x, y, z,
                             'chr17', s, s + 25_000, cell))
                sid += 1
    path = 'example-data/fofct_core.csv'
    with open(path, 'w') as f:
        f.write(header)
        for r in rows:
            f.write(','.join(str(x) for x in r) + chr(10))
    return path

FOFCT = find_fofct()
print('using', FOFCT)
cd = ChromData.from_fofct(FOFCT)
print(cd)
print()
print('traces per chrom:')
print(
    cd.spots.groupby('chrom', observed=True)['trace_id']
      .nunique().sort_values(ascending=False).head(10)
)"""),

    md("## Call loops on a single chromosome\n\nDefault parameters match ArcFISH (`fdr_cutoff=0.1`, `pval_cutoff=1e-5`, `gap=50 kb`, `inner_cut=25 kb`, `outer_cut=50 kb`)."),

    code("""\
# Pick a chromosome with enough traces
chrom = (
    cd.spots.groupby('chrom', observed=True)['trace_id']
      .nunique().idxmax()
)
print('calling loops on', chrom)

loops = call_loops_axiswise_f(
    cd,
    chrom=chrom,
    device='auto',   # CUDA > MPS > CPU
    store=True,      # also write to cd.results['loops']
    verbose=True,
)
loops"""),

    md("## Visualising the result\n\nThe companion modules `uchrom.fea` and `uchrom.pl` compute and render the population-level aggregates that chromatin-tracing papers use to present loop calls."),

    code("""\
import matplotlib.pyplot as plt
import numpy as np
from uchrom.fea import mean_distance_matrix, contact_frequency, radius_of_gyration
from uchrom.pl import plot_distance_matrix, plot_contact_map, plot_rg_histogram

df = cd.get_chrom(chrom).to_dataframe()

# Median pairwise distance matrix across all traces
dmat, bin_ids, n = mean_distance_matrix(df, chrom=chrom)
fig = plot_distance_matrix(dmat, title=f'Median 3D distance ({n} traces)')

# Overlay called loop summits on the heatmap
ax = fig.axes[0]
for _, row in loops.iterrows():
    i, j = int(row['summit_i']), int(row['summit_j'])
    ax.plot(j, i, 'o', mfc='none', mec='white', mew=1.5, ms=14)
    ax.plot(i, j, 'o', mfc='none', mec='white', mew=1.5, ms=14)
ax.set_title(ax.get_title() + f' — {len(loops)} loop(s) overlaid')
plt.show()"""),

    code("""\
# Population-level contact map at a user-chosen distance threshold
threshold = float(np.nanmedian(dmat[dmat > 0]) * 0.5)  # loose rule of thumb
cmat, bin_ids, n = contact_frequency(df, threshold=threshold, chrom=chrom)
fig = plot_contact_map(cmat, title=f'Contact frequency (< {threshold:.2g}, {n} traces)')
ax = fig.axes[0]
for _, row in loops.iterrows():
    i, j = int(row['summit_i']), int(row['summit_j'])
    ax.plot(j, i, 'o', mfc='none', mec='cyan', mew=1.5, ms=14)
    ax.plot(i, j, 'o', mfc='none', mec='cyan', mew=1.5, ms=14)
plt.show()"""),

    code("""\
# Per-trace radius of gyration distribution
rg = radius_of_gyration(df, chrom=chrom)
fig = plot_rg_histogram(rg, title=f'Rg distribution ({len(rg)} traces)')
plt.show()"""),

    md("## Tuning thresholds\n\nAll parameters live on `LoopCallerParams`:"),

    code("""\
params = LoopCallerParams(
    fdr_cutoff=0.05,    # stricter FDR
    pval_cutoff=1e-6,   # stricter p-value
    gap=25_000,         # tighter cluster gap
    k_sigma=3.0,        # aggressive outlier filter
)
loops_strict = call_loops_axiswise_f(cd, chrom=chrom, params=params, device='auto', store=False)
print(f'default: {len(loops)} loops  |  strict: {len(loops_strict)} loops')"""),

    md("## Whole-genome loop calling\n\nLoop over chromosomes and concatenate.  Each call is independent so trivial to parallelise if needed."),

    code("""\
all_loops = []
for chrom in cd.chroms:
    ls = call_loops_axiswise_f(cd, chrom=chrom, device='auto',
                               store=False, verbose=False)
    ls['chrom'] = chrom
    all_loops.append(ls)

loops_genome = pd.concat(all_loops, ignore_index=True)
print(f'Total called loops genome-wide: {len(loops_genome)}')
loops_genome.sort_values('pval').head(10)"""),

    md("## Persist results into the ChromData\n\nThe single-chromosome call already wrote to `cd.results['loops']`.  The result round-trips through `.h5cd`."),

    code("""\
out = Path(FOFCT).parent / 'with_loops.h5cd'
cd.write(str(out))

cd_reloaded = ChromData.read(str(out))
print(cd_reloaded.results['loops'])"""),

    md("## CLI\n\nFor batch scripts:\n\n```bash\npython -m uchrom.strc.loop --input=data.h5cd --output=data_loops.h5cd \\\n    --chrom=chr17 --device=auto\n\n# BEDPE export instead\npython -m uchrom.strc.loop --input=data.h5cd --output=loops.bedpe \\\n    --chrom=chr17 --device=auto\n```"),

    md("""\
## Notes on the comparison with ArcFISH

This implementation is independent of the upstream ArcFISH
(GPL-3.0) source; all algorithmic components — per-trace 4 σ filter,
distance-stratified LOWESS normalisation, per-axis F-test, ACAT
combine, BH-FDR, pseudo-contact-frequency summit filter — are
reimplemented here.

On the canonical Takei 2021 mESC benchmark we see **~2–3× speedup on
Apple MPS** and typically 60–70 % precision vs ArcFISH's summit set
at ±25 kb anchor tolerance, with a more conservative call set overall.
MPS forces float32; on CUDA with float64 you will see higher overlap
with the upstream output."""),
]

write_nb(Path("tutorials") / "04_loop_calling.ipynb", nb4)


# ============================================================
# 5. TAD calling
# ============================================================

nb5 = [
    md("""\
# 5. TAD calling (ArcFISH-style)

`uchrom.strc.tad.call_tads_by_pval` is a GPU-accelerated reimplementation
of the ArcFISH TAD caller (Yu et al. 2025).  For each candidate boundary
position it asks: is the variance *inside* the window smaller than the
variance *across* the window?  A per-axis F-test answers this and ACAT
combines the three axes into one p-value per bin.  Local minima in that
p-value are scored as TAD boundaries; the hierarchical option emits
nested TAD levels by repeatedly dropping the weakest boundary."""),

    code("""\
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from uchrom import ChromData
from uchrom.strc.tad import call_tads_by_pval, TADCallerParams
from uchrom.fea import mean_distance_matrix
from uchrom.pl import plot_distance_matrix"""),

    md("## Load the example FOF-CT\n\nUse the same synthetic file produced by tutorial 2 / 4; in practice you would point this at a real dataset such as Takei et al. 2021 (4DN `4DNFIHF3JCBY`)."),

    code("""\
from pathlib import Path
import os

here = Path.cwd()
candidates = [p / 'example-data' / 'fofct_core.csv' for p in [here, *here.parents]]
FOFCT = next((str(p) for p in candidates if p.exists()), None)
if FOFCT is None:
    raise FileNotFoundError('Run tutorial 2 or 4 first to produce the example FOF-CT.')
print(FOFCT)
cd = ChromData.from_fofct(FOFCT)
cd"""),

    md("## Run the TAD caller"),

    code("""\
chrom = cd.spots['chrom'].astype(str).iloc[0]
params = TADCallerParams(
    window_bp=1e5,     # boundary window (bp)
    fdr_cutoff=0.1,
    hierarchical=True,
    max_levels=3,
)
tads = call_tads_by_pval(cd, chrom=chrom, params=params, device='auto', verbose=True)
print(f'{len(tads)} TAD entries across {tads[\"level\"].nunique()} levels')
tads.head(15)"""),

    md("## Overlay TAD boundaries on the median distance matrix\n\nA good TAD call should draw its boundaries at the corners of the \"blocks\" visible in the median pairwise distance heatmap."),

    code("""\
df = cd.get_chrom(chrom).to_dataframe()
dmat, bin_ids, n_traces = mean_distance_matrix(df, chrom=chrom)
B = len(bin_ids)
mid_bp = np.array([(s + e) * 0.5 for (s, e) in bin_ids])

fig = plot_distance_matrix(dmat, title=f'Median distance + TAD boundaries ({n_traces} traces)')
ax = fig.axes[0]

# Draw level-1 TAD boundaries as white lines
top_level = tads[tads['level'] == tads['level'].min()]
for _, row in top_level.iterrows():
    # Find the bin index of each TAD end; draw a line there
    for edge_bp in (row['start'], row['end']):
        # Closest bin midpoint
        k = int(np.argmin(np.abs(mid_bp - edge_bp)))
        if 0 < k < B:
            ax.axhline(k - 0.5, color='white', lw=1.2, alpha=0.8)
            ax.axvline(k - 0.5, color='white', lw=1.2, alpha=0.8)
plt.show()"""),

    md("## Hierarchy\n\nWhen `hierarchical=True`, TADs are emitted at multiple levels of strictness.  Level 1 keeps only the most confident boundaries (coarse TADs); deeper levels include progressively weaker ones, producing nested structure."),

    code("""\
print('TADs per level:')
print(tads.groupby('level').size())

fig, axes = plt.subplots(1, min(3, tads['level'].max()), figsize=(12, 4), sharey=True)
if not hasattr(axes, '__len__'):
    axes = [axes]
for i, lv in enumerate(sorted(tads['level'].unique())[:3]):
    ax = axes[i]
    sub = tads[tads['level'] == lv]
    ax.set_title(f'level {lv} ({len(sub)} TADs)')
    for _, r in sub.iterrows():
        ax.axvspan(r['start'], r['end'], alpha=0.25, color='tab:blue',
                   edgecolor='navy', linewidth=1)
    ax.set_xlim(mid_bp.min(), mid_bp.max())
    ax.set_xlabel('Genomic position (bp)')
    ax.set_yticks([])
plt.tight_layout()
plt.show()"""),

    md("""\
## Notes

- The variance-normalisation preprocessing is shared with
  :func:`uchrom.strc.loop.call_loops_axiswise_f` — you only pay for it
  once per chromosome if you cache.
- For a "flat" TAD partition set ``hierarchical=False`` or just use
  ``level == 1``.
- This caller complements the classical directionality-index method
  available in :func:`uchrom.strc.tad.get_domains`; they agree on
  strong TADs and disagree on boundary-marginal ones."""),
]

write_nb(Path("tutorials") / "05_tad_calling.ipynb", nb5)


# ============================================================
# 6. A/B compartment
# ============================================================

nb6 = [
    md("""\
# 6. A/B compartment calling (ArcFISH-style)

`uchrom.strc.comp.call_compartments_axes_pc` is a GPU-accelerated
reimplementation of the ArcFISH `ABCaller.by_axes_pc`.  The idea:

- Turn each axis' normalised variance matrix into a pseudo-contact
  matrix ``K = exp(-var)``.
- Take the **second-largest eigenvector** of each axis' ``K``.  The
  first captures the overall distance-decay trend; the second captures
  compartment-scale alternation.
- Weight the three per-axis PC2's by the ArcFISH axis weights, stack
  them as a 3-feature vector per bin, and run ``KMeans(n=2)``.
- Assign A/B so that the cluster with smaller mean intra-distance is
  the more compact one (A by convention)."""),

    code("""\
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from uchrom import ChromData
from uchrom.strc.comp import call_compartments_axes_pc, CompartmentCallerParams
from uchrom.fea import mean_distance_matrix
from uchrom.pl import plot_distance_matrix"""),

    md("## Load example data"),

    code("""\
from pathlib import Path
here = Path.cwd()
candidates = [p / 'example-data' / 'fofct_core.csv' for p in [here, *here.parents]]
FOFCT = next((str(p) for p in candidates if p.exists()), None)
if FOFCT is None:
    raise FileNotFoundError('Run tutorial 2 or 4 first to produce the example FOF-CT.')
cd = ChromData.from_fofct(FOFCT)
cd"""),

    md("## Run the compartment caller"),

    code("""\
chrom = cd.spots['chrom'].astype(str).iloc[0]
comps = call_compartments_axes_pc(
    cd, chrom=chrom,
    params=CompartmentCallerParams(min_bins=2),
    device='auto', verbose=True,
)
print('compartment counts:')
print(comps['compartment'].value_counts())
comps.head(10)"""),

    md("## Compartment track\n\nThe weighted PC2 track alternates along the chromosome; A / B labels come from KMeans."),

    code("""\
fig, (ax_track, ax_label) = plt.subplots(
    2, 1, figsize=(10, 4), sharex=True,
    gridspec_kw={'height_ratios': [3, 1]},
)

mid_bp = (comps['start'] + comps['end']) / 2
ax_track.plot(mid_bp, comps['pc2'], 'k-', lw=1)
ax_track.axhline(0, color='grey', lw=0.5)
ax_track.set_ylabel('weighted PC2')
ax_track.set_title(f'A/B compartments — {chrom} ({len(comps)} bins)')

colors = {'A': 'tab:red', 'B': 'tab:blue'}
for lab, sub in comps.groupby('compartment'):
    for _, r in sub.iterrows():
        ax_label.axvspan(r['start'], r['end'], color=colors[lab], alpha=0.7)
ax_label.set_yticks([])
ax_label.set_xlabel('Genomic position (bp)')
ax_label.set_ylabel('A/B')
plt.tight_layout()
plt.show()"""),

    md("## Compartments on the distance matrix\n\nVisualising per-bin A/B labels next to the population-mean distance matrix makes the compartment pattern clear: A-A and B-B pairs are usually closer than A-B pairs."),

    code("""\
df = cd.get_chrom(chrom).to_dataframe()
dmat, bin_ids, _ = mean_distance_matrix(df, chrom=chrom)
fig = plot_distance_matrix(dmat, title=f'Median distance with A/B track')

ax = fig.axes[0]
# Colour the diagonal edge by compartment label
B = len(bin_ids)
for i in range(B):
    lab = comps.iloc[i]['compartment']
    ax.plot(i, -2, 's', ms=8, color=colors[lab], clip_on=False)
    ax.plot(-2, i, 's', ms=8, color=colors[lab], clip_on=False)
ax.set_xlim(-3, B)
ax.set_ylim(-3, B)
plt.show()"""),

    md("""\
## Notes

- The A/B assignment here is a convention (smaller mean intra-distance
  → A).  With a gene-density annotation you would pick whichever
  cluster has higher TSS density as A — this library does not ship
  that integration.
- ``n_clusters`` can be > 2 if you want to explore sub-compartment
  structure (A1 / A2 / B1 / B2).  The naming in the output DataFrame
  will no longer be ``{A, B}``.
- Like the loop and TAD callers, this caller shares the
  ``filter_normalize`` preprocessing step with the other ArcFISH-style
  routines."""),
]

write_nb(Path("tutorials") / "06_compartment.ipynb", nb6)


# ============================================================
# README
# ============================================================

readme = """\
# U-Chrom tutorials

Jupyter notebooks walking through the main analysis pipelines.  All
notebooks assume you have installed `uchrom` (`pip install -e .` from
the repo root) and are running from the repo root so relative paths
work.

| Notebook | Topic |
|----------|-------|
| `01_chromdata_basics.ipynb` | The `ChromData` container |
| `02_import_fofct.ipynb` | Loading FOF-CT imaging data |
| `03_reconstruction.ipynb` | 3D reconstruction from Hi-C |
| `04_loop_calling.ipynb` | ArcFISH-style loop calling |
| `05_tad_calling.ipynb` | ArcFISH-style TAD calling (hierarchical) |
| `06_compartment.ipynb` | A/B compartment calling |

The notebooks are regenerated by running
`python tutorials/_build_notebooks.py` from the repo root, which keeps
them small and diff-friendly.
"""
Path("tutorials/README.md").write_text(readme)
print("wrote tutorials/README.md")
