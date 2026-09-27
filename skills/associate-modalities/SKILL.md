---
name: associate-modalities
description: Use for any "does A correlate with B" question in U-Chrom data — IF / histone mark, RNA, ATAC or nuclear size vs Rg / compaction, central vs peripheral position of bins, ATAC vs RNA of a gene (driven by cell type?), cell-type separation (kNN purity) in Hi-C vs RNA embeddings. Level, Spearman, confounders.
---

# Associate a feature with structure (or two modalities)

## When to use
"Across cells, does ⟨IF / histone mark⟩ correlate with compaction (median trace Rg)?", "along chrN, do bins
with more ⟨mark⟩ sit more central / peripheral?", "does ATAC gene activity correlate with RNA for gene X, and
is it driven by cell type?", "how well do cell types separate in the Hi-C vs RNA embedding (kNN purity)?" —
any feature (IF, RNA, ATAC, nuclear volume, embedding) vs structure or vs another modality.

Script: `<skill dir>/scripts/associate.py` (CLI prints JSON; or import `cell_level`, `bin_level`,
`knn_purity`). Run *load-data* first if you have not looked at the dataset.

## 1. Choose the level — and say it
| the question is about… | level | unit of n | command |
|---|---|---|---|
| cells ("across cells", "cells with more X…") | **cell** | cells | `associate.py cell data.h5cd --x if.<MARK> --y rg` |
| genomic positions ("bins / loci / regions with more X…", "along chrN") | **bin** | bins | `associate.py bin data.h5cd --x <TRACK> --y <TRACK> --chrom <CHROM> --bin-size <BIN>` |
| cell types | **cell type** | cell types (few!) | per-type medians (`between_group_medians_rho`) — descriptive only |
| embeddings | **cell** | cells | `associate.py purity data.h5cd --emb hic_umap,rna_umap --k 15` |

Spot-level correlations (every spot a sample) are pseudo-replicated — never the headline; the `bin`
command prints one only for contrast.

Per-cell values — prefer the per-cell measurement when one exists (`if.<MARK>` in `cells` is the
cell's IF value; `track:<MARK>` is the mean at DNA spots, a different quantity — name which you used): a `cells` column (`if.*`, `rna.*`, `atac.*`, `nuc_volume_um3`), `rg` / `span`
(**median over the cell's traces**), `rg_norm` (Rg ÷ its chromosome's median, removes chromosome
composition), `n_spots`, or `track:<name>` (mean of a per-spot track). Per-spot values for `bin`: any
`tracks` column (IF at the DNA locus, a radial score such as `n_rad_score`, distance to the nuclear
periphery) or `dist_to_cell_center`. **Check the direction before interpreting**: a normalised radial
score is usually 0 at the centre and 1 at the periphery (it then anti-correlates with a
distance-to-periphery track across spots — verify with `spearmanr`), so a *negative* ρ with it means
"more central".

## 2. Test
- **Spearman** by default (robust to skew; say "Spearman ρ"); give ρ, p and n.
- **Confounders** (`--covar`, default `nuc_volume_um3`): add `n_spots` for structure statistics and
  depth (`n_counts_rna`, `n_fragments_atac`, `n_contacts_hic`) for sequencing features. The script
  reports each confounder's correlation with x and y and a **partial Spearman** controlling for them.
  Nuclear size drives both IF intensity and Rg in many datasets — always mention it for cell-level
  structure associations. Report the **raw ρ as the answer** and the partial ρ as a sensitivity check;
  a covariate can be a mediator (e.g. spots per trace), so a vanishing partial ρ means "not separable
  from nuclear size / detection in these data", not "spurious".
- **Within vs between cell types** (`--group cell_type`): per-type ρ (types with ≥ 5 cells), the median
  within-type ρ and a pooled within-type ρ (percentile ranks inside each type). If the overall ρ is much
  larger than within types, the association is *driven by cell-type differences* — say so.
- Bin level: per-bin means over all spots of the chosen cells; neighbouring bins are autocorrelated,
  so the p-value is descriptive. Report n bins and spots per bin.
- Embeddings: purity = mean fraction of each cell's k nearest neighbours (Euclidean, self excluded)
  sharing its label; compare to `chance_purity` (Σ p²) and name the embedding and k.

## Checks
- Level stated (cell / bin / cell type) and n at that level.
- Method named (Spearman unless asked otherwise), p-value, direction in words.
- Confounders: nuclear size (and spots per trace / depth) mentioned with the partial correlation.
- Within-type result reported when cell types differ in both variables.
- One field of view / batch → no replicate. Correlation is not causation.

## Report
> At the ⟨level⟩ level (n = …), ⟨x⟩ and ⟨y⟩: Spearman ρ = … (p = …). Controlling for ⟨confounders⟩:
> partial ρ = …. Within cell types: … (median ρ …; pooled …) → ⟨driven by cell type / holds within⟩.
> Caveats: ….
