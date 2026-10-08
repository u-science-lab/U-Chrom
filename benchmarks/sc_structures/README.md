# sc_structures — structure calling from single cells

Validation of the single-cell callers on real data, run on Sherlock (`sherlock/`; the laptop only edits and runs
the unit tests).  Three questions:

| Part | Library | Scripts |
| --- | --- | --- |
| the tracing callers on 3-D structures reconstructed from scHi-C | `uchrom.io.read_3dg_cells` (Dip-C / hickit `.3dg`), loader `tan2018_gm12878` (with the authors' structures), `strc.comp.call_compartments_axes_pc(centromeres=)` | `structures_*.py` |
| compartment values of single cells (scA/B) | `uchrom.strc.comp.single_cell_compartments` (+ `fea.sequence` CpG frequency) | `scab_*.py` |
| imputation (random walk with restart), loops across cells (SnapHiC), domain boundaries of single cells | `uchrom.fea.impute_rwr`, `uchrom.strc.loop.call_loops_snaphic`, `uchrom.strc.tad.single_cell_boundaries`; native kernels `packages/uchrom-maps/src/rwr.rs` | `snaphic_*.py`, `impute_*.py` |

## Running on Sherlock

`sherlock/_env.sh` sets the environment (`venv-sc` in `$GROUP_HOME`, a repo copy `$SCRATCH/uchrom-nd/repo-sc*`
synced from the laptop with tracked files only, native packages `$SCRATCH/uchrom-nd/engine-sc/$ENGINE`,
`UCHROM_DATA=$SCRATCH/uchrom-nd/data`, outputs `$SCRATCH/uchrom-nd/runs/sc/`); `sherlock/setup.sbatch` builds the
env and the engines and runs the unit tests (compiled dependencies from binary wheels only: Sherlock's toolchain
cannot build the newest numpy).  One sbatch script per analysis (`structures_*`, `scab_*`, `snaphic_*`,
`impute_speed`); every job sets its time limit, follows `/etc/agents/AGENTS.md` and writes JSON next to its log.
Numbers below: shared AMD EPYC 9754 node, numpy 2.2.6 (x86-64).

## Datasets

Registered (`apps/atlas/recipes/README.md`): `nagano2017_dip_serum` (loader: 1,175 diploid serum mES cells, 10 kb
per-cell maps, mm10 — SnapHiC's data), `yu2021_snaphic` (the paper's loops and reference lists),
`snaphic_filter_regions`, `tan2018_gm12878` (+ structures), `wu2025_scmicroc`, `tan2021_cortex`, `kim2020_scihic`,
`mm10_genome` / `hg19_genome` / `hg38_genome` (CpG), Rao 2014 GM12878 slices and annotations, Bonev 2017 mESC
(4DN mcool), Su 2020 / Takei 2021 tracing, Stevens 2017 (atlas), dscHi-C (atlas).

## Results

**Against the original implementations, same inputs**
- SnapHiC (github.com/HuMingLab/SnapHiC @782dc2b, its own env; 100 mES cells, chr17-19): with its sliding-window
  holes reproduced (`SnapHiCParams(sliding_window_holes=True)`) the same 479 loops, z-scores within 1.4e-13,
  outlier counts equal, t within 7e-5 — 5 s vs 21 min on 32 processes; default (holes filled): 528 vs 479 loops,
  441 identical, 98 % of theirs within 20 kb.
- scA/B vs Dip-C (@289c1a4, Python 2.7; 20 Tan 2021 cells): same bins, values within 8e-10 (float32), no rank
  differs; 5.1 s per cell vs 0.18 s for all 20.  vs scHiCluster's compartment score: max relative difference
  6e-8.

**SnapHiC vs the paper** (742 cells, 100 kb - 1 Mb; precision vs HiCCUPS + MAPS reference, recall of bulk HiCCUPS)

| Calls | Loops | Precision | Recall | APA on Bonev |
| --- | --- | --- | --- | --- |
| U-Chrom, whole chromosomes (default) | 19,324 | 0.60 | 0.60 | 1.89 |
| U-Chrom, 10 Mb windows | 23,269 | 0.52 | 0.59 | 1.74 |
| the paper's calls | 15,896 | 0.66 | 0.60 | 1.98 |
| HiCCUPS on the pseudo-bulk of the same cells | 396 | 0.995 | 0.06 | 4.3 |

Loops by cells (whole chromosomes; paper): 50 → 498 (516), 100 → 2,685 (2,452), 200 → 9,178 (6,820).  We call
20-35 % more than the paper at matched N — likely the input preprocessing (their own alignment vs the Tanay lab's
fend pairs lifted mm9 → mm10).  SnapHiC2's windows did not match whole chromosomes here.  GM12878 (24 cells,
chr21, vs Rao loops): 33 loops, precision 0.52, recall 0.18 — far below SnapHiC's 75-100 cells.

