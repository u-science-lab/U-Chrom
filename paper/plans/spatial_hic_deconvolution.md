# Plan (deferred): spatial deconvolution of spatial Hi-C spots into 3-D structures

Status: recorded 2026-09-30, **not started**.  Fig. 3 stays on faithfulness / speed /
comparability; this is a candidate for an additional figure.

## Idea

A spatial Hi-C spot (DBiT-style barcode grid, 10-50 µm) holds the contacts of a few
cells or partial nuclei.  IGM deconvolves a population average into S structures; a
spot is a tiny population, so a spot-level IGM (S = k cells per spot, contacts
hard-assigned to one cell each) could split a spot into per-cell structures — the 3-D
analogue of spot deconvolution in spatial transcriptomics (Tangram etc.).

## Data (2026)

| Paper | Spot | Contacts per spot (median) | 3-D modelling |
|---|---|---|---|
| Spatial Hi-C-RNA, Guo … Deng, Cell 2026, doi:10.1016/j.cell.2026.07.039 (GEO GSE311199) | 20 µm (brain, melanoma), 10 µm (E11.5) | cis > 1 kb 136k / trans 42k (adult brain); 35k / 27k (E11.5) | none |
| Spatial-ATAC-Hi-C, Wang … Yue, Nat Methods 2026, doi:10.1038/s41592-026-03217-4 (GEO GSE307620) | 50 x 50 grid, likely 20 µm (unverified) | ~96k Hi-C fragments | none (Higashi / scHiCluster per spot) |
| Spatial Hi-C, Chen … Chen, Nat Methods 2026, doi:10.1038/s41592-026-03218-3 (GSA CRA016676, Zenodo 17961135) | 10 / 20 / 50 µm | 72k valid contacts (50 µm, E13) | abstract claims single-spot 3-D; no modelling code released |

## Obstacles

1. Contacts per cell: 30-60k if a 20 µm spot holds 2-4 cells — borderline but in the
   range of Stevens 2017 single-cell structures.
2. **Homologs cannot be phased** (inbred mice, no SNPs): each contact has 2k possible
   origins in a spot of k diploid cells.  The main obstacle.
3. Sectioning (10 µm) cuts nuclei: partial genomes; maybe only local structures.

## Two routes

- **Reference-free**: spot-level IGM with S = k (A-step assigns each contact to the cell
  whose structure it fits; M-step refines).  Engine change: raw contacts, binary
  assignment, small S.
- **Reference-based (Tangram-like)**: map reference single-cell 3-D structures with cell
  types (brain: Tan 2021 Dip-C; embryo: HiRES, Liu 2023 Science) onto spots in contact
  space, optionally constrained by the spot's RNA (Cell 2026 data), then refine with the
  spot's contacts starting from the reference structures (`init_positions`).  Phasing and
  missing parts come from the reference.

## Steps when started

1. Per-spot statistics on the Cell 2026 and Chen 2026 data: contacts, and the number of
   cells per spot from the Dip-C rule "a fragment end takes part in at most two contacts".
2. In-silico mixtures of **real** single cells with known origin (like simulated
   doublets): haploid (Stevens 2017, 8 cells), diploid phased (Dip-C), diploid unphased.
   Metrics: contact-to-cell assignment accuracy; structure similarity to each cell's own
   reconstruction; scored with the `benchmarks/screcon` framework.
3. Pick the route from step 2; then the spatial data (per-region structure maps, links to RNA).
4. Novelty check: Hi-C multiplet deconvolution into structures; reference-based
   deconvolution of spatial Hi-C.

Estimated effort: steps 1 + 4 about one day, step 2 two to three days.
