# Datasets: sources and recipes

Every dataset U-Chrom's tutorials, tests, benchmarks and atlas use: where it comes from (study,
accession, licence), how to get it, and who uses it.

**Where data live.**  The repository holds no data except the small fixtures of the unit tests and a
few reference tables next to the code that reads them.  Everything else lives in the *data
directory*: `$UCHROM_DATA`, else `~/.cache/uchrom` (`uchrom.datasets.data_dir()`).  Paths below
without a prefix are relative to it.  Its layout is the one the former `example-data/` folder had, so
an old folder works as `UCHROM_DATA`.

**Four ways to a dataset** (the *How to get it* column of the tables):

- **atlas `ID`**: a `.chromdata.zarr` store of the public atlas (https://uchrom-atlas-r2.u-science.org),
  opened over HTTP without downloading it: `uchrom.datasets.atlas("ID")` (backed: only what is used
  is fetched).  `python -m uchrom.datasets atlas` lists the ids.
- **fetch `NAME`**: the original files, downloaded once from their source (4DN, GEO, Zenodo, GitHub,
  UCSC, ...) into the data directory and md5-checked where the registry has a checksum:
  `python -m uchrom.datasets fetch NAME` or `uchrom.datasets.fetch("NAME")`;
  `python -m uchrom.datasets list` shows the names and `python -m uchrom.datasets path NAME` where the
  files are.  The registry is `packages/uchrom/uchrom/datasets/_sources.py`.  A few entries are
  *built* on fetch instead of downloaded whole (`packages/uchrom/uchrom/datasets/_builders.py`):
  `rao2014_imr90_chr21` / `rao2014_k562_chr21` are sliced from the GEO `.hic` over HTTP, and
  `takei2025_fov0` is streamed out of the Zenodo tarball.
- **recipe**: a script in this folder (`apps/atlas/recipes/build_*.py`, `link_*.py`) that builds a
  store or a benchmark input from fetched files, reading from and writing to the data directory.  Some
  link contact maps made from the raw reads on Sherlock (`*/sherlock/`); those are not public.
- **fixture**: a small real file in a package's `tests/fixtures/` (each folder has a README listing
  the sources), read offline by the unit tests.

Tutorials are named without `tutorials/` and `.ipynb` (the list is `tutorials/README.md`).  The paper's
figure scripts (`u-chrom-paper`, a separate repository) are named where they read these data.
`.h5cd` files of older builds are no longer read: convert them once with
`python -m uchrom.io.upgrade old.h5cd`, or rebuild.  A new dataset gets a registry entry or a recipe and
a section here in the same PR (see *Adding a new dataset* at the end).

## Contents at a glance

**In the repository: test fixtures and small reference tables**

| Dataset / location | Size | How to get it | Used by |
| --- | --- | --- | --- |
| `cell1.pairs.gz`: Stevens 2017 Cell 1 contact pairs | 1.3 MB | fixture, `packages/uchrom/tests/fixtures/` | NucDynamics / EMber / I/O tests; `build_sim_cell1.py`; `benchmarks/fig3/a_nucdyn_engine_speed.py` |
| `K562_chr21_30kb.cool`: Ray 2019 K562 Hi-C, chr21 at 30 kb (**formerly misnamed `IMR90_chr21_30kb.cool`**) | 0.28 MB | fixture, `packages/uchrom/tests/fixtures/` (source: fetch `ray2019_k562`) | DI caller, `load_cool` and GEM-FISH tests; `benchmarks/cd2_callers_validation.py`; the DI example of the docs; never paired with IMR90 imaging |
| `4DNFIFINA2U9.csv`, `4DNFIJ52NVDV.csv`: Takei 2021 cell and RNA tables (copies) | 58 KB + 219 KB | fixture, `packages/chromdata/tests/fixtures/` and `packages/uchrom/tests/fixtures/` (also fetch `takei_tables`) | FOF-CT companion-table, FOF-CT writer and cell-embedding tests |
| `mESC_Sox2_5cells_wnan.chromdata.zarr`: Huang 2021 Sox2 locus, 5 traces with missing loci | 176 KB | fixture, `packages/uchrom/tests/fixtures/` and `packages/uchrom-browser/tests/fixtures/` | imputation tests; browser data tests |
| `sim_cell1/`: NucDynamics structure of Cell 1 + its contacts (structure predates the `count_contacts` fix) | 1.4 MB | fixture, `packages/uchrom-browser/tests/fixtures/`; recipe `build_sim_cell1.py` | browser genome-view test; `benchmarks/fig2/f_roundtrip.py`; Fig. 6 agent benchmark |
| `fixture_barcode_only.ecsv`, `fixture_with_chrom.ecsv`: PyHiM ECSV traces | 1 KB each | fixture, `packages/uchrom/tests/fixtures/` | `packages/uchrom/tests/im/test_from_pyhim_trace.py` |
| `macs3/`: MACS3's own regression results (BSD 3-Clause) | 1.2 MB | fixture, `packages/uchrom/tests/fixtures/` | `packages/uchrom/tests/fea/test_peak_features.py` |
| `apps/atlas/recipes/ref_hg38/`: UCSC hg38 `gap` and `centromeres` tables | 12 KB + 1.5 KB | in this folder | `probe_human_ssab_layout.py` |
| `benchmarks/screcon/data/takei2021_1mb_loci.csv` (derived), `tan2021_adult_cortex_cells.tsv` | 78 KB + 31 KB | in the repository | `benchmarks/screcon/matched_data.py`; the cell list of fetch `tan2021_cortex` |

**Original files the tutorials fetch**

| Dataset / location | Size | How to get it | Used by |
| --- | --- | --- | --- |
| `4DNFIHF3JCBY.csv`: Takei 2021 mESC FOF-CT tracing, 25 kb | 22 MB | fetch `takei` | tutorials `chromdata_basics`, `chromdata_stores`, `import_fofct`, `plotting_and_browser`, `loop_calling`, `tad_calling`, `fishnet_domains`, `compartment`, `features`, `jie_aligner`; FOF-CT tests (skipped without it); caller, format, cell-position, simulation and Fig. 3 benchmarks |
| `4DNFIFINA2U9.csv`, `4DNFIJ52NVDV.csv`: its cell table and nascent RNA spots | 58 KB + 219 KB | fetch `takei_tables` (copies are fixtures) | tutorials `chromdata_basics`, `chromdata_stores`, `import_fofct`, `plotting_and_browser`; format and cell-position benchmarks |
| `DNAseqFISH+.zip`: Takei 2021 raw seqFISH+ spot detections | 144 MB | fetch `seqfish` | tutorial `jie_aligner`; `benchmarks/screcon/matched_data.py` |
| `IMR90_chr21-18-20Mb.csv`: Bintu 2018 IMR90 chr21 tracing | 2 MB | fetch `bintu_imr90` | tutorials `gem_fish_reconstruction`, `bulk_reconstruction`, `fish_imputation`, `import_pyhim_ecsv`; Fig. 3b / 3c |
| `IMR90_chr21_pyhim.ecsv`: the same tracing as PyHiM ECSV | 5.7 MB | recipe `bintu_to_pyhim_ecsv.py` | `benchmarks/cd2_callers_validation.py` (the `import_pyhim_ecsv` tutorial converts in the notebook) |
| `huang2021_sox2/`: Huang 2021 mESC Sox2 ORCA tracing with missing loci | 7 MB | fetch `huang2021_sox2` | tutorial `fish_imputation` |
| `kim2020_scihic/`: Kim 2020 sci-Hi-C, H1 ES + HFF, 500 kb | 128 MB + 92 KB | fetch `kim2020_scihic` | tutorial `higashi_embedding` |
| `genomes/mm10/chr19.fa.gz`, `genomes/mm10/mm10.refGene.gtf.gz`: UCSC mm10 | 19 MB + 13 MB | fetch `mm10_chr19`, `mm10_refgene` | tutorial `features` |
| `takei2025_fov0/`: Takei 2025 cerebellum, rep 1 FOV 0, first 47 cells (raw CSV + built store) | 280 MB; store 73 MB | fetch `takei2025_fov0` (built: streamed from Zenodo); recipe `build_takei2025_fov0.py` for the store | tutorial `import_seqfish_multiomics` (raw); browser tests, Fig. 2 / Fig. 6 and format benchmarks (store) |
| `stevens2017_mesc/`, `su2020_imr90/chromosome21.tsv`, `rao2014_imr90/IMR90_chr21_5kb_hg19.cool` | see the Figure 3 table | fetch `stevens2017`, `su2020_chr21`, `rao2014_imr90_chr21` | tutorials `reconstruction`; `tad_calling`, `compartment`; `bulk_reconstruction`, `gem_fish_reconstruction` |

**The atlas: original files and the stores built from them** (store ids and sizes in *The atlas* below)

| Dataset / location | Size | How to get it | Used by |
| --- | --- | --- | --- |
| `takei2025_cerebellum/`: Takei 2025 cerebellum DNA seqFISH+, rep 1, all FOVs | 2.85 GB download; combined store 2.05 GB | fetch `takei2025_cerebellum`; recipe `build_takei2025_cerebellum.py`; atlas `takei2025_cerebellum` | tutorials `features`, `cell_embeddings`, `import_seqfish_multiomics` (atlas); the two `takei2025_*auto_discovery` tutorials (local build); Fig. 2, format and cell-position benchmarks |
| `schicar_mop/`: scHiCAR mouse frontal cortex, RNA + ATAC + contacts, no 3-D | 61 MB + 1.47 GB + 1.37 GB download; store + maps ~0.4 GB | fetch `schicar_rna`, `schicar_dna`, `schicar_atac`; recipe `build_schicar_mop.py`; atlas `schicar_mouse_cortex` | tutorial `cell_embeddings` (atlas); Fig. 2e / 2f, Fig. 6, omics-embedding, spatial-composition and format benchmarks |
| `schicar_mop/raw/merfish_mop/`: MERFISH mouse MOp atlas | 332 MB | fetch `merfish_mop` | scHiCAR to MERFISH mapping (`benchmarks/schicar_merfish/`) |
| `spatial_hic_chen2026/`: Spatial Hi-C, mouse embryo / brain (Chen, Guo 2026) | 15.9 GB download; stores 0.7–16 MB + linked files | fetch `spatial_hic_chen2026`; recipes `build_spatial_hic_chen2026.py` (needs R), `link_spatial_hic_chen2026_contacts.py`; atlas `chen2026_*` | validation benchmarks; `benchmarks/spatial_composition/`; the atlas page's hero animation |
| `spatial_atac_hic/`: Spatial ATAC-Hi-C, mouse brain (Wang P. 2026) | 9.5 GB download; store + links ~0.3 GB | fetch `spatial_atac_hic`; recipes `build_spatial_atac_hic.py`, `link_spatial_atac_hic_contacts.py`; atlas `atac_hic_mouse_brain` | atlas |
| `spatial_hicrna/`: Spatial Hi-C-RNA, mouse brain / embryo, human melanoma (Guo 2026) | 2.3 GB download; contacts from 7 `.pairs.gz` of 7–160 GB on Sherlock | fetch `spatial_hicrna`; recipes `build_spatial_hicrna.py`, `link_spatial_hicrna_contacts.py`; atlas `hicrna_*` | `benchmarks/spatial_hicrna_validation.py`, `embedded_contacts.py`, `spatial_composition/` |
| `hires2023/`: HiRES mouse embryo / brain, contacts + RNA + 3-D | 70 MB + 76 GB | fetch `hires2023_meta`, `hires2023`; recipe `build_hires2023.py`; atlas `hires_embryo`, `hires_brain` | atlas; the atlas page's hero animation |
| `dschic2025/`: dscHi-C mouse cortex at 3 / 12 / 23 months | 44 GB | fetch `dschic2025_aging`; recipe `build_dschic2025.py`; atlas `dschic_aging_cortex` | atlas |
| `gageseq2024/`: GAGE-seq mouse cortex / human bone marrow CD34+ | 38 GB | fetch `gageseq2024`; recipe `build_gageseq2024.py`; atlas `gageseq_mouse_cortex`, `gageseq_human_bm_cd34` | atlas; `benchmarks/spatial_composition/` |
| `droplet_hic2024/`: Droplet Hi-C / Paired Hi-C mouse cortex | 4 MB + 72 GB | fetch `droplet_hic2024_meta`, `droplet_hic2024`; recipe `build_droplet_hic2024.py`; atlas `droplet_hic_mouse_cortex`, `paired_hic_mouse_cortex` | atlas; `benchmarks/spatial_composition/` |
| `unic2025/`: Uni-C human and mouse single cells, CTCs and bulk | 110 GB | fetch `unic2025`; recipe `build_unic2025.py`; atlas `unic_human`, `unic_mouse` | atlas |

**Benchmark sources** (Fig. 3, single-cell and bulk reconstruction, formats)

| Dataset / location | Size | How to get it | Used by |
| --- | --- | --- | --- |
| `stevens2017_mesc/`: Stevens 2017 mESC scHi-C, 8 cells, contacts + published structures | 43 MB | fetch `stevens2017`; recipe `build_stevens2017.py`; atlas `stevens2017_mesc` | tutorial `reconstruction` (Cell 1 contacts; atlas store); tutorial `chromdata_stores` (atlas); Fig. 3a and the native-engine validation |
| `bintu2018/`: Bintu 2018 chr21:28–30 Mb tracing, IMR90 + K562 | 7.8 MB + 20 MB | fetch `bintu2018` | Fig. 3b |
| `su2020_imr90/chromosome21.tsv` + `Hi-C_contacts_chromosome21.tsv`: Su 2020 IMR90 chr21 tracing + binned Hi-C | 261 MB + 1 MB | fetch `su2020_chr21` | tutorials `tad_calling`, `compartment`; Fig. 3b; `benchmarks/screcon/` and `benchmarks/bulk/` truths |
| `su2020_imr90/genomic-scale.tsv` + `Hi-C_contacts_genome-scale.tsv`: Su 2020 genome-scale DNA-MERFISH | 200 MB + 2.8 MB | fetch `su2020_genome` | `benchmarks/bulk/` (primary diploid truth); `benchmarks/screcon/diploid_sim.py` |
| `abbas2019_gemfish/`: GEM-FISH repository data (Wang 2016 FISH, TADs, Hi-C, final models) | 40 MB | fetch `abbas2019_gemfish` | Fig. 3a / 3c |
| `rao2014_imr90/IMR90_chr21_5kb_hg19.cool`, `rao2014_k562/K562_chr21_5kb_hg19.cool`: Rao 2014 Hi-C slices | 3.8 MB each | fetch `rao2014_imr90_chr21`, `rao2014_k562_chr21` (built over HTTP) | IMR90: tutorials `bulk_reconstruction`, `gem_fish_reconstruction`; both: Fig. 3b / 3c |
| `rao2014_imr90/IMR90_chr{20,22}_5kb_hg19.cool` | 7.8 MB + 3.3 MB | recipe `build_rao2014_slices.py --cell IMR90 --chroms 20` (then `22`) | Fig. 3c chr20 / chr22 |
| `ray2019_k562/4DNFI4QQPDMR.mcool`: K562 in situ Hi-C | 849 MB | fetch `ray2019_k562` | provenance of `K562_chr21_30kb.cool` |
| `4DNFIFLJGGNR.csv`: Takei 2021 mESC FOF-CT, 1 Mb genome-wide loci | 47 MB | fetch `takei2021_1mb` | `benchmarks/screcon/` (simulation truth, locus map, diploid simulation); `benchmarks/bulk/` (mESC truth) |
| `nagano2017_hap/`: Nagano 2017 haploid mESC scHi-C fend pairs + mm9 fends + chain | 1.39 GB (+5 GB streamed, 253 MB kept) | fetch `nagano2017_hap` | `benchmarks/screcon/matched.py` (step 1) |
| `takei2021_brain/`: Takei 2021 Science mouse cortex seqFISH+ tables | 597 MB | fetch `takei2021_brain` | `benchmarks/screcon/matched.py` (brain imaging reference) |
| `tan2021_cortex/`: Tan 2021 Dip-C adult cortex, 510 cells | 13 GB | fetch `tan2021_cortex` | `benchmarks/screcon/matched.py` (brain Dip-C baseline) |
| `tan2018_gm12878/`: Tan 2018 Dip-C GM12878, 17 cells | ~0.7 GB | fetch `tan2018_gm12878` | diploid EMber / NucDynamics validation |
| `wu2025_scmicroc/`: Wu 2025 scMicro-C GM12878, 12 deepest cells | 3.1 GB (102 GB streamed) | fetch `wu2025_scmicroc` | EMber deep development and test (PREREG §11); Fig. 3a / S8 |
| `rao2014_imr90/4DNFIR1JDZH7.mcool`: Rao 2014 IMR90, 4DN GRCh38 | 4.6 GB | fetch `rao2014_imr90_4dn` (**Sherlock only**; laptops read it over HTTP) | `benchmarks/bulk/`; `benchmarks/fig3/mds_vs_minimds/` (range reads) |
| `bonev2017_mesc/4DNFIC21MG3U.mcool`: Bonev 2017 mESC Hi-C, 4DN mm10 | 12.6 GB | fetch `bonev2017_mesc_4dn` (**Sherlock only**) | `benchmarks/bulk/`; `benchmarks/fig3/b_takei_bonev.py` (range reads) |
| `WTC11_HiC_2Mb.hcs`: the IGM demo input (GPL-3) | 3.9 MB | downloaded on demand by `benchmarks/bulk/_igm_bench.py` into `$UCHROM_IGM_CACHE` | IGM protocol of the native engine vs the original IGM |
| bulk IGM inputs (`fine_20kb.npz`, `igm_200kb.npz`, `su_3mb.npz`, `su_1mb.npz`, `takei_1mb.npz`) | 0.1–10 GB | **derived** on Sherlock (`benchmarks/bulk/real_inputs.py`, `sherlock/build_real.sbatch`) | `benchmarks/bulk/` |
| `liu2025_mop/`: Liu 2025 mouse MOp DNA-MERFISH, 4DN FOF-CT core + cell table | 1.68 GB + 17 MB; store 294 MB | fetch `liu2025_mop`; recipe `build_liu2025_mop.py` | Fig. 2 dataset scale; FOF-CT writer, format, streaming and cell-position benchmarks |
| `benchmarks/fig6/_data/takei2025_fov0_x{1,3,10,30}.chromdata.zarr` | 8–70 MB | **derived**: `benchmarks/fig6/make_scaled.py` (replicated FOV 0 cells, geometry only) | Fig. 6c browser benchmarks |
| `schicar_mop/data/...` (inputs of the scHiCAR to MERFISH mapping) | — | **derived, recipe pending** | `benchmarks/schicar_merfish/schicar_to_merfish_mapping.ipynb` |

