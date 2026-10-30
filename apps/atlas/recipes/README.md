# Datasets: sources and recipes

Every dataset U-Chrom's tutorials, tests, benchmarks and atlas use: where it comes from (study,
accession, licence), how to get it, and who uses it.

**Where data live.**  The repository holds no data except the small fixtures of the unit tests and a
few reference tables next to the code that reads them.  Everything else lives in the *data
directory*: `$UCHROM_DATA`, else `~/.cache/uchrom` (`uchrom.datasets.data_dir()`).  Paths below
without a prefix are relative to it.  Its layout is the one the former `example-data/` folder had, so
an old folder works as `UCHROM_DATA`.

**Ways to a dataset** (the *How to get it* column of the tables):

- **load `NAME`** — the usual one: the dataset as a `ChromData`, `uchrom.datasets.load("NAME")`.  For an
  atlas id it opens the atlas store; for a dataset with a *loader* (below) it builds the `ChromData` once from
  the fetched original files, writes it to the data directory with its contact maps linked next to it, and
  reads it from there afterwards (`python -m uchrom.datasets load NAME` builds it ahead).
- **atlas `ID`**: a `.chromdata.zarr` store of the public atlas (https://uchrom-atlas-r2.u-science.org),
  opened over HTTP without downloading it: `uchrom.datasets.load("ID")` / `atlas("ID")` (backed: only what is
  used is fetched).  `python -m uchrom.datasets atlas` lists the ids; `uchrom.datasets.fetch("ID")` downloads
  the store's one-file copy (`.cdz`) into `atlas/ID.cdz` of the data directory, which `load` then reads
  instead (offline work).
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
  link contact maps made from the raw reads on a compute cluster (`*/slurm/`: Slurm jobs; `$UCHROM_ARCHIVE` is
  where the cluster keeps their results); those are not public.
- **fixture**: a small real file in a package's `tests/fixtures/` (each folder has a README listing
  the sources), read offline by the unit tests.

