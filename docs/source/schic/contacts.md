# Contact maps per cell

A cell's contacts become a contact map — a sparse matrix of contact counts between genomic bins.  The maps of
all cells are kept in one `.scool` (one cooler per cell), *linked* to the `ChromData` of the cells, not
copied into it; a pseudo-bulk map (all cells, or one cell type) is a linked `.cool` / `.mcool`.  The
`ChromData` then has cells (with their metadata and embeddings) and, until a structure is computed, no
spots.

```python
import uchrom.datasets as ds

cd = ds.load("kim2020_scihic")                  # sci-Hi-C: 1,931 cells, cell types, per-cell 500 kb maps
cd.uns["linked_scool"]["per_cell"]              # the link: path (relative to the store), bin size, assembly
one = cd.load_linked_scool(key="per_cell", cell=cd.cells.index[0])   # one cell's map, a cooler
path = cd.linked_scool_path("per_cell")         # the .scool itself, for tools that read files
```

| Task | API |
|------|-----|
| read contact pairs: `.pairs`, phased pairs (hickit / Dip-C) | `uchrom.io.read_pairs`, `read_phased_pairs` |
| link per-cell maps / a pseudo-bulk map to the cells | `cd.link_scool(path, key=...)`, `cd.link_cool(path, key=...)` |
| read them back | `cd.load_linked_scool(key=, cell=)`, `cd.linked_scool_path(key, cells=)`, `cd.linked_cool_path(key)` |
| link RNA / ATAC measured in the same cells | `cd.link_anndata`, `cd.link_mudata`; `cd.linked_adata` |
| ship a dataset as one store (atlas) | `python -m chromdata.embedded STORE`: the maps embedded, partitioned by chromosome |
| spots of a section in the tissue (spatial Hi-C) | `cd.set_cell_positions`, `cd.cell_positions`, `cd.link_spatialdata` |

In an atlas store the maps are *embedded* rather than linked; the same calls read them over HTTP, and
`linked_scool_path(key, cells=...)` exports the cells asked for once, one read per chromosome.  Analyses
take the `ChromData` and the key of its maps — [FastHigashi](embeddings), the scHiCluster features, the
directionality index — rather than file paths.  Linking, embedding and reading maps on a real store: the
[`.chromdata.zarr` store](../tutorials/chromdata_stores) tutorial.

API: [chromdata](../reference/api/core), [uchrom.io](../reference/api/io).