**Single-cell boundaries** (742 mES cells vs Bonev insulation): 7,270 consensus boundaries (bulk 7,574), 60 % within
2 bins of a bulk boundary (chance 16 %), 58 % of the bulk ones recovered; mean insulation vs bulk Spearman 0.60;
200 / 50 cells: precision 0.56 / 0.45.  GM12878 chr21: 49 % near an Arrowhead edge (chance 14 %).

**scA/B**
- Tan 2021 cortex (495 cells, the paper's 9 structure types): kNN 0.875 (scHiCluster embedding 0.677); thinned to
  100 k / 50 k / 20 k / 10 k contacts: 0.84 / 0.81 / 0.72 / 0.63.
- dscHi-C (32,777 cells, 7 types): kNN 0.911 (store's scHiCluster PCA 0.869); 70 s, +2 GB; CPU-bound (numpy kernel
  54 s — a candidate for `uchrom-maps`).
- vs pseudo-bulk E1 per type: r 0.72-0.86, but CpG alone 0.72-0.83 (partial r given CpG 0.29-0.48); differences
  between types follow E1 differences (median r 0.59).
- GM12878 chr21 vs Rao E1: per cell r 0.82 (Tan 2018, 1 Mb), A/B agreement 0.85; Kim 2020 H1 / HFF kNN 0.973 (cells
  under ~2.1 k contacts do not cluster).

**Tracing callers on reconstructed structures** (Tan 2018 GM12878 Dip-C, 14 cells = 28 chr21 homologs, 20 kb, vs Rao 2014)

| | Structures | Same cells pooled |
| --- | --- | --- |
| compartments vs E1 (100 kb) | r 0.77, agreement 0.86 | r 0.93, 0.95 |
| boundaries vs insulation (±1 locus) | ArcFISH at chance (0.13 vs 0.12); FISHnet frequency peaks 0.34 (chance 0.12) | precision 0.38, recall 0.70 |
| loops | axis-wise F: none (published anchors at 0.69× background distance) | HiCCUPS: 4 |

By traces (compartment r): structures 0.16 / 0.58 / 0.73 / 0.77 at 4 / 8 / 16 / 28; Su 2020 imaging 0.25 / 0.67 /
0.77 / 0.835 (0.90 from 64) — compartments are limited by the cell count; ArcFISH fires at nearly every locus on
reconstructions (no such excess on imaging at equal N) — domains and loops are limited by the structures.
Genome-wide (250 kb, 639 traces, 338 s): per-chromosome r 0.67 vs pseudo-bulk E1, 0.76 with arms called
separately (`centromeres=`).  EMber (frozen; 100 kb, 4 models): compartments r 0.71 vs Rao, 0.93 vs the
published structures.  Stevens 2017 (8 haploid cells): too shallow (r 0.24, as their merged contacts).

**Run time** (native kernels, per cell): chr1 RWR band 0.033 s on 16 threads (numpy 2.0 s); SnapHiC 742 cells
genome-wide: windows 4 min / 3.4 GB, whole chromosomes 98 min / 6.0 GB (32 threads); single-cell boundaries 742
cells 6 min.  Native vs numpy: bands within 9e-15, sums within 2e-15, identical calls.

## Where the numbers are kept

The result files of the runs above are committed in `results/` (see `results/MANIFEST.md`: script, machine,
code revision per file); their large outputs are archived on Sherlock's Oak, `$OAK/uchrom/results/sc_structures/2026-10-08_ad141a7/`.  New
runs write their numbers with `benchmarks/_record.py` (`save`: results + provenance — revision, host, CPU,
threads, versions, datasets, parameters) and are compared with the committed ones
(`python benchmarks/_record.py results/x.json new/x.json --rtol 0.02`; timings left out).

