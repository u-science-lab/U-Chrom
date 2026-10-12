# Cross-assay analysis: one cell-type contrast across scHi-C, spatial Hi-C and imaging

"Analysis A" of the cross-assay proposal (2026-10-11), in two scripts:

- `pilot.py` (Step 0): the pilot, with its own readers of the per-cell maps and structure sets;
- `cross_assay.py` (Steps 1-2): every per-cell value from one library call, `uchrom.fea.separation_profile`, on
  each dataset's `ChromData`, plus Liu et al. 2025's DNA-MERFISH of the mouse MOp.  Its `check` stage compares the
  library with the pilot's readers (equal counts per cell; the imaging medians with the pilot's closed ranges).

## Step 0: the pilot
  The question: do excitatory neurons (ExN) and
mature oligodendrocytes (Oligo) differ in contact decay in the same direction in every sequencing dataset of
the mouse cortex, and does DNA seqFISH+ imaging agree?  The other classes (InN, Astro, OPC, Micro) give a class
ranking per dataset.

The pilot is deliberately coarse and uses only data that were already at hand: no read pairs are refetched from
GEO, and Liu 2025 was not downloaded.

## Metrics

| Data | Metric (per cell) |
|---|---|
| sequencing (atlas per-cell 1-Mb maps; Tan 2021 pairs binned the same way) | `log2((short + 0.5) / (long + 0.5))`, short = cis contacts at map offset 1 (separations 0-2 Mb, mean 1 Mb), long = offsets 19-53 (18-54 Mb), autosomes pooled; cells with >= 500 cis contacts at offsets >= 1 |
| imaging, and Dip-C 3-D models on the same loci | `log2(d_long / d_short)`, the medians of the 3-D distances of locus pairs 19-53 Mb and 1-2 Mb apart (same chromosome copy; copies and autosomes pooled); cells with >= 10 short and >= 30 long pairs |
| imaging, proximity variant | `log2(p_short / p_long)`, p = share of pairs closer than r; r = the cell's 1-Mb unit (median distance of pairs 0.75-1.25 Mb apart, `benchmarks/screcon/matched.py`) or the set's median unit |

Higher always means that the short range is relatively richer in contacts or more compact.

Per dataset, the analysis reports:

- the class medians;
- ExN - Oligo:
  - the difference of medians, with a bootstrap 95% CI over cells, Cliff's delta and the Mann-Whitney P;
  - adjusted for depth (OLS on class + log10 cis contacts; imaging: + log10 detected locus copies);
  - at depth thinned binomially to the 20th percentile;
  - without the top decile of a mitotic-band fraction: the published one where there is one (HiRES `frac_mitotic`, dscHi-C `frac_mitotic_band`), and the coarse proxy at offsets 2-12 for every dataset.

Across datasets, it reports the sign agreement of ExN - Oligo and Kendall's W of the class ranks.

Guo 2026 is analysed three ways:

- spots by dominant type;
- section r1 by the authors' domains, cortex against white matter;
- checks against the stored contact-distance histograms: the histogram bins closest to 1-2 / 19-53 Mb, and Guo et al.'s short/long ratio.

## Harmonised classes

Labels not listed are left out: other regions (olfactory bulb, striatum, claustrum MSN, hippocampus), vascular / leptomeningeal cells, and unknown cells.

| Dataset | ExN | InN | Astro | Oligo | OPC | Micro |
|---|---|---|---|---|---|---|
| hires_brain | Ex1-3 | In1-2 | Ast | Oli | - | - |
| gageseq_mouse_cortex | L2/3 IT CTX a-c, L2/3 IT RSP, L2 IT RvPP, L4 IT, L4/5 IT, L5 IT CTX/RSP, L6 IT, L6 CT a/b, L5/6 NP, L5 PT, L6b | Pvalb a/b, Sst a/b, Vip, Lamp5, Sncg, Meis2 | Astro | ODC | OPC | Micro |
| droplet_hic_mouse_cortex | ITL23GL, ITL45GL, ITL5GL, ITL6GL, CTGL, PTGL, NPGL, CLAGL | PVGA, SSTGA, VIPGA | ASC | OGC | OPC | MGL |
| paired_hic_mouse_cortex (pooled by class only) | ITL23GL, ITL5GL, ETL5GL, ITL6GL, CTGL, PTGL, NPGL, CLAGL | PVGA, VIPGA | ASC | OGC | OPC | MGL |
| dschic_aging_cortex | Excitatory neurons | Inhibitory interneurons | Astrocytes | Oligodendrocytes | Oligodendrocyte precursor cells | Microglial cells |
| schicar_mouse_cortex | L23IT.1-3, L45IT, L5IT, L6IT, L6CT, PT, L56NP, CLA | Pvalb, Sst, Vip, Lamp5 | Astro | Oligo | OPC | MGL |
| tan2021_cortex (pairs; Dip-C models) | Cortical L2-5 / L6 Pyramidal Cell | Interneuron | Adult Astrocyte | Mature Oligodendrocyte | Oligodendrocyte Progenitor | Microglia Etc. |
| hicrna_mouse_brain (spots: dominant type; >= 50,000 contacts) | L2_3 IT, L4, L5 IT, L5 PT, L6 IT, L6 CT, NP, L6b | Pvalb, Sst, Vip, Lamp5, Sncg, Meis2 | Astro | Oligo | - | - |
| hicrna_mouse_brain, r1 domains | cortex = domains 0 + 2 (L5-6, L2-4) | | | white matter = domain 7 | | |
| takei2021_brain | Excitatory | Pvalb, Vip, Ndnf, Sst | Astrocyte | Oligodendrocyte (lineage: may hold OPCs) | - | Microglia |
| liu2025_mop (`cross_assay.py`) | `cluster_class` Gluta (other subclasses) | `cluster_class` GABA (other subclasses) | subclass Astro | subclass Oligo | subclass OPC | subclass Micro |

