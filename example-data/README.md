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
| `4DNFIHF3JCBY.csv`                    | 22 MB   | no              | 4DN public S3 | `loop_calling`, `tad_calling`, `compartment`, `fishnet_domains` tutorials |
| `DNAseqFISH+.zip`                     | 144 MB  | no              | Zenodo 3735329 | `jie_aligner` tutorial                                                 |
| `DNAseqFISH+/*.csv` (extracted)       | ~35 MB each | no          | from the zip  | `jie_aligner` tutorial                                                  |
| `with_loops.h5cd`                     | 24 MB   | no              | generated     | output of `loop_calling.ipynb` (intermediate cache, safe to delete)     |
| `fofct_core.csv`                      | ~6 MB   | no              | generated     | synthetic offline fallback for tutorials 4/5/6/7                        |

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