## In the repository: test fixtures and small reference tables

The unit tests read these offline (`FIXTURES` in each suite's `tests/__init__.py`).  Tests that need
larger data look in the data directory (`DATA_DIR`) and skip when it is absent.

### `cell1.pairs.gz`: single-cell Hi-C read pairs of Stevens 2017 Cell 1 (fixture, 1.3 MB)

- **Location**: `packages/uchrom/tests/fixtures/cell1.pairs.gz` (4.7 MB as plain text).
- **Format**: plain-text pairs without a header, gzipped: 7 tab-separated columns
  `read_id, chrom1, pos1, chrom2, pos2, strand1, strand2`.
- **Content**: 105,700 paired-end reads from one haploid mESC G1 cell (Stevens *Cell 1*, mm10).
- **Source**: Stevens et al. 2017, *Nature* 544:59–64, "3D structures of individual mammalian genomes
  studied by single-cell Hi-C", doi:[10.1038/nature21429](https://doi.org/10.1038/nature21429).  GEO
  accession [GSE80280](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE80280) (Cell 1 =
  GSM2219497).  *Earlier versions of this catalog cited GSE80006, which is Flyamer et al. 2017
  (oocyte / zygote snHi-C), not this study.*  Distributed with the Nuc Dynamics software
  (github.com/tjs23/nuc_dynamics, `example_chromo_data.tar.gz` → `Cell_1_contacts.ncc`): every
  distinct contact of `cell1.pairs` appears in that NCC file (minus-strand ends differ by ~70 bp:
  `cell1.pairs` stores the read start on both strands).  The GEO per-cell file (`stevens2017_mesc/`,
  fetch `stevens2017`) has 111,838 contacts.
- **Used by**: `packages/uchrom/tests/recon/test_nucdyn_native.py`, `tests/recon/test_ember.py`,
  `tests/io/test_io_formats.py`; `build_sim_cell1.py` (the input of `sim_cell1/`);
  `benchmarks/fig3/a_nucdyn_engine_speed.py`.  The `reconstruction` tutorial and the root `README.md`
  now use the GEO file of the same cell (`GSM2219497_Cell_1_contact_pairs.txt.gz`, fetch
  `stevens2017`).

### `K562_chr21_30kb.cool`: K562 chr21 at 30 kb (fixture, 0.28 MB; formerly misnamed `IMR90_chr21_30kb.cool`)

- **Location**: `packages/uchrom/tests/fixtures/K562_chr21_30kb.cool`.
- **Provenance correction (Fig. 3 data check, 2026-09)**: despite its former name, this file is
  **K562** Hi-C.  Its source, 4DN [4DNFI4QQPDMR](https://data.4dnucleome.org/4DNFI4QQPDMR/)
  (849,258,990 B, md5 `84f4e708e2e7b55078b670ed4b8db709`), is "in situ Hi-C on non-heat treated K562
  cells with MboI" — experiment set 4DNESU95RUNO, Ray et al. 2019 (PMID 31506350, GEO GSE130758), Lis
  lab — not Rao et al. 2014 IMR90.  Re-deriving chr21 from that mcool with the recipe below gives a
  matrix identical to this file (all 1 557 × 1 557 entries).  Its chr21 total is 1.06 M contacts vs
  9.2 M in real Rao 2014 IMR90.  It was renamed from `IMR90_chr21_30kb.cool` (no alias kept); **do not
  pair it with IMR90 imaging**.  Real Rao 2014 IMR90: GEO GSE63525 (hg19; fetch `rao2014_imr90_chr21`
  or `build_rao2014_slices.py` → `rao2014_imr90/`) or 4DN set 4DNES1ZEJNRU (GRCh38 mcools
  4DNFIR1JDZH7, 4.6 GB, and 4DNFIJTOIGOI, 8.3 GB — both range-readable over HTTP).
- **Format**: single-resolution cooler.  1 557 bins × 30 kb covering chr21 (hg38).
- **Content**: K562 in situ Hi-C pair counts (Ray et al. 2019, control condition), aggregated from
  the native 5 kb to 30 kb.
- **Source**: 4DN accession [4DNFI4QQPDMR](https://data.4dnucleome.org/4DNFI4QQPDMR/) (849 MB K562
  `.mcool`, fetch `ray2019_k562`); chr21 at 30 kb was extracted into this small `.cool` for
  redistribution.
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
  cooler.create_cooler('K562_chr21_30kb.cool', bins, pixels, assembly='hg38')
  # Balance with ICE so reconstruct_gem_fish can pull balanced counts:
  # python -m cooler balance K562_chr21_30kb.cool
  ```
- **Used by**: tests that need any small Hi-C matrix
  (`packages/uchrom/tests/strc/test_convention.py::test_call_tads_di_matches_kernel_on_linked_cool`,
  `packages/uchrom/tests/io/test_io_formats.py::test_load_cool_pixels`,
  `packages/uchrom/tests/recon/test_gem_fish.py` with synthetic FISH),
  `benchmarks/cd2_callers_validation.py` (DI caller before / after the calling convention) and the DI
  example in `docs/source/structures/methods.md`.  The GEM-FISH tutorial used it as "IMR90" until
  2026-09; it now uses `rao2014_imr90/` (real IMR90).

### `mESC_Sox2_5cells_wnan.chromdata.zarr`: Huang 2021 Sox2 locus, 5 traces with missing loci (fixture, 176 KB)

- **Location**: `packages/uchrom/tests/fixtures/` (with `mESC_Sox2_README.md`) and
  `packages/uchrom-browser/tests/fixtures/`.  A directory store (format 2.3), converted from the former
  1.1 `.h5cd` (24 KB; in git history) with `python -m uchrom.io.upgrade`.
- **Content**: 5 traces × 41 loci = 205 spots of the 129 allele (chromosome `129`), 49 of them (24 %)
  with NaN coordinates; cells `cell_id.11`, `.14`, `.16`, `.26`, `.27`; 5 kb loci over
  34,601,078–34,806,078 (205 kb).  Extracted from the SnapFISH-IMPUTE example data (fetch
  `huang2021_sox2`: first 5 cells, region 129).
- **Source**: Huang et al. 2021, *Nature Genetics*, doi:10.1038/s41588-021-00863-6 (via
  SnapFISH-IMPUTE's example data, github.com/hyuyu104/SnapFISH-IMPUTE).
- **Used by**: `packages/uchrom/tests/im/test_impute.py`, `tests/im/test_impute_parallel.py`;
  `packages/uchrom-browser/tests/test_data.py`; the format validations
  `benchmarks/cd2_upgrade_validation.py` and `cd2_zarr_validation.py` (they read the former 1.x
  `.h5cd` files from the data directory).  The `fish_imputation` tutorial builds the same 5 traces from
  `huang2021_sox2` and writes its imputed stores to `tutorials/_out/`.

### `sim_cell1/`: NucDynamics single-cell structure + its contacts (fixture, 1.4 MB)

- **Location**: `packages/uchrom-browser/tests/fixtures/sim_cell1/`.
- **Content**: `sim_cell1.cdz` (0.7 MB; a one-file `.chromdata.zarr` store, converted from the former
  1.3 `sim_cell1.h5cd` of 1.6 MB with `python -m uchrom.io.upgrade`) — NucDynamics
  (`uchrom.recon.sc.nucdyn`, CPU) on `cell1.pairs` (Stevens et al. 2017, mESC G1, mm10): 20
  chromosomes, 25,654 particles at ~100 kb, one trace per chromosome, coordinates in model units;
  `cell1_contacts.mcool` (0.7 MB) — the same cell's 105,700 contacts at 100 kb / 200 kb / 500 kb /
  1 Mb, linked with `cd.link_cool("cell1_contacts.mcool")` (path relative to the store).
- **Known issue**: the structure was computed before the `uchrom.io.count_contacts` axis fix
  (`u-chrom-paper/manuscripts/full/figures/fig3/PLAN.md`, finding 5), so its restraints joined
  scrambled particle pairs.  The native engine (`packages/uchrom-recon`, validated against the
  original on the 8 Stevens cells) can rebuild it (`build_sim_cell1.py`, now using that engine), but
  the rebuild is deferred: the Fig. 6 agent benchmark's ground truth (`benchmarks/fig6/agent_bench/`,
  questions on bond length and contacts vs distance) was computed on this file.  Until then treat it
  as a browser / benchmark demo, not as a valid Cell 1 structure.  The mcool is built directly from
  `cell1.pairs` and is not affected.
- **Rebuild** (native engine): `pip install ./packages/uchrom-recon`, then
  `python apps/atlas/recipes/build_sim_cell1.py [--device auto|cpu|gpu] [--n-models 4] [--seed 1] [--format cdz|zarr]`
  (reads the fixture `cell1.pairs.gz`, writes `sim_cell1/` in the data directory, not the fixture);
  then regenerate the Fig. 6 agent-benchmark answers.
- **Check**: bins in contact in the input are ~2× closer in the model (median 3D distance of
  contacted / non-contacted 1 Mb pairs = 0.44–0.59 on chr1, 2, 5, 11, 19) —
  `packages/uchrom-browser/tests/test_genome_views.py`.
- **Used by**: `packages/uchrom-browser/tests/test_genome_views.py`; `benchmarks/fig2/f_roundtrip.py`
  (PDB / .3dg / .mcool rows; reads the fixture); the Fig. 6 agent benchmark
  (`benchmarks/fig6/agent_bench/`, expects `sim_cell1/sim_cell1.cdz` under `--data-root`);
  `benchmarks/cd2_zarr_validation.py` and `cd2_upgrade_validation.py` (from the former 1.x `.h5cd`);
  the web browser (3D + contact + distance matrices).

### Other files in the repository

- **Takei 2021 companion tables**: copies of `4DNFIFINA2U9.csv` and `4DNFIJ52NVDV.csv` (see *Takei
  2021 FOF-CT companion tables* below) in `packages/chromdata/tests/fixtures/` (for
  `packages/chromdata/tests/test_fofct_companions.py`) and `packages/uchrom/tests/fixtures/` (for
  `tests/io/test_fofct_writer.py`, `tests/emb/test_cell_embeddings.py`).
- **PyHiM ECSV traces**: `fixture_barcode_only.ecsv`, `fixture_with_chrom.ecsv`
  (`packages/uchrom/tests/fixtures/`), made from Bintu et al. 2018 IMR90 chr21;
  `packages/uchrom/tests/im/test_from_pyhim_trace.py`.
- **MACS3 regression results**: `packages/uchrom/tests/fixtures/macs3/` (1.2 MB) — two files of MACS3's
  own regression tests (github.com/macs3-project/MACS, `test/`, commit ee5def7fdf; BSD 3-Clause,
  `LICENSE` alongside), gzipped: `run_bdgcmp_FE.bdg` and
  `run_bdgpeakcall_w_prefix_c2.0_l200_g30_peaks.narrowPeak`.
  `packages/uchrom/tests/fea/test_peak_features.py` checks that the bdgpeakcall port writes MACS3's
  narrowPeak byte for byte.
- **UCSC hg38 reference tables**: `apps/atlas/recipes/ref_hg38/hg38.gap.txt.gz` (12 KB) and
  `hg38.centromeres.txt.gz` (1.5 KB), the UCSC hg38 `gap` and `centromeres` tables
  (goldenPath/hg38/database); the bin layout of the human Hi-C-RNA single-spot A/B
  (`probe_human_ssab_layout.py`, see `spatial_hicrna/`).
- **Benchmark tables**: `benchmarks/screcon/data/takei2021_1mb_loci.csv` and
  `tan2021_adult_cortex_cells.tsv` (see the matched-modality datasets);
  `benchmarks/bulk/results/kr_check.json`, `plumbing_imr90_chr21_22_igm200kb.json` (see the bulk
  benchmark).

## Tutorial inputs: original files

The tutorials fetch these on their first run.  Their other inputs are described with the Figure 3
datasets (`stevens2017`, `su2020_chr21`, `rao2014_imr90_chr21`) and the atlas (`stevens2017_mesc`,
`schicar_mouse_cortex`, `takei2025_cerebellum`).

### `4DNFIHF3JCBY.csv`: Takei 2021 mESC FOF-CT chromatin tracing (22 MB; fetch `takei`)

- **Format**: [4DN FISH Omics Format — Chromatin Tracing](https://fish-omics-format.readthedocs.io/)
  (FOF-CT) core table.  Headers (`##…`) describe the experiment; the data table has columns:
  `Spot_ID, Trace_ID, X, Y, Z, Chrom, Chrom_Start, Chrom_End, Cell_ID, …`.
- **Content**: mm10, 20 chromosomes × 60 bins × 25 kb, ~400 traces per chromosome across 201 E14 mESC
  cells.
- **Source**: Takei et al. 2021, *Nature* 590:344–350, "Integrated spatial genomics reveals global
  architecture of single nuclei".  4DN portal:
  [data.4dnucleome.org/4DNFIHF3JCBY](https://data.4dnucleome.org/4DNFIHF3JCBY/).  Public S3, no
  credentials needed:
  `https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/e699334e-fb34-4a0e-8ef6-670b2099831a/4DNFIHF3JCBY.csv`.
- **Used by**: tutorials `chromdata_basics`, `chromdata_stores`, `import_fofct`,
  `plotting_and_browser`, `loop_calling`, `tad_calling`, `fishnet_domains`, `compartment`, `features`,
  `jie_aligner`; `packages/chromdata/tests/test_fofct_companions.py` and
  `packages/uchrom/tests/io/test_fofct_writer.py` (skipped without it);
  `benchmarks/cd2_callers_validation.py` (ChromData 2.0 validation, all 20 chromosomes);
  `benchmarks/fofct_roundtrip_validation.py` (FOF-CT writer, with the cell / RNA tables);
  `benchmarks/cd21_streaming_validation.py` (streaming vs in-memory ArcFISH loop / TAD calls);
  `benchmarks/cell_spatial_validation.py` (cell positions); `benchmarks/cd2_upgrade_validation.py`,
  `cd2_zarr_validation.py`; `benchmarks/screcon/simulate.py` (`takei2021_25kb` truth);
  `benchmarks/fig3/b_takei_bonev.py`, `b_dimes.py` (`--takei`), `b_first_look.py` (optional mESC
  input); the quickstart and datasets pages of the docs.

### Takei 2021 FOF-CT companion tables: `4DNFIFINA2U9.csv` + `4DNFIJ52NVDV.csv` (58 KB + 219 KB; fetch `takei_tables`)

- **Format**: 4DN FOF-CT v0.1 CSV (`##`-headers; both files label their namespace
  `4dn_FOF-CT_quality` although they are the *cell* and *RNA* tables).
  - `4DNFIFINA2U9.csv` — *cell data*, 201 rows: `Cell_ID, Extra_Cell_ROI_ID, keep1, cent_ROI_x,
    cent_ROI_y, area(um2), area_cyto(um2)` + RNA copy numbers of 45 genes (Eef2 … Zfp352).
  - `4DNFIJ52NVDV.csv` — *nascent RNA spots*, 3,335 rows: `Spot_ID, X, Y, Z (µm), RNA_name, Gene_ID,
    Cell_ID, Extra_Cell_ROI_ID, Peak_Intensity`; 23 genes.
- **Pairs with** the core table `4DNFIHF3JCBY.csv` (same 201 `Cell_ID`s, same micron frame): 4DN
  experiment `4DNEXM45AILX`, experiment set
  [`4DNESL2AY9CM`](https://data.4dnucleome.org/experiment-set-replicates/4DNESL2AY9CM/).
- **Source**: Takei et al. 2021, *Nature* 590:344–350, "Integrated spatial genomics reveals global
  architecture of single nuclei".  From the 4DN open-data bucket:
  ```
  https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/c5bafa92-d08b-4e20-84de-6e75103c016d/4DNFIFINA2U9.csv
  https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/4b66ffc5-50e0-4832-99c2-0020c934ff24/4DNFIJ52NVDV.csv
  ```
  md5 `799c25d9bf53ab0104911b47946d9920` / `ef8022344853a82c93b1f59e0129e2e4` (checked by `fetch`; SHA-256
  `ebeca858…9941` / `70171dfd…bd2`).
- **Get it**: fetch `takei_tables` (into the data directory root, next to `4DNFIHF3JCBY.csv`); copies
  are fixtures of chromdata and uchrom (see above).
- **Used by**: `ChromData.from_fofct(core, cell_table=…, rna_table=…)` → `cd.cells` (`rna.<gene>`
  columns, `nucleus_area_um2`, …) and `cd.points['rna']`; tutorials `chromdata_basics`,
  `chromdata_stores`, `import_fofct`, `plotting_and_browser`; the fixture copies:
  `packages/chromdata/tests/test_fofct_companions.py`, `packages/uchrom/tests/io/test_fofct_writer.py`,
  `tests/emb/test_cell_embeddings.py`; `benchmarks/cd2_upgrade_validation.py` (1.x → 2.0),
  `cd2_zarr_validation.py` (→ `.chromdata.zarr`), `fofct_roundtrip_validation.py` (FOF-CT writer),
  `cell_spatial_validation.py` (cell positions; cell table only); the web browser (colour cells by a
  gene, show RNA spots).
- The same set also has sequential IF (17 chromatin marks) described in the paper; it is not among the
  4DN FOF-CT files.

### `DNAseqFISH+.zip`: Takei 2021 raw seqFISH+ spots (144 MB; fetch `seqfish`)

- **Format**: zip containing 8 CSVs — 4 replicates at 1-Mb resolution and 4 at 25-kb resolution.
  Columns: `fov, channel, cellID, regionID (hyb1-60), x, y, z, dot_intensity, chr{N}_intensity × 20,
  chromID, labelID`.
- **Content**: same experiment as the FOF-CT above, but **before** trace assignment — every row is a
  detected fluorescent spot with a decoded chromosome ID but ambiguous fiber assignment (median 6
  candidate spots per `(cell, chromID, region)`).  `labelID ≥ 0` marks the upstream pipeline's trace
  choice (useful as ground truth when benchmarking aligners).
- **Source**: Takei et al. 2021, Zenodo record [3735329](https://zenodo.org/records/3735329),
  doi:10.5281/zenodo.3735329;
  `https://zenodo.org/records/3735329/files/DNAseqFISH%2B.zip?download=1`.
- **Coordinate conventions**: `x, y` in pixels × 103 nm/pixel; `z` in pixels × 250 nm/pixel.
- **Used by**: tutorial `jie_aligner` (spot-to-fiber tracing; reads
  `DNAseqFISH+/DNAseqFISH+25kbloci-E14-replicate1.csv` straight from the zip, nothing is extracted).
  `benchmarks/screcon/matched_data.py takei-mesc` reads the 1 Mb tables of replicates 1 + 2 (201 + 245
  = 446 E14 cells) as the mESC imaging reference of the matched-modality comparison (also the
  matched-imaging analysis of `robust`); `locus-map` joins replicate 1 with `4DNFIFLJGGNR.csv`.

### `IMR90_chr21-18-20Mb.csv`: Bintu 2018 IMR90 chr21 chromatin tracing (2 MB; fetch `bintu_imr90`)

- **Format**: CSV with a header line, then columns `Chromosome index, Segment index, Z, X, Y`.  One row
  per detected segment per imaged chromosome.  Coordinates in nanometres.  Segment spacing is 30 kb.
- **Content**: IMR90 cells, chr21:18,627,714–20,577,518 (hg38; hg19 chr21:20,000,032–21,949,831);
  1,277 imaged chromosomes × 65 segments as the tutorials read it (earlier versions of this catalog
  said 1 278 × 66).
- **Source**: Bintu et al. 2018, *Science* 362, eaau1783, "Super-resolution chromatin tracing reveals
  domains and cooperative interactions in single cells".  The paper is a higher-resolution follow-up
  to Wang et al. 2016 (*Science* 353:598) which Abbas et al. 2019 (GEM-FISH) originally used; the
  data are in the authors' GitHub repository:
  `https://raw.githubusercontent.com/BogdanBintu/ChromatinImaging/master/Data/IMR90_chr21-18-20Mb.csv`
  (original CSV also at [mendeley.com/datasets/3jkp7zhwbr/1](https://data.mendeley.com/datasets/3jkp7zhwbr/1)).
- **Used by**: tutorial `gem_fish_reconstruction`, paired with the real Rao 2014 IMR90 Hi-C
  `rao2014_imr90/IMR90_chr21_5kb_hg19.cool` in hg19 (the tutorial sums the 5 kb Hi-C into 30 kb bins on
  the Bintu segment grid).  Result on this real pair (2026-09-27): Pearson 0.71–0.73 and mean relative
  error 0.33–0.35 against the FISH median distances (the same FISH also constrains the model).  Earlier
  versions paired it with the K562 `K562_chr21_30kb.cool` (then misnamed IMR90): Pearson 0.77, relative
  error 0.35.  Also tutorials `bulk_reconstruction` (the independent check of the MDS / IGM models),
  `fish_imputation` (300 traces for the accuracy test) and `import_pyhim_ecsv` (converted to PyHiM
  ECSV in the notebook); `bintu_to_pyhim_ecsv.py`; Fig. 3b / 3c (`benchmarks/fig3/b_first_look.py`,
  `c_gemfish_first_look.py`).

### `IMR90_chr21_pyhim.ecsv`: the Bintu 2018 tracing in PyHiM ECSV format (5.7 MB; recipe)

- **Format**: [PyHiM](https://github.com/pyHi-M/pyHiM) chromatin trace table (Astropy ECSV).
  Columns: `Spot_ID, Trace_ID, x, y, z, Chrom, Chrom_Start, Chrom_End, ROI #, Mask_id, Barcode #,
  label`.  `meta['comments']` carries `xyz_unit=micron`, `genome_assembly=hg38`.
- **Content**: hg38 chr21:18.6–20.6 Mb, 1,277 traces at 30 kb spacing, IMR90 fibroblasts.
- **How it is made**: `python apps/atlas/recipes/bintu_to_pyhim_ecsv.py` fetches `bintu_imr90` and
  writes `IMR90_chr21_pyhim.ecsv` in the data directory.  It maps the Bintu columns to the PyHiM schema:
  - `Chromosome index` → `Trace_ID`
  - `Segment index` → `Barcode #`
  - `X, Y, Z` (nm) → `x, y, z` (microns)
  - `Chrom = chr21`, `Chrom_Start/End` derived from segment index × 30 kb
  - `Mask_id = Chromosome index` (each trace = one "cell")
  - `ROI # = 0`, `label = "None"`
- **Used by**: `benchmarks/cd2_callers_validation.py` (ChromData 2.0: structure callers before / after
  the calling convention; runs the recipe when the file is missing).  The `import_pyhim_ecsv` tutorial
  does the same conversion inside the notebook and reads it with `ChromData.from_pyhim_trace()`.

### `huang2021_sox2/`: Huang 2021 mESC Sox2 tracing with missing loci (7 MB; fetch `huang2021_sox2`)

- **Files**: `huang2021_sox2/mESC_Sox2_coor_wnan.txt` (md5 `ab391637b75e412eec39d4082e6e3f8d`) — the
  coordinate table, tab-separated, one row per (`region` = allele, `haploid` = cell, `pos` = locus), a
  missing locus is a row with empty `x, y, z` (nm); `huang2021_sox2/mESC_Sox2_ann.txt` (md5
  `c28b7b7e0f590a424f255388997f54bc`) — the locus table (`region, pos, start, end`).
- **Content**: ORCA-style tracing of the *Sox2* locus in 129 × CAST mouse ES cells at 5 kb: 1,416
  cells × 2 alleles × 41 loci, 29 % of the positions without coordinates.
- **Source**: Huang et al. 2021, *Nature Genetics*, doi:10.1038/s41588-021-00863-6, as distributed
  with SnapFISH-IMPUTE ([github.com/hyuyu104/SnapFISH-IMPUTE](https://github.com/hyuyu104/SnapFISH-IMPUTE),
  MIT; `data/` at the pinned commit `7f7f1a7`).
- **Used by**: tutorial `fish_imputation` (the first 5 traces of the 129 allele, the same selection as
  the fixture `mESC_Sox2_5cells_wnan.chromdata.zarr`).

### `kim2020_scihic/`: Kim 2020 sci-Hi-C, H1 ES + HFF (128 MB + 92 KB; fetch `kim2020_scihic`)

- **Files**: `kim2020_scihic/H1Esc-HFF.R1.tar.gz` and `kim2020_scihic/H1Esc-HFF.R1.labeled`.
- **Format**: tarball of per-cell `.matrix` files; each is a sparse triplet
  `bin1<TAB>bin2<TAB>count<TAB>weight<TAB>chrom1<TAB>chrom2`, with `bin1`/`bin2` as **global bin
  indices** across the whole hg19 genome at 500 kb (offsets are not encoded — derive them by min-bin
  per chrom across the cells, or compute from canonical hg19 chromsizes).  Chromosome strings are
  prefixed `human_` (e.g. `human_chr14`).  The companion `*.labeled` is a 2-column TSV
  `matrix_filename<TAB>cell_type` with values in `{H1Esc, HFF}`.
- **Content**: 1 931 cells (750 H1Esc + 1 181 HFF), pooled from a combinatorial-indexing sci-Hi-C
  library at 500 kb.  Used as a benchmark in Kim et al.'s topic-model paper.
- **Source**: Kim et al. 2020, *Nature Communications* 11:6386, "Capturing cell type-specific chromatin
  compartment patterns by applying topic modeling to single-cell Hi-C data" — accompanying website at
  [noble.gs.washington.edu/proj/schic-topic-model](https://noble.gs.washington.edu/proj/schic-topic-model/):
  ```
  https://noble.gs.washington.edu/proj/schic-topic-model/data/matrix_files/H1Esc-HFF.R1.tar.gz
  https://noble.gs.washington.edu/proj/schic-topic-model/data/matrix_labels/H1Esc-HFF.R1.labeled
  ```
- **Used by**: tutorial `higashi_embedding` (FastHigashi cell embedding + ARI / NMI vs the cell-type
  labels).  The tutorial extracts the tarball next to the files on its first run, picks 150 cells of
  each type at random, writes the Higashi inputs, runs FastHigashi at rank 64 with
  `do_conv/do_rwr/do_col=True` and scores the k-means clustering of `cd.cellm['higashi']` against the
  labels.  An earlier version reported ARI ≈ 0.55 at 300 cells (~2 min on CPU, Mac mini M2).

### `genomes/mm10/`: UCSC mm10 chr19 sequence and refGene annotation (fetch `mm10_chr19`, `mm10_refgene`)

- **Files**: `genomes/mm10/chr19.fa.gz` (19 MB, md5 `4394207eabb880eeff44535321d6dd33`) from
  `https://hgdownload.soe.ucsc.edu/goldenPath/mm10/chromosomes/chr19.fa.gz`;
  `genomes/mm10/mm10.refGene.gtf.gz` (13 MB, GTF, md5 `954bb1999f12d10ba61917ecfa430068`) from
  `https://hgdownload.soe.ucsc.edu/goldenPath/mm10/bigZips/genes/mm10.refGene.gtf.gz`.
- **Source**: UCSC Genome Browser, mm10; refGene = NCBI RefSeq genes on mm10 (Navarro Gonzalez et al.
  2021, *Nucleic Acids Res* 49:D1046).
- **Used by**: tutorial `features` (per-bin GTF-annotation and sequence features on chromosome 19).
  The same refGene file is fetched by `schicar_atac` into `schicar_mop/raw/` for `build_schicar_mop.py`.

### `takei2025_fov0/`: Takei 2025 cerebellum, rep 1 FOV 0, first 47 cells (raw 280 MB; store 73 MB)

- **Content**: DNA seqFISH+ traces (383,674 spots, 1,500 traces, 47 cells: Granule, Bergmann,
  Purkinje, MLI1, MLI2+PLI, Other) with **59 per-spot immunofluorescence / RNA-FISH channels as
  tracks** (H3K27ac, H3K4me3, H3K27me3, H3K9me3, LaminB1, …), cell types and the published UMAP
  (`cellm['umap']`); per-cell means of the 48 IF channels as `cells['if.<mark>']` and a histone / IF
  embedding `if_pca / _tsne / _umap` from the within-cell mark–mark correlations
  (`build_takei2025_fov0.py`, `--update` redoes only that step).
- **Source**: Takei et al. 2025, *Nature* (doi:10.1038/s41586-025-08838-x); Zenodo
  [7693825](https://zenodo.org/records/7693825) `cerebellum_rep1.tar.gz` (2.8 GB) — only the start of
  the first FOV is read (streamed); locus map and clustering from CaiGroup/dna-seqfish-plus-multi-omics.
- **Raw input**: `python -m uchrom.datasets fetch takei2025_fov0` (~2 min: streams the first 400,000
  rows of FOV 0 out of the tarball, drops the last possibly cut cell →
  `takei2025_fov0/cerebellum_rep1_pos0_cells.csv`, 394,688 rows, 273 MB, md5-checked; + the locus map
  `LC1-100k-09022022-mm10-25kb-meta.csv` and the clustering
  `cerebellum_mRNA_cluster_nuc_vol_filtered.csv`).
- **Build**: `python apps/atlas/recipes/build_takei2025_fov0.py` →
  `takei2025_fov0/takei2025_fov0.chromdata.zarr` (73 MB; the 1.x `.h5cd` of older builds was 220 MB).
- **Used by**: tutorial `import_seqfish_multiomics` (raw input).  The store: the web browser (genome
  track view, distance matrices, stats); `packages/uchrom-browser/tests/test_backed.py`,
  `test_groups.py` (real-data checks, skipped without it); `benchmarks/omics_embeddings.py`;
  `benchmarks/fig2/f_roundtrip.py` (chromdata.zarr / FOF-CT / AnnData rows); Fig. 6
  (`benchmarks/fig6/bench_server.py`, `make_scaled.py`, agent benchmark `benchmarks/fig6/agent_bench/`;
  `u-chrom-paper/manuscripts/full/figures/fig6/extract_data.py`); `benchmarks/cd2_upgrade_validation.py`
  (1.x → 2.0), `cd2_zarr_validation.py` (→ `.chromdata.zarr`), `cd2_io_benchmark.py` (from the former
  `.h5cd`).

## The atlas: stores and their recipes

The public atlas (https://uchrom-atlas-r2.u-science.org, Cloudflare R2 bucket `u-chrom-atlas`) holds
self-contained `.chromdata.zarr` stores.  For each one, a recipe below builds the store and the files it
links (contact maps, AnnData, images) in the data directory from fetched files;
`python -m chromdata.embedded STORE [--upgrade]` copies the linked files into the store; and
`apps/atlas/PUBLISH.md` covers the upload, `apps/atlas/datasets.json` (display text, grouped by study)
and the catalog (`python -m chromdata.catalog build apps/atlas/datasets.json --root $UCHROM_DATA`).
`apps/atlas/benchmarks/validate.py` recomputes the checks of every store, `apps/atlas/benchmarks/hosted.py`
times the hosted browser on them, `python apps/atlas/build.py figures` draws the thumbnails of the atlas
page and `apps/atlas/hero_data.py` its hero animation (a Chen 2026 cerebellum section and three HiRES
brain cells).

| Atlas id | Size (MB) | Store (data directory) | Recipe | Inputs (fetch) |
| --- | --- | --- | --- | --- |
| `hicrna_mouse_brain`, `hicrna_mouse_embryo`, `hicrna_human_melanoma` | 2,254 / 4,578 / 2,728 | `spatial_hicrna/<id>.chromdata.zarr` | `build_spatial_hicrna.py`, `link_spatial_hicrna_contacts.py` (contacts from Sherlock) | `spatial_hicrna` |
| `chen2026_e13_embryo_50um`, `chen2026_brain_embryo_10um`, `chen2026_brain_embryo_20um`, `chen2026_cortex_adult_10um`, `chen2026_hippocampus_adult_10um`, `chen2026_cerebellum_adult_20um` | 711 / 1,887 / 1,446 / 664 / 306 / 165 | `spatial_hic_chen2026/<tissue>.chromdata.zarr` (id without `chen2026_`) | `build_spatial_hic_chen2026.py`, `link_spatial_hic_chen2026_contacts.py` (contacts from Sherlock) | `spatial_hic_chen2026` |
| `atac_hic_mouse_brain` | 390 | `spatial_atac_hic/mouse_brain.chromdata.zarr` | `build_spatial_atac_hic.py`, `link_spatial_atac_hic_contacts.py` (contacts from Sherlock) | `spatial_atac_hic` |
| `stevens2017_mesc` | 26 | `stevens2017_mesc/stevens2017_mesc.chromdata.zarr` | `build_stevens2017.py` | `stevens2017` |
| `hires_brain`, `hires_embryo` | 261 / 3,174 | `hires2023/<id>.chromdata.zarr` | `build_hires2023.py brain`, `build_hires2023.py embryo` | `hires2023_meta`, `hires2023` |
| `dschic_aging_cortex` | 2,278 | `dschic2025/dschic_aging_cortex.chromdata.zarr` | `build_dschic2025.py` | `dschic2025_aging` |
| `gageseq_mouse_cortex`, `gageseq_human_bm_cd34` | 485 / 319 | `gageseq2024/<id>.chromdata.zarr` | `build_gageseq2024.py mouse`, `build_gageseq2024.py human` | `gageseq2024` |
| `droplet_hic_mouse_cortex`, `paired_hic_mouse_cortex` | 322 / 339 | `droplet_hic2024/<id>.chromdata.zarr` | `build_droplet_hic2024.py droplet`, `build_droplet_hic2024.py paired` | `droplet_hic2024_meta`, `droplet_hic2024` |
| `schicar_mouse_cortex` | 263 | `schicar_mop/schicar_mop.chromdata.zarr` | `build_schicar_mop.py` | `schicar_rna`, `schicar_dna`, `schicar_atac` |
| `unic_human`, `unic_mouse` | 681 / 271 | `unic2025/<id>.chromdata.zarr` | `build_unic2025.py human`, `build_unic2025.py mouse` | `unic2025` |
| `takei2025_cerebellum` | 2,051 | `takei2025_cerebellum/takei2025_cerebellum_rep1.chromdata.zarr` | `build_takei2025_cerebellum.py` | `takei2025_cerebellum` |

Sizes are those of the published stores with their embedded copies (`python -m uchrom.datasets atlas`,
2026-10-06).  The Stevens 2017 store is described with the Figure 3 datasets.

### `takei2025_cerebellum/`: Takei 2025 cerebellum DNA seqFISH+, replicate 1, all FOVs

- **Source**: Takei et al. 2025, *Nature* (doi:10.1038/s41586-025-08838-x); Zenodo
  [7693825](https://zenodo.org/records/7693825) (CC-BY-4.0), `cerebellum_rep1.tar.gz` (2,846,258,062 B,
  md5 `758ebb15…4d84471d62b4`, checked by `fetch`).  Locus map and clustering from
  CaiGroup/dna-seqfish-plus-multi-omics (the same URLs as `takei2025_fov0`).  The record's other files:
  `cerebellum_rep2.tar.gz` (5.28 GB, md5 `411edf7e4ebcfaf6e6619c5c8d30c415`; fetch
  `takei2025_cerebellum_rep2`), `transcriptomic-data.zip` (0.46 GB, the RNA seqFISH spot tables of every
  sample, md5 `c29594d9ed0f4dfea67c0140c56050a1`; fetch `takei2025_rna`), `E14_rep1/2.tar.gz` (11.1 /
  11.3 GB), `NMuMG.tar.gz` (4.16 GB), a mean-IF CSV and `readme.txt` (the last four not in the registry;
  md5s from the Zenodo API).
- **Fetch / build**:
  ```bash
  python -m uchrom.datasets fetch takei2025_cerebellum                  # 2.85 GB
  python apps/atlas/recipes/build_takei2025_cerebellum.py               # ~3 min on an M5 Pro
  ```
  The tarball holds **3 FOVs** (`cerebellum_rep1_pos{0,1,2}.csv`, 2.23 / 2.77 / 2.87 GB; plus macOS
  `._*` entries, skipped).  Each FOV is loaded in its own subprocess with `read_seqfish_multiomics`
  (default `dbscan_ldp_nbr_allele` traces, DBSCAN noise dropped, 62 spot tracks) →
  `takei2025_cerebellum/fov/takei2025_cerebellum_rep1_pos<N>.chromdata.zarr`, then concatenated into
  `takei2025_cerebellum/takei2025_cerebellum_rep1.chromdata.zarr` (`--format cdz`: one zip file); stats
  in `build_summary.json`.  `--stream` builds the combined store in one pass instead
  (`takei2025_cerebellum_rep1.stream.chromdata.zarr`).  Per-FOV `.h5cd` files of older builds are no
  longer read (convert them with `python -m uchrom.io.upgrade` or rebuild).

  | | spots | traces | cells | h5cd 1.x | loader peak RSS |
  |---|---|---|---|---|---|
  | FOV 0 | 3,108,941 | 16,609 | 545 | 1.79 GB | 10.6 GB |
  | FOV 1 | 3,821,962 | 20,997 | 592 | 2.19 GB | 12.2 GB |
  | FOV 2 | 3,981,735 | 21,506 | 662 | 2.29 GB | 13.1 GB |
  | **combined** | **10,912,638** | **59,112** | **1,799** | **6.29 GB** | 13.2 GB (concat) |

  The combined `.chromdata.zarr` was **2.17 GB** as format 2.0 (Zarr + Parquet; written in 55 s from
  the per-FOV files, peak RSS 26.5 GB); read with `original_order=True` it equals the 1.x combined file
  value for value (coords, loci, trace / cell ids, 62 tracks, cells, cellm).  As format 2.1 it was
  2.94 GB and as format 2.2 2.05 GB (`*.v22.chromdata.zarr`, `benchmarks/cd22_convert_validate.py`); the
  atlas store `takei2025_cerebellum` is the format-2.2 store, `--upgrade`d (2,051 MB).

  The raw CSVs stay in `takei2025_cerebellum/raw/` (7.9 GB; `benchmarks/fig2/allele_qc.py` reads their
  three allele columns); `--drop-raw` deletes them.
- **Caveat — allele calls**: the default `dbscan_ldp_nbr_allele` traces often merge both homologs / add
  off-trace spots; see `benchmarks/fig2/allele_qc.py` and
  `u-chrom-paper/manuscripts/full/figures/fig2/results/allele_qc.json`.
- **Also**: `uchrom.io.load_takei2025_cerebellum()` returns the local store
  `takei2025_cerebellum/takei2025_cerebellum_rep1.chromdata.zarr` when it exists; otherwise (with
  `download=True`, the default) it fetches `takei2025_cerebellum` (or `takei2025_cerebellum_rep2`) and
  `takei2025_rna` (md5-checked), extracts the tarball into `takei2025_cerebellum/cerebellum_rep<N>/` and
  builds the store with a linked RNA AnnData (`takei2025_cerebellum_rep<N>.h5ad`).
- **Used by**: the atlas store (`ds.atlas("takei2025_cerebellum")`): tutorials `features` (chromosome 19
  and the IF channels it needs), `cell_embeddings`, `import_seqfish_multiomics` (its last section), the
  quickstart of the docs.  The local build: tutorials `takei2025_auto_discovery` and
  `takei2025_iterative_auto_discovery` (`load_takei2025_cerebellum()`); `benchmarks/fig2/` (`b_storage.py`,
  `c_access.py` — whole-cell subsets, 1e4–1e7 spots; 1e8 by replication, `replicate_store.py` —,
  `allele_qc.py`, `rowgroup_sweep.py`, `spot_tracks_encoding.py`, `cd22_variants.py`);
  `benchmarks/cd2_zarr_validation.py` (→ `.chromdata.zarr`, value identity);
  `benchmarks/cd21_streaming_validation.py` (2.0 → 2.1 conversion, streaming seqFISH+ import from
  `raw/`, streaming distance maps); `benchmarks/cd22_convert_validate.py` (2.1 → 2.2 conversion,
  bitwise check); `benchmarks/cell_spatial_validation.py` (cell positions).

### `schicar_mop/`: scHiCAR mouse frontal cortex, RNA + ATAC + contacts, no 3-D (Wei et al. 2026)

**Upstream sources:**

- **scHiCAR** — Wei X, Xu Y, Yang D, … Diao Y. "Trimodal single-cell profiling of transcriptome,
  epigenome and 3D genome in complex tissues with scHiCAR." *Nature Biotechnology* (2026),
  doi:[10.1038/s41587-026-03013-7](https://doi.org/10.1038/s41587-026-03013-7).  GEO
  [GSE305439](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE305439) (`mouse_brain_scHiCAR_1`,
  mouse frontal cortex; SubSeries of GSE305889, BioProject PRJNA1305748).  Files under
  `https://ftp.ncbi.nlm.nih.gov/geo/series/GSE305nnn/GSE305439/suppl/`, fetched into
  `schicar_mop/raw/GSE305439/`:

  | File | Size | Content | fetch |
  |------|------|---------|-------|
  | `GSE305439_RNA.matrix.mtx.gz` / `.barcodes.tsv.gz` / `.features.tsv.gz` | 61 MB | RNA counts (10x-style MTX) | `schicar_rna` |
  | `GSE305439_mouse_brain_scHiCAR_1_RNA_metadata.txt.gz` | 152 KB | 5 313 cells: `RNAbarcode, nCount_RNA, nFeature_RNA, celltype, UMAP1, UMAP2, DNAbarcode` | `schicar_rna` |
  | `GSE305439_DNA.dedup.pairs.gz` | 1.47 GB | deduplicated contact pairs (keyed by DNA barcode) | `schicar_dna` |
  | `GSE305439_DNA.ATAC.tsv.gz` | 1.35 GB | ATAC fragments `chrom, start, end, DNA barcode, 2-nt tag, strand` (175,496,023 fragments, all from the 5,313 metadata cells) | `schicar_atac` |

- **UCSC mm10 refGene** (NCBI RefSeq genes on mm10, UCSC Genome Browser; Navarro Gonzalez et al. 2021,
  *Nucleic Acids Res* 49:D1046) —
  `https://hgdownload.soe.ucsc.edu/goldenPath/mm10/bigZips/genes/mm10.refGene.gtf.gz` (13 MB, GTF) →
  `schicar_mop/raw/mm10.refGene.gtf.gz` (fetched with `schicar_atac`); gene body + 2 kb upstream
  windows for ATAC gene activity in `build_schicar_mop.py`.  The larger sibling subseries (e.g.
  GSE267126) are multi-TB and are not used.
- **MERFISH MOp atlas** (fetch `merfish_mop`, for the mapping analysis below) — Zhang M, Eichhorn SW,
  Zingg B, … Zhuang X. "Spatially resolved cell atlas of the mouse primary motor cortex by MERFISH."
  *Nature* 598:137–143 (2021),
  doi:[10.1038/s41586-021-03705-x](https://doi.org/10.1038/s41586-021-03705-x).  Brain Image Library,
  doi:[10.35077/g.21](https://doi.org/10.35077/g.21); processed files under
  `https://download.brainimagelibrary.org/cf/1c/cf1c1a431ef8d021/processed_data/` →
  `schicar_mop/raw/merfish_mop/`: `counts.h5ad` (305 MB, all 12 experiments, volume-normalised cell ×
  258 genes) and `cell_labels.csv` (27 MB, `sample_id, slice_id, class_label, subclass, label`).  The
  mapping analysis uses experiment `mouse2_sample1`.

**The store** (`python apps/atlas/recipes/build_schicar_mop.py`, after
`python -m uchrom.datasets fetch schicar_rna schicar_dna schicar_atac`; atlas `schicar_mouse_cortex`):

- `schicar_mop/schicar_mop.chromdata.zarr` (5.4 MB; the 1.x `.h5cd` of older builds was 44 MB) —
  `ChromData` **without spots**: 5,313 cells (RNA barcode ids, 22 cell types, QC), 500 highly variable
  genes as `rna.<gene>` (log-normalised dispersion, genes in ≥1 % cells), ATAC gene activity of 484 of
  them as `atac.<gene>` (fragment midpoints in gene body + 2 kb upstream, UCSC mm10 refGene),
  `n_fragments_atac`, `n_contacts_hic`; `cellm`: `paper_umap` (from the GEO metadata),
  `rna_pca / _tsne / _umap` (library-size normalised, 30 PCs), `atac_lsi / _tsne / _umap` (100 kb bins,
  TF-IDF + LSI, LSI 1 dropped: r = 0.97 with log depth) and `hic_pca / _tsne / _umap` (scHiCluster on
  the 1 Mb scool) — all from `uchrom.emb.embed_cells`.  The ATAC here is weakly peaked (TSS enrichment
  ≈ 2.9 on the first 5 M fragments), so 100 kb bins beat 5–50 kb ones for cell-type structure (kNN-10
  purity 0.33 vs 0.19–0.30); `python benchmarks/omics_embeddings.py` gives the per-modality numbers.
  `--update` redoes only the ATAC / Hi-C step;
- `contacts_all.mcool` (42 MB) — all 120,280,303 contacts, 250 kb … 2 Mb;
- `contacts_<celltype>.cool` — 22 pseudo-bulk maps at 500 kb;
- `contacts_cells_1Mb.scool` (257 MB) — one map per cell (all 5,313);
- `schicar_mop_rna.h5ad` — RNA UMI counts of every gene (`uns['linked_anndata']`).

Links are stored relative to the dataset folder; `python -m chromdata.embedded` embeds them for the
atlas.  In all ~400 MB plus the h5ad.

**Used by**: the atlas store: tutorial `cell_embeddings`.  The local build: the web browser (matrix,
embedding and field views for data without 3-D); `benchmarks/omics_embeddings.py`;
`benchmarks/fig2/e_contacts.py`, `e_contacts_query.py` (Fig. 2f and supplement: group pseudo-bulk vs the
per-type `contacts_<type>.cool`; link vs copy import), `f_crossmodal.py` (Fig. 2f: RNA Leiden clusters →
pseudo-bulk maps and P(s) from the linked `.scool`), `f_roundtrip.py` (Fig. 2b, .scool row);
`benchmarks/fig6/bench_server.py` (contact-map and pseudo-bulk latency); agent benchmark
`benchmarks/fig6/agent_bench/`; `benchmarks/spatial_composition/` (spot compartments vs cell-type
composition); `benchmarks/cd2_upgrade_validation.py` (1.x → 2.0), `cd2_zarr_validation.py`
(→ `.chromdata.zarr`).

**scHiCAR → MERFISH mapping — derived inputs, recipe pending.**  The mapping analysis
(`benchmarks/schicar_merfish/schicar_to_merfish_mapping.ipynb`, Tangram) reads `$UCHROM_SCHICAR_ROOT`
(required; the scHiCAR data folder, e.g. `schicar_mop/` of the data directory).  It does not read the
raw files directly but intermediates that were produced outside this repository and whose build
scripts are not yet checked in:

| Derived file (relative to `$UCHROM_SCHICAR_ROOT`) | Derived from |
|---|---|
| `data/schicar/schicar_rna_mop.h5ad` | GSE305439 RNA + metadata (MOp-matched cells) |
| `data/schicar/hic_features.csv` | GSE305439 pairs → per-cell contact summary features |
| `data/schicar/atac_features.npz` | GSE305439 ATAC → per-cell 1 Mb bins |
| `data/schicar/paper_loops_5kb.csv`, `paper_loop_density_5kb.npz` | scHiCAR paper 5 kb loop calls |
| `data/merfish_mop/merfish_mouse2sample1.h5ad` | BIL `counts.h5ad` + `cell_labels.csv`, `mouse2_sample1` |

Until the build scripts land, the mapping analysis is **not reproducible from public data alone** and
is kept with its recorded outputs.

### `spatial_hic_chen2026/`: Spatial Hi-C, mouse embryo and brain sections, no 3-D (Chen, Guo et al. 2026)

- **Source**: Chen, Guo et al. 2026, *Nature Methods*, "Spatially resolved chromatin architectures in
  mammalian brain tissues" (doi:10.1038/s41592-026-03218-3).  Processed data: Zenodo
  [17961135](https://zenodo.org/records/17961135) (CC-BY-4.0; 13 files, 15.9 GB: 12 Seurat `.qs`
  objects and one per-read cis BEDPE).  Code: Zenodo [22144954](https://zenodo.org/records/22144954)
  (MIT; its `test_data/stat_cropped.csv` holds the barcode table).  Raw reads (GSA CRA016676) are
  **not** fetched; the contacts of the other sections are reprocessed from them on Sherlock (below).
- **Download**: `python -m uchrom.datasets fetch spatial_hic_chen2026` (md5-checked) →
  `spatial_hic_chen2026/raw/zenodo17961135/`, `raw/code/`.
- **Build** (~5 min, peak ~14 GB RAM for the BEDPE step):
  1. `python apps/atlas/recipes/build_spatial_hic_chen2026.py --export` runs
     `spatial_hic_chen2026_export.R` on every `.qs`; it needs R with Seurat ≥ 5 and qs 0.27.3 (CRAN
     archive; install stringfish 0.16.0 and RApiSerialize first).  It writes
     `export/<object>/<section>/`: metadata, factor columns, embeddings, and each assay as a sparse
     matrix.  It uses the `counts` layer, or `data` where `counts` is empty (the scAB assays).  Derived
     assays (SCT, spARC_*, *_scale, BANKSY_*) are skipped.
  2. The same script, without `--export`, assembles the stores.  `--no-contacts` skips the BEDPE step.
     Existing `.scool` / `.mcool` files are reused unless you pass `--redo-contacts`.
- **Content**: one store per tissue (atlas ids `chen2026_<tissue>`).

  | Store | Spots (Hi-C / RNA) | Sections | Bins |
  |---|---|---|---|
  | `e13_embryo_50um` | 6,069 / 4,043 | 3 Hi-C + 2 RNA | 500 kb |
  | `cerebellum_adult_20um` | 12,091 / 11,931 | 2 + 2 | 500 kb |
  | `brain_embryo_20um` | 13,689 / 15,080 | E14.5, E16.5, E18.5 | 500 kb |
  | `brain_embryo_10um` | 17,204 / 23,264 | E14.5, E16.5, E18.5 | 500 + 250 kb |
  | `cortex_adult_10um` | 8,184 / 8,802 | 1 + 1 | 500 + 250 kb |
  | `hippocampus_adult_10um` | 8,601 / 9,216 | 1 + 1 | 500 kb |

  Each store is a `ChromData` **without spots**:
  - **`cells`**: one row per spot, with id `<section>:<col>x<row>`.  Columns: section, assay (hic /
    rna), grid column and row, Seurat image coordinates, and the Seurat metadata (QC, clusters,
    annotations, label-transfer and pseudotime scores).  R factors are stored as categories.
  - **Cell positions**: `cell_positions()` gives the grid column and row (unit "spot", one frame per
    section, `spot_size_um` recorded).  `cell_positions("image")` gives the pixels of the section
    image.  VisiumV1 objects store `imagecol` / `imagerow`, VisiumV2 ones `x` (= row) / `y` (=
    column).  The orientation was checked against the images: spots sit on darker tissue.
  - **`bins`**: the ssA/B bins, with a `resolution` column.
  - **`cellm`**: the published PCA / UMAP / BANKSY embeddings, keyed
    `<assay>_<reduction>.<Seurat object>`.
  - **Linked files** (paths relative to the store):
    - `<tissue>_ssab.h5ad` (`uns['linked_bin_matrices']['ssAB']`): single-spot A/B scores, Hi-C spots
      × bins (`var.bin_id` = row of `bins`).  They are not in `cellm` because `cellm` is read on open.
    - `<tissue>_images/<section>.png` (`uns['linked_images']`): the 1080 × 1080 image of each section,
      taken from the Seurat object.  It is a grayscale bright-field image, **not** an H&E stain.  Its
      pixels are the units of `cell_positions("image")`.
    - `<tissue>_rna.h5ad` (`uns['linked_anndata']`): spatial RNA counts.
  - **E13.5 section 1 only**: the per-read BEDPE becomes `e13_embryo_50um_spots_1Mb.scool` (one cis map
    per spot, cells named by cell id) and `e13_embryo_50um_bulk.mcool` (25 kb – 1 Mb).
    - Read names end in `<barcode B>_<barcode A>`; spot = `(51 − iA)x iB`.
    - One-mismatch barcodes are corrected when unambiguous.
    - Of the 86.5 M cis pairs: 79.5 M kept, 1.3 M with no barcode, 5.7 M off-tissue.
- **Validation** (`python benchmarks/spatial_hic_chen2026_validation.py`):
  - Per-spot contacts against the authors' `stat_cropped.csv`: all 1,999 spots matched, Pearson r
    (log) = 0.998.  Our totals are 0.77× theirs: the published BEDPE holds 86.5 M pairs against their
    103.2 M `cis_contact`, which is probably counted before deduplication.
  - Compartment E1 of our 500-kb bulk map against the section's mean published ssA/B, per chromosome:
    median |r| = 0.956 (min 0.923, chr3).
  - Every store: links resolve, all spots have positions, the ssA/B and RNA AnnData are aligned with
    the Hi-C / RNA spots.
- **Contacts of the other sections from the raw reads** (`apps/atlas/recipes/spatial_hic_chen2026/sherlock/`):
  - Source: GSA CRA016676 (2.31 TB, 15 spatial Hi-C runs).  `runs.tsv` maps runs to sections, from the
    GSA metadata (`raw/CRA016676.xlsx`); the mapping agrees with the barcode pixels.
  - Pipeline: read-1 barcodes → bwa mem -5SP → pairtools parse / sort / merge → exact deduplication
    within each spot → cis pairs ≥ 1 kb → per-barcode-pair `.scool` + `.mcool`.
  - Pilot CRR1161506 (= E13_HiC_R1) against the authors:
    - cis > 10 kb: 81.60 M vs 81.65 M; trans: 43.07 M vs 42.87 M.
    - Per-spot counts: Pearson r (log) 0.999.
    - Bulk 500-kb E1 against E1 from the authors' BEDPE: median |r| 0.999.
    - Pairs shorter than 1 kb are almost all inward-facing (+-), i.e. unligated fragments, and are
      dropped as HiCUP does.
  - Validation script: `benchmarks/spatial_hic_chen2026_reprocess_validation.py`.
  - Output on Oak (`$OAK/uchrom/spatial_hic_chen2026/<run>/`): dedup pairs, per-spot 1-Mb `.scool`, bulk
    `.mcool` (25 kb – 1 Mb), per-barcode statistics.  Not public: copy each run's `pixels_1Mb.scool`,
    `bulk.mcool`, `barcode_stats.tsv` and `log.json` into `spatial_hic_chen2026/contacts/` over the DTN
    (4.6 GB for the 7 runs below).
- **Reprocessed contacts linked into the stores**:
  `python apps/atlas/recipes/link_spatial_hic_chen2026_contacts.py [RUN …]` (seconds per run).
  - Which barcode pair is which spot is decided on the data.  Every candidate pairing is scored: each
    spot's contact-partner compartment profile (minus the mean over spots) against the authors' ssA/B
    of the spot it would be (minus their mean), median Pearson r over 1,500 spots.  The right pairing
    scores ~0.3, every other ~0.  A run is linked only when the best beats the runner-up by 0.05.
  - Candidates: the 8 orientations of the grid (swap the barcodes, flip either index) with our barcode
    order and with the authors' (`sherlock/barcodes_96_authors_index.tsv`, read off the `pixel` / spot
    names of brain_embryo_20um: position 2 complete, position 1 91 of 96), and `cells.pixel` (both
    orders) where a store has it.
  - Per section: `per_spot.<section>` (`<store>_<section>.<run>.reprocessed_1Mb.scool`, cells renamed
    to the store's ids) and `bulk.<section>` (`contacts/<run>.bulk.mcool`); `.reprocessed` is appended
    when the section already has maps from the authors' BEDPE (E13_HiC_R1).
    `uns['contacts_stats']['reprocessed'][<run>]` holds the counts, every candidate's score and the
    choice.

  | run | section (store) | pairing | score (runner-up) | spots linked |
  |---|---|---|---|---|
  | CRR1161506 | E13_HiC_R1 (e13_embryo_50um) | grid, swap, flip 2 — as the pilot | 0.316 (0.014) | 1,999 / 1,999 |
  | CRR1161507 | E13_HiC_R2 (e13_embryo_50um) | grid, swap, no flip | 0.304 (0.011) | 2,011 / 2,011 |
  | CRR1829212 | E14_5_HiC (brain_embryo_20um) | `pixel` as b1_b2 | 0.292 (0.002) | 3,533 / 3,533 |
  | CRR1829214 | E16_5_HiC (brain_embryo_20um) | `pixel` as b1_b2 | 0.266 (0.002) | 4,479 / 4,479 |
  | CRR1829213 | E14_5_HiC (brain_embryo_10um) | `pixel` as b1_b2 | 0.300 (0.001) | 5,426 / 5,426 |
  | CRR1829215 | E16_5_HiC (brain_embryo_10um) | `pixel` as b1_b2 (= authors' order) | 0.272 (0.004) | 5,470 / 5,470 |
  | CRR1829216 | E18_5_HiC (brain_embryo_20um) | `pixel` as b1_b2 | 0.334 (0.007) | 5,677 / 5,677 |
  | CRR1829217 | E18_5_HiC (brain_embryo_10um) | `pixel` as b1_b2, swap | 0.307 (0.007) | 6,308 / 6,308 |
  | CRR1829219 | Adult16_HiC (cortex_adult_10um) | authors' order, both flipped | 0.292 (0.003) | 7,795 / 8,184 |
  | CRR1829220 | Adult22_HiC (hippocampus_adult_10um) | authors' order, flip 2 | 0.254 (0.002) | 8,185 / 8,601 |
  | CRR1831973 | E13_HiC_R3 (e13_embryo_50um) | **not linked** (grid only; no orientation stands out) | 0.011 (0.007) | — |
  | CRR1161509 | Cere_HiC_R1 (cerebellum_adult_20um) | **not linked** | 0.003 (0.001) | — |
  | CRR1161510 | Cere_HiC_R2 (cerebellum_adult_20um) | **not linked** | 0.000 | — |

  - Checks that do not use the linking criterion (`benchmarks/spatial_hic_chen2026_reprocessed.py`, all
    10 linked sections): per-spot contact totals laid out on the grid form a tissue image, Moran's I
    0.07–0.44 (shuffled spots -0.005–0.010; lowest brain_embryo_10um E16_5 0.072 and cortex 0.119);
    bulk compartment E1 (500 kb) against the authors' mean A/B of the section, median |r| over the 19
    autosomes + X 0.92–0.96 (worst chromosome 0.45 in E16_5 20 µm, 0.47 in E16_5 10 µm).
  - E13_HiC_R1 has both: ours against the maps from the authors' BEDPE, chr2 at 1 Mb — per spot median
    pixel r 0.947 (200 spots; IQR 0.941–0.953), all spots summed r 0.988 (log 0.9997); ours hold 1.17×
    their contacts.
  - The cerebellum sections need the authors' barcode order (laid out in it, our counts form a coherent
    tissue image: Moran's I 0.85 / 0.76 against 0.26 / 0.40 in ours), but no orientation of it matches
    the published spots.  Their chip's position-1 order differs from the embryo chips' (E14.5 alone
    already swaps two pairs against E16.5 / E18.5); without the authors' barcode table for that chip
    the pairing is left open rather than fitted.
- **Used by**: the atlas (`chen2026_*`); the web browser — the Spatial view (sections over their
  images), the Genome view (ssA/B tracks per spot / group; E13.5 per-spot and pseudo-bulk contact maps),
  embeddings; `benchmarks/spatial_hic_chen2026_validation.py`, `spatial_hic_chen2026_reprocessed.py`;
  `benchmarks/spatial_composition/` (spot compartments vs cell-type composition); the cerebellum
  section outlines of the atlas page's hero animation (`apps/atlas/hero_data.py`).

### `spatial_atac_hic/`: Spatial ATAC-Hi-C, mouse brain, no 3-D (Wang P. et al. 2026)

- **Source**: Wang P. et al., "Spatial chromatin architecture and accessibility co-profiling of
  mammalian tissues", *Nature Methods* 2026 (doi:10.1038/s41592-026-03217-4).
  - Data: GEO [GSE307620](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE307620).
  - Code: GitHub `wangjuan001/Spatial-ATAC-Hi-C` (MIT), used for the read layout.
  - Two coronal sections: MouseBrainR6 (GSM9228169) and MouseBrainR8 (GSM9228170), each a 50 × 50 grid.
    The same spot barcodes carry both the ATAC and the Hi-C reads.
- **Processed files** (`python -m uchrom.datasets fetch spatial_atac_hic`, 9.5 GB →
  `spatial_atac_hic/raw/GSE307620/`):
  - cellranger-atac fragments of the ATAC library and of the Hi-C library.  **The Hi-C "fragments" are
    single fragments: the contact pairing is not in them.**
  - Visium-style tissue positions, scale factors and hires / lowres images (grayscale bright-field).
- **Build**: `python apps/atlas/recipes/build_spatial_atac_hic.py` (~10 min, 9 GB RAM) writes
  `spatial_atac_hic/mouse_brain.chromdata.zarr` (atlas `atac_hic_mouse_brain`).  It is a ChromData
  without spots with:
  - 4,290 in-tissue spots (R6 1,966, R8 2,324), with ATAC and Hi-C fragment counts per spot.
  - Grid and image-pixel positions, and the linked hires images (`mouse_brain_images/`).
  - `atac_cpm.<section>` bulk tracks on 500-kb bins.
  - `linked_bin_matrices["ATAC"]` (`mouse_brain_atac.h5ad`): spots × 500-kb log1p CPM, shown as genome
    tracks per spot / group.
  - ATAC LSI / t-SNE / UMAP from the 50,000 5-kb bins with the most fragments.
  - `atac_cluster` (k-means, k = 12).
- **Embedding choice**:
  - 100-kb / 500-kb bins carried little tissue structure: the grid distance of each spot's 10 embedding
    neighbours was 18–20 against 24 for random.
  - The top 5-kb bins give 14–16, and LSI components 1–5 are spatially smooth (neighbour r 0.6–0.9).
  - The clusters follow the anatomy (striatum, white matter, cortical layers).
- **Contacts from the raw reads** (SRA, 4 runs, 177 GB; `apps/atlas/recipes/spatial_atac_hic/sherlock/`):
  - All four runs show the same layout and about 10 % ligation junctions (`GATCGATC`): each section's
    two runs are two sequencing rounds of one ATAC-Hi-C library, and they are merged.
  - Read 2 carries the barcodes: read2[22:30] + read2[60:68] = the 16-base spot barcode.  Both linkers
    are required (the authors' `bcsplit.py` / `00.filter-linker.sh`).
  - Mapping, per-spot deduplication and the 1-kb cis cut reuse the Chen 2026 pipeline (above).
  - Output on Oak (`$OAK/uchrom/spatial_atac_hic/<section>/`, 3.3 GB): dedup pairs, per-spot 1-Mb
    `.scool`, bulk `.mcool` (25 kb – 1 Mb), per-barcode statistics.  Not public: copy the four files each
    section needs into `spatial_atac_hic/contacts/` over the DTN (recipe in the script below; 655 MB for
    both sections).

  | section | read pairs | kept contacts | spots with a map (in store) |
  |---|---|---|---|
  | MouseBrainR6 | 829.7 M | 90.6 M | 1,946 of 1,966 |
  | MouseBrainR8 | 895.1 M | 108.7 M | 2,313 of 2,324 |

  Removed: MAPQ < 30 (34 %), duplicates (11 %), cis pairs closer than 1 kb (39 %), barcodes off the
  whitelist (3 %).
- **Contacts linked into the store**: `python apps/atlas/recipes/link_spatial_atac_hic_contacts.py`
  (seconds; reads `contacts/`).  Per section:
  - `per_spot.<section>`: `mouse_brain_<section>.spots_1Mb.scool`, the pipeline's `.scool` with each cell
    renamed from its 16-base barcode to the store's id `<section>:<barcode>`.
  - `bulk.<section>`: `contacts/<section>.bulk.mcool`.
  - `uns['contacts_stats'][<section>]`: the counts above and the checks below.
- **Validation against the authors** (`cells.n_fragments_hic`, their per-spot Hi-C fragment counts):
  - Per-spot depth agrees: Pearson r of log counts 0.999 (R6) / 0.998 (R8); Spearman 0.998 / 0.997.
  - Barcode order: with barcode B before A the correlation drops to 0.20 / −0.05, so A + B (read order)
    is the store's barcode.
  - Totals: ours are 0.32 × theirs.  Theirs (R6: 263 M) lie between our kept pairs (91 M) and kept + the
    < 1 kb cis pairs (417 M); their filter is not documented closely enough to reproduce it.
  - The sum of a section's spot maps equals its bulk map pixel for pixel (r = 1.000 on chr1 at 1 Mb; 0.92
    of the bulk total — the bulk also has the spots outside the store and those under 100 pairs).
  - Compartments: PC1 of the R6 bulk O/E correlation on chr1 (1 Mb) follows the ATAC signal, |r| = 0.86.
- **Used by**: the atlas (`atac_hic_mouse_brain`); the web browser (Spatial view, ATAC tracks / domains).

### `spatial_hicrna/`: Spatial Hi-C-RNA, mouse brain / embryo, human melanoma (Guo et al. 2026)

- **Source**: Guo et al. 2026, *Cell* (doi:10.1016/j.cell.2026.07.039); GEO
  [GSE311199](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE311199).
  - Seven samples: mouse brain r1 / r2, mouse embryo E11.5 / E13.5 r1 / r2, human melanoma r1 / r2.
  - Hi-C and RNA come from the **same spots**.  Checked on mouse_brain_r1: the 10,000 RNA barcodes are
    the Hi-C grid barcodes, and all 6,275 in-tissue spots have both RNA (median 3,351 UMI) and contacts.
  - The registry fetches the processed files only (`spatial_hicrna/raw/GSE311199/`: h5ad, RNA,
    images); the per-sample `.pairs` (6.6–159 GB each, ~680 GB) are not fetched.
- **Processed on Sherlock** (`apps/atlas/recipes/spatial_hicrna/sherlock/`, `process.sbatch`):
  - Input: the published `.nodups.pairs.gz`.
  - Output on Oak (`$OAK/uchrom/spatial_3dgenome/<sample>/`, 21 GB): per-spot 1-Mb `.scool`, bulk
    `.mcool` (25 kb – 1 Mb) and per-spot statistics.
  - Kept: 31–47 × 10⁸ pairs per sample (1.2 × 10⁸ for E13.5 r2).
  - In the two E13.5 embryos 37–44 % of the pairs fall on spots outside the published tissue positions
    (about 1 % elsewhere); not yet explained.
- **Stores** (`hicrna_mouse_brain`, `hicrna_mouse_embryo`, `hicrna_human_melanoma`, also the atlas ids;
  the prefix keeps them apart from the ATAC-Hi-C `mouse_brain`):
  ```bash
  python -m uchrom.datasets fetch spatial_hicrna                  # GEO files, 2.3 GB
  python apps/atlas/recipes/build_spatial_hicrna.py               # ~2 min: RNA, images, positions, published labels / latents
  # contact maps: copy $OAK/uchrom/spatial_3dgenome/<sample>/ (17.8 GB) to spatial_hicrna/contacts/ (via the DTN)
  python apps/atlas/recipes/link_spatial_hicrna_contacts.py       # links per-spot .scool + bulk .mcool, mouse-brain ssAB
  python benchmarks/spatial_hicrna_validation.py                  # -> benchmarks/results/spatial_hicrna_validation.json
  ```
  Cells are spots (`<section>:<barcode>`); only in-tissue spots are kept (brain 6,275 / 6,199; E11.5
  32,799; E13.5 17,278 / 14,784; melanoma 6,268 / 6,381), every one with RNA and a linked contact map.
- **Single-spot A/B (ssAB)**: the authors' `X_abcompartment` is linked for mouse brain r1 only
  (`hicrna_mouse_brain_ssab.h5ad`, 6,275 x 4,816 bins).  The bin layout is not given; it is chr1–19 in
  500-kb bins from 3 Mb, dropping the last bin of a chromosome if < 100 kb.  Check: against the bulk E1
  shifted by 0 / ±1 / ±2 bins the median |r| is 0.959 / 0.897, 0.848 / 0.789, 0.724 (best at shift 0).
  The human ssAB (5,359 columns) is **not linked**.  `apps/atlas/recipes/probe_human_ssab_layout.py`
  shows what the data say: 500-kb bins from the start of each of chr1–22 (no 3 Mb offset as in the
  mouse), centromere models and the `heterochromatin` / `short_arm` gaps of the UCSC hg38 tables
  (`apps/atlas/recipes/ref_hg38/`) removed — chr1 columns match bulk E1 bin for bin (|r| 0.83–0.98) up
  to column ~240 and then again with an offset of exactly 43 bins (the 21.5 Mb of centromere +
  heterochromatin), and every chromosome start located from the first 40 retained bins has |r|
  0.74–0.98 (next-best position 0.5–0.86).  That rule gives 5,378 columns; the file has 5,359, and per
  chromosome the column counts differ from the rule by −5..+2, so the exact bins dropped near the
  centromeres are not the annotation's and the columns cannot be placed bin by bin without the
  authors' table.
- **Validation** (real data, `benchmarks/spatial_hicrna_validation.py`):
  - Spearman of per-spot RNA UMI against Hi-C contacts: 0.66 – 0.91 over the 7 samples (lowest in
    E13.5).
  - Bulk compartment E1 (500 kb), replicate vs replicate, median |r| over chromosomes: brain 0.999,
    E13.5 0.992 (min 0.84), melanoma 0.999.
  - Single-spot A/B, mouse_brain_r1: the compartment profile of a spot's own cis contacts
    (contact-weighted bulk E1 of the partner bins, 1 Mb) against its published ssAB: median r **0.043**
    (IQR 0.025–0.061, 95 % of spots > 0) against -0.001 (49 % > 0) with the spots shuffled.
    Significant but small — single spots hold few contacts, so this is weak evidence rather than a
    reproduction of ssAB.
  - Hi-C profile PCA, 15 nearest neighbours sharing the published label: cell type (23) 0.22 (shuffled
    0.11); CellCharter clusters (12) 0.42 (0.12); FH clusters (5) 0.58 (0.22).
- **Embedding for an atlas** (`chromdata.embedded`, `benchmarks/embedded_contacts.py`):
  `python -m chromdata.embedded <store>` copies the linked maps and h5ad files into the store
  (`embedded/…`, Zarr, sharded, partitioned by chromosome).  Mouse brain (2 bulk, 2 per-spot, ssAB,
  RNA): bulk 0.31–0.37x of the `.mcool`, per-spot 0.73–0.78x of the `.scool`, ssAB 0.99x, RNA 0.79x;
  matrices from the embedded store equal the linked ones exactly (8 queries + ssAB chr1); requests a
  cold reader makes: one spot on one chromosome 6 data GETs (0.06 MB), 500-spot pseudo-bulk of a
  chromosome 8 GETs (2.1 MB), bulk 10 Mb region at 25 kb 6 GETs (1.7 MB), one metadata GET to open a
  map (counted on the store layer, local disk, not measured on S3).
- **Embedded copies of all stores** (self-contained, each opens alone in the browser; sizes of the
  whole store): hicrna_mouse_brain 2.1 GB, hicrna_human_melanoma 2.5 GB, hicrna_mouse_embryo 4.3 GB,
  Chen brain_embryo_10um 1.2 GB / brain_embryo_20um 0.99 GB / e13_embryo_50um 0.68 GB, spatial_atac_hic
  mouse_brain 0.37 GB (maps, ssAB / ATAC, RNA h5ad, section images).  Checked by moving each store alone
  into an empty directory: every map, image and bin track served.  Chen cortex_adult_10um (0.63 GB) and
  hippocampus_adult_10um (0.29 GB) now have maps and are embedded too (brain_embryo_10um 1.8 GB,
  brain_embryo_20um 1.4 GB after the new runs); cerebellum_adult_20um has none (barcode table missing).
  Re-run `python -m chromdata.embedded <store>` after linking more runs (already-embedded keys are
  skipped); the link script's final `cd.write` keeps the embedded copies.  CRR1829221 / CRR1829222
  (Adult_H / Adult_Z, small runs) belong to no store.
- **Open**: the E13.5 spots outside the published mask have no image / map in the stores; human ssAB
  layout; the pairs outside the mask (37–44 %) are unexplained.
- **Used by**: the atlas (`hicrna_*`); `benchmarks/spatial_hicrna_validation.py`,
  `benchmarks/embedded_contacts.py`; `benchmarks/spatial_composition/` (spot compartments vs cell-type
  composition).

### Single-cell Hi-C / multi-omics of the atlas (`hires2023/`, `dschic2025/`, `gageseq2024/`, `droplet_hic2024/`, `unic2025/`)

The single-cell studies cited by Guo et al. 2026 (Cell; refs. 15-22) that have usable public data.  Each
build streams the deposited pairs once (`sc_hic_common.py`: `gzip -dc | grep -v '^#'` into pyarrow,
contacts binned into on-disk buckets) into a per-cell 1 Mb `.scool` and an all-cells bulk `.mcool`
(50 kb - 1 Mb, ICE), writes the RNA as a linked `.h5ad`, computes RNA PCA / UMAP and a scHiCluster Hi-C
embedding, and writes a `.chromdata.zarr`; `python -m chromdata.embedded STORE --upgrade` then embeds
the links for the atlas.  The Stevens 2017 store of the atlas (`stevens2017_mesc`) is described with the
Figure 3 datasets.

- **HiRES** (Liu et al. 2023, *Science*, doi:10.1126/science.adg3797; GEO GSE223917): 7,469 embryo cells
  (E7.0 - E9.5) + 399 adult brain cells; per cell `.pairs.gz` and the authors' diploid 20 kb hickit
  structure (`*.20k.0.clean.3dg`, brain `*.20k.3dg`), coarse-grained to 200 kb (mean of each bin's
  particles per copy); RNA = the deposited UMI table.
  - Get it: fetch `hires2023_meta` (70 MB: cell metadata + RNA UMI counts) and `hires2023` (75 GB:
    per-cell pairs + 20 kb structures, 7,895 cells, two connections at a time); then
    `python apps/atlas/recipes/build_hires2023.py embryo [--workers 8]` and `... brain` →
    `hires2023/hires_embryo.chromdata.zarr`, `hires2023/hires_brain.chromdata.zarr` (atlas
    `hires_embryo`, `hires_brain`).  The original build downloaded the series tar instead (one
    connection; per-file requests got HTTP 403 / 503 from NCBI after ~150 files).
  - Checked on 100 cells: per-cell map totals equal the pairs line counts (135,083 = 135,083), 200 kb
    coordinates equal the mean of the 20 kb particles (max |diff| 2e-6).
  - Also: three brain cells' structures in the atlas page's hero animation (`apps/atlas/hero_data.py`).
- **dscHi-C** (Wu et al. 2025, *Cell Discov.*, doi:10.1038/s41421-025-00770-8; GEO GSE285812): mouse
  cortex at 3 / 12 / 23 months, 32,777 annotated cells (`main_celltype`, `sub_celltype`), 3.24e9 pairs
  read, 2.60e9 on annotated cells.
  - Get it: fetch `dschic2025_aging` (44 GB), then `python apps/atlas/recipes/build_dschic2025.py` →
    `dschic2025/dschic_aging_cortex.chromdata.zarr` (atlas `dschic_aging_cortex`).
  - Not used: the dscHi-C-multiome deposit (GSE285233): its contact barcodes match none of the RNA
    cells (no correlation of counts; neither a 10x ARC nor ATAC whitelist), so the modalities cannot be
    paired.
- **GAGE-seq** (Zhou et al. 2024, *Nat. Genet.*, doi:10.1038/s41588-024-01745-3; GEO GSE238001): mouse
  cortex (3 libraries, 3,296 annotated cells) and human bone marrow CD34+ (3 libraries, 1,445 cells);
  cell types from the authors' GitHub (`meta_info/cell_type_annotation`, MIT, pinned commit); RNA = one
  line per UMI, gene symbols from Ensembl 98.
  - Get it: fetch `gageseq2024` (38 GB: contacts + RNA, the annotation and the Ensembl 98 GTFs), then
    `python apps/atlas/recipes/build_gageseq2024.py mouse` and `... human` →
    `gageseq2024/gageseq_mouse_cortex.chromdata.zarr`, `gageseq2024/gageseq_human_bm_cd34.chromdata.zarr`
    (atlas `gageseq_mouse_cortex`, `gageseq_human_bm_cd34`).
  - Also: `benchmarks/spatial_composition/` (mouse cortex).
- **Droplet Hi-C / Paired Hi-C** (Chang et al. 2024, *Nat. Biotechnol.*,
  doi:10.1038/s41587-024-02447-1; GEO GSE253407): mouse cortex, Droplet Hi-C 6,235 cells (LC462,
  LC716), Paired Hi-C 24,284 cells (Hi-C LC464 / LC465 / LC608 with RNA LC466 / LC467 / LC613, barcodes
  paired by the metadata).  The pairs keep every read pair; cis pairs < 1 kb are dropped.
  - Get it: fetch `droplet_hic2024_meta` (4 MB) and `droplet_hic2024` (72 GB), then
    `python apps/atlas/recipes/build_droplet_hic2024.py droplet` and `... paired` →
    `droplet_hic2024/droplet_hic_mouse_cortex.chromdata.zarr`,
    `droplet_hic2024/paired_hic_mouse_cortex.chromdata.zarr` (atlas ids the same).
  - Also: `benchmarks/spatial_composition/` (Paired Hi-C).
- **Uni-C** (Gao et al. 2025, *Nat. Commun.*, doi:10.1038/s41467-025-62215-w; GEO GSE267873): deeply
  sequenced single cells, one `.pairs.gz` each (pairtools, deduplicated, MAPQ >= 40; GRCh37 / GRCm38,
  Ensembl chromosome names): GM12878 (10), COLO320-DM (6), circulating tumour cells of the PDX mouse
  PanT24 (7) and of the KPC mice KPC0402 / KPC0403 (6 + 6), MC38 (8); bulk GM12878, COLO320-DM, PanT24
  tumour, MC38 (2).  About 90 % of the pairs are cis pairs < 1 kb (read-through fragments, the uniform
  coverage the variants come from) and are dropped.  `build_unic2025.py` (worker processes, one file
  each) writes per-cell 100 kb and 1 Mb `.scool`, per sample the merged cells and the bulk library as
  `.mcool` (ICE from 100 kb), cell statistics incl. the fractions of cis contacts at 25 kb - 2 Mb and
  2 - 12 Mb, and a scHiCluster PCA.  The per-cell VCFs are not used.
  - Get it: fetch `unic2025` (110 GB: 48 `.pairs.gz`, 43 single cells + 5 bulk libraries), then
    `python apps/atlas/recipes/build_unic2025.py human [--workers 6]` and `... mouse` →
    `unic2025/unic_human.chromdata.zarr`, `unic2025/unic_mouse.chromdata.zarr` (atlas `unic_human`,
    `unic_mouse`).
- Not fetched: ChAIR (Nat. Methods 2025; CNCB OMIX009588 / 9589, 120 GB from China), Nagano 2013 (10 Th1
  cells), Ramani 2017 sciHi-C (cell lines, hg19 / mm10 mix).

## Figure 3 datasets — bridges between contacts and geometry

Inputs of `benchmarks/fig3/` (plan and reference numbers:
`u-chrom-paper/manuscripts/full/figures/fig3/PLAN.md`).  `python -m uchrom.datasets fetch --fig3` fetches
or builds the registered ones (`stevens2017`, `bintu_imr90`, `bintu2018`, `su2020_chr21`,
`abbas2019_gemfish`, `rao2014_imr90_chr21`, `rao2014_k562_chr21`; ~0.38 GB; the two Hi-C slices need
`hic-straw` and `cooler`).  Other slices come from `python apps/atlas/recipes/build_rao2014_slices.py`.
DOIs checked against Crossref (2026-09-27).

### `stevens2017_mesc/`: Stevens 2017 haploid mESC single-cell Hi-C + published structures (43 MB; fetch `stevens2017`)

- **Source**: Stevens TJ *et al.* "3D structures of individual mammalian genomes studied by single-cell
  Hi-C." *Nature* 544:59–64 (2017), doi:[10.1038/nature21429](https://doi.org/10.1038/nature21429).  GEO
  [GSE80280](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE80280), Cells 1–8 =
  GSM2219497–GSM2219504; open access.
- **Files** (per cell, `https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM2219nnn/<GSM>/suppl/`):
  `<GSM>_Cell_<n>_contact_pairs.txt.gz` (0.3–1 MB; tab-separated `chrA posA chrB posB`, no header;
  31,507–111,838 contacts) and `<GSM>_Cell_<n>_genome_structure_model.pdb.gz` (~4.7 MB; the paper's 10
  final NucDynamics models at 100 kb, coordinates in particle radii).  Not fetched: `Cell-<n>.hdf5.gz`
  (~2.6 GB each) and `GSE80280_RAW.tar` (20 GB).  GEO publishes no checksums; checked by parsing (8 × 10
  models).
- **Content**: haploid 129/Ola mESC in G1, mm10.
- **Atlas store**: `python apps/atlas/recipes/build_stevens2017.py` →
  `stevens2017_mesc/stevens2017_mesc.chromdata.zarr` (atlas `stevens2017_mesc`, 26 MB): the 8 cells'
  contacts (`stevens2017_mesc_cells_1Mb.scool`, one map per cell; `stevens2017_mesc_bulk.mcool`, the 8
  cells merged, 100 kb - 1 Mb) and the 10 published 100 kb models (model 1 = coords, 2-10 = layers
  `model_2` … `model_10`), one trace per cell and chromosome.
- **Used by**: tutorial `reconstruction` (NucDynamics and EMber on Cell 1's GEO contacts,
  `GSM2219497_Cell_1_contact_pairs.txt.gz`; compared with the published structure from the atlas store);
  tutorial `chromdata_stores` (the atlas store: backed, remote and embedded reads); the root `README.md`
  and the docs (quickstart, reconstruction methods).  Fig. 3a — NucDynamics reference structures and
  the paper's precision metric (`benchmarks/fig3/a_sc_consistency.py`); the native NucDynamics engine's
  validation on all 8 cells (ensemble RMSD vs ED Table 2, RMSD / distance-matrix r vs these models,
  restraint violations: `a_nucdyn_engine_run.py`, `a_nucdyn_engine_score.py`) and its speed benchmarks
  against the original code (`a_nucdyn_engine_speed.py`, `a_nucdyn_engine_original_timing.py`,
  `a_nucdyn_engine_original_run.py`; Cell 1).

### `bintu2018/`: Bintu 2018 chr21:28–30 Mb tracing, IMR90 + K562 (28 MB; fetch `bintu2018`)

- **Source**: Bintu B *et al.* "Super-resolution chromatin tracing reveals domains and cooperative
  interactions in single cells." *Science* 362:eaau1783 (2018),
  doi:[10.1126/science.aau1783](https://doi.org/10.1126/science.aau1783).  GitHub
  [BogdanBintu/ChromatinImaging](https://github.com/BogdanBintu/ChromatinImaging) `Data/` (no licence
  file in the repo; data published with the paper).  The 18.6–20.6 Mb IMR90 file of the same repository
  is `bintu_imr90` (tutorial inputs).
- **Files**: `bintu2018/IMR90_chr21-28-30Mb.csv` (7,795,158 B; 4,871 chromosomes) and
  `bintu2018/K562_chr21-28-30Mb.csv` (20,080,720 B; 13,996 chromosomes); sizes match the GitHub API.
  Same CSV layout as `IMR90_chr21-18-20Mb.csv` (`Chromosome index, Segment index, Z, X, Y`, nm; 65 ×
  30 kb segments).
- **Coordinates**: hg38 chr21:28,000,071–29,949,939; hg19 chr21:29,372,390–31,322,257 (from the repo's
  `Data/README.md`).
- **Used by**: Fig. 3b (`benchmarks/fig3/b_first_look.py`): imaging contact frequency vs Rao 2014 Hi-C
  of the same cell line, and the cross-cell-line controls.

### `su2020_imr90/`: Su 2020 IMR90 chr21 + genome-scale tracing, binned Hi-C (465 MB; fetch `su2020_chr21`, `su2020_genome`)

- **Source**: Su J-H *et al.* "Genome-Scale Imaging of the 3D Organization and Transcriptional Activity
  of Chromatin." *Cell* 182:1641–1659 (2020),
  doi:[10.1016/j.cell.2020.07.032](https://doi.org/10.1016/j.cell.2020.07.032).  Zenodo
  [3928890](https://zenodo.org/records/3928890) (doi:10.5281/zenodo.3928890), CC-BY-4.0.
- **Files** (md5 from Zenodo, verified, checked by `fetch`): with `su2020_chr21`: `chromosome21.tsv`
  (260,629,499 B, `170d9d8b…`; columns `Z(nm) X(nm) Y(nm)`, `Genomic coordinate`, `Chromosome copy
  number`, genes / transcription / TSS), `Hi-C_contacts_chromosome21.tsv` (1,045,862 B, `7842ef31…`; the
  authors' Rao 2014 IMR90 reads summed into the 651 imaged bins), and `README_August_2020.txt`; with
  `su2020_genome`: `genomic-scale.tsv` (200,285,524 B, md5 `a1d79c2b…`), `Hi-C_contacts_genome-scale.tsv`
  (2,846,153 B, md5 `13e3607e…`; formerly checked in) and the same README.
- **Content**: IMR90, hg38, 651 × 50 kb loci across chr21 (10.4–46.7 Mb), 7,591 traced chromosome
  copies.  Genome scale (DNA-MERFISH): 1,041 loci of 100 kb (`chr1:2950000-3050000`, ~3 Mb spacing) on
  chr1–22 and chrX, 1,787 cells from 3 experiments (431 / 917 / 439), each row labelled with its
  **homolog (1 / 2)** — 3,720,534 rows = 1,787 × 2 × 1,041, 16.2 % of positions missing — plus the
  distance of each spot to the nuclear lamina; columns `Z(nm) x(nm) y(nm) genomic coordinate, homolog
  number, cell number, experiment number, distance to lamina (nm)`.  `Hi-C_contacts_genome-scale.tsv`:
  1,041 × 1,041 Rao 2014 IMR90 read counts summed into 500 kb bins centred on the loci.  The other
  Zenodo files (chr2, replicates with transcription / nuclear bodies, α-amanitin; 0.08–0.65 GB each) are
  not fetched.
- **Used by**: tutorials `tad_calling` and `compartment` (chr21); Fig. 3b
  (`benchmarks/fig3/b_first_look.py`, whole-chromosome imaging vs Hi-C; `b_dimes.py`);
  `benchmarks/screcon/simulate.py` (`su2020_chr21` truth cells) and `diploid_sim.py` (genome scale, both
  homologs); `benchmarks/bulk/` (population deconvolution benchmark: genome-scale = primary diploid
  truth, chr21 = single-chromosome truth population; `truths.py`, `forward.py`; the genome-scale Hi-C
  sums are the cross-check of the IMR90 input, `real_inputs.py su_crosscheck`).

### `abbas2019_gemfish/`: GEM-FISH repository data (40 MB; fetch `abbas2019_gemfish`)

- **Source**: Abbas A *et al.* "Integrating Hi-C and FISH data for modeling of the 3D organization of
  chromosomes." *Nat Commun* 10:2049 (2019),
  doi:[10.1038/s41467-019-10005-6](https://doi.org/10.1038/s41467-019-10005-6).  GitHub
  [ahmedabbas81/GEM-FISH](https://github.com/ahmedabbas81/GEM-FISH), MIT licence, pinned at commit
  `e83fdb4` (2019-01-02).  The FISH is Wang S *et al.* *Science* 353:598–602 (2016),
  doi:[10.1126/science.aaf8084](https://doi.org/10.1126/science.aaf8084); the Hi-C is Rao 2014 IMR90
  (GSE63525).
- **Files** (md5 verified): `complete_example.zip` (21.8 MB; Wang 2016 `chr20/21/22.xlsx` — per-cell
  TAD-centre coordinates in µm, 30 / 34 / 27 TADs — the hg19 TAD windows `tads_chr2{0,1,2}_hg19.txt`,
  chr20 Rao 2014 IMR90 5–100 kb RAWobserved + KR vectors), `GEM-FISH_TAD-level-resolution.zip` (0.2 MB;
  chr21 TAD-level input), `GEM-FISH_TAD-conformations.zip` (4.2 MB; chr21 per-TAD 5 kb Hi-C),
  `validation_tests_final_models.zip` (14 MB; the paper's **final 5 kb models** of chr20/21/22 in nm,
  per-TAD Hi-C).  No chrX data in the repo.
- **Used by**: Fig. 3a / 3c (`benchmarks/fig3/c_gemfish_wang2016.py`, `c_hipps_wang2016.py`).  The
  shipped final chr21 model scores a mean relative error of 0.143 against the shipped FISH, reproducing
  the paper's Table 1 (0.14).

### `rao2014_imr90/`, `rao2014_k562/`: Rao 2014 Hi-C slices (built, 3.8 MB each; fetch `rao2014_imr90_chr21`, `rao2014_k562_chr21`)

- **Source**: Rao SSP *et al.* "A 3D Map of the Human Genome at Kilobase Resolution Reveals Principles
  of Chromatin Looping." *Cell* 159:1665–1680 (2014),
  doi:[10.1016/j.cell.2014.11.021](https://doi.org/10.1016/j.cell.2014.11.021).  GEO
  [GSE63525](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE63525):
  `GSE63525_IMR90_combined.hic` (13 GB) and `GSE63525_K562_combined.hic`, hg19, MAPQ > 0 — the files
  Bintu 2018 used.
- **How they are built**: `python -m uchrom.datasets fetch rao2014_imr90_chr21` (or
  `rao2014_k562_chr21`) runs `uchrom.datasets._builders.slice_hic`, which reads only the needed blocks
  over HTTP range requests with `hicstraw` (~30 s per chromosome, < 2 GB RAM; needs `hic-straw` and
  `cooler`) and writes raw observed counts to `rao2014_imr90/IMR90_chr21_5kb_hg19.cool` /
  `rao2014_k562/K562_chr21_5kb_hg19.cool` (chr21: 10.27 M IMR90 / 9.54 M K562 contacts; no md5 in the
  registry: the cooler records its creation date, so a rebuild differs in that attribute only — bins and
  pixels are identical).  The recipe `python apps/atlas/recipes/build_rao2014_slices.py [--cell IMR90 K562]
  [--chroms 21] [--res 5000]` calls the same function for any cell line, chromosome set and resolution
  (`rao2014_<cell>/<CELL>_chr<chroms>_<res>_hg19.cool`).  For Fig. 3c chr20 / chr22,
  `--cell IMR90 --chroms 20` and `--chroms 22` (one file each) write `IMR90_chr20_5kb_hg19.cool`
  (20.78 M contacts, 7.8 MB, 59 s) and `IMR90_chr22_5kb_hg19.cool` (11.68 M contacts, 3.3 MB, 26 s).
  GM12878 works the same way (`--cell GM12878 --chroms 22 --res 100000`).
- **Checked**: the IMR90 chr21:28–30 Mb block reproduces Bintu 2018 Fig. 1J (median distance vs Hi-C,
  ρ = −0.96; here −0.975).  The IMR90 chr21 slice formerly checked in was 3,815,649 B (md5
  `f731fc98d5e4ae81936a066e46afa3fc`; 9,626 bins, 2,745,237 pixels, 10,266,877 contacts).
- **Used by**: the IMR90 chr21 slice: tutorials `gem_fish_reconstruction` and `bulk_reconstruction`.
  Fig. 3b / 3c (`benchmarks/fig3/b_first_look.py`, `c_gemfish_first_look.py`,
  `c_gemfish_wang2016.py --chrom`, `c_hipps_wang2016.py`), incl. the HIPPS / DIMES baselines
  (`c_hipps_wang2016.py`, `b_dimes.py`; their code is cloned, not vendored: github.com/anyuzx/HIPPS-DIMES,
  MIT, commit `beee45d`).

### `ray2019_k562/4DNFI4QQPDMR.mcool`: K562 in situ Hi-C (849 MB; fetch `ray2019_k562`)

- **Source**: Ray J *et al.* "Chromatin conformation remains stable upon extensive transcriptional
  changes driven by heat shock." *PNAS* 116:19431 (2019),
  doi:[10.1073/pnas.1901244116](https://doi.org/10.1073/pnas.1901244116); 4DN
  [4DNFI4QQPDMR](https://data.4dnucleome.org/4DNFI4QQPDMR/) (set 4DNESU95RUNO, GEO GSE130758), GRCh38,
  md5 `84f4e708e2e7b55078b670ed4b8db709` (verified).  S3:
  `https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/1c856462-1e76-4850-bfa6-defcf1524d42/4DNFI4QQPDMR.mcool`.
- **Used by**: provenance check only — the fixture `K562_chr21_30kb.cool` equals its chr21 summed to
  30 kb (see that section).

### Large Fig. 3 sources — documented, not downloaded (slice instead)

| Dataset | Accession / URL | Size | Build | Slice recipe |
| --- | --- | --- | --- | --- |
| Rao 2014 GM12878 in situ | GEO GSE63525 `GSE63525_GM12878_insitu_primary+replicate_combined.hic` (also `_combined_30.hic`, MAPQ ≥ 30, on 4DN as [4DNFI1UEG1HD](https://data.4dnucleome.org/files-processed/4DNFI1UEG1HD/)) | 51 GB (`_30.hic` 37 GB) | hg19 | `build_rao2014_slices.py --cell GM12878 --chroms 22 --res 100000` (and 10 kb) |
| Rao 2014 IMR90 in situ, 4DN | set 4DNES1ZEJNRU: [4DNFIR1JDZH7](https://data.4dnucleome.org/4DNFIR1JDZH7/) (4,639,622,711 B, md5 `f91b77fa…`), [4DNFIJTOIGOI](https://data.4dnucleome.org/4DNFIJTOIGOI/) (8.3 GB) | 4.6–8.3 GB | GRCh38 | range-read one resolution: `h5py.File(fsspec.open(url).open())` → `cooler.Cooler(h['resolutions/5000'])` (~10 s per region; `benchmarks/fig3/mds_vs_minimds/remote_slice.py`); whole file on Sherlock: fetch `rao2014_imr90_4dn` (bulk benchmark, see below) |
| Bonev 2017 mESC Hi-C (Takei 2021's comparison) | GEO GSE96107; 4DN set 4DNESDXUWBD9 [4DNFIC21MG3U](https://data.4dnucleome.org/4DNFIC21MG3U/) (12,551,353,248 B, md5 `dda4ed67…`, mm10) | 11–13 GB | mm10 | same fsspec range read, the 20 Takei 2021 loci × 25 kb (`benchmarks/fig3/b_takei_bonev.py`); smaller unsorted-ES mcool 4DNFIDA2WGV8 (0.9 GB); whole file on Sherlock: fetch `bonev2017_mesc_4dn` (bulk benchmark, see below) |
| Stevens 2017 HDF5 + raw | GSE80280 `Cell-<n>.hdf5.gz`, `GSE80280_RAW.tar` | 2.6 GB each / 20 GB | mm10 | not needed (contacts + `.pdb` suffice) |

The GM12878 `.hic` files hold every standard Juicer resolution from 1 kb to 2.5 Mb (primary + replicate
merged); the miniMDS comparison `benchmarks/fig3/mds_vs_minimds/` currently uses the 4DN IMR90 chr21
(4DNFIR1JDZH7, range reads) instead.

## Matched-modality datasets — scHi-C structures vs chromatin tracing of the same cell type

Used by `benchmarks/screcon/matched.py` (inputs built by `benchmarks/screcon/matched_data.py`; jobs
`benchmarks/screcon/sherlock/{download,matched}_*.sbatch`).  All are fetched on demand (none is in the
`--default` set); facts below were checked on the downloaded files unless marked *unverified*.

### Locus axis — `benchmarks/screcon/data/takei2021_1mb_loci.csv` (78 KB, in the repository, **derived**)

- 2,460 Takei 2021 ~1 Mb loci (25 kb probes, mm10): `name` (`chrN-#k` for the 1,267 channel-1 loci, a
  nearby gene for the 1,193 channel-2 loci), `chrom`, `start`, `end`.
- The raw Zenodo tables (3735329, 4708112) give locus *names* only; the coordinates are in the papers'
  Table S1, which is not on Zenodo.  Recovered instead from public files: the 4DN FOF-CT table
  `4DNFIFLJGGNR.csv` (coordinates, no names) holds exactly the 705,143 spots of
  `DNAseqFISH+1Mbloci-E14-replicate1.csv` in `DNAseqFISH+.zip` (201 cells; X = x·0.103, Y = y·0.103,
  Z = z·0.25 µm); joining on (cell, rounded X/Y/Z) matches 683,808 spots and gives every name exactly
  one coordinate (no ambiguity).  Rebuild (after fetch `takei2021_1mb` and `seqfish`):
  `python benchmarks/screcon/matched_data.py locus-map --fofct 4DNFIFLJGGNR.csv --zip DNAseqFISH+.zip`.
  The brain Table S7 uses the same 2,460 names (all present).

### `benchmarks/screcon/data/tan2021_adult_cortex_cells.tsv` (31 KB, in the repository)

510 rows (`gsm`, `name`, `age`, `cross`, `cell_type`): the Tan 2021 adult cortex cells that passed the
authors' filter (`GSE146397_metadata.cells_contacts_100k.txt.gz`, ≥ 100 k contacts), matched to their
GSM by the GEO sample records (`!Sample_description`).  An identical copy,
`packages/uchrom/uchrom/datasets/tan2021_adult_cortex_cells.tsv`, is the cell list of fetch
`tan2021_cortex`.

### `4DNFIFLJGGNR.csv`: Takei 2021 mESC FOF-CT, 1 Mb genome-wide loci (47 MB; fetch `takei2021_1mb`)

- **Format**: FOF-CT core table (same columns as `4DNFIHF3JCBY.csv`), `##XYZ_unit=micron`, mm10.
- **Content**: E14 mESC, replicate 1: 2,460 loci (25 kb each) at ~1 Mb spacing across chr1–19 and chrX,
  201 cells, 705,143 spots.  One `Trace_ID` per (cell, chromosome) holds the spots of **both homologs**
  (not resolved in the deposited table; ~1.8 spots per locus).  `benchmarks/screcon/truth.py` separates
  the homologs with a constrained 2-means (heuristic; checked on the homolog-resolved 25 kb table:
  median 97.8 % of spots on the right homolog) and keeps chrX (male line) as a single copy.
- **Source**: Takei et al. 2021, *Nature* 590:344–350 (same study as `4DNFIHF3JCBY.csv`).  4DN portal:
  [data.4dnucleome.org/4DNFIFLJGGNR](https://data.4dnucleome.org/files-processed/4DNFIFLJGGNR/), "DNA-Spot/Trace
  Data core table for the 2460 genomic loci across the mouse genome at 1-Mb resolution in ESCs,
  replicate 1"; md5 `da9826551f13f944815fe35a33a8e9c1` (verified, checked by `fetch`).  Public S3:
  `https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/8189709b-f1e7-4f0b-bf68-89eb9fd0afcf/4DNFIFLJGGNR.csv`.
- **Used by**: `benchmarks/screcon/simulate.py truth --dataset takei2021_1mb` (imaging-truth simulation
  benchmark for single-cell Hi-C 3-D reconstruction; also the `robust` development / test simulations,
  `robust_devlog.md`, `TEST_RESULTS.md`); `benchmarks/screcon/matched_data.py locus-map` (the mm10
  coordinates of the 2,460 locus names, above); `benchmarks/screcon/diploid_sim.py` (both homologs);
  `benchmarks/bulk/` (diploid mESC truth, heuristic homologs; vs Bonev 2017).

### `nagano2017_hap/`: Nagano 2017 haploid mESC single-cell Hi-C (1.39 GB + 253 MB extracted; fetch `nagano2017_hap`)

- **Source**: Nagano T, Lubling Y *et al.* "Cell-cycle dynamics of chromosomal organization at
  single-cell resolution." *Nature* 547:61–67 (2017), doi:10.1038/nature23001.  GEO
  [GSE94489](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE94489) holds raw reads + feature
  tables only; the per-cell contact maps are the authors' archives linked from
  [github.com/tanaylab/schic2](https://github.com/tanaylab/schic2) (S3 bucket `schic2`).
- **Files**: `schic_hap_serum_adj_files.tar.gz` (882,240,359 B; 790 cells `NST.<n>/adj`),
  `schic_hap_2i_adj_files.tar.gz` (502,155,700 B; 982 cells `NXT.<n>/adj`) — `adj` = tab-separated
  `fend1 fend2 count` (GATC fragment ends, MboII/DpnII); `GSE94489_haploids_features_table.txt.gz`
  (123,901 B; 1,772 cells: `cond` 2i_all / 2i_G1 / Serum_G1/S, `passed_qc`, `total_contacts`,
  cell-cycle `group`, ...); `GSE94489_README.txt` (barcodes); `GATC.fends` (253,322,243 B;
  `fend chr coord`, **mm9**) streamed out of `schic2_mm9_db.tar.gz` (4,996,816,093 B; not kept;
  `--no-extract` skips it); `mm9ToMm10.over.chain.gz` (UCSC, 535,855 B) — contacts are lifted to mm10.
- **Content** (verified): 1,772 haploid cells (2i 982, serum 790); `passed_qc` = 1 for 1,247.  Cell line
  per GEO: haploid ESC20 / H129-1 (ECACC 14040203), 129 background (GEO calls it "hybrid ESC cell line";
  *strain details unverified beyond the GEO text*).
- **Selection** (stated rules, `sherlock/_matched_env.sh`): serum = `Serum_G1/S`, `passed_qc == 1`,
  group G1 / early-S / late-S/G2 (no mitotic), ≥ 100 k contacts (403 cells); 2i = both 2i conditions,
  same QC, ≥ 50 k contacts, 200 drawn with seed 1.  Unique fend pairs per selected cell after mm10
  liftover: serum median 181,883 (100,509 – 694,393), 2i median 77,415 (50,855 – 384,505); the adj row
  count matches the feature table's `total_contacts` (±1, checked on 3 cells), < 0.01 % of pairs lost in
  the liftover.  The cell-cycle `group` is the authors' inference from contact profiles; cells in S / G2
  carry replicated chromatin and are modelled as haploid anyway (the G1 subset is reported separately).
- **Download**: `python -m uchrom.datasets fetch nagano2017_hap` (or
  `sherlock/download_matched.sbatch PART=mesc`).
- **Used by**: `benchmarks/screcon/matched_data.py nagano` → NucDynamics / hickit → `matched.py`
  (step 1); `robust` matched-imaging analysis (serum cells split into development / held-back halves,
  `robust_matched_split.py`, PREREG §6).

### `takei2021_brain/`: Takei 2021 Science mouse cortex DNA seqFISH+ (597 MB; fetch `takei2021_brain`)

- **Source**: Takei Y *et al.* "Single-cell nuclear architecture across cell types in the mouse brain."
  *Science* 374:586–594 (2021), doi:10.1126/science.abj1966; Zenodo
  [4708112](https://zenodo.org/records/4708112).  6–7-week-old female C57BL/6J mice (bioRxiv
  10.1101/2021.04.26.441547 methods); 3 biological replicates.
- **Files**: `TableS7_brain_DNAseqFISH_1Mb_voxel_coordinates_2762cells.csv` (349,019,829 B; 4,752,662
  spots; voxel coordinates, 103 × 103 × 250 nm; `cluster label`, `chromID`, `geneID` = locus name,
  DBSCAN `labelID`, `XistID`), `TableS8_..._25kb_...csv` (246,648,783 B),
  `TableS5_brain_RNA_profiles_2762cells.csv` (497,312 B),
  `TableS10-median-radial-score-per-celltype-1Mb-resolution.csv` (441,276 B).  Not fetched: the IF /
  DAPI / ncRNA zips (0.6–13.7 GB each).
- **Content** (verified): 2,762 cells; `cluster label` sizes 155, 58, 41, 53, 152, 90, 240, 78, 1,895
  (= the paper's Fig. 1I legend).  Names (from Table S5 marker means: Pvalb, Vip, Ndnf, Sst, Mfge8 /
  Aldoc, Csf1r, Cldn5, Olig1 / Plp1, Slc17a7): 1 Pvalb, 2 Vip, 3 Ndnf, 4 Sst, 5 astrocyte, 6 microglia,
  7 endothelial, 8 oligodendrocyte lineage, 9 excitatory.  Median 1,678 1 Mb spots per cell (≈ 34 % of
  2 × 2,460); DBSCAN gives two homolog clusters for 30 % of (cell, chromosome).
- **Download**: `python -m uchrom.datasets fetch takei2021_brain` (or
  `sherlock/download_matched.sbatch PART=brain`).
- **Used by**: `benchmarks/screcon/matched.py` brain imaging reference (step 2; `matched_data.py`).

### `tan2021_cortex/`: Tan 2021 Dip-C, adult mouse cortex (510 cells, 13 GB; fetch `tan2021_cortex`)

- **Source**: Tan L *et al.* "Changes in genome architecture and transcriptional dynamics progress
  independently of sensory experience during post-natal brain development." *Cell* 184:741–758 (2021),
  doi:10.1016/j.cell.2020.12.032.  GEO SuperSeries
  [GSE162511](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE162511); Dip-C SubSeries GSE146397.
  **Not fetched**: `GSE146397_RAW.tar` (all samples, 183 GB) — per-GSM files only.
- **Files** (per cell, `https://ftp.ncbi.nlm.nih.gov/geo/samples/<GSMnnn>/<GSM>/suppl/<GSM>_<name>.*` →
  `tan2021_cortex/cells/<name>/`): `contacts.pairs.txt.gz` (hickit pairs, ~2.5 MB), `impute.pairs.txt.gz`
  (haplotype-imputed, ~3 MB), `20k.{1..5}.clean.3dg.txt.gz` (dip-c 3DG, 20 kb particles per haplotype,
  `chrom(mat|pat) start x y z`, contact-poor particles removed; ~3.5 MB each; the structures the paper
  used).  The cells are those of `tan2021_adult_cortex_cells.tsv` (above).
- **Content** (verified from GEO records + README): cortex P56 (251 cells), P309 (131), P347 (128); P56 /
  P347 = CAST/EiJ ♀ × C57BL/6J ♂ (`cb`), P309 = the reciprocal cross (`bc`); males (README: male
  processing for all ages except P1; *sex per cell not in the GEO records*).  Structure types from
  `metadata.cells_contacts_100k`: L2–5 pyramidal 160, oligodendrocyte 74, interneuron 56, L6 pyramidal
  54, microglia 37, hippocampal pyramidal 31, astrocyte 30, medium spiny neuron 29, OPC 24, other 19.
  Contacts per cell (`contacts.pairs`, every 25th cell): 207 k – 571 k, median ~420 k (the ≥ 100 k
  filter is the authors').  The published `clean.3dg` cover a median 4,792 of the 2 × 2,460 locus
  copies.  *Unverified*: per-cell sex (GEO has none), whether the cell-type labels came from the paper's
  own clustering of these exact structures (the metadata file calls them "structure types").
- **Download**: `python -m uchrom.datasets fetch tan2021_cortex` (or
  `sherlock/download_matched.sbatch PART=brain`).
- **Used by**: `benchmarks/screcon/matched.py` brain Dip-C baseline (step 2; `matched_data.py`).

### Liu 2025 DNA-MERFISH, mouse cortex (4DN) — catalogued, not downloaded

Liu S, … Zhuang X, *Sci Adv* (2025).  4DN experiment sets (sizes from the 4DN API, 2026-10-01):
[4DNESMTNNB3N](https://data.4dnucleome.org/experiment-set-replicates/4DNESMTNNB3N/) wild-type MOp, 4
experiments, core FOF-CT tables 1.45–1.68 GB each (one, `4DNFID46OABK`, is the `liu2025_mop/` entry
below) plus 0.9–1.8 GB and 7–9 GB companion tables;
[4DNESPE924IP](https://data.4dnucleome.org/experiment-set-replicates/4DNESPE924IP/) Mecp2 +/− MOp (4
experiments, 1.3–2.1 GB + 6–10 GB tables);
[4DNESQU9R2NY](https://data.4dnucleome.org/experiment-set-replicates/4DNESQU9R2NY/) Mecp2 +/− visual
cortex (2 experiments, 1.8 GB + 8–9 GB tables).  ~2,000 loci genome-wide (different from the Takei
loci) — a second imaging reference would need its own locus axis; too large to stage for a baseline.

## Diploid single-cell Hi-C — EMber / NucDynamics validation

Phased single-cell contacts of diploid human cells with published structures, used by the diploid
EMber / NucDynamics benchmarks of `benchmarks/screcon/` (PREREG §6 diploid addition and §11).

### `tan2018_gm12878/`: Tan 2018 Dip-C, GM12878 (17 cells, ~0.7 GB; fetch `tan2018_gm12878`)

- **Source**: Tan L, Xing D, Chang C-H, Li H, Xie XS. "Three-dimensional genome structures of single
  diploid human cells." *Science* 361:924–928 (2018), doi:10.1126/science.aat5641.  GEO
  [GSE117876](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE117876) (per-GSM files).
- **Files**: per cell k (1–17) the hickit re-processing `GSM<3314358+k>_gm12878_<k>.tar.gz` (~20 MB:
  `gm12878_<k>.pairs.gz` — 4DN pairs, hg19 names without `chr`, columns `readID chr1 pos1 chr2 pos2
  strand1 strand2 phase0 phase1 phase_prob00..11`: `phase0/1` the SNP phases of the legs (`0`, `1`,
  `.`), `phase_prob*` hickit's 2-D imputation; `gm12878_<k>.3dg.gz` hickit's structure, copies `1a` /
  `1b`); the published Dip-C structures `<GSM>_[rep1_|rep2_]gm12878_<k>.impute3.round4.clean.3dg.txt.gz`
  (20 kb, `1(pat)` / `1(mat)`; three replicate runs) and the contacts after Dip-C's 3-D phase imputation
  `<GSM>_gm12878_<k>.impute3.round4.con.txt.gz`; `<GSM>` = GSM3271347 + k − 1 for k ≤ 9, GSM3271356 +
  2 (k − 10) for k ≥ 10 (cells 10–17 have two libraries; the files are on the "-1" GSM).
- **Content** (verified from GEO / the files): GEO has no hickit re-processing for cells 4, 8, 16 and no
  structure for cell 8 (dedup / raw contacts only), so 14 cells have the pairs input.  Cell 1: 1,048,961
  contacts, 8.0 % of the legs phased, 0.7 % of the contacts phased at both ends, 14.7 % at one end;
  78.7 % cis.  Haplotype 0 = paternal (`pat`), 1 = maternal (Dip-C `classes.Haplotypes`); hickit copy `a`
  = haplotype 0.  GM12878 is female (chrX two copies).
- **Download**: `python -m uchrom.datasets fetch tan2018_gm12878`; on Sherlock
  `sherlock/download_diploid.sbatch` (also unpacks the tarballs to `cells/gm12878_<k>/`).
- **Used by**: diploid EMber / NucDynamics validation (`benchmarks/screcon/diploid_real.py`,
  `diploid_heldout.py`, `sherlock/dip_real.sbatch`, `deep_dipc.sbatch`; PREREG §6 diploid addition).

### `wu2025_scmicroc/`: Wu 2025 scMicro-C, GM12878 (12 deepest cells, ~0.4 GB + 3dg; fetch `wu2025_scmicroc`)

- **Source**: Wu H, Zhang J, Tan L, Xie XS. "Single-cell Micro-C profiles 3D genome structures at high
  resolution and characterizes multi-enhancer hubs." *Nature Genetics* 57:1777–1786 (2025),
  doi:10.1038/s41588-025-02247-6.  GEO SuperSeries
  [GSE281150](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE281150); the GM12878 scMicro-C cells
  are SubSeries [GSE192759](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE192759) (355 cells,
  hg38; BWA-MEM, dip-c + hickit 0.1.1, structures `hickit -M -Sr1m -c1 -r10m -c2 -b4m -b1m -b200k -D5
  -b50k -D5 -b20k -D5 -b10k -D5 -b5k`).
- **Files**: per cell `GSM<id>_cell_<nnn>.impute.pairs.gz` (GEO per-GSM; 4DN pairs, `chr` names, columns
  `readID chr1 pos1 chr2 pos2 strand1 strand2 phase0 phase1 phase_prob00..11`) for the 12 cells with the
  largest files in GEO `filelist.txt` (2026-10-04): cells 035, 024, 320, 026, 028, 017, 047, 049, 032,
  027, 014, 051.  The authors' structures `3dg/GSM<id>_cell_<nnn>_{5,10,20}kb_{1..5}[.clean].3dg.txt.gz`
  (five hickit runs per resolution, copies `chr1(pat)` / `chr1(mat)`) exist only inside the 102 GB
  series tarball `GSE192759_5kb_10kb_20kb_3dg_files.tar.gz`, which `fetch` streams once, keeping only
  these cells' members (`3dg/_members.txt` lists the archive; ~25 min on Sherlock, 3.1 GB kept).  The
  tarball has no structures for cells 026 and 051 (the two low-cis cells below), so 10 of the 12 cells
  have them (30 files each).
- **Content** (verified, `benchmarks/screcon/highres.py count` → `contacts_per_cell.tsv`): contacts are
  already de-duplicated (rows = unique contacts); the deepest cell, 035 (GSM5764669), has 3,006,012
  contacts, 5.6 % of the ends phased, 0.4 % of the contacts phased at both ends, 91.8 % cis; then 024
  (2.85 M), 320 (2.64 M), 047 (2.24 M), 028 (2.23 M).  No chrY contacts (female; `ploidy="auto"` → two
  copies of every chromosome incl. chrX).  Cells 026 and 051 have only 33 % / 12 % cis contacts (likely
  damaged nuclei or doublets) and are not used.  The deepest public diploid single-cell data with phase
  columns; Uni-C (GSE267873, `unic2025/`) is deeper but has no phase columns.
- **Download**: `python -m uchrom.datasets fetch wu2025_scmicroc` (`--no-extract`: pairs only); on
  Sherlock `sherlock/highres_download.sbatch`.
- **Used by**: EMber deep (PREREG §11: development cells 035, 024, 320; held-back test cells 047, 028,
  017, 049, 032, 027, 014; `DEEP_TEST_RESULTS.md`) and Fig. 3a / S8: `benchmarks/screcon/highres.py`,
  `deep_diploid.py`, `sherlock/deep_dev.sbatch`, `highres_run.sbatch`, `highres_score.sbatch`;
  `u-chrom-paper/manuscripts/full/figures/fig3/build_render_scmicroc.py`, `capture_highres.py`,
  `make_figS_fig3_highres.py`.

## Bulk Hi-C deconvolution benchmark (`benchmarks/bulk/`)

Population deconvolution of bulk Hi-C (`uchrom.recon.bulk.deconv.deconvolve(method="igm")`; design
`benchmarks/bulk/design.md` sections 6-7, commands `benchmarks/bulk/README.md`).

**Imaging truths** (catalogued above): Su 2020 genome-scale (fetch `su2020_genome`, primary diploid
genome-wide truth), Su 2020 chr21 (fetch `su2020_chr21`), Takei 2021 1 Mb (fetch `takei2021_1mb`,
homologs split heuristically by `benchmarks/screcon/truth.split_homologs`).

**Real Hi-C** (whole files only on Sherlock; laptop checks use HTTP range reads):

- **Rao 2014 IMR90, 4DN GRCh38** — `rao2014_imr90/4DNFIR1JDZH7.mcool` (4,639,622,711 B, md5
  `f91b77fa61acdc58360911c80b007646`, 4DN set 4DNES1ZEJNRU; Rao SSP *et al.* *Cell* 159:1665 (2014), GEO
  GSE63525; 4DN data-use policy: open).  GRCh38 like the Su 2020 loci, so no liftover.  Levels 1 kb–10 Mb
  (no 20 kb): the IGM 20 kb matrix is summed from the 10 kb level.
  `python -m uchrom.datasets fetch rao2014_imr90_4dn` (Sherlock: `benchmarks/bulk/sherlock/build_real.sbatch`).
- **Bonev 2017 mESC, 4DN mm10** — `bonev2017_mesc/4DNFIC21MG3U.mcool` (12,551,353,248 B, md5
  `dda4ed67a1179f917721fb81b1adebe0`, 4DN set 4DNESDXUWBD9; Bonev B *et al.* *Cell* 171:557 (2017),
  doi:10.1016/j.cell.2017.09.043, GEO GSE96107).  `python -m uchrom.datasets fetch bonev2017_mesc_4dn`
  (Sherlock); also range-read by `benchmarks/fig3/b_takei_bonev.py` and `benchmarks/bulk/kr_check.py`.
- **Rao 2014 IMR90, GEO hg19** `GSE63525_IMR90_combined.hic` (13 GB) — not downloaded; read over HTTP
  range requests by `benchmarks/bulk/kr_check.py` (its Juicer KR vectors are the reference for
  U-Chrom's KR balancing).

**IGM demo input** — `WTC11_HiC_2Mb.hcs` (3,908,025 B): GPL-3 data of github.com/alberlab/igm (`demo/`
at commit `edbb331`), kept out of the repository and out of the registry:
`benchmarks/bulk/_igm_bench.py:fetch_igm_demo` downloads it on demand into `$UCHROM_IGM_CACHE` (default
`~/.cache/uchrom/igm/`) and checks its size.
Used for the IGM protocol of the native engine vs the original IGM
(`benchmarks/bulk/sherlock/ours_demo_*.sbatch`, `orig_demo.sbatch`, `compare_demo.sbatch`).

**Derived inputs** (Sherlock, `$SCRATCH/uchrom-nd/runs/bulk/real/<cell>/`, not stored; recipe
`benchmarks/bulk/real_inputs.py preprocess`, IGM SI section 6 protocol in
`uchrom.recon.bulk.deconv.preprocess`): `fine_20kb.npz` (raw 20 kb counts, chr1–22 + X), `igm_200kb.npz`
(whole genome, 200 kb, 24 contacts per bin), `su_3mb.npz` / `su_1mb.npz` (IMR90 onto 3 Mb / 1 Mb bins
centred on the Su loci), `takei_1mb.npz` (mESC onto 1 Mb bins centred on the Takei loci),
`su_crosscheck.json`.  Probabilities for `uchrom.recon.bulk.deconv.deconvolve(method="igm")`.

**EMber-pop benchmark** (`benchmarks/bulk/PREREG_POP.md`): derived from the Su 2020 genome-scale and Takei
2021 1 Mb truths (fetch `su2020_genome`, `takei2021_1mb`) and the 4DN Rao 2014 IMR90 mcool (fetch
`rao2014_imr90_4dn`), not stored: per unit (Sherlock `$SCRATCH/uchrom-nd/runs/pop/<unit>/`) `bulk_cells.npz` /
`truth.npz` (cells of `benchmarks/bulk/data/pop_split.tsv`, checked in, 1,988 rows, seed 20261007) and the
simulated inputs `C1.npz` (step kernel, exact), `C2.npz` (Gaussian kernel, exact), `C3.npz` (200 reads per locus
pair, ε 0.1, IGM preprocessing) from `forward.py`; `real_imr90/input_3mb.npz` (IGM preprocessing of the 4DN mcool
onto 3 Mb bins centred on the Su loci, target 32.885 = the Su development cells' exact row sum;
`sherlock/pop_build_real.sbatch`).  The IGM demo input (`WTC11_HiC_2Mb.hcs`, above) for fit / runtime.

**Checked in**: `benchmarks/bulk/results/kr_check.json` (KR check, range reads) and
`benchmarks/bulk/results/plumbing_imr90_chr21_22_igm200kb.json` (provenance of the laptop plumbing run:
4DN IMR90 chr21 + chr22, range-read 10 kb level → 20 kb → 200 kb).

## Other benchmark inputs

### `liu2025_mop/`: Liu et al. 2025 mouse MOp DNA-MERFISH, 4DN FOF-CT (1.7 GB; fetch `liu2025_mop`)

- **Source**: Liu S, Wang CY, Zheng P, … Zhuang X. "Cell type-specific 3D-genome organization and
  transcription regulation in the brain." *Sci Adv* (2025), PMID 40009678.  4DN experiment set
  [4DNESMTNNB3N](https://data.4dnucleome.org/experiment-set-replicates/4DNESMTNNB3N/) (DNA-MERFISH of
  2,000 loci + RNA-MERFISH of 240 genes, mouse primary motor cortex, wild type), experiment
  4DNEXBUVZYLI.
  - core table [4DNFID46OABK](https://data.4dnucleome.org/4DNFID46OABK/) (1,684,734,602 B, md5
    `e2234c8d…75a4abb`):
    `https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/7c153998-3e92-4dbe-8e35-7a09570e6ed3/4DNFID46OABK.csv`
  - cell table [4DNFICX8IVEK](https://data.4dnucleome.org/4DNFICX8IVEK/) (16,564,294 B, md5
    `f66afc5a…e5e5`):
    `https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/ad72715d-57cc-4d68-8ddb-536b94ed9bb0/4DNFICX8IVEK.csv`
- **How it was chosen**: a portal search for released files of type `FOF-CT - DNA-spot/trace core` (321
  files, all open on the public S3 bucket) sorted by size.  The top 10 (1.27–2.14 GB) are all
  Zhuang-lab mouse MOp / visual-cortex tables; the larger ones are *Mecp2* KO samples, so we took the
  **largest wild-type core table**.  It is 77× the Takei 2021 table (`4DNFIHF3JCBY`, 22 MB).  Next
  largest from other studies: Su et al. 2020 IMR90 DNA-MERFISH (`4DNFIGJT3AN3` 572 MB, `4DNFIZ4TAGXZ`
  248 MB).
- **Content** (`python apps/atlas/recipes/build_liu2025_mop.py` → `liu2025_mop/liu2025_mop.chromdata.zarr`
  294 MB + `build_summary.json`; 1.57 GB as the former h5cd 1.x; 267 MB as format 2.2,
  `liu2025_mop.v22.chromdata.zarr`): **9,582,069 spots, 188,891 traces, 11,045 cells**, 20
  chromosomes, median 50 spots per trace, µm, GRCm38.  The cell table has 14,733 rows (3,695 cells
  without traces; 7 traced cells without a row), with 240 RNA counts and cell-type labels.
  `from_fofct` reads the 1.68 GB core table in 14 s at 11.6 GB peak RSS.
- **Used by**: `build_liu2025_mop.py` (dataset-scale entry for Fig. 2);
  `benchmarks/fofct_roundtrip_validation.py` (FOF-CT writer); `benchmarks/cd2_zarr_validation.py`
  (→ `.chromdata.zarr`); `benchmarks/cd21_streaming_validation.py` (2.0 → 2.1, streaming
  `from_fofct(out=)` vs in memory, streaming distance maps vs the dense reference);
  `benchmarks/cd22_convert_validate.py` and `benchmarks/fig2/cd22_variants.py` (format 2.2);
  `benchmarks/cell_spatial_validation.py` (cell positions).

### `benchmarks/fig6/_data/`: scaled copies of Takei 2025 FOV 0 (derived)

`benchmarks/fig6/make_scaled.py --src $UCHROM_DATA/takei2025_fov0/takei2025_fov0.chromdata.zarr --out benchmarks/fig6/_data --factors 1 3 10 30`
tiles k copies of the real FOV 0 cells side by side (cell and trace ids suffixed `_r<k>`; geometry only:
spots, coords, `cells.cell_type`) → `takei2025_fov0_x{1,3,10,30}.chromdata.zarr` (8–70 MB; the `.h5cd`
copies of older runs were 27 MB – 0.83 GB).  Ignored by git.  They are labelled *replicated* wherever
they are reported.  Used by the Fig. 6c browser benchmarks (`benchmarks/fig6/bench_server.py`,
`bench_frontend.py`, `run_all.sh`).

## Pre-staging data (optional)

Tutorials and benchmarks fetch what they need; to stage data ahead (offline / cluster work):

```bash
python -m uchrom.datasets fetch --default                                  # the tutorials' inputs (~0.93 GB)
python -m uchrom.datasets fetch --fig3                                     # Fig. 3 inputs (~0.38 GB, two built)
python -m uchrom.datasets fetch su2020_genome su2020_chr21 takei2021_1mb   # bulk benchmark truths
python -m uchrom.datasets fetch rao2014_imr90_chr21                        # built: sliced from the GEO .hic over HTTP
```

The default set is what the tutorials fetch: `takei`, `takei_tables`, `seqfish`, `bintu_imr90`,
`huang2021_sox2`, `su2020_chr21`, `stevens2017`, `kim2020_scihic`, `mm10_chr19`, `mm10_refgene`,
`rao2014_imr90_chr21` (built) and `takei2025_fov0` (built); all are md5-checked except the Rao slice.  `--root DIR` stages into another directory (e.g. a shared data folder; or set
`UCHROM_DATA`); `--no-extract` skips the members streamed out of archives.  Files already present are
skipped.

## Adding a new dataset

1. An original file → an entry in `packages/uchrom/uchrom/datasets/_sources.py` (URL, md5, size,
   description; `python -m uchrom.datasets fetch NAME` then works), and a section here.
2. A built dataset (a store of the atlas, a benchmark input) → a `build_*.py` recipe in this folder that
   reads from and writes to `uchrom.datasets.data_dir()`; for the atlas, `apps/atlas/PUBLISH.md`.
3. A small file a unit test needs → that package's `tests/fixtures/` (with a row in its README).
4. Always cite the paper + accession, and note the licence / terms of use where they matter.