## Running the pilot

The pilot runs on Sherlock (`sherlock/pilot.sbatch`):

1. The imaging structure sets are built from the registered files with `benchmarks/screcon/matched_data.py`:
   - `takei-brain --split labels|kmeans --min-detect 0.2`;
   - `dipc --rep 1`.
2. The stages `imaging`, `guo`, `tan`, `seq` and `analyze` run in that order.
3. The per-cell tables are archived on Oak (`$OAK/uchrom/results/cross_assay/<date>_pilot_<job>/`).

The headline numbers are `results/pilot.json` (with provenance) and `results/pilot.md`.  `results/MANIFEST.md` lists the runs.

## Steps 1-2: `cross_assay.py`

The same question and statistics (the pilot's functions are imported), with every per-cell value from
`uchrom.fea.separation_profile` (`SeparationParams` defaults: short = separations [1, 2) Mb, long = [19, 54) Mb,
bin / locus midpoint to midpoint, chrX / chrY / chrM left out; the profile at 1-Mb offsets 0-199 is kept per cell):

- sequencing: the per-cell maps linked to each atlas store (map offset 1 over offsets 19-53, as in the pilot);
- Tan 2021: the contact pairs binned into a `.scool` at 1 Mb (`uchrom.io.pairs_to_scool`; pairs are 1-based, the
  pilot binned `pos // 1 Mb`, so a few contacts at bin edges move);
- imaging: the Liu 2025 store (`liu2025_mop`, 11,045 traced cells; built on Sherlock by `sherlock/liu2025.sbatch`)
  and the pilot's structure sets as `ChromData` (one trace per cell, copy and chromosome); the median distance of
  pairs [19, 54) Mb over [1, 2) Mb apart.

It adds Astro - Oligo per dataset (Takei 2021 put Oligo above Astro, the reverse of every sequencing dataset; Liu
2025 separates Oligo from OPC).  On Sherlock: `sherlock/cross_assay.sbatch` (stages `seq tan imaging check
analyze`; the code from a repository copy synced through the DTN, the pilot's sets and tables as inputs), archived
to `$OAK/uchrom/results/cross_assay/<date>_full_<job>/`; results `results/cross_assay.json` / `.md`.

## Distance space: EMber reconstructions (`recon.py`)

Single-cell Hi-C reconstructed with the frozen EMber (1 Mb, CPU), stored as ChromData and summarised by the same
`separation_profile` call as the imaging data; then, per cis pair of the Liu 2025 imaging loci, the ExN - Oligo
difference of the median distance (`uchrom.fea.distance_map`) in imaging and in each reconstruction.

- Diploid where the contacts are phased (Tan 2021 Dip-C, HiRES), and as a calibration haploid on the same contacts,
  down-sampled to 150k / 45k / 20k cis contacts, and from Tan's 1-Mb maps; haploid from the atlas 1-Mb maps for the
  inbred datasets (GAGE-seq, dscHi-C, Droplet Hi-C, scHiCAR).  The authors' structures (Dip-C, hickit) on the same
  grid as a reference.
- Results (`results/recon_summary.md`): every reconstruction ranks the classes as imaging does (Droplet swaps ExN
  and InN); ExN - Oligo +0.19 to +0.30 (imaging +0.27); the locus-level difference maps agree with imaging,
  Spearman 0.54-0.69 after detrending by separation (0.50-0.63 pair-specific; shuffled labels -0.08), which is
  0.69-0.87 of the agreement their split-half reliabilities allow (Spearman-Brown).  Haploid reconstructions keep the
  ranking and most of the locus pattern but their effect size drifts with depth (0.20 -> 0.35 from all contacts to
  20k): compare directions, rankings and patterns across datasets, not sizes.  Takei 2021 is too noisy at the locus
  level (split-half 0.04).

## Datasets

All datasets are registered:

- the atlas stores `hires_brain`, `gageseq_mouse_cortex`, `droplet_hic_mouse_cortex`, `paired_hic_mouse_cortex`, `dschic_aging_cortex`, `schicar_mouse_cortex` and `hicrna_mouse_brain`, read over HTTP;
- `tan2021_cortex` (GEO GSE146397);
- `takei2021_brain` (Zenodo 4708112, Table S7);
- `liu2025_mop` (4DN `4DNFID46OABK` + `4DNFICX8IVEK`, fetched with md5 checks; `apps/atlas/recipes/README.md`);
- `hires2023_brain` (the 426 HiRES brain cells' pairs and structures, GEO GSE223917; cells of the authors' metadata in
  `data/hires_brain_cells.tsv`, from the atlas store `hires_brain`).
