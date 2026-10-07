# Quick start

Three short paths through U-Chrom, each on real data and each a few seconds to a minute on a laptop.
The chapters and their tutorials go further.

## 1. Open a dataset from the atlas

The [data atlas](../viz/atlas) is a public collection of `.chromdata.zarr` stores.  A store opens
*backed* over HTTP: only the small tables are fetched, and a cell is read when you ask for it.

```python
import uchrom.datasets as ds

cd = ds.load("takei2025_cerebellum")             # ~2 s: cells, bins, the index (backed, over HTTP)
cd
```
```text
ChromData (backed: takei2025_cerebellum.chromdata.zarr): n_spots=10912638, n_traces=59112, n_cells=1799, n_bins=100049
  cells:   ['leiden', 'cell_type', 'x_centroid', 'y_centroid', 'z_centroid', 'nuc_volume_um3', ...] (1799 cells)
  cellm:   {'umap': (1799, 2)}
  spot_tracks:    ['CPSF6', 'ATRX', 'H4K8ac', 'HDAC2', 'H3K9ac', 'H3K9me3', ...]
```

```python
cell = cd.get_cell(cd.cells.index[0])            # one cell: 4,183 spots in 24 traces, read on demand
cell.cells["cell_type"], cell.coords[:3]
```

Takei et al. 2025 (*Nature*): DNA seqFISH+ of the mouse cerebellum — 3-D positions of 100,049 loci
with 62 chromatin marks per spot in 1,799 cells.

## 2. Call structures on chromatin tracing data

```python
import uchrom as uc
import uchrom.datasets as ds

# Takei et al. 2021 (Nature), mouse ES cells, 4DN FOF-CT 4DNFIHF3JCBY (built once from the 4DN files)
cd = ds.load("takei2021_mesc")                              # 201 cells, 8,285 traces
tads = uc.tl.call_tads(cd, chrom="chr3")                    # ArcFISH: TADs from 3-D distances
tads.head(3)
```
```text
  chrom    start      end  level     score      pval       fdr
0  chr3  7675000  8550000      1  2.782985  0.001648  0.028020
1  chr3  8550000  8925000      1  2.782985  0.001648  0.028020
2  chr3  8925000  9050000      1  1.809957  0.015490  0.097476
```

The call is stored with its parameters: `cd.intervals["tads.arcfish"]`,
`cd.results.record("tads.arcfish").params`.  Save everything as one store:

```python
cd.write("takei2021.chromdata.zarr")
```

## 3. Reconstruct a single cell from Hi-C

```python
import uchrom as uc

import uchrom.datasets as ds

# Stevens et al. 2017 (Nature), haploid mouse ES cell 1 (GEO GSE80280, fetched once)
pairs = ds.fetch("stevens2017") / "GSM2219497_Cell_1_contact_pairs.txt.gz"
s = uc.tl.reconstruct_sc(pairs, n_models=4)                  # EMber, native engine; ~5 s on a laptop GPU
s
```
```text
ChromData: n_spots=25724, n_traces=20, n_bins=25724
  spots:   ['chrom', 'start', 'end', 'trace_id', 'bin_id']
  layers:  ['model_0', 'model_1', 'model_2', 'model_3']
  results: ['ember.stages', 'ember.em', 'ember.contact_weights']
  uns:     ['xyz_unit', 'ember']
```

Four models of the cell's 20 chromosomes at 100 kb, one per layer.

This needs the native engine (`pip install ./packages/uchrom-recon`).

## Look at it

```bash
python -m uchrom_browser takei2021.chromdata.zarr
```

The web browser opens the store backed: cells, traces in 3-D, distance and contact maps, tracks and
embeddings, linked through the cells you select.  The atlas datasets are in its *Open* dialog, and
online at [uchrom-browser.u-science.org](https://uchrom-browser.u-science.org).

## Next

- [Concepts](concepts): the data model in one page.
- The chapters by data type — [chromatin tracing](../tracing/index), [DNA seqFISH+](../seqfish/index),
  [single-cell and spatial Hi-C](../schic/index), [bulk Hi-C](../bulk/index) — and those common to all data,
  from [data model & storage](../data/index) to [visualisation](../viz/index).