**Datasets with a loader** (`packages/uchrom/uchrom/datasets/_load_*.py`; built once into the data directory,
rebuilt when the loader's version changes; each checked to give what the tutorials built by hand before):

| `load` name | Store (data directory) | From (`fetch`) | What it is | Used by |
|-------------|------------------------|----------------|------------|---------|
| `takei2021_mesc` | `takei2021_mesc/takei2021_mesc.chromdata.zarr` | `takei`, `takei_tables` | Takei 2021 mESC DNA seqFISH+ as 4DN FOF-CT: 201 cells, 1,200 loci at 25 kb (8,285 traces), the cell table (`rna.<gene>`) and nascent-RNA spots | tutorials `chromdata_basics`, `plotting_and_browser`, `features`, `loop_calling`, `tad_calling`, `fishnet_domains`, `compartment`, `jie_aligner`, `datasets_atlas` |
| `takei2021_mesc_detections` | `takei2021_mesc/takei2021_mesc_detections.chromdata.zarr` | `seqfish`, `takei` | the raw DNA seqFISH+ detections of the same cells (replicate 1, 25 kb loci): 316,995 untraced spots, the authors' homolog call as `label` | tutorial `jie_aligner` |
| `bintu_imr90`, `bintu_imr90_hg19` | `bintu_imr90/*.chromdata.zarr` | `bintu_imr90` | Bintu 2018 IMR90 chr21 tracing, 1,277 chromosomes × 65 segments of 30 kb, on hg38 (18.6–20.6 Mb) / on hg19 (20.0–21.95 Mb, to pair with Rao 2014) | tutorials `fish_imputation`, `bulk_reconstruction`, `gem_fish_reconstruction` |
| `su2020_chr21` | `su2020_chr21/su2020_chr21.chromdata.zarr` + `.cool` | `su2020_chr21` | Su 2020 IMR90 chr21 tracing: 7,591 chromosome copies × 651 loci of 50 kb (hg38), genes per locus; the authors' Rao 2014 Hi-C in the same loci, linked (`rao2014`) | tutorials `tad_calling`, `compartment` |
| `su2020_chr2` | `su2020_chr2/su2020_chr2.chromdata.zarr` + `.cool` | `su2020_chr2` | Su 2020 IMR90 chromosome 2 tracing: 3,029 copies × 935 loci of 50 kb (hg38); the authors' Rao 2014 Hi-C in the same loci, linked (`rao2014`) | — |
| `su2020_chr21_cell_cycle` | `su2020_chr21_cell_cycle/su2020_chr21_cell_cycle.chromdata.zarr` | `su2020_chr21_cell_cycle` | Su 2020 IMR90 chr21 tracing, 4,558 copies × 651 loci, `traces["cell_cycle"]` | — |
| `su2020_genome`, `su2020_genome_amanitin`, `su2020_genome_transcription` | `<name>/<name>.chromdata.zarr` | the same names | Su 2020 IMR90 genome-scale DNA-MERFISH, 1,041 loci (hg38), one trace per cell, chromosome and homolog: untreated (1,787 cells), after α-amanitin (4,102), with nascent transcription and distances to lamina / nucleoli / speckles (3,668; `spot_tracks`) | — |
| `tan2021_cortex` | `tan2021_cortex/tan2021_cortex.chromdata.zarr` + `tan2021_cortex_5kb.scool` (2.0 GB + 663 MB) | `tan2021_cortex` | Tan 2021 Dip-C adult mouse cortex: 510 cells (P56 / P309 / P347) with the authors' cell types, 5 kb maps per cell (`per_cell`) and the first of the authors' five 20 kb structures of each cell (124 M particles, a trace per homolog; mm10) | — |
| `takei2021_brain_4dn`, `liu2020_mina`, `hung2024_orca`, `huang2021_4dn` | `<name>/<name>.chromdata.zarr` | the same names (4DN FOF-CT) | Takei 2021 mouse cortex DNA seqFISH+ (2,762 cells, 1 Mb and 25 kb loci as traces `c1-` / `c2-`, cell types), Liu 2020 MINA of fetal liver (13,306 cells, chr19 with lamina / nucleolus distances, RNA per cell), Hung 2024 ORCA of Pitx1 in limb buds (103,820 traces), Huang 2021 Sox2 in mESC (8,364 traces, allele and transcription per trace) — see *4DN chromatin-tracing studies* | — |
| `bintu2018_4dn`, `mateo2019_orca`, `hafner2023_orca`, `murphy2024_orca` | `<name>/<name>.chromdata.zarr` | the same names (4DN FOF-CT) | every experiment of a 4DN chromatin-tracing study in one object (`uchrom.io.read_4dn_tracing`; `cells`: `set`, `condition` = the set's 4DN description, `biosample`; the companion tables as `spot_tracks` / `traces` / `cells` columns) — see *4DN chromatin-tracing studies* | — |
| `huang2021_sox2` | `huang2021_sox2/huang2021_sox2.chromdata.zarr` | `huang2021_sox2` | Huang 2021 mESC Sox2 tracing (SnapFISH-IMPUTE tables, `uchrom.io.read_snapfish`): 1,416 cells × 2 alleles × 41 loci of 5 kb, undetected loci as NaN | tutorial `fish_imputation` |
| `rao2014_imr90_chr21` | `rao2014_imr90/rao2014_imr90_chr21.chromdata.zarr` | `rao2014_imr90_chr21` (built from GEO) | Rao 2014 IMR90 Hi-C chr21 at 5 kb (hg19, raw counts), the map linked as `bulk` | tutorials `bulk_reconstruction`, `gem_fish_reconstruction`, `hic_structures` |
| `kim2020_scihic` | `kim2020_scihic/kim2020_scihic.chromdata.zarr` + `.scool` | `kim2020_scihic` | Kim 2020 sci-Hi-C, H1 ES + HFF: 1,931 cells with cell types, 500 kb maps per cell (linked `.scool`, key `per_cell`; the hg19 bin numbering checked) | tutorial `higashi_embedding` |
| `tan2018_gm12878` | `tan2018_gm12878/tan2018_gm12878.chromdata.zarr` + `tan2018_gm12878_5kb.scool` (44 MB) | `tan2018_gm12878` | Tan 2018 Dip-C GM12878: the 14 cells with hickit pairs, 5 kb maps per cell (hg19, homologs summed; key `per_cell`), contacts / cis fraction per cell; the authors' Dip-C structures (20 kb particles, one trace per cell × chromosome × homolog, 3.83 M particles; the replicate runs `rep1` / `rep2` as layers, replicate RMSD per cell and per particle; store ~320 MB) | tutorial `sc_structures`; uchrom-reproducibility `supp_table3/hic_structures/pseudobulk_gm12878.py`; uchrom-reproducibility `supp_table3/sc_structures/structures_*.py` |
| `wu2025_scmicroc` | `wu2025_scmicroc/wu2025_scmicroc.chromdata.zarr` + `wu2025_scmicroc_5kb.scool` (57 MB) | `wu2025_scmicroc` (pairs only, the 3dg tarball is not streamed) | Wu 2025 scMicro-C GM12878: 12 deep cells, 5 kb maps per cell (hg38, homologs summed; key `per_cell`), `qc_pass` (cis fraction ≥ 0.5: false for cells 026, 051) | uchrom-reproducibility `supp_table3/hic_structures/pseudobulk_gm12878.py` |
| `nagano2017_dip_serum` | `nagano2017_dip_serum/nagano2017_dip_serum.chromdata.zarr` + `.scool` (709 MB) | `nagano2017_dip_serum` | Nagano 2017 diploid serum mESC (the cells of SnapHiC, Yu 2021): 1,175 cells, 10 kb maps per cell (fend pairs placed on mm9 GATC fends, lifted to mm10; homologs summed; key `per_cell`), GEO feature table, contacts per cell, `snaphic_top742` (the 742 deepest cells) | tutorial `sc_structures`; uchrom-reproducibility `supp_table3/sc_structures/snaphic_*.py` |

**Pseudo-bulk maps** (`uchrom.fea.pseudobulk`: per-cell maps summed per cell group, ICE-balanced, one `.cool`
per group linked as `pseudobulk.<group>`) are written next to a local store
(`<store dir>/<store name>_pseudobulk/`, linked by relative path), for an atlas store into the data
directory (`pseudobulk/<store name>/`), and reused while the cell list, source and parameters recorded in the
file are the same.  They are derived files: delete them freely.

Tutorials are named without `tutorials/` and `.ipynb` (the list is `tutorials/README.md`).  The paper's
figure scripts (`u-chrom-paper`, a separate repository) are named where they read these data.
`.h5cd` files of older builds are no longer read: convert them once with
`python -m uchrom.io.upgrade old.h5cd`, or rebuild.  A new dataset gets a registry entry or a recipe and
a section here in the same PR (see *Adding a new dataset* at the end).

## Contents at a glance

**In the repository: test fixtures and small reference tables**

| Dataset / location | Size | How to get it | Used by |
| --- | --- | --- | --- |
| `cell1.pairs.gz`: Stevens 2017 Cell 1 contact pairs | 1.3 MB | fixture, `packages/uchrom/tests/fixtures/` | NucDynamics / EMber / I/O tests; `build_sim_cell1.py`; uchrom-reproducibility `supp_table3/nucdyn/a_nucdyn_engine_speed.py` |
| `K562_chr21_30kb.cool`: Ray 2019 K562 Hi-C, chr21 at 30 kb (**formerly misnamed `IMR90_chr21_30kb.cool`**) | 0.28 MB | fixture, `packages/uchrom/tests/fixtures/` (source: fetch `ray2019_k562`) | DI caller, `load_cool` and GEM-FISH tests; an unpublished benchmark; the DI example of the docs; never paired with IMR90 imaging |
| `4DNFIFINA2U9.csv`, `4DNFIJ52NVDV.csv`: Takei 2021 cell and RNA tables (copies) | 58 KB + 219 KB | fixture, `packages/chromdata/tests/fixtures/` and `packages/uchrom/tests/fixtures/` (also fetch `takei_tables`) | FOF-CT companion-table, FOF-CT writer and cell-embedding tests |
| `mESC_Sox2_5cells_wnan.chromdata.zarr`: Huang 2021 Sox2 locus, 5 traces with missing loci | 176 KB | fixture, `packages/uchrom/tests/fixtures/` and `packages/uchrom-browser/tests/fixtures/` | imputation tests; browser data tests |
| `sim_cell1/`: NucDynamics structure of Cell 1 + its contacts (structure predates the `count_contacts` fix) | 1.4 MB | fixture, `packages/uchrom-browser/tests/fixtures/`; recipe `build_sim_cell1.py` | browser genome-view test; uchrom-reproducibility `extended_data_fig1/f_roundtrip.py`; Fig. 6 agent benchmark |
| `fixture_barcode_only.ecsv`, `fixture_with_chrom.ecsv`: PyHiM ECSV traces | 1 KB each | fixture, `packages/uchrom/tests/fixtures/` | `packages/uchrom/tests/im/test_from_pyhim_trace.py` |
| `macs3/`: MACS3's own regression results (BSD 3-Clause) | 1.2 MB | fixture, `packages/uchrom/tests/fixtures/` | `packages/uchrom/tests/fea/test_peak_features.py` |
| `apps/atlas/recipes/ref_hg38/`: UCSC hg38 `gap` and `centromeres` tables | 12 KB + 1.5 KB | in this folder | `probe_human_ssab_layout.py` |
| an unpublished benchmark (derived), `tan2021_adult_cortex_cells.tsv` | 78 KB + 31 KB | in the repository | an unpublished benchmark; the cell list of fetch `tan2021_cortex` |

**Original files the tutorials fetch**

| Dataset / location | Size | How to get it | Used by |
| --- | --- | --- | --- |
| `4DNFIHF3JCBY.csv`: Takei 2021 mESC FOF-CT tracing, 25 kb | 22 MB | fetch `takei` | tutorials `chromdata_basics`, `chromdata_stores`, `import_fofct`, `plotting_and_browser`, `loop_calling`, `tad_calling`, `fishnet_domains`, `compartment`, `features`, `jie_aligner`; FOF-CT tests (skipped without it); caller, format, cell-position, simulation and Fig. 3 benchmarks |
| `4DNFIFINA2U9.csv`, `4DNFIJ52NVDV.csv`: its cell table and nascent RNA spots | 58 KB + 219 KB | fetch `takei_tables` (copies are fixtures) | tutorials `chromdata_basics`, `chromdata_stores`, `import_fofct`, `plotting_and_browser`; format and cell-position benchmarks |
| `DNAseqFISH+.zip`: Takei 2021 raw seqFISH+ spot detections | 144 MB | fetch `seqfish` | tutorial `jie_aligner`; an unpublished benchmark |
| `IMR90_chr21-18-20Mb.csv`: Bintu 2018 IMR90 chr21 tracing | 2 MB | fetch `bintu_imr90` | tutorials `gem_fish_reconstruction`, `bulk_reconstruction`, `fish_imputation`, `import_pyhim_ecsv`; Fig. 3b / 3c |
| `IMR90_chr21_pyhim.ecsv`: the same tracing as PyHiM ECSV | 5.7 MB | recipe `bintu_to_pyhim_ecsv.py` | an unpublished benchmark (the `import_pyhim_ecsv` tutorial converts in the notebook) |
| `huang2021_sox2/`: Huang 2021 mESC Sox2 ORCA tracing with missing loci | 7 MB | fetch `huang2021_sox2` | tutorial `fish_imputation` |
| `kim2020_scihic/`: Kim 2020 sci-Hi-C, H1 ES + HFF, 500 kb | 128 MB + 92 KB | fetch `kim2020_scihic` | tutorial `higashi_embedding` |
| `genomes/mm10/chr19.fa.gz`, `genomes/mm10/mm10.refGene.gtf.gz`: UCSC mm10 | 19 MB + 13 MB | fetch `mm10_chr19`, `mm10_refgene` | tutorials `features`, `pseudobulk` (refGene: gene density) |
| `takei2025_fov0/`: Takei 2025 cerebellum, rep 1 FOV 0, first 47 cells (raw CSV + built store) | 280 MB; store 73 MB | fetch `takei2025_fov0` (built: streamed from Zenodo); recipe `build_takei2025_fov0.py` for the store | tutorial `import_seqfish_multiomics` (raw); browser tests, Fig. 2 / Fig. 6 and format benchmarks (store) |
| `stevens2017_mesc/`, `su2020_imr90/chromosome21.tsv`, `rao2014_imr90/IMR90_chr21_5kb_hg19.cool` | see the Figure 3 table | fetch `stevens2017`, `su2020_chr21`, `rao2014_imr90_chr21` | tutorials `reconstruction`; `tad_calling`, `compartment`; `bulk_reconstruction`, `gem_fish_reconstruction` |

**The atlas: original files and the stores built from them** (store ids and sizes in *The atlas* below)

| Dataset / location | Size | How to get it | Used by |
| --- | --- | --- | --- |
| `takei2025_cerebellum/`: Takei 2025 cerebellum DNA seqFISH+, rep 1, all FOVs | 2.85 GB download; combined store 2.05 GB | fetch `takei2025_cerebellum`; recipe `build_takei2025_cerebellum.py`; atlas `takei2025_cerebellum` | tutorials `features`, `cell_embeddings`, `import_seqfish_multiomics` (atlas); the two `takei2025_*auto_discovery` tutorials (local build); Fig. 2, format and cell-position benchmarks |
| `schicar_mop/`: scHiCAR mouse frontal cortex, RNA + ATAC + contacts, no 3-D | 61 MB + 1.47 GB + 1.37 GB download; store + maps ~0.4 GB | fetch `schicar_rna`, `schicar_dna`, `schicar_atac`; recipe `build_schicar_mop.py`; atlas `schicar_mouse_cortex` | tutorial `cell_embeddings` (atlas); Fig. 2e / 2f, Fig. 6, omics-embedding, spatial-composition and format benchmarks |
| `schicar_mop/raw/merfish_mop/`: MERFISH mouse MOp atlas | 332 MB | fetch `merfish_mop` | scHiCAR to MERFISH mapping (an unpublished benchmark) |
| `spatial_hic_chen2026/`: Spatial Hi-C, mouse embryo / brain (Chen, Guo 2026) | 15.9 GB download; stores 0.7–16 MB + linked files | fetch `spatial_hic_chen2026`; recipes `build_spatial_hic_chen2026.py` (needs R), `link_spatial_hic_chen2026_contacts.py`; atlas `chen2026_*` | validation benchmarks; an unpublished benchmark; the atlas page's hero animation |
| `spatial_atac_hic/`: Spatial ATAC-Hi-C, mouse brain (Wang P. 2026) | 9.5 GB download; store + links ~0.3 GB | fetch `spatial_atac_hic`; recipes `build_spatial_atac_hic.py`, `link_spatial_atac_hic_contacts.py`; atlas `atac_hic_mouse_brain` | atlas |
| `spatial_hicrna/`: Spatial Hi-C-RNA, mouse brain / embryo, human melanoma (Guo 2026) | 2.3 GB download; contacts from 7 `.pairs.gz` of 7–160 GB on a compute cluster | fetch `spatial_hicrna`; recipes `build_spatial_hicrna.py`, `link_spatial_hicrna_contacts.py`; atlas `hicrna_*` | uchrom-reproducibility `supp_fig6/atlas/spatial_hicrna_validation.py`, `embedded_contacts.py`, `spatial_composition/` |
| `hires2023/`: HiRES mouse embryo / brain, contacts + RNA + 3-D | 70 MB + 76 GB | fetch `hires2023_meta`, `hires2023`; recipe `build_hires2023.py`; atlas `hires_embryo`, `hires_brain` | atlas; the atlas page's hero animation |
| `dschic2025/`: dscHi-C mouse cortex at 3 / 12 / 23 months | 44 GB | fetch `dschic2025_aging`; recipe `build_dschic2025.py`; atlas `dschic_aging_cortex` | atlas; tutorial `pseudobulk`; uchrom-reproducibility `supp_table3/hic_structures/pseudobulk_dschic.py` |
| `gageseq2024/`: GAGE-seq mouse cortex / human bone marrow CD34+ | 38 GB | fetch `gageseq2024`; recipe `build_gageseq2024.py`; atlas `gageseq_mouse_cortex`, `gageseq_human_bm_cd34` | atlas; an unpublished benchmark |
| `droplet_hic2024/`: Droplet Hi-C / Paired Hi-C mouse cortex | 4 MB + 72 GB | fetch `droplet_hic2024_meta`, `droplet_hic2024`; recipe `build_droplet_hic2024.py`; atlas `droplet_hic_mouse_cortex`, `paired_hic_mouse_cortex` | atlas; an unpublished benchmark |
| `unic2025/`: Uni-C human and mouse single cells, CTCs and bulk | 110 GB | fetch `unic2025`; recipe `build_unic2025.py`; atlas `unic_human`, `unic_mouse` | atlas |

**Benchmark sources** (Fig. 3, single-cell and bulk reconstruction, formats)

| Dataset / location | Size | How to get it | Used by |
| --- | --- | --- | --- |
| `stevens2017_mesc/`: Stevens 2017 mESC scHi-C, 8 cells, contacts + published structures | 43 MB | fetch `stevens2017`; recipe `build_stevens2017.py`; atlas `stevens2017_mesc` | tutorial `reconstruction` (Cell 1 contacts; atlas store); tutorials `chromdata_stores`, `datasets_atlas` (atlas, its `.cdz`); Fig. 3a and the native-engine validation |
| `bintu2018/`: Bintu 2018 chr21:28–30 Mb tracing, IMR90 + K562 | 7.8 MB + 20 MB | fetch `bintu2018` | Fig. 3b |
| `su2020_imr90/chromosome21.tsv` + `Hi-C_contacts_chromosome21.tsv`: Su 2020 IMR90 chr21 tracing + binned Hi-C | 261 MB + 1 MB | fetch `su2020_chr21` | tutorials `tad_calling`, `compartment`; Fig. 3b; an unpublished benchmark and an unpublished benchmark truths |
| `su2020_imr90/genomic-scale.tsv` + `Hi-C_contacts_genome-scale.tsv`: Su 2020 genome-scale DNA-MERFISH | 200 MB + 2.8 MB | fetch `su2020_genome` | an unpublished benchmark (primary diploid truth); an unpublished benchmark |
| `abbas2019_gemfish/`: GEM-FISH repository data (Wang 2016 FISH, TADs, Hi-C, final models) | 40 MB | fetch `abbas2019_gemfish` | Fig. 3a / 3c |
| `rao2014_imr90/IMR90_chr21_5kb_hg19.cool`, `rao2014_k562/K562_chr21_5kb_hg19.cool`: Rao 2014 Hi-C slices | 3.8 MB each | fetch `rao2014_imr90_chr21`, `rao2014_k562_chr21` (built over HTTP) | IMR90: tutorials `bulk_reconstruction`, `gem_fish_reconstruction`, `hic_structures`; both: Fig. 3b / 3c |
| `rao2014_imr90/IMR90_chr{20,22}_5kb_hg19.cool` | 7.8 MB + 3.3 MB | recipe `build_rao2014_slices.py --cell IMR90 --chroms 20` (then `22`) | Fig. 3c chr20 / chr22 |
| `rao2014_imr90/IMR90_chr1_5kb_hg19.cool`, `rao2014_gm12878/GM12878_chr21_5kb_hg19.cool`: Rao 2014 Hi-C slices | 39 MB + 9.8 MB | fetch `rao2014_imr90_chr1`, `rao2014_gm12878_chr21` (built over HTTP) | GM12878: tutorial `sc_structures`; Hi-C structure callers: validation, chr1 performance (uchrom-reproducibility `supp_table3/hic_structures/`) |
| `rao2014_annotations/`: Rao 2014 HiCCUPS loop and Arrowhead domain lists, IMR90 + GM12878 | 1.6 MB | fetch `rao2014_annotations` | tutorial `hic_structures`; uchrom-reproducibility `supp_table3/hic_structures/` (reference calls) |
| `genomes/hg19/chr{21,1}.fa.gz`: UCSC hg19 sequences | 12 MB + 74 MB | fetch `hg19_chr21`, `hg19_chr1` | tutorials `hic_structures`, `sc_structures` (chr21); uchrom-reproducibility `supp_table3/hic_structures/` (GC phasing of compartments) |
| `genomes/{mm10,hg19,hg38}/<g>.fa.gz`: UCSC whole-genome sequences | 830 + 905 + 938 MB | fetch `mm10_genome`, `hg19_genome`, `hg38_genome` | CpG frequency per bin for `uchrom.strc.comp.single_cell_compartments`; tutorial `sc_structures` (mm10); uchrom-reproducibility `supp_table3/sc_structures/scab_*.py` |
| `genomes/liftover/hg38ToHg19.over.chain.gz`: UCSC liftOver chain | 1.2 MB | fetch `hg38_to_hg19_chain` | uchrom-reproducibility `supp_table3/hic_structures/pseudobulk_gm12878.py` (scMicro-C hg38 → Rao 2014 hg19) |
| `genomes/hg38/hg38.refGene.gtf.gz`: UCSC hg38 refGene annotation (GTF) | 24 MB | fetch `hg38_refgene` | nmeth-bc Fig. 2 (`capture_fig2_spatial.py` in the paper repository: genes of the browser's genome view) |
| `reference/seurat/cc.genes.updated.2019.rda`: Tirosh et al. 2016 cell-cycle genes (S, G2/M), 2019 symbols, as Seurat ships them | 0.5 kB | fetch `seurat_cc_genes_2019` | uchrom-reproducibility `extended_data_fig2` (stage cellcycle: S / G2M scores of the spots' RNA as covariates) |
| `ray2019_k562/4DNFI4QQPDMR.mcool`: K562 in situ Hi-C | 849 MB | fetch `ray2019_k562` | provenance of `K562_chr21_30kb.cool` |
| `4DNFIFLJGGNR.csv`: Takei 2021 mESC FOF-CT, 1 Mb genome-wide loci | 47 MB | fetch `takei2021_1mb` | an unpublished benchmark (simulation truth, locus map, diploid simulation); an unpublished benchmark (mESC truth) |
| `nagano2017_dip/`: Nagano 2017 diploid serum mESC fend pairs (+ the `nagano2017_hap/` fends and chain) | 1.96 GB | fetch `nagano2017_dip_serum`; loader `nagano2017_dip_serum` | uchrom-reproducibility `supp_table3/sc_structures/snaphic_*.py` (SnapHiC's data) |
| `yu2021_snaphic/`: SnapHiC paper source data (loops by number of cells; mESC reference loops) | 34 MB | fetch `yu2021_snaphic` | tutorial `sc_structures`; uchrom-reproducibility `supp_table3/sc_structures/snaphic_mesc.py` |
| `snaphic/{mm10,hg19}_filter_regions.txt`: SnapHiC's excluded bins | 3.8 MB | fetch `snaphic_filter_regions` | `call_loops_snaphic(exclude=)`; tutorial `sc_structures`; uchrom-reproducibility `supp_table3/sc_structures/snaphic_*.py` |
| `nagano2017_hap/`: Nagano 2017 haploid mESC scHi-C fend pairs + mm9 fends + chain | 1.39 GB (+5 GB streamed, 253 MB kept) | fetch `nagano2017_hap`; recipe `build_nagano2017_hap.py` (NucDynamics structures) | an unpublished benchmark (step 1); atlas store `nagano2017_hap` |
| `takei2021_brain/`: Takei 2021 Science mouse cortex seqFISH+ tables | 597 MB | fetch `takei2021_brain` | an unpublished benchmark (brain imaging reference) |
| `tan2021_cortex/`: Tan 2021 Dip-C adult cortex, 510 cells | 13 GB | fetch `tan2021_cortex` | an unpublished benchmark (brain Dip-C baseline) |
| `tan2018_gm12878/`: Tan 2018 Dip-C GM12878, 17 cells | ~0.7 GB | fetch `tan2018_gm12878` | diploid EMber / NucDynamics validation |
| `quinodoz2018_sprite/`: Quinodoz 2018 SPRITE mouse ES cells, the authors' clusters | 6.2 GB | fetch `quinodoz2018_sprite` (**cluster**) | multi-way contacts of the store (`ChromData.clusters`, format 2.4): uchrom-reproducibility `extended_data_fig1/g_clusters_sprite.py` |
| `spacea_ma2026/`: Ma 2026 SpaceA, spatial SPRITE of 9 mouse embryo sections, E11.5-E14.5 (5 libraries, 17 runs) | 2.7 TB fastq; C6 run 1 alone: clusters 87 MB, store 550 MB with the derived maps | fetch `ma2026_spacea_<library>` (GSA, academic use); recipe `spacea_ma2026/slurm/` (a compute cluster) | per-spot check of `ChromData.clusters` (U-Chrom PR #153); the browser's cluster track; not in the atlas |
| `wu2025_scmicroc/`: Wu 2025 scMicro-C GM12878, 12 deepest cells | 3.1 GB (102 GB streamed) | fetch `wu2025_scmicroc` | EMber deep development and test (PREREG §11); Fig. 3a / S8 |
| `rao2014_imr90/4DNFIR1JDZH7.mcool`: Rao 2014 IMR90, 4DN GRCh38 | 4.6 GB | fetch `rao2014_imr90_4dn` (**cluster only**; laptops read it over HTTP) | an unpublished benchmark; an unpublished benchmark (range reads) |
| `bonev2017_mesc/4DNFIC21MG3U.mcool`: Bonev 2017 mESC Hi-C, 4DN mm10 | 12.6 GB | fetch `bonev2017_mesc_4dn` (**cluster only**) | an unpublished benchmark; an unpublished benchmark (range reads); tutorial `sc_structures` and uchrom-reproducibility `supp_table3/sc_structures/` (bulk mESC loops and insulation) |
| `WTC11_HiC_2Mb.hcs`: the IGM demo input (GPL-3) | 3.9 MB | downloaded on demand by an unpublished benchmark into `$UCHROM_IGM_CACHE` | IGM protocol of the native engine vs the original IGM |
| bulk IGM inputs (`fine_20kb.npz`, `igm_200kb.npz`, `su_3mb.npz`, `su_1mb.npz`, `takei_1mb.npz`) | 0.1–10 GB | **derived** on a compute cluster (an unpublished benchmark, `slurm/build_real.sbatch`) | an unpublished benchmark |
| `liu2025_mop/`: Liu 2025 mouse MOp DNA-MERFISH, 4DN FOF-CT core + cell table | 1.68 GB + 17 MB; store 294 MB | fetch `liu2025_mop`; recipe `build_liu2025_mop.py` | Fig. 2 dataset scale; FOF-CT writer, format, streaming and cell-position benchmarks |
| `4DNFIQXONUUH.csv`: Takei 2021 mESC FOF-CT, replicate 2 | 34 MB | fetch `takei_rep2` | uchrom-reproducibility `supp_table3/arcfish_parity` (ArcFISH's loop / domain tutorial data); tutorials `tad_calling`, `loop_calling` (both replicates, as the ArcFISH paper) |
| `su2020_imr90/chromosome2_p-arm_replicate.tsv`: Su 2020 chr2 p-arm tracing | 78 MB | fetch `su2020_chr2_parm` | uchrom-reproducibility `supp_table3/arcfish_parity` (ArcFISH's compartment tutorial data) |
| uchrom-reproducibility `supp_fig6/browser/_data/takei2025_fov0_x{1,3,10,30}.chromdata.zarr` | 8–70 MB | **derived**: uchrom-reproducibility `supp_fig6/browser/make_scaled.py` (replicated FOV 0 cells, geometry only) | Fig. 6c browser benchmarks |
| `schicar_mop/data/...` (inputs of the scHiCAR to MERFISH mapping) | — | **derived, recipe pending** | an unpublished benchmark |

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
  uchrom-reproducibility `supp_table3/nucdyn/a_nucdyn_engine_speed.py`.  The `reconstruction` tutorial and the root `README.md`
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
  an unpublished benchmark (DI caller before / after the calling convention) and the DI
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
  an unpublished benchmark and `cd2_zarr_validation.py` (they read the former 1.x
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
  (an unpublished design note, finding 5), so its restraints joined
  scrambled particle pairs.  The native engine (`packages/uchrom-recon`, validated against the
  original on the 8 Stevens cells) can rebuild it (`build_sim_cell1.py`, now using that engine), but
  the rebuild is deferred: the Fig. 6 agent benchmark's ground truth (uchrom-reproducibility `supp_fig7`,
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
- **Used by**: `packages/uchrom-browser/tests/test_genome_views.py`; uchrom-reproducibility `extended_data_fig1/f_roundtrip.py`
  (PDB / .3dg / .mcool rows; reads the fixture); the Fig. 6 agent benchmark
  (uchrom-reproducibility `supp_fig7`, expects `sim_cell1/sim_cell1.cdz` under `--data-root`);
  an unpublished benchmark and `cd2_upgrade_validation.py` (from the former 1.x `.h5cd`);
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
- **Benchmark tables**: an unpublished benchmark and
  `tan2021_adult_cortex_cells.tsv` (see the matched-modality datasets);
  an unpublished benchmark, `plumbing_imr90_chr21_22_igm200kb.json` (see the bulk
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
  an unpublished benchmark (ChromData 2.0 validation, all 20 chromosomes);
  an unpublished benchmark (FOF-CT writer, with the cell / RNA tables);
  uchrom-reproducibility `extended_data_fig1/cd21_streaming_validation.py` (streaming vs in-memory ArcFISH loop / TAD calls);
  an unpublished benchmark (cell positions); an unpublished benchmark,
  `cd2_zarr_validation.py`; an unpublished benchmark (`takei2021_25kb` truth);
  an unpublished benchmark, `b_dimes.py` (`--takei`), `b_first_look.py` (optional mESC
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
  `tests/emb/test_cell_embeddings.py`; an unpublished benchmark (1.x → 2.0),
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
  An unpublished benchmark reads the 1 Mb tables of replicates 1 + 2 (201 + 245
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
  ECSV in the notebook); `bintu_to_pyhim_ecsv.py`; Fig. 3b / 3c (an unpublished benchmark,
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
- **Used by**: an unpublished benchmark (ChromData 2.0: structure callers before / after
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

### `quinodoz2018_sprite/`: Quinodoz 2018 SPRITE clusters, mouse ES cells (6.2 GB; fetch `quinodoz2018_sprite`)

- **File**: `quinodoz2018_sprite/GSE114242_mouse_combined_clusters.tar.gz` (md5 `30f9c1e0a64c7dd011a8876319626e94`),
  a tar of two gzipped cluster files of the authors' pipeline: `mouse.mapq-ge10.clusters.gz` (3.8 GB; reads with
  MAPQ ≥ 10) and `mouse.mapq-ge30.clusters.gz` (2.7 GB; MAPQ ≥ 30).
- **Format**: one SPRITE cluster per line, `barcode<TAB>chrom:pos<TAB>chrom:pos…`, one `chrom:pos` per read (the
  read start as the pipeline writes it: pysam's 0-based `reference_start`, positions 0 occur; mm9).  A barcode is
  the cluster's tag sequence (`…_DPM6.YbotE63.Odd2Bo82…`).
- **Content**: multi-way contacts of mouse ES cells (bulk, no cells): clusters of 1 to thousands of reads.
- **Source**: Quinodoz et al. 2018, *Cell* 174:744 (doi:10.1016/j.cell.2018.05.024), "Higher-order
  inter-chromosomal hubs shape 3D genome organization in the nucleus"; GEO
  [GSE114242](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE114242) (public, no restriction on use stated):
  ```
  https://ftp.ncbi.nlm.nih.gov/geo/series/GSE114nnn/GSE114242/suppl/GSE114242_mouse_combined_clusters.tar.gz
  ```
  The series also has the authors' pairwise maps (`GSE114242_mouse_intra_*.tar.gz`) and the human clusters.
- **Used by**: uchrom-reproducibility `extended_data_fig1/g_clusters_sprite.py` (cluster job
  `extended_data_fig1/slurm/clusters.sbatch`): the clusters as a `ClusterTable` (a read at `pos` → the
  fragment `[pos, pos + 1)`), written to a store and read back (checksum over clusters), store size, region
  queries in memory, backed and over HTTP; `g_clusters_layout.py` (`slurm/clusters_layout.sbatch`): the locus
  index's chunk and codec.  Not downloaded on laptops.

### `spacea_ma2026/`: SpaceA, spatial SPRITE of mouse embryo sections (2.7 TB fastq, 17 runs; fetch `ma2026_spacea_<library>`)

- **Source**: Ma et al. 2026, *Developmental Cell* (doi:10.1016/j.devcel.2026.09.004), SpaceA; Genome Sequence
  Archive (CNCB-NGDC) [CRA038845](https://ngdc.cncb.ac.cn/gsa/browse/CRA038845), **academic use** under the GSA's
  terms (not re-hosted; not in the public atlas).  Analysis code: github.com/YuetongXU/SpaceA-Paper (commit
  `c1e1753`, barcode configs, the Snakefile, the DPM split and the cluster filter), the Guttman lab's
  github.com/GuttmanLab/sprite-pipeline (commit `5e11a58`, BarcodeIdentification and the cluster scripts).
- **Files**: paired fastq per run, `https://download.cncb.ac.cn/gsa6/CRA038845/<run>/<run>_r{1,2}.fastq.gz`, md5 in
  the project's `md5sum.txt`.  Five libraries, each sequenced in 2-6 runs (`runs.tsv`), registered one entry per
  library: `ma2026_spacea_c6` (E13.5 C6; CRR2725644-46, 378 GB), `_l1l2` (E11.5 L1 + L2; CRR2725632-34, 524 GB),
  `_l5l6` (E12.5 L5 + L6; CRR2725635-37, 373 GB), `_c1c4` (E13.5 C1 + C4; CRR2725638-43, 958 GB), `_f5f6` (E14.5
  F5 + F6; CRR2725647-48, 452 GB).  A library of two sections tells them apart by the DPM tag (the authors'
  `split_dpm_from_full_BC_fq.py`); which tag is which section (`samples.tsv`: L1 dpm1, L2 dpm2, L5 dpm2, L6 dpm4,
  C1 dpm4, C4 dpm3, F5 dpm3, F6 dpm4) is the comment on the tag's line in the library's config.  GSA stalls and
  closes transfers: `slurm/fetch.sbatch` (an array over `runs.tsv`) resumes them (aria2c with 4 connections, else
  `wget -c`), requeues itself before its time limit and checks the md5s.
- **Recipe** (`apps/atlas/recipes/spacea_ma2026/slurm/`, Slurm jobs; settings in `common.sh` — `SPACEA_ROOT`,
  `SPACEA_REF` —): `setup_env.sbatch` (conda environment, the two repositories at their commits, STAR index of mm10
  + UCSC refGene, sjdbOverhang 149) → `fetch.sbatch` → `process.sbatch <run>` (the authors' Snakefile step by step
  up to the alignment: cutadapt, BarcodeIdentification with the library's config + full barcodes, STAR →
  `<run>.star.bam`; `stats.tsv`) → `clusters.sbatch <sample>` (the reads of the section's DPM tag from every run of
  its library, merged, Picard duplicates over them, MAPQ 255, `get_clusters -n 6` → `$SPACEA_DEST/<sample>/`) →
  `build_store.sbatch <sample>` (`build_store.py`: the clusters as `ChromData.clusters["spacea"]`, one cell per
  spot; then `derive.py`, below).
- **Spots**: read 2 is ODD|EVEN|ODD|Y|LIGTAG|DPM; a spot is the pair of the two orthogonal channel sets
  (LIGTAG, 50 tags `oddTop1-50`; Y, 100 tags `evenTop1-100`), cell id `oddTopN.evenTopM`, position = the channel
  pair (`cells` columns `centroid_x` = LIGTAG / `centroid_y` = Y, unit `channel`).  Inferred from the configs and the authors' file naming (their
  split script and spot list are not public); confirmed by the fragments-per-spot grid, which shows the embryo.
- **CRR2725644 alone** (the first pilot, 3 % of C6's reads): 52.8 M pairs after cutadapt, 18.5 M with a full barcode, 8.0 M uniquely mapped, 7.16 M after
  duplicates → 1,407,822 clusters; store 192 MB, 4,974 spots (median 994 fragments, 2,475 spots with ≥ 1,000).
  Every cluster is kept as written; the authors' filters (cluster size 2–1,000, chromosome share, cis share, spot
  QC) are analysis choices.
- **Used by**: the per-spot check of `ChromData.clusters` (U-Chrom PR #153: `get_cell`, `region` with size and
  spot filters, backed and over HTTP, equal to memory).

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
- **Source**: Kim et al. 2020, *PLOS Computational Biology* 16:e1008173 (doi:10.1371/journal.pcbi.1008173), "Capturing cell type-specific chromatin
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
- **Used by**: tutorial `features` (per-bin GTF-annotation and sequence features on chromosome 19);
  tutorial `pseudobulk` (refGene: gene density per 1 Mb bin, the orientation of the compartment
  eigenvectors of the dscHi-C maps).  The same refGene file is fetched by `schicar_atac` into `schicar_mop/raw/` for `build_schicar_mop.py`.

### `genomes/hg38/hg38.refGene.gtf.gz`: UCSC hg38 refGene annotation (fetch `hg38_refgene`)

- **File**: `genomes/hg38/hg38.refGene.gtf.gz` (24 MB, GTF, md5 `a35c6a276a5cf1d9f200266a82176897`) from
  `https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/genes/hg38.refGene.gtf.gz` (downloaded 2026-10-09; UCSC
  updates the file, so a later download may differ and fail the md5 check: update the md5 with the date).
- **Source**: UCSC Genome Browser, hg38; refGene = NCBI RefSeq genes on hg38 (Navarro Gonzalez et al. 2021,
  *Nucleic Acids Res* 49:D1046).  Fetched from UCSC's public download server, not re-hosted (UCSC's conditions
  of use apply).
- **Used by**: the gene track of the browser's genome view in nmeth-bc Fig. 2 (`capture_fig2_spatial.py`, paper
  repository: gene spans, the union of each gene's RefSeq transcripts).

### `reference/seurat/`: cell-cycle genes (fetch `seurat_cc_genes_2019`)

- **Files**: `reference/seurat/cc.genes.updated.2019.rda` (538 bytes, md5 `55d7e35793436d5e91646d774d9f86c4`) from
  `https://raw.githubusercontent.com/satijalab/seurat/d28233a843ede385acdee1cae7e9fb9d70e76078/data/cc.genes.updated.2019.rda`
  (a fixed commit of the Seurat repository).
- **Content**: an R list (`cc.genes.updated.2019`) of two character vectors, `s.genes` (43) and `g2m.genes` (54):
  the cell-cycle genes of Tirosh *et al.* 2016 (*Science* 352:189–196) with their 2019 HGNC symbols.  Read with R
  (`load()`); mouse symbols are the human ones in title case.
- **Licence**: Seurat's data (MIT, Seurat's `LICENSE`); the gene lists are the published ones.
- **Used by**: uchrom-reproducibility `extended_data_fig2` (stage `cellcycle`: S and G2/M scores of each spot's RNA, as
  covariates of the contact features next to the RNA and copy-number principal components).

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
  `test_groups.py` (real-data checks, skipped without it); an unpublished benchmark;
  uchrom-reproducibility `extended_data_fig1/f_roundtrip.py` (chromdata.zarr / FOF-CT / AnnData rows); Fig. 6
  (uchrom-reproducibility `supp_fig6/browser/bench_server.py`, `make_scaled.py`, agent benchmark uchrom-reproducibility `supp_fig7`;
  the paper's figure scripts (u-chrom-paper `manuscripts/nmeth-bc/figures/shared/agents_panels/extract_data.py`)); an unpublished benchmark
  (1.x → 2.0), `cd2_zarr_validation.py` (→ `.chromdata.zarr`), `cd2_io_benchmark.py` (from the former
  `.h5cd`).

## The atlas: stores and their recipes

The public atlas (https://uchrom-atlas-r2.u-science.org, Cloudflare R2 bucket `u-chrom-atlas`) holds
self-contained `.chromdata.zarr` stores.  For each one, a recipe below builds the store and the files it
links (contact maps, AnnData, images) in the data directory from fetched files;
`python -m chromdata.embedded STORE [--upgrade]` copies the linked files into the store; and
`apps/atlas/PUBLISH.md` covers the upload, `apps/atlas/datasets.json` (display text, grouped by study)
and the catalog (`python -m chromdata.catalog build apps/atlas/datasets.json --root $UCHROM_DATA`).
uchrom-reproducibility `supp_fig6/atlas/validate.py` recomputes the checks of every store, uchrom-reproducibility `supp_fig6/atlas/hosted.py`
times the hosted browser on them, `python apps/atlas/build.py figures` draws the thumbnails of the atlas
page and `apps/atlas/hero_data.py` its hero animation (a Chen 2026 cerebellum section and three HiRES
brain cells).

| Atlas id | Size (MB) | Store (data directory) | Recipe | Inputs (fetch) |
| --- | --- | --- | --- | --- |
| `hicrna_mouse_brain`, `hicrna_mouse_embryo`, `hicrna_human_melanoma` | 2,254 / 4,578 / 2,728 | `spatial_hicrna/<id>.chromdata.zarr` | `build_spatial_hicrna.py`, `link_spatial_hicrna_contacts.py` (contacts from the cluster) | `spatial_hicrna` |
| `chen2026_e13_embryo_50um`, `chen2026_brain_embryo_10um`, `chen2026_brain_embryo_20um`, `chen2026_cortex_adult_10um`, `chen2026_hippocampus_adult_10um`, `chen2026_cerebellum_adult_20um` | 711 / 1,887 / 1,446 / 664 / 306 / 165 | `spatial_hic_chen2026/<tissue>.chromdata.zarr` (id without `chen2026_`) | `build_spatial_hic_chen2026.py`, `link_spatial_hic_chen2026_contacts.py` (contacts from the cluster) | `spatial_hic_chen2026` |
| `atac_hic_mouse_brain` | 390 | `spatial_atac_hic/mouse_brain.chromdata.zarr` | `build_spatial_atac_hic.py`, `link_spatial_atac_hic_contacts.py` (contacts from the cluster) | `spatial_atac_hic` |
| `stevens2017_mesc` | 26 | `stevens2017_mesc/stevens2017_mesc.chromdata.zarr` | `build_stevens2017.py` | `stevens2017` |
| `hires_brain`, `hires_embryo` | 261 / 3,174 | `hires2023/<id>.chromdata.zarr` | `build_hires2023.py brain`, `build_hires2023.py embryo` | `hires2023_meta`, `hires2023` |
| `dschic_aging_cortex` | 2,278 | `dschic2025/dschic_aging_cortex.chromdata.zarr` | `build_dschic2025.py` | `dschic2025_aging` |
| `gageseq_mouse_cortex`, `gageseq_human_bm_cd34` | 485 / 319 | `gageseq2024/<id>.chromdata.zarr` | `build_gageseq2024.py mouse`, `build_gageseq2024.py human` | `gageseq2024` |
| `droplet_hic_mouse_cortex`, `paired_hic_mouse_cortex` | 322 / 339 | `droplet_hic2024/<id>.chromdata.zarr` | `build_droplet_hic2024.py droplet`, `build_droplet_hic2024.py paired` | `droplet_hic2024_meta`, `droplet_hic2024` |
| `schicar_mouse_cortex` | 263 | `schicar_mop/schicar_mop.chromdata.zarr` | `build_schicar_mop.py` | `schicar_rna`, `schicar_dna`, `schicar_atac` |
| `unic_human`, `unic_mouse` | 681 / 271 | `unic2025/<id>.chromdata.zarr` | `build_unic2025.py human`, `build_unic2025.py mouse` | `unic2025` |
| `takei2025_cerebellum` | 2,051 | `takei2025_cerebellum/takei2025_cerebellum_rep1.chromdata.zarr` | `build_takei2025_cerebellum.py` | `takei2025_cerebellum` |
| `bintu2018_4dn`, `mateo2019_orca`, `hafner2023_orca`, `murphy2024_orca`, `hung2024_orca`, `huang2021_4dn`, `liu2020_mina`, `takei2021_brain_4dn` | 40 / 151 / 151 / 131 / 456 / 6 / 49 / 87 | `<name>/<name>.chromdata.zarr` | loaders of the same names (`uchrom.datasets.load`; see *4DN chromatin-tracing studies*); Hafner / Hung with field-of-view positions; RNA embeddings by `derive_embeddings.py`: `liu2020_mina` `--rna-regex 'Gene_Expression_Counts_\d+' --leiden`, `takei2021_brain_4dn` `--rna-after nuc_volume` | the same names |
| `su2020_chr2`, `su2020_chr21_cell_cycle`, `su2020_genome`, `su2020_genome_amanitin`, `su2020_genome_transcription` | 26 / 26 / 42 / 105 / 105 | `<name>/<name>.chromdata.zarr` | loaders of the same names; the atlas copy of `su2020_chr2` without its variable-bin Hi-C link | the same names |
| `takei2021_mesc` | 51 | `takei2021_mesc_4dn/takei2021_mesc_4dn.chromdata.zarr` (since 2026-10-30: the whole 4DN set; before, `takei2021_mesc/` of the loader `takei2021_mesc`, replicate 1 at 25 kb) | loader `takei2021_mesc_4dn`, `derive_embeddings.py --rna-after 'area_cyto(um2)' --leiden` | `takei2021_mesc_4dn` |
| `liu2025_mop`, `liu2025_mecp2` | 813 / 1,309 | `liu2025_mop_4dn/liu2025_mop_4dn.chromdata.zarr` (since 2026-10-30: the four MOp experiments; before, one, by `build_liu2025_mop.py`), `liu2025_mecp2/liu2025_mecp2.chromdata.zarr` | loaders `liu2025_mop_4dn`, `liu2025_mecp2`; `derive_embeddings.py --rna-after neuron_identity` / `--rna-after Mecp2_genotype` | the same names |
| `tan2021_cortex`, `nagano2017_dip_serum` | 3,064 / 896 | `<name>/<name>.chromdata.zarr` | loaders of the same names, `derive_embeddings.py --hic per_cell` | `tan2021_cortex`, `nagano2017_dip_serum` |
| `nagano2017_hap` | 889 | `nagano2017_hap/nagano2017_hap.chromdata.zarr` | `build_nagano2017_hap.py`, `derive_embeddings.py --hic per_cell --leiden` | `nagano2017_hap` |
| `spacea_e135_c6` | 274 | SpaceA C6 store (run 1), without `results['hic']` | the SpaceA recipe (PR #155) | — |
| `takei2025_e14`, `takei2025_nmumg` | 4,421 / 1,883 | `takei2025_e14/takei2025_e14_rep1.chromdata.zarr`, `takei2025_nmumg/takei2025_nmumg.chromdata.zarr` | `build_takei2025_cerebellum.py --sample E14_rep1`, `... --sample NMuMG` | `takei2025_e14`, `takei2025_nmumg` |
| `liu2025_kras`, `cheng2025_perturb`, `chen2023_sox9`, `patterson2023_chrx`, `sawh2020_celegans`, `gutnik2024_celegans`, `messina2023_him`, `le2024_se`, `fujimori2026_hek293t`, `fujimori2026_k562`, `fujimori2026_mesc`, `tastemel2025_sox2`, `jay2025_thymocytes`, `jensen2025_cargo`, `llimos2022_axin2` | 312 / 55 / 19 / 8 / 2 / 3 / 5 / 169 / 13 / 3 / 9 / 41 / 7 / 6 / 2 | `<name>/<name>.chromdata.zarr` | loaders of the same names (see *4DN chromatin-tracing studies*) | the same names |
| `tan2018_gm12878` | 394 | `tan2018_gm12878/tan2018_gm12878.chromdata.zarr` | loader `tan2018_gm12878`, `derive_embeddings.py --hic per_cell` | `tan2018_gm12878` |
| `tan2019_dipc`, `wu2024_limca`, `liu2026_hires_xci` | 1,029 / 1,322 / 1,258 | `<name>/<name>.chromdata.zarr` | `build_dipc_structures.py <name>`, `derive_embeddings.py --hic per_cell --leiden` | the same names |
| `xu2025_sperm_human`, `xu2025_sperm_mouse` | 1,017 / 704 | `xu2025_sperm/<id>.chromdata.zarr` | `build_dipc_structures.py xu2025_sperm`, `derive_embeddings.py --hic per_cell --leiden` | `xu2025_sperm` |
| `lando2024_mesc`, `zhou2019_rice` | 71 / 15 | `<name>/<name>.chromdata.zarr` | `build_nuc_structures.py <name>`, `derive_embeddings.py --hic per_cell` (`--leiden` for Lando) | the same names |

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
  2.94 GB and as format 2.2 2.05 GB (`*.v22.chromdata.zarr`, an unpublished benchmark); the
  atlas store `takei2025_cerebellum` is the format-2.2 store, `--upgrade`d (2,051 MB).

  The raw CSVs stay in `takei2025_cerebellum/raw/` (7.9 GB; uchrom-reproducibility `extended_data_fig1/allele_qc.py` reads their
  three allele columns); `--drop-raw` deletes them.
- **Cell lines** (`--sample E14_rep1` / `--sample NMuMG`; fetch `takei2025_e14` / `takei2025_nmumg`: the record's
  `E14_rep1.tar.gz` and `NMuMG.tar.gz` with the same locus map): built the same way into
  `takei2025_e14/takei2025_e14_rep1.chromdata.zarr` and `takei2025_nmumg/takei2025_nmumg.chromdata.zarr`.  No
  clustering is deposited for them, so the cells carry only their field of view (`cells['fov']`) and no cell type;
  `uns['source']` names the sample.  E14 replicate 1: 11 FOVs, 523 cells, 22,797 traces, 32.1 M spots (median
  48,841 loci per cell; 4.62 GB, peak RSS 86 GB when combining).  NMuMG: 10 FOVs, 384 cells, 19,911 traces, 12.0 M
  spots (median 24,297 loci per cell; 1.97 GB, peak RSS 34 GB).  `--combine-only` redoes the combined store from the per-FOV stores.  Atlas
  `takei2025_e14`, `takei2025_nmumg`.
- **Caveat — allele calls**: the default `dbscan_ldp_nbr_allele` traces often merge both homologs / add
  off-trace spots; see uchrom-reproducibility `extended_data_fig1/allele_qc.py` and
  uchrom-reproducibility `extended_data_fig1/results/allele_qc.json`.
- **Also**: `uchrom.io.load_takei2025_cerebellum()` returns the local store
  `takei2025_cerebellum/takei2025_cerebellum_rep1.chromdata.zarr` when it exists; otherwise (with
  `download=True`, the default) it fetches `takei2025_cerebellum` (or `takei2025_cerebellum_rep2`) and
  `takei2025_rna` (md5-checked), extracts the tarball into `takei2025_cerebellum/cerebellum_rep<N>/` and
  builds the store with a linked RNA AnnData (`takei2025_cerebellum_rep<N>.h5ad`).
- **Used by**: the atlas store (`ds.atlas("takei2025_cerebellum")`): tutorials `features` (chromosome 19
  and the IF channels it needs), `cell_embeddings`, `import_seqfish_multiomics` (its last section), the
  quickstart of the docs.  The local build: tutorials `takei2025_auto_discovery` and
  `takei2025_iterative_auto_discovery` (`load_takei2025_cerebellum()`); uchrom-reproducibility `extended_data_fig1` (`b_storage.py`,
  `c_access.py` — whole-cell subsets, 1e4–1e7 spots; 1e8 by replication, `replicate_store.py` —,
  `allele_qc.py`, `rowgroup_sweep.py`, `spot_tracks_encoding.py`, `cd22_variants.py`);
  an unpublished benchmark (→ `.chromdata.zarr`, value identity);
  uchrom-reproducibility `extended_data_fig1/cd21_streaming_validation.py` (2.0 → 2.1 conversion, streaming seqFISH+ import from
  `raw/`, streaming distance maps); an unpublished benchmark (2.1 → 2.2 conversion,
  bitwise check); an unpublished benchmark (cell positions).

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
  purity 0.33 vs 0.19–0.30); an unpublished benchmark gives the per-modality numbers.
  `--update` redoes only the ATAC / Hi-C step;
- `contacts_all.mcool` (42 MB) — all 120,280,303 contacts, 250 kb … 2 Mb;
- `contacts_<celltype>.cool` — 22 pseudo-bulk maps at 500 kb;
- `contacts_cells_1Mb.scool` (257 MB) — one map per cell (all 5,313);
- `schicar_mop_rna.h5ad` — RNA UMI counts of every gene (`uns['linked_anndata']`).

Links are stored relative to the dataset folder; `python -m chromdata.embedded` embeds them for the
atlas.  In all ~400 MB plus the h5ad.

**Used by**: the atlas store: tutorial `cell_embeddings`.  The local build: the web browser (matrix,
embedding and field views for data without 3-D); an unpublished benchmark;
uchrom-reproducibility `extended_data_fig1/e_contacts.py`, `e_contacts_query.py` (Fig. 2f and supplement: group pseudo-bulk vs the
per-type `contacts_<type>.cool`; link vs copy import), `f_crossmodal.py` (Fig. 2f: RNA Leiden clusters →
pseudo-bulk maps and P(s) from the linked `.scool`), `f_roundtrip.py` (Fig. 2b, .scool row);
uchrom-reproducibility `supp_fig6/browser/bench_server.py` (contact-map and pseudo-bulk latency); agent benchmark
uchrom-reproducibility `supp_fig7`; an unpublished benchmark (spot compartments vs cell-type
composition); an unpublished benchmark (1.x → 2.0), `cd2_zarr_validation.py`
(→ `.chromdata.zarr`).

**scHiCAR → MERFISH mapping — derived inputs, recipe pending.**  The mapping analysis
(an unpublished benchmark, Tangram) reads `$UCHROM_SCHICAR_ROOT`
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
  **not** fetched; the contacts of the other sections are reprocessed from them on a compute cluster (below).
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
- **Validation** (an unpublished benchmark):
  - Per-spot contacts against the authors' `stat_cropped.csv`: all 1,999 spots matched, Pearson r
    (log) = 0.998.  Our totals are 0.77× theirs: the published BEDPE holds 86.5 M pairs against their
    103.2 M `cis_contact`, which is probably counted before deduplication.
  - Compartment E1 of our 500-kb bulk map against the section's mean published ssA/B, per chromosome:
    median |r| = 0.956 (min 0.923, chr3).
  - Every store: links resolve, all spots have positions, the ssA/B and RNA AnnData are aligned with
    the Hi-C / RNA spots.
- **Contacts of the other sections from the raw reads** (`apps/atlas/recipes/spatial_hic_chen2026/slurm/`):
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
  - Validation script: an unpublished benchmark.
  - Output in the archive (`$UCHROM_ARCHIVE/spatial_hic_chen2026/<run>/`): dedup pairs, per-spot 1-Mb `.scool`, bulk
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
    order and with the authors' (`slurm/barcodes_96_authors_index.tsv`, read off the `pixel` / spot
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

  - Checks that do not use the linking criterion (uchrom-reproducibility `supp_fig6/atlas/spatial_hic_chen2026_reprocessed.py`, all
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
  embeddings; an unpublished benchmark, `spatial_hic_chen2026_reprocessed.py`;
  an unpublished benchmark (spot compartments vs cell-type composition); the cerebellum
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
- **Contacts from the raw reads** (SRA, 4 runs, 177 GB; `apps/atlas/recipes/spatial_atac_hic/slurm/`):
  - All four runs show the same layout and about 10 % ligation junctions (`GATCGATC`): each section's
    two runs are two sequencing rounds of one ATAC-Hi-C library, and they are merged.
  - Read 2 carries the barcodes: read2[22:30] + read2[60:68] = the 16-base spot barcode.  Both linkers
    are required (the authors' `bcsplit.py` / `00.filter-linker.sh`).
  - Mapping, per-spot deduplication and the 1-kb cis cut reuse the Chen 2026 pipeline (above).
  - Output in the archive (`$UCHROM_ARCHIVE/spatial_atac_hic/<section>/`, 3.3 GB): dedup pairs, per-spot 1-Mb
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
- **Processed on a compute cluster** (`apps/atlas/recipes/spatial_hicrna/slurm/`, `process.sbatch`):
  - Input: the published `.nodups.pairs.gz`.
  - Output in the archive (`$UCHROM_ARCHIVE/spatial_3dgenome/<sample>/`, 21 GB): per-spot 1-Mb `.scool`, bulk
    `.mcool` (25 kb – 1 Mb) and per-spot statistics.
  - Kept: 31–47 × 10⁸ pairs per sample (1.2 × 10⁸ for E13.5 r2).
  - In the two E13.5 embryos 37–44 % of the pairs fall on spots outside the published tissue positions
    (about 1 % elsewhere); not yet explained.
- **Stores** (`hicrna_mouse_brain`, `hicrna_mouse_embryo`, `hicrna_human_melanoma`, also the atlas ids;
  the prefix keeps them apart from the ATAC-Hi-C `mouse_brain`):
  ```bash
  python -m uchrom.datasets fetch spatial_hicrna                  # GEO files, 2.3 GB
  python apps/atlas/recipes/build_spatial_hicrna.py               # ~2 min: RNA, images, positions, published labels / latents
  # contact maps: copy $UCHROM_ARCHIVE/spatial_3dgenome/<sample>/ (17.8 GB) to spatial_hicrna/contacts/
  python apps/atlas/recipes/link_spatial_hicrna_contacts.py       # links per-spot .scool + bulk .mcool, mouse-brain ssAB
  # per-spot contact statistics: sbatch spatial_hicrna/slurm/contact_stats.sbatch <sample> (one pass over the
  # .pairs, 2-4.5 h per sample), copy <sample>.contact_stats_q30.npz from the archive to spatial_hicrna/contacts/
  python apps/atlas/recipes/link_spatial_hicrna_contact_stats.py  # cellm contacts.*, cells contacts.n_cis / n_trans
  python uchrom-reproducibility/supp_fig6/atlas/spatial_hicrna_validation.py                  # -> supp_fig6/atlas/results/spatial_hicrna_validation.json
  ```
  Cells are spots (`<section>:<barcode>`); only in-tissue spots are kept (brain 6,275 / 6,199; E11.5
  32,799; E13.5 17,278 / 14,784; melanoma 6,268 / 6,381), every one with RNA and a linked contact map.
- **Per-spot contact statistics** (added 2026-10-09; `uchrom.io.ContactStats`, `spatial_pairs_stats.py`):
  per spot the cis contact-distance histogram in scHiCluster's log2 bins (2.5 kb × 2^(k/8), Guo et al.'s
  short / long-range ratio), per read orientation, and cis / trans contacts per chromosome; MAPQ >= 30, the
  contacts of the per-spot maps.  In the stores: `cellm["contacts.distance"]` (spots × 132 / 134 bins, summed
  over chromosomes, int32), `contacts.orientation`, `contacts.cis`, `contacts.trans`, `cells` columns
  `contacts.n_cis` / `n_trans`, `uns["contact_stats"]["contacts"]` (+12–53 MB per store).
  `uchrom.fea.contact_features(cd)` gives the short / long ratio, bands, decay slopes and cis fraction.
  - Checks: for every spot of the 7 samples (89,984 spots, 2.28 × 10¹⁰ contacts) cis + trans equal the
    per-spot maps' counts (`hic_contacts`); a second filter (`contact_stats_all.npz`, every pair, as the
    paper's contact lists) stays in the archive.
  - the archive: `$UCHROM_ARCHIVE/spatial_3dgenome/<sample>/<sample>.contact_stats_{q30,all}.npz` (21–103 MB each) and
    `.contact_stats.json` (pair counts, pair types, filters, timings).
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
- **Validation** (real data, uchrom-reproducibility `supp_fig6/atlas/spatial_hicrna_validation.py`):
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
- **Embedding for an atlas** (`chromdata.embedded`, an unpublished benchmark):
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
- **Used by**: the atlas (`hicrna_*`); uchrom-reproducibility `supp_fig6/atlas/spatial_hicrna_validation.py`,
  an unpublished benchmark; an unpublished benchmark (spot compartments vs cell-type
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
  - Brain only: fetch `hires2023_brain` (4.5 GB: the 426 brain cells' pairs and 20 kb structures on GEO, names
    `ValaB8w*` / `ValbB8w*`, the 399 of the brain metadata among them; same paths as `hires2023`).  Used by
    uchrom-reproducibility `fig2` (EMber reconstructions of the brain cells, on a compute cluster).
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
  - Used by: tutorial `pseudobulk` (cell-type pseudo-bulk maps, compartment strength at matched depth) and
    uchrom-reproducibility `supp_table3/hic_structures/pseudobulk_dschic.py`, both reading the atlas store over HTTP.
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
  - Also: an unpublished benchmark (mouse cortex).
- **Droplet Hi-C / Paired Hi-C** (Chang et al. 2025, *Nat. Biotechnol.*,
  doi:10.1038/s41587-024-02447-1; GEO GSE253407): mouse cortex, Droplet Hi-C 6,235 cells (LC462,
  LC716), Paired Hi-C 24,284 cells (Hi-C LC464 / LC465 / LC608 with RNA LC466 / LC467 / LC613, barcodes
  paired by the metadata).  The pairs keep every read pair; cis pairs < 1 kb are dropped.
  - Get it: fetch `droplet_hic2024_meta` (4 MB) and `droplet_hic2024` (72 GB), then
    `python apps/atlas/recipes/build_droplet_hic2024.py droplet` and `... paired` →
    `droplet_hic2024/droplet_hic_mouse_cortex.chromdata.zarr`,
    `droplet_hic2024/paired_hic_mouse_cortex.chromdata.zarr` (atlas ids the same).
  - Also: an unpublished benchmark (Paired Hi-C).
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

### Single-cell Hi-C with the authors' structures (`tan2019_dipc/`, `xu2025_sperm/`, `wu2024_limca/`, `liu2026_hires_xci/`, `lando2024_mesc/`, `zhou2019_rice/`)

Studies that deposit, per cell, the contacts and the authors' own 3-D structure.  `build_dipc_structures.py STUDY`
(hickit / Dip-C `.3dg`, 20 kb particles averaged to 100 kb, or 200 kb for HiRES) and `build_nuc_structures.py
STUDY` (NucDynamics `.n3d` / PDB with `.ncc` contacts) bin each cell's contacts at 100 kb (`<store>_cells_100kb.scool`)
and all cells together (`<store>_bulk.mcool`, 100 kb, 500 kb, 1 Mb; ICE from 500 kb), write the first structure of
each cell as the coordinates (a trace per cell, chromosome and copy) and a second run or model, where one is
deposited, as a layer with its deviation from the first after superposition (per particle:
`spot_tracks['run_deviation']` / `['model_deviation']`; per cell: `rmsd_*`, `median_dev_*`).  Then
`derive_embeddings.py STORE --hic per_cell [--leiden]` and `python -m chromdata.embedded STORE`.  Fetch the
originals with `python -m uchrom.datasets fetch STUDY` (GEO per-sample files; the series matrices give the
labels).

- **Tan 2019 Dip-C** (Tan L, Xing D, Daley N, Xie XS, *Nat Struct Mol Biol* 26:297, 2019,
  doi:10.1038/s41594-019-0205-2; GEO GSE121791): 409 cells of the mouse retina (132) and main olfactory
  epithelium (277), the `impute.pairs` and the 20 kb `clean.3dg` of runs 1 and 2; 4.4 GB.  103 M contacts.  The
  runs agree for most cells (RMSD of run 2 to run 1 after superposition: median 1.09 particle radii) but differ by
  more than 5 radii in 112 cells, mostly shallow ones (Spearman -0.7 between the RMSD and the contacts); single
  chromosome copies differ as much, and swapping the homologs does not bring the runs together, so the runs
  themselves disagree.  GEO's `cell type` repeats the tissue.  Atlas `tan2019_dipc`.
- **Xu 2025 sperm** (Xu H *et al.*, *Nat Commun* 16:3805, 2025, doi:10.1038/s41467-025-59055-z; GEO GSE276999):
  `.pairs.gz` and one 20 kb `.3dg` per cell (haploid sperm: a structure per chromosome); 10.8 GB.  Two stores:
  `xu2025_sperm_human` (hg38, 1,028 sperm, 179 M contacts) and `xu2025_sperm_mouse` (mm10, 739 sperm and 48 ES
  cells as controls, 119 M contacts); the Hi-C Leiden clusters put the 48 ES cells, and only them, in a cluster
  of their own.  Atlas `xu2025_sperm_human`, `xu2025_sperm_mouse`.
- **Wu 2024 LiMCA** (Wu H *et al.*, *Nat Methods* 21:974, 2024, doi:10.1038/s41592-024-02239-0; GEO GSE239969):
  410 cells of the mouse main olfactory epithelium (postnatal day 3-119; the authors' cell types: mOSN, iOSN,
  progenitor-1 / -2, unknown), `impute.pairs` (267 M contacts) and 20 kb `clean.3dg` of runs 1 and 2, and the
  gene counts of all cells in one table, whose columns name the cells `p014.bc_001` for the structures'
  `p014-bc_001` (mapped; all 410 found); 6.4 GB.  Runs 1 and 2: RMSD median 1.48 particle radii, more than 5 in 131
  cells.  The RNA Leiden clusters follow the authors' cell types (e.g. 83 of cluster 0's 84 cells are mOSN, 41
  of cluster 4's 48 progenitor-1).  Atlas `wu2024_limca`.
- **Liu 2026 HiRES of X inactivation** (Liu X *et al.*, *Genomics Proteomics Bioinformatics* qzag002, 2026,
  doi:10.1093/gpbjnl/qzag002; GEO GSE278310 + the update GSE310759): female C57BL/6J x CAST/EiJ mESC on day 0,
  0.5, 1, 1.5, 2, 2.5, 3 and 4 of differentiation (`d05`, `d15`, `d25` are half days), 1,741 cells with `.pairs.gz`
  (386 M contacts) and one 20 kb `clean.20k.0.3dg` each (averaged to 200 kb), the metadata tables (day, sample,
  the authors' RMSDs, Y/X ratio) and the UMI tables; 16 GB.  The UMI tables hold 1,507 of the cells (254 cells of
  every day are missing although the metadata give their UMIs).  Atlas `liu2026_hires_xci`.
- **Lando 2024** (Lando D *et al.*, *Mol Cell* 84:1406, 2024, doi:10.1016/j.molcel.2024.02.015; GEO
  GSE214264): 36 haploid 129/Ola mESC (Rex1-GFPd2) leaving naive pluripotency: 3 naive, 8 Rex1-high and 15
  Rex1-low after 24 h, 9 primed after 48 h; `.ncc` contacts (3.6 M) and `.n3d` structures at 100 kb, 10 models
  (models 1 and 2 read: RMSD median 0.29 particle radii); 277 MB.  Atlas `lando2024_mesc`.
- **Zhou 2019 rice** (Zhou S, Jiang W, Zhao Y, Zhou DX, *Nat Plants* 5:795, 2019,
  doi:10.1038/s41477-019-0471-3; GEO GSE123109): 15 cells of *Oryza sativa* Nipponbare (IRGSP-1.0): 4 egg, 4 sperm,
  3 unicellular zygotes, 4 shoot cells; `.ncc` contacts (2,200-17,300 per cell, most of them within 300 kb: 96 % of Egg_1's cis contacts) and one
  NucDynamics PDB per cell at 5 kb, chains named by `GSE123109_chromosome_chain_annotation.txt.gz`; 27 MB.
  Check: contacting 100-kb bins more than 200 kb apart lie 0.17-0.40 times as far apart as random pairs at the
  same separation in 13 cells; in Shoot_cell_3 and Sperm_2 0.79-0.90 (no other chain fits their contacts better).
  No map figure (too few contacts); its 15 cells form one Leiden cluster, so none is kept.  Atlas `zhou2019_rice`.

## Figure 3 datasets — bridges between contacts and geometry

Inputs of uchrom-reproducibility `supp_table3/nucdyn` (plan and reference numbers:
an unpublished design note).  `python -m uchrom.datasets fetch --fig3` fetches
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
  the paper's precision metric (an unpublished benchmark); the native NucDynamics engine's
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
- **Used by**: Fig. 3b (an unpublished benchmark): imaging contact frequency vs Rao 2014 Hi-C
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
  Zenodo files are fetched by their own entries (md5 from Zenodo, checked by `fetch`): `su2020_chr2` —
  `chromosome2.tsv` (130,300,276 B, `4ac51195…`; 935 loci of 50 kb over the whole chr2, 3,029 traced
  copies) + `Hi-C_contacts_chromosome2.tsv` (1,844,954 B, `be53b23e…`); `su2020_chr21_cell_cycle` —
  `chromosome21-cell_cycle.tsv` (166,260,146 B, `d8dc951c…`; chr21 with the cell-cycle state of each of
  4,558 copies); `su2020_genome_amanitin` — `genomic-scale-amanitin.tsv` (537,247,243 B, `cac8fa1d…`;
  4,102 cells after α-amanitin); `su2020_genome_transcription` —
  `genomic-scale-with_transcription_and_nuclear_bodies.tsv` (Zenodo name with spaces; 654,711,554 B,
  `172bda3f…`; 3,668 cells with nascent transcription per locus and distances to lamina, nucleoli and
  speckles).  Each has a loader (the table above).
- **Used by**: tutorials `tad_calling` and `compartment` (chr21); Fig. 3b
  (an unpublished benchmark, whole-chromosome imaging vs Hi-C; `b_dimes.py`);
  an unpublished benchmark (`su2020_chr21` truth cells) and `diploid_sim.py` (genome scale, both
  homologs); an unpublished benchmark (population deconvolution benchmark: genome-scale = primary diploid
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
- **Used by**: Fig. 3a / 3c (an unpublished benchmark, `c_hipps_wang2016.py`).  The
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
  Fig. 3b / 3c (an unpublished benchmark, `c_gemfish_first_look.py`,
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
| Rao 2014 IMR90 in situ, 4DN | set 4DNES1ZEJNRU: [4DNFIR1JDZH7](https://data.4dnucleome.org/4DNFIR1JDZH7/) (4,639,622,711 B, md5 `f91b77fa…`), [4DNFIJTOIGOI](https://data.4dnucleome.org/4DNFIJTOIGOI/) (8.3 GB) | 4.6–8.3 GB | GRCh38 | range-read one resolution: `h5py.File(fsspec.open(url).open())` → `cooler.Cooler(h['resolutions/5000'])` (~10 s per region; an unpublished benchmark); whole file on a compute cluster: fetch `rao2014_imr90_4dn` (bulk benchmark, see below) |
| Bonev 2017 mESC Hi-C (Takei 2021's comparison) | GEO GSE96107; 4DN set 4DNESDXUWBD9 [4DNFIC21MG3U](https://data.4dnucleome.org/4DNFIC21MG3U/) (12,551,353,248 B, md5 `dda4ed67…`, mm10) | 11–13 GB | mm10 | same fsspec range read, the 20 Takei 2021 loci × 25 kb (an unpublished benchmark); smaller unsorted-ES mcool 4DNFIDA2WGV8 (0.9 GB); whole file on a compute cluster: fetch `bonev2017_mesc_4dn` (bulk benchmark, see below) |
| Stevens 2017 HDF5 + raw | GSE80280 `Cell-<n>.hdf5.gz`, `GSE80280_RAW.tar` | 2.6 GB each / 20 GB | mm10 | not needed (contacts + `.pdb` suffice) |

The GM12878 `.hic` files hold every standard Juicer resolution from 1 kb to 2.5 Mb (primary + replicate
merged); the miniMDS comparison an unpublished benchmark currently uses the 4DN IMR90 chr21
(4DNFIR1JDZH7, range reads) instead.

## Matched-modality datasets — scHi-C structures vs chromatin tracing of the same cell type

Used by an unpublished benchmark (inputs built by an unpublished benchmark; jobs
an unpublished benchmark).  All are fetched on demand (none is in the
`--default` set); facts below were checked on the downloaded files unless marked *unverified*.

### Locus axis — an unpublished benchmark (78 KB, in the repository, **derived**)

- 2,460 Takei 2021 ~1 Mb loci (25 kb probes, mm10): `name` (`chrN-#k` for the 1,267 channel-1 loci, a
  nearby gene for the 1,193 channel-2 loci), `chrom`, `start`, `end`.
- The raw Zenodo tables (3735329, 4708112) give locus *names* only; the coordinates are in the papers'
  Table S1, which is not on Zenodo.  Recovered instead from public files: the 4DN FOF-CT table
  `4DNFIFLJGGNR.csv` (coordinates, no names) holds exactly the 705,143 spots of
  `DNAseqFISH+1Mbloci-E14-replicate1.csv` in `DNAseqFISH+.zip` (201 cells; X = x·0.103, Y = y·0.103,
  Z = z·0.25 µm); joining on (cell, rounded X/Y/Z) matches 683,808 spots and gives every name exactly
  one coordinate (no ambiguity).  Rebuild (after fetch `takei2021_1mb` and `seqfish`):
  `python an unpublished benchmark locus-map --fofct 4DNFIFLJGGNR.csv --zip DNAseqFISH+.zip`.
  The brain Table S7 uses the same 2,460 names (all present).

### an unpublished benchmark (31 KB, in the repository)

510 rows (`gsm`, `name`, `age`, `cross`, `cell_type`): the Tan 2021 adult cortex cells that passed the
authors' filter (`GSE146397_metadata.cells_contacts_100k.txt.gz`, ≥ 100 k contacts), matched to their
GSM by the GEO sample records (`!Sample_description`).  An identical copy,
`packages/uchrom/uchrom/datasets/tan2021_adult_cortex_cells.tsv`, is the cell list of fetch
`tan2021_cortex`.

### `4DNFIFLJGGNR.csv`: Takei 2021 mESC FOF-CT, 1 Mb genome-wide loci (47 MB; fetch `takei2021_1mb`)

- **Format**: FOF-CT core table (same columns as `4DNFIHF3JCBY.csv`), `##XYZ_unit=micron`, mm10.
- **Content**: E14 mESC, replicate 1: 2,460 loci (25 kb each) at ~1 Mb spacing across chr1–19 and chrX,
  201 cells, 705,143 spots.  One `Trace_ID` per (cell, chromosome) holds the spots of **both homologs**
  (not resolved in the deposited table; ~1.8 spots per locus).  an unpublished benchmark separates
  the homologs with a constrained 2-means (heuristic; checked on the homolog-resolved 25 kb table:
  median 97.8 % of spots on the right homolog) and keeps chrX (male line) as a single copy.
- **Source**: Takei et al. 2021, *Nature* 590:344–350 (same study as `4DNFIHF3JCBY.csv`).  4DN portal:
  [data.4dnucleome.org/4DNFIFLJGGNR](https://data.4dnucleome.org/files-processed/4DNFIFLJGGNR/), "DNA-Spot/Trace
  Data core table for the 2460 genomic loci across the mouse genome at 1-Mb resolution in ESCs,
  replicate 1"; md5 `da9826551f13f944815fe35a33a8e9c1` (verified, checked by `fetch`).  Public S3:
  `https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/8189709b-f1e7-4f0b-bf68-89eb9fd0afcf/4DNFIFLJGGNR.csv`.
- **Used by**: an unpublished benchmark truth --dataset takei2021_1mb` (imaging-truth simulation
  benchmark for single-cell Hi-C 3-D reconstruction; also the `robust` development / test simulations,
  `robust_devlog.md`, `TEST_RESULTS.md`); an unpublished benchmark locus-map` (the mm10
  coordinates of the 2,460 locus names, above); an unpublished benchmark (both homologs);
  an unpublished benchmark (diploid mESC truth, heuristic homologs; vs Bonev 2017).

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
- **Selection** (stated rules, `slurm/_matched_env.sh`): serum = `Serum_G1/S`, `passed_qc == 1`,
  group G1 / early-S / late-S/G2 (no mitotic), ≥ 100 k contacts (403 cells); 2i = both 2i conditions,
  same QC, ≥ 50 k contacts, 200 drawn with seed 1.  Unique fend pairs per selected cell after mm10
  liftover: serum median 181,883 (100,509 – 694,393), 2i median 77,415 (50,855 – 384,505); the adj row
  count matches the feature table's `total_contacts` (±1, checked on 3 cells), < 0.01 % of pairs lost in
  the liftover.  The cell-cycle `group` is the authors' inference from contact profiles; cells in S / G2
  carry replicated chromatin and are modelled as haploid anyway (the G1 subset is reported separately).
- **Download**: `python -m uchrom.datasets fetch nagano2017_hap` (or
  `slurm/download_matched.sbatch PART=mesc`).
- **Atlas store** (`build_nagano2017_hap.py`: `contacts` → `reconstruct` → `store`, then `derive_embeddings.py
  --hic per_cell --leiden`) → `nagano2017_hap/nagano2017_hap.chromdata.zarr`: the 603 cells of the selection
  above (403 serum, 200 2i), their mm10 contacts (`nagano2017_hap_cells_100kb.scool`, one map per cell;
  `nagano2017_hap_bulk.mcool`, merged, 100 kb - 1 Mb) and **structures computed here** — the authors published
  none: U-Chrom NucDynamics (protocol `nuc_dynamics_2017`, 100 kb particles, 2 models, seed 1; ~40 s per cell
  on a GPU), model 1 = coords, model 2 = layer `model_2`, their RMSD after superposition in
  `cells["rmsd_model_2"]`.
- **Used by**: an unpublished benchmark nagano` → NucDynamics / hickit → `matched.py`
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
  `slurm/download_matched.sbatch PART=brain`).
- **Used by**: an unpublished benchmark brain imaging reference (step 2; `matched_data.py`).

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
  `slurm/download_matched.sbatch PART=brain`).
- **Used by**: an unpublished benchmark brain Dip-C baseline (step 2; `matched_data.py`);
  uchrom-reproducibility `supp_table3/sc_structures/scab_tan2021.py`, `scab_dipc_reference.py` (contacts only: scA/B against Dip-C and
  the paper's structure types).

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
EMber / NucDynamics benchmarks of an unpublished benchmark (PREREG §6 diploid addition and §11).

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
- **Download**: `python -m uchrom.datasets fetch tan2018_gm12878`; on a compute cluster
  `slurm/download_diploid.sbatch` (also unpacks the tarballs to `cells/gm12878_<k>/`).
- **Used by**: diploid EMber / NucDynamics validation (an unpublished benchmark,
  `diploid_heldout.py`, `slurm/dip_real.sbatch`, `deep_dipc.sbatch`; PREREG §6 diploid addition).
  The loader `tan2018_gm12878` (`load`) bins the 14 cells' pairs at 5 kb into
  `tan2018_gm12878/tan2018_gm12878_5kb.scool` (44 MB; ~26 s): the GM12878 pseudo-bulk of
  uchrom-reproducibility `supp_table3/hic_structures/pseudobulk_gm12878.py`.  Since loader version 2 the store also holds the authors'
  structures (`*impute3.round4.clean.3dg.txt.gz` read with `uchrom.io.read_3dg_cells`: Dip-C particle at `p`
  holds `(p − 20 kb, p]`, phase 0 = `(pat)`, checked against each cell's contacts; cells 4 and 16 have
  structures but no pairs and are left out); used by uchrom-reproducibility `supp_table3/sc_structures/structures_*.py` (the tracing
  callers on reconstructed structures).  The `.con` files are not used there: they hold the
  contacts kept after Dip-C's filters (cell 1: 430 k vs 1,048,961 pairs), not comparable with the pairs.
- **Atlas**: `tan2018_gm12878` = the loader's store with `derive_embeddings.py --hic per_cell` (a 1 Mb per-cell
  map and a Hi-C embedding of the 14 cells) and its maps embedded.

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
  these cells' members (`3dg/_members.txt` lists the archive; ~25 min on a compute cluster, 3.1 GB kept).  The
  tarball has no structures for cells 026 and 051 (the two low-cis cells below), so 10 of the 12 cells
  have them (30 files each).
- **Content** (verified, an unpublished benchmark count` → `contacts_per_cell.tsv`): contacts are
  already de-duplicated (rows = unique contacts); the deepest cell, 035 (GSM5764669), has 3,006,012
  contacts, 5.6 % of the ends phased, 0.4 % of the contacts phased at both ends, 91.8 % cis; then 024
  (2.85 M), 320 (2.64 M), 047 (2.24 M), 028 (2.23 M).  No chrY contacts (female; `ploidy="auto"` → two
  copies of every chromosome incl. chrX).  Cells 026 and 051 have only 33 % / 12 % cis contacts (likely
  damaged nuclei or doublets) and are not used.  The deepest public diploid single-cell data with phase
  columns; Uni-C (GSE267873, `unic2025/`) is deeper but has no phase columns.
- **Download**: `python -m uchrom.datasets fetch wu2025_scmicroc` (`--no-extract`: pairs only); on
  the cluster job `slurm/highres_download.sbatch`.
- **Used by**: EMber deep (PREREG §11: development cells 035, 024, 320; held-back test cells 047, 028,
  017, 049, 032, 027, 014; `DEEP_TEST_RESULTS.md`) and Fig. 3a / S8: an unpublished benchmark,
  `deep_diploid.py`, `slurm/deep_dev.sbatch`, `highres_run.sbatch`, `highres_score.sbatch`;
  unpublished figure scripts (`build_render_scmicroc.py`, `capture_highres.py`,
  `make_figS_fig3_highres.py`).  The loader `wu2025_scmicroc` (`load`; fetches the pairs only) bins the
  12 cells at 5 kb into `wu2025_scmicroc/wu2025_scmicroc_5kb.scool` (57 MB; ~26 s), `qc_pass` false for
  026 and 051: the scMicro-C half of the GM12878 pseudo-bulk (uchrom-reproducibility `supp_table3/hic_structures/pseudobulk_gm12878.py`).

## Hi-C structure calling on maps (uchrom-reproducibility `supp_table3/hic_structures/`)

Validation of the callers on bulk / pseudo-bulk contact maps (`uchrom.strc.comp.call_compartments_eig` /
`compartment_strength`, `uchrom.strc.tad.call_tads_insulation`, `uchrom.strc.loop.call_loops_hiccups` /
`call_loops_mustache`, `uchrom.fea.pileup`): agreement with the published Rao 2014 calls, depth thinning,
and run time / memory on the largest chromosome.  The slices are built like the Fig. 3 ones (see
`rao2014_imr90/` above: `uchrom.datasets._builders.slice_hic`, raw observed counts over HTTP range
requests, no md5 because the cooler records its creation date).

### `rao2014_imr90/IMR90_chr1_5kb_hg19.cool`, `rao2014_gm12878/GM12878_chr21_5kb_hg19.cool` (built; fetch `rao2014_imr90_chr1`, `rao2014_gm12878_chr21`)

- **Source**: Rao 2014 (citation above), GEO GSE63525: `GSE63525_IMR90_combined.hic` and
  `GSE63525_GM12878_insitu_primary+replicate_combined.hic` (hg19, MAPQ > 0).
- **Files**: IMR90 chr1 at 5 kb — 49,851 bins, 26,494,735 pixels, 80,327,352 contacts, 39 MB (the largest
  chromosome: the performance checks of every caller run on it); GM12878 chr21 at 5 kb — 9,626 bins,
  7,258,708 pixels, 38,007,885 contacts, 9.8 MB (a second cell line, 3.7× the IMR90 chr21 depth).
- **Used by**: uchrom-reproducibility `supp_table3/hic_structures/` (each caller's validation and profiling script).

### `rao2014_annotations/`: Rao 2014 HiCCUPS loops and Arrowhead domains (1.6 MB; fetch `rao2014_annotations`)

- **Source**: Rao 2014 (citation above), GEO GSE63525 supplementary files
  `GSE63525_IMR90_HiCCUPS_looplist.txt.gz` (md5 `326c6dbafcb860ad1e726c544f71a5a6`),
  `GSE63525_IMR90_Arrowhead_domainlist.txt.gz` (`6129d35df3b6726ddab38056170e3482`),
  `GSE63525_GM12878_primary+replicate_HiCCUPS_looplist.txt.gz` (`2195f24061059dca3cb190b73af3bd6e`),
  `GSE63525_GM12878_primary+replicate_Arrowhead_domainlist.txt.gz` (`42a23da326be4379b042ae9658ed6a0b`).
  Tab-separated, hg19, chromosome names without `chr`; GEO data, open.
- **Read with**: `uchrom.io.read_juicer_loops` / `read_juicer_domains` (`chr` added to the names).
- **Used by**: tutorial `hic_structures` and uchrom-reproducibility `supp_table3/hic_structures/` — the reference loops (recall /
  precision of the loop callers, the anchors of the pileups) and domains (Arrowhead edges vs insulation
  boundaries).  IMR90 chr21 has 92 HiCCUPS loops and 86 Arrowhead domains.

### `genomes/hg19/`: UCSC hg19 chr21 and chr1 sequences (fetch `hg19_chr21`, `hg19_chr1`)

- **Files**: `genomes/hg19/chr21.fa.gz` (12 MB, md5 `26cdd5a3a539b63930752604feb2912b`) and
  `genomes/hg19/chr1.fa.gz` (74 MB, md5 `e103808b81f7d0a52353dee92d2ff164`) from
  `https://hgdownload.soe.ucsc.edu/goldenPath/hg19/chromosomes/`.
- **Source**: UCSC Genome Browser, hg19 (GRCh37).
- **Used by**: tutorial `hic_structures` (chr21) and uchrom-reproducibility `supp_table3/hic_structures/` — the GC content per bin
  that orients the compartment eigenvector (A = GC-rich) of the Rao 2014 slices.

### `genomes/{mm10,hg19,hg38}/`: UCSC whole-genome sequences (830 + 905 + 938 MB; fetch `mm10_genome`, `hg19_genome`, `hg38_genome`)

- **Files**: `genomes/mm10/mm10.fa.gz` (md5 `db005b65828db31735f384e4c5787be5`),
  `genomes/hg19/hg19.fa.gz` (`806c02398f5ac5da8ffd6da2d1d5d1a9`), `genomes/hg38/hg38.fa.gz`
  (`1c9dcaddfa41027f17cd8f7a82c7293b`) from `https://hgdownload.soe.ucsc.edu/goldenPath/<g>/bigZips/`; the md5
  sums are those of each folder's `md5sum.txt`.  Gzipped FASTA, soft-masked.
- **Source**: UCSC Genome Browser — GRCm38 / GRCh37 / GRCh38.
- **Used by**: `uchrom.strc.comp.single_cell_compartments` (CpG frequency per bin, the track of scA/B; Dip-C
  `cpg.sh` definition); uchrom-reproducibility `supp_table3/sc_structures/scab_*.py` (Tan 2021 cortex, dscHi-C, GM12878, Kim 2020).

### `genomes/liftover/hg38ToHg19.over.chain.gz`: UCSC liftOver chain (1.2 MB; fetch `hg38_to_hg19_chain`)

- **File**: md5 `ff3031d93792f4cbb86af44055efd903`, from
  `https://hgdownload.soe.ucsc.edu/goldenPath/hg38/liftOver/hg38ToHg19.over.chain.gz` (UCSC Genome Browser;
  free for academic, non-profit and personal use).
- **Used by**: uchrom-reproducibility `supp_table3/hic_structures/pseudobulk_gm12878.py` — lifts the scMicro-C (hg38) chr21 map to
  hg19 (bin midpoints; 99.6 % of the contacts lifted) to add it to the Dip-C pseudo-bulk and compare with
  Rao 2014 GM12878.

### Pseudo-bulk inputs: single cells of known type

- GM12878: `tan2018_gm12878` + `wu2025_scmicroc` (loaders above; 24 cells, ~1 % of Rao's chr21 depth).
- Cell types of the atlas (per-cell maps embedded at 1 Mb, read over HTTP): `dschic_aging_cortex` (32,777
  cells; the 7 cell-type maps sum to the store's all-cells map exactly), `droplet_hic_mouse_cortex`,
  `hires_brain`, `schicar_mouse_cortex` — uchrom-reproducibility `supp_table3/hic_structures/pseudobulk_dschic.py`.

## Single-cell structure calling (uchrom-reproducibility `supp_table3/sc_structures/`)

Inputs of the single-cell callers' validation (SnapHiC loops, single-cell boundaries, scA/B, the tracing callers
on reconstructed structures; results in uchrom-reproducibility `supp_table3/sc_structures/README.md`, run on a compute cluster).  Also used there:
`tan2018_gm12878` (with the authors' structures), `wu2025_scmicroc`, `tan2021_cortex`, `kim2020_scihic`, the whole
genomes `mm10_genome` / `hg19_genome` / `hg38_genome`, Rao 2014 GM12878 slices and annotations, Bonev 2017 mESC
(4DN mcool), Su 2020 / Takei 2021 tracing, the atlas stores `stevens2017_mesc` and `dschic_aging_cortex`.

### `nagano2017_dip/`: Nagano 2017 diploid serum mES cells (1.96 GB; fetch / loader `nagano2017_dip_serum`)

- **Source**: Nagano T *et al.* "Cell-cycle dynamics of chromosomal organization at single-cell resolution."
  *Nature* 547:61-67 (2017), doi:10.1038/nature23001; GEO GSE94489; the Tanay lab's schic2 bucket.  The cells
  SnapHiC called loops from (Yu *et al.* 2021).
- **Files**: `schic_hyb_1CDS1_adj_files.tar.gz` (870,949,456 B, md5 `fa1f498f25c3ee19788583b4bc2975ea`) and
  `schic_hyb_1CDS2_adj_files.tar.gz` (1,093,157,219 B, md5 `fa594c9750f16da95e13d97edf6b6c15`) from
  `https://schic2.s3.eu-west-1.amazonaws.com/`; `GSE94489_serum_diploids_features_table.txt.gz` (md5
  `f0b506709c078f5ce5252ae4ed17a27a`, GEO); the mm9 `GATC.fends` (streamed out of `schic2_mm9_db.tar.gz`) and the
  mm9 → mm10 chain go to `nagano2017_hap/`, shared with that entry.
- **Loader** `nagano2017_dip_serum` (`_load_snaphic.py`): each cell's fend pairs placed on mm9 fends, lifted to
  mm10, binned at 10 kb into one `.scool` (709 MB; built in ~42 min — on a compute cluster), linked as `per_cell`; the
  feature table and contacts per cell in `cells`; `snaphic_top742` marks the 742 cells with the most contacts
  (SnapHiC's selection; the paper's own read counts are not public — ours pick the same cells as the Tanay lab's
  counts).
- **Used by**: uchrom-reproducibility `supp_table3/sc_structures/snaphic_*.py`, `impute_*.py`; the docs page *Calling structures from
  single cells*.

### `yu2021_snaphic/`: SnapHiC source data (34 MB; fetch `yu2021_snaphic`)

- **Source**: Yu M *et al.* "SnapHiC: a computational pipeline to identify chromatin loops from single-cell Hi-C
  data." *Nat Methods* 18:1056-1059 (2021), doi:10.1038/s41592-021-01231-2; Springer supplementary data.
- **Files**: `41592_2021_1231_MOESM4_ESM.xlsx` (12.4 MB, md5 `9e7359602088134e7dc72b17b865ec03`: SnapHiC's loops
  from N = 10 ... 742 mES cells, six random subsets per N) and `41592_2021_1231_MOESM6_ESM.xlsx` (21.4 MB, md5
  `bf83659f56dda7c78be08c8a634bea50`: the mESC reference lists — HiCCUPS on Bonev 2017, MAPS on H3K4me3 PLAC-seq,
  cohesin and H3K27ac HiChIP) from
  `https://static-content.springer.com/esm/art%3A10.1038%2Fs41592-021-01231-2/MediaObjects/`.  Reading xlsx needs
  `openpyxl` (not a dependency): the benchmarks read TSVs written once from the sheets (`yu2021_snaphic/tsv/`).
- **Used by**: uchrom-reproducibility `supp_table3/sc_structures/snaphic_mesc.py` (precision / recall as in the paper, loops by N).

### `snaphic/`: SnapHiC's excluded bins (3.8 MB; fetch `snaphic_filter_regions`)

- **Files**: `mm10_filter_regions.txt` (md5 `2a951b44284a6edcfaee9d44e0e1d3a7`) and `hg19_filter_regions.txt`
  (`af7bec820c35f8fb773175ca255a1ada`) from `https://raw.githubusercontent.com/HuMingLab/SnapHiC/782dc2bc7e5a9e3c376bac4a61666a1a02d061b8/ext/`
  — 10-kb bins of low mappability (≤ 0.8) or in the ENCODE blacklist.  SnapHiC is GPL-3.0: the files are fetched
  from the authors' repository, not copied.
- **Used by**: `uchrom.strc.loop.call_loops_snaphic(exclude=...)`; uchrom-reproducibility `supp_table3/sc_structures/snaphic_*.py`.

## Bulk Hi-C deconvolution benchmark (an unpublished benchmark)

Population deconvolution of bulk Hi-C (`uchrom.recon.bulk.deconv.deconvolve(method="igm")`; design
an unpublished design note sections 6-7, commands an unpublished design note).

**Imaging truths** (catalogued above): Su 2020 genome-scale (fetch `su2020_genome`, primary diploid
genome-wide truth), Su 2020 chr21 (fetch `su2020_chr21`), Takei 2021 1 Mb (fetch `takei2021_1mb`,
homologs split heuristically by an unpublished benchmark).

**Real Hi-C** (whole files only on a compute cluster; laptop checks use HTTP range reads):

- **Rao 2014 IMR90, 4DN GRCh38** — `rao2014_imr90/4DNFIR1JDZH7.mcool` (4,639,622,711 B, md5
  `f91b77fa61acdc58360911c80b007646`, 4DN set 4DNES1ZEJNRU; Rao SSP *et al.* *Cell* 159:1665 (2014), GEO
  GSE63525; 4DN data-use policy: open).  GRCh38 like the Su 2020 loci, so no liftover.  Levels 1 kb–10 Mb
  (no 20 kb): the IGM 20 kb matrix is summed from the 10 kb level.
  `python -m uchrom.datasets fetch rao2014_imr90_4dn` (on a cluster: an unpublished benchmark).
- **Bonev 2017 mESC, 4DN mm10** — `bonev2017_mesc/4DNFIC21MG3U.mcool` (12,551,353,248 B, md5
  `dda4ed67a1179f917721fb81b1adebe0`, 4DN set 4DNESDXUWBD9; Bonev B *et al.* *Cell* 171:557 (2017),
  doi:10.1016/j.cell.2017.09.043, GEO GSE96107).  `python -m uchrom.datasets fetch bonev2017_mesc_4dn`
  (cluster); also range-read by an unpublished benchmark and an unpublished benchmark.
- **Rao 2014 IMR90, GEO hg19** `GSE63525_IMR90_combined.hic` (13 GB) — not downloaded; read over HTTP
  range requests by an unpublished benchmark (its Juicer KR vectors are the reference for
  U-Chrom's KR balancing).

**IGM demo input** — `WTC11_HiC_2Mb.hcs` (3,908,025 B): GPL-3 data of github.com/alberlab/igm (`demo/`
at commit `edbb331`), kept out of the repository and out of the registry:
an unpublished benchmark:fetch_igm_demo` downloads it on demand into `$UCHROM_IGM_CACHE` (default
`~/.cache/uchrom/igm/`) and checks its size.
Used for the IGM protocol of the native engine vs the original IGM
(an unpublished benchmark, `orig_demo.sbatch`, `compare_demo.sbatch`).

**Derived inputs** (on a cluster, `$SCRATCH/uchrom/runs/bulk/real/<cell>/`, not stored; recipe
an unpublished benchmark preprocess`, IGM SI section 6 protocol in
`uchrom.recon.bulk.deconv.preprocess`): `fine_20kb.npz` (raw 20 kb counts, chr1–22 + X), `igm_200kb.npz`
(whole genome, 200 kb, 24 contacts per bin), `su_3mb.npz` / `su_1mb.npz` (IMR90 onto 3 Mb / 1 Mb bins
centred on the Su loci), `takei_1mb.npz` (mESC onto 1 Mb bins centred on the Takei loci),
`su_crosscheck.json`.  Probabilities for `uchrom.recon.bulk.deconv.deconvolve(method="igm")`.

**Checked in**: an unpublished benchmark (KR check, range reads) and
an unpublished benchmark (provenance of the laptop plumbing run:
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
  an unpublished benchmark (FOF-CT writer); an unpublished benchmark
  (→ `.chromdata.zarr`); uchrom-reproducibility `extended_data_fig1/cd21_streaming_validation.py` (2.0 → 2.1, streaming
  `from_fofct(out=)` vs in memory, streaming distance maps vs the dense reference);
  an unpublished benchmark and uchrom-reproducibility `extended_data_fig1/cd22_variants.py` (format 2.2);
  an unpublished benchmark (cell positions); uchrom-reproducibility `fig2/cross_assay.py` (per-cell
  distances at short / long separations by cell class, `cluster_class` / `cluster_subclass`; on a compute cluster fetched
  and built by uchrom-reproducibility `fig2/slurm/liu2025.sbatch` into `$SCRATCH/uchrom/data/liu2025_mop/`,
  2026-10-11, the same 9,582,069 spots / 188,891 traces / 11,045 cells, `from_fofct` 40 s at 12.0 GB).

### uchrom-reproducibility `supp_table3/arcfish_parity/`: the inputs of the ArcFISH parity check

The parity check (uchrom-reproducibility `supp_table3/arcfish_parity`, `results/MANIFEST.md`) runs U-Chrom's ArcFISH callers and the authors'
package on the same FOF-CT tables, written by `inputs.py` from:

- `takei` (4DN 4DNFIHF3JCBY, replicate 1) and **`takei_rep2`** (4DN
  [4DNFIQXONUUH](https://data.4dnucleome.org/4DNFIQXONUUH/), 34 MB, md5 `659a89aa…bedd5a2765`, replicate 2 of the
  same experiment set; open 4DN data): read together, chr6 — the data of the authors' loop / domain tutorial (the
  tutorials `tad_calling` and `loop_calling` read both replicates, all 20 regions, to compare with the ArcFISH paper);
- **`su2020_chr2_parm`** (Su et al. 2020, Zenodo 3928890 `chromosome2_p-arm_replicate.tsv`, 78 MB, md5
  `ead30c67…a20540`, CC-BY-4.0): IMR90 chromosome 2 p-arm, the first 100 traces — the data of the authors'
  compartment tutorial;
- `takei2025_fov0` (chr15 averaged into 1-Mb bins per trace), `bintu_imr90`, `su2020_chr21` (first 1,000 traces).

The FOF-CT tables are written to `$SCRATCH/uchrom/arcfish_parity/inputs/` (not kept in the repository).

### uchrom-reproducibility `supp_fig6/browser/_data/`: scaled copies of Takei 2025 FOV 0 (derived)

uchrom-reproducibility `supp_fig6/browser/make_scaled.py --src $UCHROM_DATA/takei2025_fov0/takei2025_fov0.chromdata.zarr --out uchrom-reproducibility/supp_fig6/browser/_data --factors 1 3 10 30`
tiles k copies of the real FOV 0 cells side by side (cell and trace ids suffixed `_r<k>`; geometry only:
spots, coords, `cells.cell_type`) → `takei2025_fov0_x{1,3,10,30}.chromdata.zarr` (8–70 MB; the `.h5cd`
copies of older runs were 27 MB – 0.83 GB).  Ignored by git.  They are labelled *replicated* wherever
they are reported.  Used by the Fig. 6c browser benchmarks (uchrom-reproducibility `supp_fig6/browser/bench_server.py`,
`bench_frontend.py`, `run_all.sh`).

## 4DN chromatin-tracing studies (fetch / load `bintu2018_4dn`, `mateo2019_orca`, `hafner2023_orca`, `murphy2024_orca`, `takei2021_brain_4dn`, `liu2020_mina`, `hung2024_orca`, `huang2021_4dn`, `liu2025_kras`, `cheng2025_perturb`, `chen2023_sox9`, `patterson2023_chrx`, `sawh2020_celegans`, `gutnik2024_celegans`, `messina2023_him`, `le2024_se`, `fujimori2026_hek293t`, `fujimori2026_k562`, `fujimori2026_mesc`, `tastemel2025_sox2`, `jay2025_thymocytes`, `jensen2025_cargo`, `llimos2022_axin2`, `takei2021_mesc_4dn`, `liu2025_mop_4dn`, `liu2025_mecp2`)

Chromatin tracing the labs deposited in the 4DN Data Portal as FISH-Omics Format tables (FOF-CT; the portal's
[chromatin tracing collection](https://data.4dnucleome.org/resources/data-collections/chromatin-tracing-datasets)).
Each experiment of a set is a *core* table (spots) with optional companions keyed by its ids (*spot quality*,
*trace data*, *cell data*); RNA-only sets (Hafner 2023's RNA FISH counts) are listed but have no traces.

- **Files**: one row per file in `packages/uchrom/uchrom/datasets/fourdn_tracing.tsv` (dataset, set, experiment,
  file accession, uuid, md5, bytes, kind, biosample, the set's description; from the portal's metadata,
  2026-10-27; the 4DN studies from Liu 2025 on 2026-10-28 / 29), downloaded from 4DN open data on S3
  (`https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/<uuid>/<accession>.csv`) to
  `<dataset>/<set>/<accession>.csv`, md5-checked.  Sizes: `bintu2018_4dn` 11 files, 195 MB; `mateo2019_orca`
  25 files, 603 MB; `hafner2023_orca` 162 files, 495 MB; `murphy2024_orca` 20 files, 308 MB; `liu2025_kras` 29
  files, 1.6 GB; `cheng2025_perturb` 16 files, 207 MB; `chen2023_sox9` 16 files, 62 MB; `patterson2023_chrx` 21
  files, 25 MB; `sawh2020_celegans` 7 files, 6 MB; `gutnik2024_celegans` 6 files, 10 MB; `messina2023_him` 2
  files, 18 MB; `le2024_se` 5 files, 587 MB; `fujimori2026_hek293t` 57 files, `fujimori2026_k562` 2,
  `fujimori2026_mesc` 8 (72 MB together); `tastemel2025_sox2` 11 files, 201 MB; `jay2025_thymocytes` 2 files, 14 MB;
  `jensen2025_cargo` 3 files, 20 MB; `llimos2022_axin2` 12 files, 7 MB; `takei2021_mesc_4dn` 12 files, 266 MB;
  `liu2025_mop_4dn` 8 files, 6.2 GB; `liu2025_mecp2` 12 files, 10.2 GB (cores and cell tables: their spot
  demultiplexing and RNA-spot tables, 60 GB, are not registered).
- **Sources**:
  - Bintu B, Mateo LJ *et al.* *Science* 362:eaau1783 (2018), doi:10.1126/science.aau1783 — 10 sets: chr21:28–30 Mb
    in IMR90 (also by cell-cycle stage), K562, A549 and HCT116 RAD21-AID ± auxin; 34.6–37.1 Mb in HCT116 ± auxin
    (and after division in auxin); 18.6–20.6 Mb in IMR90.  GRCh38, 30 kb segments.  (Three of these files are also
    on the authors' GitHub: `bintu_imr90`, `bintu2018`.)
  - Mateo LJ *et al.* *Nature* 568:49 (2019), doi:10.1038/s41586-019-1035-4 — ORCA of the Drosophila bithorax
    complex in embryos (dm6; 2 / 3 / 10 kb steps), with RNA counts of the same cells (`cells`: `mRNA_*`,
    `nascentRNA_*`, tissue / embryo ids); 7 sets.  The same data are on Zenodo 4741214.
  - Hafner A *et al.* *Mol Cell* 83:1377 (2023), doi:10.1016/j.molcel.2023.04.008 — ORCA in mESC (GRCm38): chr3 and
    chr6 at 150 Mb (~1 Mb steps) and 3 Mb (30 kb steps), CTCF-AID / RAD21-AID ± auxin, DMSO; Geminin and nuclear size
    per cell; 40 sets (32 of DNA).
  - Murphy SE & Boettiger AN *Nat Genet* 56:493 (2024), doi:10.1038/s41588-024-01661-6 — ORCA of HoxA (GRCm38,
    5 kb): TC1 mESC with EED / RING1B degrons, neural progenitors, E10.5 brain; 5 sets.
  - Takei Y *et al.* *Science* 374:586 (2021), doi:10.1126/science.abj1966 — DNA seqFISH+ of the mouse cortex (mm10):
    3 experiments, each with a 1-Mb and a 25-kb core table (their traces kept apart, `c1-` / `c2-`), the cells' cell
    types (the table's `cluster label`, named from its header: 1 Pvalb ... 9 Exc) and RNA counts; 675 MB.  The
    RNA spot tables are fetched but not read.
  - Liu M *et al.* *Nat Commun* 11:2907 (2020), doi:10.1038/s41467-020-16732-5 — MINA of fetal mouse liver: chr19
    traced at 50 loci with each spot's distance to the lamina and nucleolus and the RNA counts of 137 genes per
    cell; 4 experiments, 181 MB.  Chromosomes deposited as `19` (named `chr19`).
  - Hung TC *et al.* *Nat Genet* 56:306 (2024), doi:10.1038/s41588-023-01641-2 — ORCA of the Pitx1 locus in mouse
    limb buds; 5 experiments, 1.28 GB.
  - Huang H *et al.* *Nat Genet* 53:1064 (2021), doi:10.1038/s41588-021-00863-6 — the Sox2 locus in F123 mESC
    (129 x CAST), allele and Sox2 / GFP / mCherry transcription per trace; 5 sets, 29 MB (the SnapFISH copy is
    `huang2021_sox2`).  One trace table writes `#columns=` (one `#`); some loci end before they start (2.4 %).
  - Liu M *et al.* *Nat Genet* 57:3075 (2025), doi:10.1038/s41588-025-02297-w — genome-wide tracing (all
    autosomes) and 5-kb tracing of selected regions in normal lung AT2 and pancreatic duct cells, pre-invasive
    lesions, adenoma, LUAD and PDAC of K-MADM-Trp53 mice and KP adenoma cells with Rnf2 knocked down, rescued or
    degraded (mm10); 22 sets, 29 experiments, 91,020 cells, 1,182,597 traces of 1,651 loci.  Chromosomes deposited
    as `Chr14` (named `chr14`).
  - Cheng Y *et al.* *Nat Methods* 22:950 (2025), doi:10.1038/s41592-025-02652-z — Perturb-tracing: chr22
    (27 loci) in A549-Cas9 cells of a pooled screen of 137 genes (404 sgRNAs, 8 non-targeting), each trace's
    sgRNA in a trace table (`Perturbation`, copied to `cells['perturbation']`), and CHD7 / PCBP1 / ZNF114
    knock-downs, CHD7 over-expression in A549, RPE-1 (chr21 / chr22) and neural crest cells (hg38); 15 sets,
    97,594 traces.
  - Chen LF, Long HK *et al.* *Mol Cell* 83:1446 (2023), doi:10.1016/j.molcel.2023.03.009 — ORCA of 4 Mb around
    SOX9 (78 loci of 5 kb at 50-kb steps; hg38) in H9 hESC and cranial neural crest cells, wild type and CTCF-site
    deletions (E1.35, promoter), with spot intensities; 5 sets, 12,764 traces.
  - Patterson B, Yang B *et al.* *Sci Adv* 9:eadf2245 (2023), doi:10.1126/sciadv.adf2245 — chrX at 40 loci in
    female hESC (H9, HES-3, H7) and IMR-90 iPSC, primed and naive, some with XIST / ATRX RNA FISH (hg38); 21 sets,
    10,835 traces.
  - Sawh AN *et al.* *Mol Cell* 78:96 (2020), doi:10.1016/j.molcel.2020.02.006 — chrV (one locus per TAD, 22 TADs;
    and three regions at 100 kb) and chrI (14 TADs) in early C. elegans embryos, wild type and cec-4 (ce10); 7
    sets, 8,268 traces.
  - Gutnik S *et al.* *Genome Biol* 25:71 (2024), doi:10.1186/s13059-024-03199-6 — chrV at 22 loci in embryos of
    the N2 and Hawaiian strains and their F1 hybrids, maternal or paternal copy marked by strain-specific probes
    (ce10); 6 sets, 16,806 traces.
  - Messina O *et al.* *Nat Commun* 14:6678 (2023), doi:10.1038/s41467-023-42485-y — Hi-M of the dpp locus (35
    loci across 430 kb of chr2L; dm6) in embryos at nuclear cycles 12 and 14; 2 sets, 19,211 traces.
  - Le DJ *et al.* bioRxiv 2024, doi:10.1101/2024.05.08.593251 (preprint) — ORCA of 376 super-enhancers (15 kb)
    across the genome of E14 mESC (5,375 cells), and of 44 with the nascent RNA burst of their genes per allele (1,733
    cells); 7,108 cells, 235,539 traces.
  - Fujimori T *et al.* *Sci Adv* 12:eaeb0060 (2026), doi:10.1126/sciadv.aeb0060 (4DN lists the bioRxiv preprint) —
    ORCA of a reporter at AAVS1 silenced by KRAB (wild type, Y46A, EEW25AAA) or HDAC4 for 1 / 5 days and after
    22 days of wash-out, in HEK293T, on the authors' `custom-build:hg38+pJT039(insertion)` (16 sets, 50,400
    traces); MYC in K562 (hg38, 2 sets, 2,247); NANOG in mESC over 3 days of differentiation (mm10, 4 sets, 31,388).
    Three stores, one per assembly / organism (one store takes one assembly).  The sets' control-experiment
    table (`4DNFIWQ9QBOB`, 5 KB) is not fetched.
  - Tastemel M *et al.* bioRxiv 2025, doi:10.1101/2025.02.21.639596 (preprint) — the Sox2 locus (42 loci, 5 kb;
    chr3:34.6-34.8 Mb) in F123 mESC with four CTCF sites inserted between Sox2 and its super-enhancer (other lines
    than Huang 2021's: no file or set shared), CTCF / RAD21 degraded, p300 inhibited, Kat6b knocked out, 24 h of
    differentiation; 11 sets, 27,800 cells, 55,600 traces.
  - Jay A *et al.* bioRxiv 2025, doi:10.1101/2025.05.30.656885 (preprint) — ORCA of Ets1-Fli1 (30 loci, 30 kb) in
    double-positive thymocytes; 1 set, 2,880 traces.

  - Jensen CL *et al.* *Mol Cell* 85:347 (2025), doi:10.1016/j.molcel.2024.10.021 — ORCA of 40 loci (5 kb) around
    Prdm8-Fgf5 (chr5) in R1 mESC with dCas9-VPR recruited by CARGO arrays 7.5 kb upstream of Prdm8 or 33 kb
    upstream of Fgf5, and a non-targeting control; 3 sets, 10,441 traces.
  - Llimos G *et al.* *Nat Commun* 13:2042 (2022), doi:10.1038/s41467-022-29625-6 — AXIN2 (25 loci, chr17) in
    lymphoblastoid lines homozygous for the indel rs143348853 or the reference; 2 sets, 6,047 traces.  The headers
    state GRCm38; the loci are hg38 (the loader sets it: `uns['genome_assembly_note']`).
  - Takei 2021 mESC, the whole set 4DNESL2AY9CM (`takei2021_mesc_4dn`, atlas `takei2021_mesc` since 2026-10-30):
    both replicates, each with a 1-Mb (2,460 loci) and a 25-kb (1,200 loci) core, quality, cell and RNA-spot
    tables; 446 cells, 27,302 traces, 7,772 nascent-RNA spots, RNA counts of 45 genes (429 cells in the cell
    tables); positions in the fields of view (`cent_ROI_x / y`).
  - Liu 2025, the four MOp experiments of 4DNESMTNNB3N (`liu2025_mop_4dn`, atlas `liu2025_mop` since 2026-10-30:
    46,340 cells, 695,013 traces) and the Mecp2 heterozygous MOp and V1 sets 4DNESPE924IP / 4DNESQU9R2NY
    (`liu2025_mecp2`: 64,591 cells, 1,120,853 traces, each cell's Mecp2 genotype; subclasses for the MOp cells);
    RNA counts of 242 genes per cell and positions in the tissue (`cell_center_x / y_global`, a region per section).
  - Not added: Su 2020's 4DN sets (the data of the Zenodo stores `su2020_*`), Wang 2016 and Cheng 2021 (sets on
    the portal without files), Nir 2018 (single-molecule localisations, not traces).

  Cheng, Chen, Patterson, Sawh, Gutnik, Messina, Fujimori, Jay, Jensen and Llimos deposit no `Cell_ID`: each trace is its own cell,
  carrying its set and description.  None of these files or sets is registered twice (checked on accession and
  md5 against the whole registry).
- **Terms**: the portal asks to cite the 4DN White Paper (doi:10.1038/nature23884) and the 4DN Data Portal paper
  (doi:10.1038/s41467-022-29697-4), to acknowledge the lab that made the data, and to contact it before using the
  data in a publication.  In the public atlas since 2026-10-27 (ids `bintu2018_4dn`, `mateo2019_orca`,
  `hafner2023_orca`, `murphy2024_orca`; with the Su 2020 stores `su2020_chr2`, `su2020_chr21_cell_cycle`,
  `su2020_genome`, `su2020_genome_amanitin`, `su2020_genome_transcription`; the chr2 store without the linked
  Hi-C of variable bins, which the embedded copies do not take).
- **As deposited** (handled by `read_4dn_tracing`, each case recorded in `uns`): Hafner 2023 and Murphy 2024 state
  `XYZ_unit=micron` over nm (the unit is taken from the spacing of successive loci: `fofct_unit_fixes`); some
  Hafner core tables declare a column the rows lack (`X, Y, Z,R,Chrom`) or leave `Chrom` out of `##columns`, one
  repeats the names in a CSV header row with an extra `readout` column, and one cell table has a malformed
  `##columns` line (`fofct_column_fixes`); ids are spelled `Spot_ID` / `spotID` / `spot_ID`, loci `chr` /
  `chr_start`; Hafner's spots with an empty `Chrom` (unassigned) are left out (`fofct_dropped_spots`); Mateo 2019 lists some traces twice (69,676 identical rows dropped) and Murphy 2024 reuses trace ids across fields of view (each later block of rows of an id becomes its own trace, `<id>.b<k>`: `fofct_trace_splits`, 1,293 traces); Bintu 2018's 18.6–20.6 Mb and 34.6–37.1 Mb regions are deposited from 18,000,001 and 34,000,001 and are moved to the authors' hg38 coordinates (`Data/README.md` of their repository: +627,713 and +628,095 bp; `fofct_locus_shifts`).  Hafner's
  `Cell_ID` is numbered per field of view (`0` = no cell), so cells are `(FOV, Cell_ID)`; so are Liu 2025's,
  per imaging run too (`CellID`, `FOVid` and `Dataset ID` in the core table: cells `<run>-<FOV>-<CellID>`, kept as
  `cells['run']`, `cells['fov']`; every cell then spans under 25 µm, median 8.2 µm).  Patterson 2023's
  `##columns=` lines close a bracket they never open (`…,Chrom_End)`) and Chen 2023's rows end in empty fields
  past the declared columns (all-empty extra columns are dropped).  Le 2024 leaves `##columns=` empty with the
  names in brackets on the next line; gives each spot's quality and its allele's nascent RNA in two tables keyed by
  `Spot_ID` (joined; the RNA table's locus columns repeat the spot's and are left out); numbers cells and traces per
  field of view in its 44-SE experiment, the field only in the quality table (`fov_from`: cells `<fov>-<Cell_ID>`;
  local crop coordinates); and its `Trace_ID` is an allele over every chromosome (`trace_by` Trace_ID + Chrom).
  Tastemel 2025's `Trace_ID` numbers the locus (traces = `Cell_ID` + `Extra_Cell_ROI_ID`, the allele: `trace_by`),
  and one locus has zero length (34,721,078, at the insertion).  Jay 2025, Jensen 2025 and Llimos 2022 state `XYZ_unit=micron`
  over nm.  Liu 2025's cores give `Cell_ID` and `FOV_ID`, and so do its cell tables: cells are joined to them by
  field and cell.  Takei 2021's RNA-spot tables are read into `points['rna']` (their cells named as the core's).
- **Loaders**: `load NAME` builds `<name>/<name>.chromdata.zarr` (every experiment with traces, ids prefixed by the
  experiment accession; coordinates in µm).
- **Used by**: the web browser (to be reviewed before an atlas release).

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
