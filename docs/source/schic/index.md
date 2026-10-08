# Single-cell and spatial Hi-C

Single-cell Hi-C (and Dip-C, scMicro-C, sci-Hi-C) gives each cell a sparse list of contacts — pairs of loci
that were close in that nucleus; the multi-omics variants add the cell's transcriptome or accessibility
(HiRES, GAGE-seq, scHiCAR, Paired / Droplet Hi-C), and spatial Hi-C measures contacts per spot of a tissue
section.  Contacts are not coordinates: U-Chrom keeps them as contact maps linked to the cells, embeds the
cells by them, and computes 3-D structures from them.

| Step | Page | API |
|------|------|-----|
| contacts per cell: read them, link per-cell maps and pseudo-bulk maps to the cells, open the atlas datasets | [Contact maps per cell](contacts) | `uchrom.datasets.load`, `uchrom.io.read_pairs`, `cd.link_scool`, `cd.linked_scool_path` |
| maps of cell groups: per-cell maps summed per cell type, cluster or any partition of the cells; compartments and their strength compared at matched depth | [Pseudo-bulk maps](pseudobulk.md) | `uc.tl.pseudobulk`, `uchrom.fea.pseudobulk`; then `uc.tl.call_compartments(cd, method="eig")`, `uc.tl.compartment_strength`, `uc.tl.pileup` |
| 3-D structures of one cell: an ensemble of models (NucDynamics, EMber; CPU or GPU) | [3-D structures of single cells](reconstruction) | `uc.tl.reconstruct_sc`, `uchrom.recon.sc` |
| which cells are alike: embeddings from contact maps (FastHigashi, scHiCluster) and from the RNA / accessibility measured with them | [Cell embeddings](embeddings) | `uc.tl.embed_higashi`, `uchrom.emb`, `uc.tl.embed_cells` |

The atlas holds single-cell and spatial Hi-C datasets ready to open — HiRES, dscHi-C, GAGE-seq, Droplet and
Paired Hi-C, scHiCAR, Uni-C, Stevens 2017 with its published structures, spatial Hi-C, spatial ATAC-Hi-C and
Hi-C-RNA sections ([datasets](../datasets/index)); the [web browser](../viz/index) shows each cell's
contact map, its models in 3-D and the cells in their tissue.

```{toctree}
:maxdepth: 2
:hidden:

contacts
pseudobulk
reconstruction
embeddings
```
