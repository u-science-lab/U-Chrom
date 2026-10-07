# Pseudo-bulk maps

One cell's contact map is far too sparse to call compartments, domains or loops; summed over the cells of a
group — a cell type, a cluster, an age, any partition of the cells — the maps become bulk-like **pseudo-bulk**
maps that the [map callers](../bulk/structures) read.  `uc.tl.pseudobulk` (`uchrom.fea.pseudobulk`) sums
the per-cell maps linked to the cells per group, writes one ICE-balanced `.cool` per group and links it to
the `ChromData` as `pseudobulk.<group>`:

```python
import uchrom as uc
import uchrom.datasets as ds

cd = ds.load("dschic_aging_cortex")                 # atlas store over HTTP: 32,777 cells, 1 Mb maps embedded
summary = uc.tl.pseudobulk(cd, "cell_type")         # one map per cell type: group, n_cells, n_contacts, key, path
uc.tl.call_compartments(cd, method="eig", contacts="pseudobulk.Microglial cells", phasing=...)
```

| Task | API |
|------|-----|
| one map per group: a `cd.cells` column, or a `Series` / mapping cell → group (any partition: random subsets, clusters) | `uc.tl.pseudobulk(cd, groupby)`; `groupby=None`: all cells in one map |
| only some cells or groups; coarser bins | `cells=`, `groups=`, `min_cells=`; `resolution=` (a multiple of the per-cell maps') |
| random sets of cells with the same number of contacts per group (matched depth, replicates, a depth series) | `uchrom.fea.sample_cells_by_depth(cd, groupby, n_contacts=, replicates=, contacts=)`; its `set` column is the `groupby` of `pseudobulk` |
| cis contacts only (compartments, domains, loops are cis) | `trans=False`: reads only the cis partitions of an embedded map, balances per chromosome |
| where the maps go | `out_dir=`; default next to a local store, or the data directory for a store read over HTTP; a map with the same cells and parameters is reused (`overwrite=True` recomputes) |
| the maps afterwards | `cd.uns["linked_cool"]["pseudobulk.<group>"]`, `cd.linked_cool_path(key)`; the summary in `cd.results["pseudobulk"]` |
| structures on them | `uc.tl.call_compartments(method="eig")`, `uc.tl.compartment_strength`, `uc.tl.call_tads(method="insulation")`, `uc.tl.call_loops`, `uc.tl.pileup` |

The per-cell maps are read where they are: a linked `.scool` cell by cell, or — in an atlas store — the
embedded maps one chromosome partition at a time for all selected cells, added up by group as they stream
(no per-cell file is exported).  On dscHi-C (32,777 cells, 2.6 G contacts, 1 Mb, over HTTP) the seven
cell-type maps take about 75 s with the contacts between chromosomes and about 30 s with `trans=False`, and
they sum pixel for pixel to the store's own all-cells map.

## Comparing groups: matched depth

Groups of cells rarely have the same number of contacts (the cell types of dscHi-C differ almost 20-fold),
and what is measured on a map depends on its depth: loop calls vanish in shallow maps, and the saddle
strength of a shallow map is inflated.  Compare groups on random subsets of cells with the same number of
contacts, several disjoint subsets per group to see the sampling spread: `sample_cells_by_depth` draws them,
and one `pseudobulk` call with its `set` column makes them all in one pass over the maps:

```python
from uchrom.fea import sample_cells_by_depth

cis = cd.cells["n_contacts"] * (1 - cd.cells["frac_trans"])          # the maps below hold cis contacts only
sets = sample_cells_by_depth(cd, ["cell_type", "age"], n_contacts=5e6, replicates=3, contacts=cis)
uc.tl.pseudobulk(cd, sets["set"], trans=False, key_prefix="subset")   # one map per set: subset.<set>
```

On dscHi-C at 1 Mb this shows the cell-type differences in compartment strength at matched depth (neurons
lowest, microglia highest), while the strength of a map's own eigenvector rises below ~20 M cis contacts
(+15 % at 2 M).

At bulk depth, structures are *called*; below it, known loops are *scored* by pileup (`uc.tl.pileup`): 24 deep
GM12878 single cells (about 1 % of a bulk map's depth) give an APA of 4.96 for the published GM12878 loops
where HiCCUPS calls 12 loops (`benchmarks/hic_structures/README.md`).

## Tutorial

```{toctree}
:maxdepth: 1

/tutorials/pseudobulk
```

API: [uchrom.fea](../reference/api/fea) (`pseudobulk`, `pileup`), [compartments](../reference/api/strc_comp).
