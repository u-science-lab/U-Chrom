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
| `IMR90_chr21_30kb.cool`               | 280 KB  | yes             | —             | `gem_fish_reconstruction` tutorial (Hi-C side)                          |
| `4DNFIHF3JCBY.csv`                    | 22 MB   | no              | 4DN public S3 | `loop_calling`, `tad_calling`, `compartment`, `fishnet_domains` tutorials |
| `DNAseqFISH+.zip`                     | 144 MB  | no              | Zenodo 3735329 | `jie_aligner` tutorial                                                 |
| `IMR90_chr21-18-20Mb.csv`             | 2 MB    | no              | GitHub raw    | `gem_fish_reconstruction` tutorial                                     |
| `DNAseqFISH+/*.csv` (extracted)       | ~35 MB each | no          | from the zip  | `jie_aligner` tutorial                                                  |
| `with_loops.h5cd`                     | 24 MB   | no              | generated     | output of `loop_calling.ipynb` (intermediate cache, safe to delete)     |
| `fofct_core.csv`                      | ~6 MB   | no              | generated     | synthetic offline fallback for tutorials 4/5/6/7                        |
| `GSE63525_GM12878_insitu_primary+replicate_combined_30.hic` | ~40 GB | no | **manual** (too large) | `benchmark.ipynb` |

`*.csv`, `*.h5cd`, and the DNAseqFISH+ zip/folder are ignored by git;
they're either generated or downloaded on demand.

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
  `fishnet_domains.ipynb`.

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

## Generated outputs

- `with_loops.h5cd` — created at the end of `loop_calling.ipynb` as a
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
