# Example data

Catalog of the datasets used by the tutorials (under `tutorials/`) and
benchmarks (under `benchmarks/`).  Small files (< 10 MB) are checked
into the repo; larger files are listed here with their source URL and
auto-downloaded by the tutorials on first run into this directory.

## Contents at a glance

| File / target location                | Size    | Shipped in repo | Auto-download | Used by                                                                 |
| ------------------------------------- | ------- | --------------- | ------------- | ----------------------------------------------------------------------- |
| `cell1.pairs`                         | 4.7 MB  | yes             | —             | `reconstruction.ipynb`, root README CLI example                         |
| `cell2.pairs.gz`                      | 5.4 MB  | yes             | —             | (available for experimentation; bulkier variant of `cell1.pairs`)       |
| `IMR90_chr21_30kb.cool`               | 280 KB  | yes             | —             | `gem_fish_reconstruction` tutorial (Hi-C side); `call_tads_di` test + `benchmarks/cd2_callers_validation.py` |
| `4DNFIFINA2U9.csv`                    | 58 KB   | yes             | —             | Takei 2021 cell table (RNA counts, nuclear area) for `from_fofct(cell_table=…)`, web browser; `benchmarks/cd2_upgrade_validation.py` (1.x → 2.0); `benchmarks/cd2_zarr_validation.py` (→ `.chromdata.zarr`); `benchmarks/fofct_roundtrip_validation.py` (FOF-CT writer) |
| `4DNFIJ52NVDV.csv`                    | 219 KB  | yes             | —             | Takei 2021 nascent RNA spots for `from_fofct(rna_table=…)`, web browser; `benchmarks/cd2_upgrade_validation.py` (1.x → 2.0); `benchmarks/cd2_zarr_validation.py` (→ `.chromdata.zarr`); `benchmarks/fofct_roundtrip_validation.py` (FOF-CT writer) |
| `takei2025_cerebellum_fixture/`       | ~750 KB | **missing** — listed but never committed (see its section) | — | `seqfish_multiomics_cerebellum` tutorial (Takei 2025 loader fixture) |
| `sim_cell1/` (`sim_cell1.cdz` + mcool) | 1.4 MB | yes             | —             | web browser: single-cell 3-D structure + its own contacts (`build_sim_cell1.py`); `tests/browser_web/test_genome_views.py`; `benchmarks/cd2_zarr_validation.py` (→ `.chromdata.zarr`) (from the former 1.x `.h5cd`) |
| `mESC_Sox2_5cells_{wnan,imputed_linear,imputed_snapfish}.h5cd` | 24 KB each | yes | — | imputation tests / tutorial (Huang 2021 mESC Sox2, 5 cells; see `mESC_Sox2_README.md`); `benchmarks/cd2_upgrade_validation.py` (1.x → 2.0); `benchmarks/cd2_zarr_validation.py` (→ `.chromdata.zarr`); kept as 1.x files so the upgrade path stays exercised |
| `takei2025_fov0/takei2025_fov0.chromdata.zarr` (older builds: `.h5cd`) | 73 MB (h5cd 1.x: 220 MB) | no | Zenodo 7693825 (streamed) | web browser: 59 IF tracks per spot, 47 cells, IF embedding (`build_takei2025_fov0.py`); `benchmarks/omics_embeddings.py`; `benchmarks/cd2_upgrade_validation.py` (1.x → 2.0); `benchmarks/cd2_zarr_validation.py` (→ `.chromdata.zarr`); `tests/browser_web` (real-data checks) |
| `schicar_mop/*.chromdata.zarr` (older builds: `.h5cd`), `*.mcool, *.cool, *.scool` | ~400 MB | no  | built from GEO GSE305439 | web browser: scHiCAR without 3-D, RNA / ATAC / Hi-C embeddings (`build_schicar_mop.py`); `benchmarks/omics_embeddings.py`; `benchmarks/cd2_upgrade_validation.py` (1.x → 2.0); `benchmarks/cd2_zarr_validation.py` (→ `.chromdata.zarr`) |
| `takei2025_cerebellum/takei2025_cerebellum_rep1.h5cd` | 6.3 GB (h5cd 1.x); 2.8 GB tarball | no | Zenodo 7693825 (built by PR #64's `build_takei2025_cerebellum.py`) | `benchmarks/cd2_zarr_validation.py` (→ `.chromdata.zarr`); `benchmarks/fig2/` panels b, c (whole-cell subsets, 1e4–1e7 spots) |
| `liu2025_mop/liu2025_mop.h5cd`        | 1.57 GB (h5cd 1.x); 1.7 GB FOF-CT CSV | no | 4DN public S3 (built by PR #64's `build_liu2025_mop.py`) | `benchmarks/cd2_zarr_validation.py` (→ `.chromdata.zarr`) |
| Takei 2025 full Zenodo dump           | ~8 GB   | no              | **manual**    | `seqfish_multiomics_cerebellum` tutorial (real-data run)                |
| `4DNFIHF3JCBY.csv`                    | 22 MB   | no              | 4DN public S3 | `loop_calling`, `tad_calling`, `compartment`, `fishnet_domains` tutorials; `tests/core/test_fofct_writer.py` (skipped when absent); `benchmarks/fofct_roundtrip_validation.py` (FOF-CT writer) |
| `liu2025_mop/4DNFID46OABK.csv` + `4DNFICX8IVEK.csv` | 1.68 GB + 17 MB | no | 4DN public S3 (see its section) | `benchmarks/fofct_roundtrip_validation.py` (FOF-CT writer) |
| `DNAseqFISH+.zip`                     | 144 MB  | no              | Zenodo 3735329 | `jie_aligner` tutorial                                                 |
| `IMR90_chr21-18-20Mb.csv`             | 2 MB    | no              | GitHub raw    | `gem_fish_reconstruction` tutorial                                     |
| `DNAseqFISH+/*.csv` (extracted)       | ~35 MB each | no          | from the zip  | `jie_aligner` tutorial                                                  |
| `H1Esc-HFF.R1.tar.gz`                 | 128 MB  | no              | UW Noble lab  | `higashi_embedding` tutorial (sci-Hi-C H1Esc+HFF mix)                   |
| `H1Esc-HFF.R1.labeled`                | 92 KB   | no              | UW Noble lab  | `higashi_embedding` tutorial (cell-type labels)                         |
| `with_loops.h5cd`                     | 24 MB   | no              | generated     | output of `loop_calling.ipynb` (intermediate cache, safe to delete)     |
| `fofct_core.csv`                      | ~6 MB   | no              | generated     | synthetic offline fallback for tutorials 4/5/6/7                        |
| `GSE63525_GM12878_insitu_primary+replicate_combined_30.hic` | ~40 GB | no | **manual** (too large) | `benchmark.ipynb` |
| `schicar_mop/raw/GSE305439/` RNA + metadata | 61 MB | no | GEO GSE305439 | scHiCAR tutorials (upstream input) |
| `schicar_mop/raw/GSE305439/` pairs | 1.47 GB | no | GEO GSE305439 (opt-in, `--schicar_dna`) | `build_schicar_mop.py` contact maps, scHiCAR tutorials |
| `schicar_mop/raw/GSE305439/` ATAC fragments + `schicar_mop/raw/mm10.refGene.gtf.gz` | 1.35 GB + 13 MB | no | GEO GSE305439 + UCSC (opt-in, `--schicar_atac`) | `build_schicar_mop.py` ATAC embedding + gene activity |
| `schicar_mop/raw/merfish_mop/` | 332 MB | no | Brain Image Library g.21 | `schicar_to_merfish_mapping.ipynb` (upstream input) |
| `schicar_mop/data/…`, `schicar_mop/organized_u_chrom_framework/…` | — | no | **derived — recipe pending** | scHiCAR tutorials (see below) |

`*.csv`, `*.h5cd`, `*.chromdata.zarr`, `*.cdz` (except
`sim_cell1/sim_cell1.cdz`) and the DNAseqFISH+ zip/folder are ignored by
git; they're either generated or downloaded on demand.  The builders write
the format 2.0 `.chromdata.zarr` store (`--format h5cd` still writes the
deprecated HDF5 file); older `.h5cd` builds keep working (they are read,
and `python -m uchrom.io.upgrade` converts them).

## Small, in-repo datasets

### `cell1.pairs` — single-cell Hi-C read pairs (Stevens 2017)

- **Format**: plain-text `.pairs` (no header) with 7 tab-separated columns
  `read_id, chrom1, pos1, chrom2, pos2, strand1, strand2`.
- **Content**: 105,700 paired-end reads from one mESC G1 cell.
- **Source**: Stevens et al. 2017, *Nature* 544:59–64, "3D structures of
  individual mammalian genomes studied by single-cell Hi-C".  GEO
  accession [GSE80006](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE80006).
  Distributed with the Nuc Dynamics software (github.com/tjs23/nuc_dynamics).
- **Used by**: `tutorials/reconstruction.ipynb` (Nuc Dynamics worked example);
  mentioned in the root `README.md` CLI demo.

### `cell2.pairs.gz` — single-cell Hi-C (v1.0 pairs format, gzipped)

- **Format**: gzipped pairs **v1.0** (with `##` header), 503,720 reads.
- **Source**: same Stevens 2017 dataset, a different cell.
- **Used by**: not wired into any tutorial yet — kept for users who want
  to experiment with a larger, header-carrying pairs file.

### `takei2025_cerebellum_fixture/` — Takei 2025 cerebellum DNA seqFISH+ slice (~750 KB)

> **Not in the repository.**  This entry predates the checks: the folder
> (and its `derive_fixture.py` / `verify.py`) was never committed.  For a
> real Takei 2025 subset use `takei2025_fov0/` below; the description is
> kept for whoever restores the fixture.

- **Format**: three CSVs that together exercise the
  `read_seqfish_multiomics` loader end-to-end —
  - `dna_spots.csv` — 1 070 rows from `cerebellum_rep1_pos0.csv`
    (rep 1, FOV 0, 6 cells, chr19 only), all 76 source columns preserved
    verbatim (59 z-scores + 3 DBSCAN allele variants + μm coordinates +
    `dot_int / n_rad_score / n_per_dist(um)`).
  - `locus_annotation.csv` — the 838 chr19 rows from
    `LC1-100k-09022022-mm10-25kb-meta.csv` trimmed to
    `name/chrom/start/end`.
  - `clustering.csv` — the 6 matching rows from
    `100k-002-001-cerebellum_mRNA_cluster_nuc_vol_filtered.csv`.
  - `derive_fixture.py` — the slicing script for reproducibility.  Not
    executed in CI.
  - `verify.py` — five-layer correctness check (HDF5 layout +
    `ChromData` consistency + value-level row reconciliation against
    the source CSVs + semantic checks + `.h5cd` round-trip).  Run
    `python example-data/takei2025_cerebellum_fixture/verify.py` to
    re-validate; pass `--skip-value-recon` plus `--spot-glob/--locus/
    --clustering` paths to validate the full Zenodo data instead.
- **Cell-type coverage**: the 6 cells span leiden clusters
  {0, 2, 3, 4, 6, 7} → cell types Granule, Bergmann, *Other*, MLI1,
  Purkinje, MLI2+PLI (one cell per type).
- **Source**: Takei et al. 2025, *Nature* "Spatial multi-omics reveals
  cell-type-specific nuclear compartments"
  (doi:10.1038/s41586-025-08838-x).  Raw data: Zenodo record
  [7693825](https://zenodo.org/records/7693825).  Locus annotation +
  clustering CSVs: CaiGroup/dna-seqfish-plus-multi-omics GitHub repo.
- **Used by**: `seqfish_multiomics_cerebellum.ipynb` (loader walk-through
  + `.h5cd` round-trip).
- **Real-data run**: the full distribution (rep 1 + rep 2 tarballs,
  ~8 GB compressed; tens of GB uncompressed; tens of millions of spots)
  is *not* auto-fetched.  Manual download:
  ```bash
  wget https://zenodo.org/records/7693825/files/cerebellum_rep1.tar.gz
  wget https://zenodo.org/records/7693825/files/cerebellum_rep2.tar.gz
  git clone https://github.com/CaiGroup/dna-seqfish-plus-multi-omics.git
  ```
  Then point the loader at the extracted CSV(s):
  ```python
  cd = ChromData.from_seqfish_multiomics(
      spot_glob='cerebellum_rep*/cerebellum_rep*_pos*.csv',
      locus_annotation='dna-seqfish-plus-multi-omics/data/annotation/'
                       'LC1-100k-09022022-mm10-25kb-meta.csv',
      cell_clustering='dna-seqfish-plus-multi-omics/data/cerebellum/'
                      'clustering/100k-002-001-cerebellum_mRNA_cluster_nuc_vol_filtered.csv',
  )
  ```

### `4DNFIFINA2U9.csv` + `4DNFIJ52NVDV.csv` — Takei 2021 FOF-CT companion tables (58 KB + 219 KB)

- **Format**: 4DN FOF-CT v0.1 CSV (`##`-headers; both files label their
  namespace `4dn_FOF-CT_quality` although they are the *cell* and *RNA*
  tables).
  - `4DNFIFINA2U9.csv` — *cell data*, 201 rows:
    `Cell_ID, Extra_Cell_ROI_ID, keep1, cent_ROI_x, cent_ROI_y, area(um2),
    area_cyto(um2)` + RNA copy numbers of 45 genes (Eef2 … Zfp352).
  - `4DNFIJ52NVDV.csv` — *nascent RNA spots*, 3,335 rows:
    `Spot_ID, X, Y, Z (µm), RNA_name, Gene_ID, Cell_ID, Extra_Cell_ROI_ID,
    Peak_Intensity`; 23 genes.
- **Pairs with** the core table `4DNFIHF3JCBY.csv` (same 201 `Cell_ID`s,
  same micron frame): 4DN experiment `4DNEXM45AILX`, experiment set
  [`4DNESL2AY9CM`](https://data.4dnucleome.org/experiment-set-replicates/4DNESL2AY9CM/).
- **Source**: Takei et al. 2021, *Nature* 590:344–350, "Integrated spatial
  genomics reveals global architecture of single nuclei".  Downloaded from
  the 4DN open-data bucket:
  ```
  https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/c5bafa92-d08b-4e20-84de-6e75103c016d/4DNFIFINA2U9.csv
  https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/4b66ffc5-50e0-4832-99c2-0020c934ff24/4DNFIJ52NVDV.csv
  ```
  SHA-256 `ebeca858…9941` / `70171dfd…bd2`.
- **Used by**: `ChromData.from_fofct(core, cell_table=…, rna_table=…)` →
  `cd.cells` (`rna.<gene>` columns, `nucleus_area_um2`, …) and
  `cd.points['rna']`; `tests/core/test_fofct_companions.py`; the web
  browser (colour cells by a gene, show RNA spots).
- The same set also has sequential IF (17 chromatin marks) described in the
  paper; it is not among the 4DN FOF-CT files.

### `IMR90_chr21_30kb.cool` — Rao 2014 IMR90 chr21 at 30 kb (0.3 MB)

- **Format**: single-resolution cooler.  1 557 bins × 30 kb covering
  chr21 (hg38).
- **Content**: IMR90 in situ Hi-C pair counts from Rao et al. 2014,
  aggregated from the native 5 kb to 30 kb to match the Bintu 2018
  chromatin-tracing resolution.
- **Source**: 4DN accession [4DNFI4QQPDMR](https://data.4dnucleome.org/4DNFI4QQPDMR/)
  (the full 810 MB IMR90 `.mcool`; we extract chr21 at 30 kb into this
  small `.cool` for redistribution).
- **How it was derived**:
  ```python
  from cooler import Cooler; import cooler, numpy as np, pandas as pd
  c5 = Cooler('4DNFI4QQPDMR.mcool::/resolutions/5000')
  m = c5.matrix(balance=False, as_pixels=False).fetch('chr21')
  # aggregate 5 kb × 6 → 30 kb by summation
  f = 6; n5 = m.shape[0]; n30 = (n5 + f - 1) // f
  agg = np.zeros((n30, n30))
  for i in range(n30):
      for j in range(n30):
          agg[i,j] = m[i*f:(i+1)*f, j*f:(j+1)*f].sum()
  bins = pd.DataFrame({
      'chrom': ['chr21']*n30,
      'start': np.arange(n30)*30_000,
      'end':   np.minimum((np.arange(n30)+1)*30_000, c5.chromsizes['chr21']),
  })
  iu = np.triu_indices(n30, k=0)
  pixels = pd.DataFrame({'bin1_id': iu[0], 'bin2_id': iu[1],
                          'count': agg[iu].astype(np.int64)})
  pixels = pixels[pixels['count'] > 0]
  cooler.create_cooler('IMR90_chr21_30kb.cool', bins, pixels, assembly='hg38')
  # Balance with ICE so reconstruct_gem_fish can pull balanced counts:
  # python -m cooler balance IMR90_chr21_30kb.cool
  ```
- **Used by**: `gem_fish_reconstruction.ipynb` — paired with the Bintu
  2018 FISH CSV for the paper-faithful Part 2 run.

## Large datasets — auto-downloaded on first run

The tutorials locate these files via a `find_*()` helper that:
1. Returns any cached copy under `example-data/` or `~/Downloads/…`.
2. Otherwise downloads into `example-data/` and caches for the next run.
3. Falls back to a small synthetic dataset if the network is unreachable
   (only applies to the 4DN CSV path; the Zenodo zip has no synthetic
   fallback).

Every tutorial's first data-loading cell prints the location it ends up
using.

### `IMR90_chr21_pyhim.ecsv` — Bintu 2018 IMR90 chr21 in PyHiM ECSV format (5.7 MB)

- **Format**: [PyHiM](https://github.com/pyHi-M/pyHiM) chromatin trace
  table (Astropy ECSV).  Columns: `Spot_ID, Trace_ID, x, y, z, Chrom,
  Chrom_Start, Chrom_End, ROI #, Mask_id, Barcode #, label`.
  `meta['comments']` carries `xyz_unit=micron`, `genome_assembly=hg38`.
- **Content**: hg38 chr21:18.6–20.6 Mb, 1,277 traces × 66 loci × 30 kb
  spacing.  IMR90 fibroblasts.
- **Source**: Bintu et al. 2018, *Science* 362:eaau1783, "Super-resolution
  chromatin tracing reveals domains and cooperative interactions in single
  cells".  Original CSV at
  [mendeley.com/datasets/3jkp7zhwbr/1](https://data.mendeley.com/datasets/3jkp7zhwbr/1).
- **How it was derived**: The original Bintu CSV has columns
  `Chromosome index, Segment index, Z, X, Y` (nm).  The conversion
  script `bintu_to_pyhim_ecsv.py` maps these to PyHiM schema:
  - `Chromosome index` → `Trace_ID` (1..1277)
  - `Segment index` → `Barcode #` (1..66)
  - `X, Y, Z` (nm) → `x, y, z` (microns)
  - `Chrom = chr21`, `Chrom_Start/End` derived from segment index × 30 kb
  - `Mask_id = Chromosome index` (each trace = one "cell")
  - `ROI # = 0`, `label = "None"`
- **Used by**: `import_pyhim_ecsv.ipynb` — demonstrates
  `ChromData.from_pyhim_trace()` on real chromatin tracing data;
  `benchmarks/cd2_callers_validation.py` (ChromData 2.0: structure
  callers before / after the calling convention).
- **Generated on demand**: If missing, the tutorial runs
  `bintu_to_pyhim_ecsv.py` to convert `IMR90_chr21-18-20Mb.csv` (which
  is auto-downloaded if needed).

### `4DNFIHF3JCBY.csv` — Takei 2021 mESC FOF-CT chromatin tracing (22 MB)

- **Format**: [4DN FISH Omics Format — Chromatin Tracing](https://fish-omics-format.readthedocs.io/)
  (FOF-CT) core table.  Headers (`##…`) describe the experiment;
  the data table has columns: `Spot_ID, Trace_ID, X, Y, Z, Chrom,
  Chrom_Start, Chrom_End, Cell_ID, …`.
- **Content**: mm10, 20 chromosomes × 60 bins × 25 kb, ~400 traces per
  chromosome across 201 E14 mESC cells.
- **Source**: Takei et al. 2021, *Nature* 590:344–350, "Integrated
  spatial genomics reveals global architecture of single nuclei".
  4DN portal: [data.4dnucleome.org/4DNFIHF3JCBY](https://data.4dnucleome.org/4DNFIHF3JCBY/).
- **Download URL** (public S3, no credentials needed):
  ```
  https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/e699334e-fb34-4a0e-8ef6-670b2099831a/4DNFIHF3JCBY.csv
  ```
- **Used by** (all use the `find_fofct()` helper):
  `loop_calling.ipynb`, `tad_calling.ipynb`, `compartment.ipynb`,
  `fishnet_domains.ipynb`; `benchmarks/cd2_callers_validation.py`
  (ChromData 2.0 validation, all 20 chromosomes);
  `tests/core/test_fofct_writer.py` and `benchmarks/fofct_roundtrip_validation.py` (FOF-CT writer)
  (with the cell / RNA tables `4DNFIFINA2U9.csv`, `4DNFIJ52NVDV.csv`).

### `liu2025_mop/` — Liu et al. 2025 mouse MOp DNA-MERFISH, 4DN FOF-CT (1.7 GB)

- **Source**: Liu S, … Zhuang X. "Cell type-specific 3D-genome
  organization and transcription regulation in the brain." *Sci Adv*
  (2025).  4DN experiment set
  [4DNESMTNNB3N](https://data.4dnucleome.org/experiment-set-replicates/4DNESMTNNB3N/),
  wild-type mouse primary motor cortex.
  - core table [4DNFID46OABK](https://data.4dnucleome.org/4DNFID46OABK/)
    (1,684,734,602 B):
    `https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/7c153998-3e92-4dbe-8e35-7a09570e6ed3/4DNFID46OABK.csv`
  - cell table [4DNFICX8IVEK](https://data.4dnucleome.org/4DNFICX8IVEK/)
    (16,564,294 B):
    `https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/ad72715d-57cc-4d68-8ddb-536b94ed9bb0/4DNFICX8IVEK.csv`
- **Content**: 9,582,069 spots, 188,891 traces, 11,045 traced cells
  (14,733 rows in the cell table, with 240 RNA counts and cell types).
  The download helper and build script (`download_data.py --liu2025_mop`,
  `build_liu2025_mop.py`) come with PR #64.
- **Used by**: `benchmarks/fofct_roundtrip_validation.py` (FOF-CT writer).

### `IMR90_chr21-18-20Mb.csv` — Bintu 2018 IMR90 chr21:18.6–20.6 Mb chromatin tracing (2 MB)

- **Format**: CSV with header line then columns
  ``Chromosome index, Segment index, Z, X, Y``.  One row per detected
  segment per imaged chromosome.  Coordinates in nanometres.  Segment
  spacing is 30 kb.
- **Content**: 1 278 imaged chromosomes × 66 segments in IMR90 cells,
  covering chr21:18,627,714–20,577,518 (hg38).
- **Source**: Bintu et al. 2018, *Science* 362, eaau1783, "Super-
  resolution chromatin tracing reveals domains and cooperative
  interactions in single cells".  The paper is a higher-resolution
  follow-up to Wang et al. 2016 (*Science* 353:598) which Abbas et al.
  2019 (GEM-FISH) originally used; Bintu 2018 data is directly
  accessible from the authors' GitHub repository.
- **Download URL**:
  ``https://raw.githubusercontent.com/BogdanBintu/ChromatinImaging/master/Data/IMR90_chr21-18-20Mb.csv``
- **Used by**: ``gem_fish_reconstruction.ipynb`` (part 2 — real FISH
  data).  The tutorial synthesises a matching Hi-C from the FISH
  population-mean so it runs offline; to reproduce the paper's exact
  setup, substitute the Rao 2014 IMR90 ``.mcool`` from 4DN at 30 kb
  resolution.

### `GSE63525_GM12878_insitu_primary+replicate_combined_30.hic` — GM12878 in-situ combined Hi-C (~40 GB)

- **Format**: Juicer `.hic` — a multi-resolution contact matrix file
  (read with `hicstraw`).
- **Content**: GM12878 lymphoblastoid cells, in-situ Hi-C, primary +
  replicate merged and MAPQ ≥ 30 filtered.  Contains every standard
  Juicer resolution from 1 kb to 2.5 Mb, all chromosomes.
- **Source**: Rao et al. 2014, *Cell* 159:1665–1680, "A 3D map of the
  human genome at kilobase resolution reveals principles of chromatin
  looping".
- **Download**: **not** auto-fetched (40 GB is too large to ship through
  `download_data.py`).  Grab it manually from one of:
  - [4DN DCIC — 4DNFI1UEG1HD](https://data.4dnucleome.org/files-processed/4DNFI1UEG1HD/)
  - [GEO GSE63525](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE63525)
    (look for `GSE63525_GM12878_insitu_primary+replicate_combined_30.hic`)
- **Used by**: `benchmark.ipynb` (MDS reconstruction benchmark).  The
  tutorial checks `example-data/` first and falls back to the
  `UCHROM_GM12878_HIC` env var, so you can keep the file on an external
  drive: `export UCHROM_GM12878_HIC=/path/to/…_combined_30.hic`.

### `DNAseqFISH+.zip` — Takei 2021 raw seqFISH+ spots (144 MB)

- **Format**: zip containing 8 CSVs — 4 replicates at 1-Mb resolution
  and 4 at 25-kb resolution.  Columns:
  `fov, channel, cellID, regionID (hyb1-60), x, y, z, dot_intensity,
  chr{N}_intensity × 20, chromID, labelID`.
- **Content**: same experiment as the FOF-CT above, but **before**
  trace assignment — every row is a detected fluorescent spot with a
  decoded chromosome ID but ambiguous fiber assignment (median 6
  candidate spots per `(cell, chromID, region)`).  `labelID ≥ 0` marks
  the upstream pipeline's trace choice (useful as ground truth when
  benchmarking aligners).
- **Source**: Takei et al. 2021, Zenodo record [3735329](https://zenodo.org/records/3735329),
  doi:10.5281/zenodo.3735329.
- **Download URL**:
  ```
  https://zenodo.org/records/3735329/files/DNAseqFISH%2B.zip?download=1
  ```
- **Used by**: `jie_aligner.ipynb` (spot-to-fiber tracing).  The
  tutorial opens the CSV directly from the zip without extracting.
- **Coordinate conventions** (applied by the tutorial):
  `x, y` in pixels × 103 nm/pixel; `z` in pixels × 250 nm/pixel.

### `H1Esc-HFF.R1.tar.gz` + `H1Esc-HFF.R1.labeled` — Kim 2020 sci-Hi-C (128 MB + 92 KB)

- **Format**: tarball of per-cell `.matrix` files; each is a sparse
  triplet `bin1<TAB>bin2<TAB>count<TAB>weight<TAB>chrom1<TAB>chrom2`,
  with `bin1`/`bin2` as **global bin indices** across the whole hg19
  genome at 500 kb (offsets are not encoded — derive them by min-bin
  per chrom across the cells, or compute from canonical hg19
  chromsizes).  Chromosome strings are prefixed `human_` (e.g.
  `human_chr14`).  The companion `*.labeled` is a 2-column TSV
  `matrix_filename<TAB>cell_type` with values in `{H1Esc, HFF}`.
- **Content**: 1 931 cells (750 H1Esc + 1 181 HFF), pooled from a
  combinatorial-indexing sci-Hi-C library at 500 kb.  Used as a
  benchmark in Kim et al.'s topic-model paper.
- **Source**: Kim et al. 2020, *Nature Communications* 11:6386, "Capturing cell
  type-specific chromatin compartment patterns by applying topic
  modeling to single-cell Hi-C data" — accompanying website at
  [noble.gs.washington.edu/proj/schic-topic-model](https://noble.gs.washington.edu/proj/schic-topic-model/).
- **Download URLs**:
  ```
  https://noble.gs.washington.edu/proj/schic-topic-model/data/matrix_files/H1Esc-HFF.R1.tar.gz
  https://noble.gs.washington.edu/proj/schic-topic-model/data/matrix_labels/H1Esc-HFF.R1.labeled
  ```
- **Used by**: `higashi_embedding.ipynb` (FastHigashi cell embedding +
  ARI vs ground-truth labels).  The tutorial picks a balanced subset
  (e.g. 150 H1Esc + 150 HFF), converts each `.matrix` to Higashi v2
  contact-pair format, runs FastHigashi at rank 64 with
  ``do_conv/do_rwr/do_col=True``, and reports ARI / NMI between the
  k-means clustering of `cd.cellm['higashi']` and the cell-type labels.
  Reproduces ARI ≈ 0.55 on a Mac mini M2 in ~2 min on CPU at 300 cells.

### scHiCAR mouse brain + MERFISH MOp (`schicar_mop/`)

Used by `schicar_to_merfish_mapping.ipynb`,
`schicar_merfish_uchrom_framework_walkthrough.ipynb` and (paths only,
no data needed) `schicar_linked_multiomics_framework.ipynb`.  The
notebooks read `$UCHROM_SCHICAR_ROOT`, defaulting to
`example-data/schicar_mop/`.

**Upstream sources (public, auto-downloadable):**

- **scHiCAR** — Wei X, Xu Y, Yang D, … Diao Y. "Trimodal single-cell
  profiling of transcriptome, epigenome and 3D genome in complex tissues
  with scHiCAR." *Nature Biotechnology* (2026),
  doi:[10.1038/s41587-026-03013-7](https://doi.org/10.1038/s41587-026-03013-7).
  GEO [GSE305439](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE305439)
  (`mouse_brain_scHiCAR_1`, mouse frontal cortex; SubSeries of GSE305889,
  BioProject PRJNA1305748).  Files under
  `https://ftp.ncbi.nlm.nih.gov/geo/series/GSE305nnn/GSE305439/suppl/`:

  | File | Size | Content |
  |------|------|---------|
  | `GSE305439_RNA.matrix.mtx.gz` / `.barcodes.tsv.gz` / `.features.tsv.gz` | 61 MB | RNA counts (10x-style MTX) |
  | `GSE305439_mouse_brain_scHiCAR_1_RNA_metadata.txt.gz` | 152 KB | 5 313 cells: `RNAbarcode, nCount_RNA, nFeature_RNA, celltype, UMAP1, UMAP2, DNAbarcode` |
  | `GSE305439_DNA.dedup.pairs.gz` | 1.47 GB | deduplicated contact pairs (keyed by DNA barcode) |
  | `GSE305439_DNA.ATAC.tsv.gz` | 1.35 GB | ATAC fragments `chrom, start, end, DNA barcode, 2-nt tag, strand` (175,496,023 fragments, all from the 5,313 metadata cells) |

  `python example-data/download_data.py --schicar_rna` fetches the RNA
  side; `--schicar_dna` (opt-in, 1.47 GB) the pairs; `--schicar_atac`
  (opt-in, 1.36 GB) the ATAC fragments plus the gene annotation below.

- **UCSC mm10 refGene** (NCBI RefSeq genes on mm10, UCSC Genome Browser;
  Navarro Gonzalez et al. 2021, *Nucleic Acids Res* 49:D1046) —
  `https://hgdownload.soe.ucsc.edu/goldenPath/mm10/bigZips/genes/mm10.refGene.gtf.gz`
  (13 MB, GTF) → `schicar_mop/raw/mm10.refGene.gtf.gz`; gene body + 2 kb
  upstream windows for ATAC gene activity in `build_schicar_mop.py`.
  Fetched by `--schicar_atac`.  The larger
  sibling subseries (e.g. GSE267126) are multi-TB and are not used.

- **MERFISH MOp atlas** — Zhang M, Eichhorn SW, Zingg B, … Zhuang X.
  "Spatially resolved cell atlas of the mouse primary motor cortex by
  MERFISH." *Nature* 598:137–143 (2021),
  doi:[10.1038/s41586-021-03705-x](https://doi.org/10.1038/s41586-021-03705-x).
  Brain Image Library, doi:[10.35077/g.21](https://doi.org/10.35077/g.21);
  processed files under
  `https://download.brainimagelibrary.org/cf/1c/cf1c1a431ef8d021/processed_data/`:
  `counts.h5ad` (305 MB, all 12 experiments, volume-normalised cell ×
  258 genes) and `cell_labels.csv` (27 MB, `sample_id, slice_id,
  class_label, subclass, label`).  The tutorials use experiment
  `mouse2_sample1`.  Fetch with `--merfish_mop`.

**Derived inputs — recipe pending.**  The notebooks do not read the raw
files directly; they read intermediates that were produced outside this
repository and whose build scripts are not yet checked in:

| Derived file (relative to `$UCHROM_SCHICAR_ROOT`) | Derived from |
|---|---|
| `data/schicar/schicar_rna_mop.h5ad` | GSE305439 RNA + metadata (MOp-matched cells) |
| `data/schicar/hic_features.csv` | GSE305439 pairs → per-cell contact summary features |
| `data/schicar/atac_features.npz` | GSE305439 ATAC → per-cell 1 Mb bins |
| `data/schicar/paper_loops_5kb.csv`, `paper_loop_density_5kb.npz` | scHiCAR paper 5 kb loop calls |
| `data/merfish_mop/merfish_mouse2sample1.h5ad` | BIL `counts.h5ad` + `cell_labels.csv`, `mouse2_sample1` |
| `organized_u_chrom_framework/GSE305439_scHiCAR1_MOp_MERFISH_linked_framework.{h5cd,h5mu}` + `_summary.json`, 1 Mb `.scool` | all of the above + Tangram mapping |

Until the build scripts land (tracked as an open item; see the
tutorials' first cell), these two notebooks are **not reproducible from
public data alone** and are shipped with their recorded outputs.

### `sim_cell1/` — NucDynamics single-cell structure + its contacts (1.4 MB, in repo)

- **Content**: `sim_cell1.cdz` (0.7 MB; a one-file `.chromdata.zarr`
  store, converted from the former 1.3 `sim_cell1.h5cd` of 1.6 MB with
  `python -m uchrom.io.upgrade`) — NucDynamics (`uchrom.recon.sc.nucdyn`,
  CPU) on `cell1.pairs` (Stevens et al. 2017, mESC G1, mm10): 20
  chromosomes, 25,654 particles at ~100 kb, one trace per chromosome,
  coordinates in model units; `cell1_contacts.mcool` — the same cell's
  105,700 contacts at 100 kb / 200 kb / 500 kb / 1 Mb, linked with
  `cd.link_cool("cell1_contacts.mcool")` (path relative to the store).
- **Rebuild**: `python example-data/build_sim_cell1.py [--arch cpu] [--format cdz|zarr|h5cd]`.
- **Check**: bins in contact in the input are ~2× closer in the model
  (median 3D distance of contacted / non-contacted 1 Mb pairs = 0.44–0.59
  on chr1, 2, 5, 11, 19) — `tests/browser_web/test_genome_views.py`.
- **Used by**: web browser (3D + contact + distance matrices).

### `takei2025_fov0/` — Takei 2025 cerebellum, rep 1 FOV 0, first 47 cells (73 MB, built)

- **Content**: DNA seqFISH+ traces (383,674 spots, 1,500 traces, 47
  cells: Granule, Bergmann, Purkinje, MLI1, MLI2+PLI, Other) with **59
  per-spot immunofluorescence / RNA-FISH channels as `tracks`** (H3K27ac,
  H3K4me3, H3K27me3, H3K9me3, LaminB1, …), cell types and the published
  UMAP (`cellm['umap']`); per-cell means of the 48 IF channels as
  `cells['if.<mark>']` and a histone / IF embedding `if_pca / _tsne /
  _umap` from the within-cell mark–mark correlations
  (`build_takei2025_fov0.py`, `--update` redoes only that step).
- **Source**: Takei et al. 2025, *Nature* (doi:10.1038/s41586-025-08838-x);
  Zenodo [7693825](https://zenodo.org/records/7693825)
  `cerebellum_rep1.tar.gz` (2.8 GB) — only the start of the first FOV is
  read (streamed); locus map and clustering from
  CaiGroup/dna-seqfish-plus-multi-omics.
- **Build**: `python example-data/build_takei2025_fov0.py [--rows 400000]`
  (~1 min, downloads ~0.1–0.3 GB of the tarball, drops the last possibly
  truncated cell) → `takei2025_fov0.chromdata.zarr` (73 MB; the 1.x
  `.h5cd` of older builds was 220 MB).
- **Used by**: web browser (genome track view, distance matrices, stats).

### `schicar_mop/` — scHiCAR mouse brain, no 3-D coordinates (built from GEO)

- **Content** (built by `python example-data/build_schicar_mop.py` from
  the GSE305439 files above):
  - `schicar_mop.chromdata.zarr` (5.4 MB; the 1.x `.h5cd` of older builds
    was 44 MB) — `ChromData` **without spots**: 5,313
    cells (RNA barcode ids, 22 cell types, QC), 500 highly variable genes
    as `rna.<gene>` (log-normalised dispersion, genes in ≥1 % cells),
    ATAC gene activity of 484 of them as `atac.<gene>` (fragment midpoints
    in gene body + 2 kb upstream, UCSC mm10 refGene), `n_fragments_atac`,
    `n_contacts_hic`; `cellm`: `paper_umap` (from the GEO metadata),
    `rna_pca / _tsne / _umap` (library-size normalised, 30 PCs),
    `atac_lsi / _tsne / _umap` (100 kb bins, TF-IDF + LSI, LSI 1 dropped:
    r = 0.97 with log depth) and `hic_pca / _tsne / _umap` (scHiCluster on
    the 1 Mb scool) — all from `uchrom.emb.embed_cells`.  The ATAC here is
    weakly peaked (TSS enrichment ≈ 2.9 on the first 5 M fragments), so
    100 kb bins beat 5–50 kb ones for cell-type structure (kNN-10 purity
    0.33 vs 0.19–0.30); `python benchmarks/omics_embeddings.py` gives the
    per-modality numbers.  `--update` redoes only the ATAC / Hi-C step;
  - `contacts_all.mcool` (42 MB) — all 120,280,303 contacts, 250 kb … 2 Mb;
  - `contacts_<celltype>.cool` — 22 pseudo-bulk maps at 500 kb;
  - `contacts_cells_1Mb.scool` (257 MB) — one map per cell (all 5,313).
  Links are stored relative to the dataset folder.
- **Used by**: web browser (matrix, embedding and field views for data
  without 3-D).

### `takei2025_cerebellum/`, `liu2025_mop/` — large real data for the format benchmarks

Both are catalogued in full (download URL, checksums, build recipe) by
PR #64 (`example-data/download_data.py --takei2025_cerebellum /
--liu2025_mop`, `build_takei2025_cerebellum.py`, `build_liu2025_mop.py`);
until it merges, the short form:

- **Takei 2025 cerebellum, replicate 1, all 3 FOVs**: Zenodo
  [7693825](https://zenodo.org/records/7693825) `cerebellum_rep1.tar.gz`
  (2.85 GB) → `takei2025_cerebellum_rep1.h5cd` (1.x, 6.29 GB): 10,912,638
  spots, 59,112 traces, 1,799 cells, 62 per-spot tracks.
- **Liu et al. 2025 mouse MOp DNA-MERFISH** (Sci Adv 2025, 4DN
  4DNESMTNNB3N): core table
  [4DNFID46OABK](https://data.4dnucleome.org/4DNFID46OABK/) (1.68 GB) +
  cell table [4DNFICX8IVEK](https://data.4dnucleome.org/4DNFICX8IVEK/) →
  `liu2025_mop.h5cd` (1.x, 1.57 GB): 9,582,069 spots, 188,891 traces,
  11,045 cells.
- **Used by**: `benchmarks/cd2_zarr_validation.py` (conversion to
  `.chromdata.zarr`, value identity, sizes) and `benchmarks/fig2/`
  (`b_storage.py`, `c_access.py`: the "chromdata.zarr 2.0" and "h5cd 2.0"
  series, Takei only).

## Generated outputs

- `with_loops.chromdata.zarr` (older runs: `with_loops.h5cd`) — created at the end of `loop_calling.ipynb` as a
  round-trip demonstration.  Safe to delete; the tutorial will
  regenerate it on next run.
- `fofct_core.csv` — a small synthetic FOF-CT that tutorials 4–7
  generate if the real Takei 2021 CSV can't be downloaded.  Has a
  hand-crafted 3-TAD + 1-loop structure purely to keep the notebook
  runnable offline.

## Pre-staging all data (optional)

Tutorials download what they need on first run, so you normally don't
have to do anything.  To pre-stage all large files (useful for
offline / CI environments), run:

```bash
python example-data/download_data.py
```

This is idempotent — files already present are skipped.

## Adding a new dataset

1. If under ~10 MB and redistributable → commit to `example-data/` and
   add a row to the "Small, in-repo datasets" table above.
2. Otherwise → add a `download_*` helper to `download_data.py`, a row
   to "Large datasets", and a `find_*()` function in whichever tutorial
   needs it (follow the existing `find_fofct()` pattern).
3. Always cite the paper + accession, and note the licence / terms of
   use where they matter.
