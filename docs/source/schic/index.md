# Single-cell and spatial Hi-C

Single-cell Hi-C (and Dip-C, scMicro-C, sci-Hi-C) gives each cell a sparse list of contacts — pairs of
loci that were close in that nucleus; the multi-omics variants add the cell's transcriptome or
accessibility (HiRES, GAGE-seq, scHiCAR, Paired / Droplet Hi-C), and spatial Hi-C measures contacts per
spot of a tissue section.  Contacts are not coordinates: U-Chrom keeps them as contact maps linked to
the cells, and computes coordinates from them when you want structures.

| Step | API |
|------|-----|
| read contacts: `.pairs`, phased pairs (hickit / Dip-C), the Stevens 2017 / NCC files | `uchrom.io.read_pairs`, `read_phased_pairs`; the reconstruction functions read the files directly |
| link per-cell contact maps (`.scool`) and pseudo-bulk maps (`.cool` / `.mcool`) to the cells | `cd.link_scool`, `cd.link_cool`; `cd.load_linked_scool(cell=...)` |
| link RNA / ATAC matrices (`.h5ad`, `.h5mu`) | `cd.link_anndata`, `cd.link_mudata`; `cd.linked_adata` |
| 3-D structures of one cell, an ensemble of models (native engine, CPU or GPU) | EMber: `uchrom.recon.sc.reconstruct_ember`, `uc.tl.reconstruct_sc`; NucDynamics: `reconstruct_nucdyn` |
| contacts of a structure (to compare with the input) | `uchrom.io.count_contacts` |
| cell features from contact maps; Higashi / FastHigashi | `uchrom.emb.scool_cell_features`, `schicluster_features`; `uchrom.emb.higashi` (extra `emb`) |
| spots of a section in the tissue | `cd.set_cell_positions`, `cd.cell_positions`, `cd.link_spatialdata` |

The atlas holds single-cell and spatial Hi-C datasets ready to open — HiRES, dscHi-C, GAGE-seq, Droplet
and Paired Hi-C, scHiCAR, Uni-C, Stevens 2017 with its published structures, spatial Hi-C, spatial
ATAC-Hi-C and Hi-C-RNA sections ([datasets](../start/datasets)).

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/reconstruction
/tutorials/higashi_embedding
```

The scHiCAR part of [cell embeddings](../tutorials/cell_embeddings) embeds the same cells by their
contact maps, their RNA and their accessibility.

## Guides

```{toctree}
:maxdepth: 1

reconstruction
```

## Then

Reconstructed models are coordinates like traced ones: distance maps and contact frequencies of the
models ([per-locus features](../features/index)), comparisons with imaging of the same cell type, and
the [web browser](../viz/index), which shows each cell's models next to its own contact map.  Linked contact maps,
pseudo-bulk maps per cell type and embedded copies for sharing: [data model & storage](../data/index).

API: [uchrom.recon](../reference/api/recon), [uchrom.emb](../reference/api/emb), [uchrom.io](../reference/api/io).
