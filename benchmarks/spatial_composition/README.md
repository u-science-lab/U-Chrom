# spatial_composition: spot compartments as mixtures of cell-type compartments

The analysis behind the Brief Communication's Fig. 2 (u-chrom-paper, `manuscripts/nmeth-bc`): a spatial Hi-C
spot's A/B compartments are the mixture of its cells' compartments.  Its figure data go to the paper repository
(`manuscripts/nmeth-bc/figures/results/spatial_composition.{npz,json}`, found as in `benchmarks/_paper.py`).

## Run

```bash
python benchmarks/spatial_composition/spatial_composition.py --workers 12
# a subset of stages (each stage reads the previous stages' files in the cache):
python benchmarks/spatial_composition/spatial_composition.py --stages analysis
```

- **Time:** about 100 s end to end with `--workers 12` (Apple silicon, local disk).
- **Disk:** the cache (`--out`, default `example-data/spatial_composition_cache/`, git-ignored) is about 2 GB
  (per-spot banded arrays of the two Guo sections). The figure data are about 0.5 MB.
- **Inputs:** read through the stores' linked files (`ChromData.read(..., backed=True)`,
  `load_linked_scool(key=...)['path']`, `linked_cool_path(...)`, `resolve_link_path(...)`). Every dataset is in
  `example-data/README.md`:
  - `spatial_hicrna/hicrna_mouse_brain.chromdata.zarr`: per-spot 1-Mb `.scool` for r1 / r2, bulk `.mcool`, spot RNA
    h5ad, and ssA/B (used only to orient E1).
  - `gageseq2024/gageseq_mouse_cortex.chromdata.zarr`, `droplet_hic2024/paired_hic_mouse_cortex.chromdata.zarr`,
    `schicar_mop/schicar_mop.chromdata.zarr`: per-cell 1-Mb `.scool` + RNA h5ad + labels.
  - `spatial_hic_chen2026/cortex_adult_10um.chromdata.zarr`: reprocessed per-spot `.scool` of Adult16_HiC, the RNA
    h5ad of the adjacent section Adult15_RNA, and the `Region` layer annotation.
- **Dependencies:** `uchrom`, `cooler`, `h5py`, `numpy`, `pandas`, `scipy`, `anndata`. Nothing else.

## Stages

| stage | output (in `--out`) | what |
|---|---|---|
| `e1` | `e1.npz` | E1 of the Guo r1 bulk at 1 Mb (ICE in memory; the `.mcool` has no weights), oriented per chromosome by the published ssA/B, z-scored per chromosome, autosomes only |
| `scores` | `spots_{r1,r2}_{numc,nump,den}.npy`, `spots_*_meta.npz`, `ref_{gage,paired,schicar}.npz`, `chen.npz` | banded linear compartment scores: per spot for Guo; pooled per (class × random half) for the references; pooled per (layer × random quarter) for Chen |
| `geometry` | `geometry.parquet` | Guo cortex mask, relative depth (0 = pia, 1 = white matter), spot QC |
| `composition` | `comp_{guo,chen}_{ref}.parquet` | NNLS deconvolution of spot RNA on 14 classes, one run per reference |
| `analysis` | `<figdata>/spatial_composition.npz`, `.json` (default: the paper repository) | all statistics and the figure arrays. The JSON holds every key number with a description of how it was computed |

## Method in brief

**Score.** For bin i of a spot, s_i = N_i / D_i.
- N_i = Σ_j C_ij v_ij and D_i = Σ_j C_ij, over cis partners j with |i − j| ≥ 2 bins.
- Both are kept in 5 distance bands (2–3, 3–6, 6–12, 12–25, ≥ 25 Mb).
- The bands are summed with fixed weights, so that each band contributes equally to the Guo r1 cortex pool.
- N and D add up over cells. So a pool of spots, or a spot made of several cells, has the contact-weighted mixture
  of its parts' scores. This is what makes the composition model linear.

**Composition.**
- Each spot's raw RNA is deconvolved by non-negative least squares on 14 coarse classes, separately with each
  reference: L2/3 IT, L4/5 IT, L6 IT, L5 PT, NP, L6 CT(+L6b), Pvalb, Sst, CGE, Astro, Oligo, OPC, Micro, Vasc.
- Markers: the top 200 per class, with rRNA / mitochondrial / capture-artefact genes removed.
- Gene platform factors come from the cortex pseudo-bulk. The fit is Poisson-weighted.
- The main composition is the UMI share.

**Model.**
- Observed deviation of a pool: δ = s(pool) − s(cortex pool).
- Predicted deviation: Δ = Σ_k π_k (S_k − S̄), where S_k is the class profile from the reference's single cells.
- One slope b (δ ≈ bΔ) absorbs the protocol scale.
- Explained share = 1 − (reproducible variance of δ − bΔ) / (reproducible variance of δ). Reproducible variance =
  the covariance between random split halves of the spots, averaged over 20 splits; each half is predicted from its
  own spots' composition.
- Nulls permute the class labels of the reference profiles.

## Pitfalls (each is explicit in the code)

1. **Bin layouts differ.**
   - The Guo maps list chr1, chr2, chrX, chr3, …; the references use natural order; Chen has another bin count.
   - At scoring time every per-bin array is mapped by (chrom, start) onto one canonical layout (the Guo r1 bulk
     bins).
   - Comparing arrays by position gave near-zero agreement in the exploratory analysis.
2. **Distance decay.** The plain partner score v = e_j is confounded by the contact-distance decay P(d). The main
   score is distance-centred: v = e_j − mean(e_j, e_mirror) = (e_j − e_{2i−j}) / 2. Its expectation is zero for any
   P(d). The plain score is kept as a sensitivity check (`explained_plain_*`).
3. **Guo array QC.**
   - The first and last barcode rows of each array carry 5–8× the median contacts.
   - r2 has a dead barcode column (x = 11, about 560 contacts per spot).
   - Spots on edge rows, in dead columns (median contacts < 5 % of the section), or with < 50k contacts are excluded.
4. **Imputed published A/B.** The published single-spot A/B of both studies is Higashi-imputed, so it is used only
   for the sign of E1. Chen's Hi-C-side label-transfer scores come from the Hi-C itself and are not used as
   composition.
5. **The Guo "mouse brain" sections are not cortex sections.** They are coronal sections through the dorsal
   hippocampus, and the references have no hippocampal types. The analysis is restricted to the cortex strip, using
   an RNA-only mask: pia = left tissue edge; white matter = arc of oligodendrocyte genes.

## Not included

These exploratory checks were run during the feasibility analysis (2026-10-06) and are not part of Fig. 2 or of
this script:
- short/long-range contact share by layer;
- RNA-residual check;
- retrosplenial-subtype split (16 classes);
- L4/L5 IT split (15 classes);
- barcode-row channel test.
