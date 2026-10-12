# benchmarks/cross_assay/results

| File | What | Run |
|---|---|---|
| `pilot.json` | Cross-assay pilot (Step 0 of Analysis A): per dataset, the class medians, ExN - Oligo (bootstrap CI, Cliff's delta, depth-adjusted, thinned, without the top mitotic decile), the rankings, the Guo histogram checks, the imaging variants; across datasets, the signs and Kendall's W.  `{"results", "provenance"}` | 2026-10-11, Sherlock jobs 47390689 + 47391568 (see below) |
| `pilot.md` | The summary table of `pilot.json` | same |
| `cross_assay.json` | Steps 1-2 (`cross_assay.py`): the same statistics with every per-cell value from `uchrom.fea.separation_profile`, Liu 2025 added, Astro - Oligo per dataset; Kendall's W with Liu.  `{"results", "provenance"}`; `results.stage_logs.check` = the library against the pilot's tables | 2026-10-11, Sherlock job 47403340 (see below) |
| `cross_assay.md` | The summary tables of `cross_assay.json` | same |
| `recon/recon_<dataset>.json` | EMber reconstructions (`recon.py`, stage analyze): per variant the ExN - Oligo difference of the log2 long / short distance ratio (bootstrap CI, Cliff's delta), class ranking, scaling exponents 2-50 Mb, agreement with `dip`; the imaging datasets alongside | 2026-10-11, see "Distance space" below |
| `recon/loci_<dataset>.json` | Stage loci: the ExN - Oligo difference of the median distance of every cis pair of the Liu 2025 / Takei 2021 loci, imaging against each reconstruction (Spearman: detrended by separation `resid`, per chromosome and separation `chromband`, pair-specific `pair`), split-half ceilings, shuffled labels | same |
| `recon_summary.{json,md}` | `recon_summary.py`: one table of all datasets, with Spearman-Brown disattenuated agreement | same |

## Run 2026-10-11

### Jobs

Both jobs ran on `sh04-05n13` (8 CPUs, 48 GB) with the env `venv-consensus` (Python 3.12.1, numpy 2.2.6, pandas 2.2.3, scipy 1.14.1, zarr 3.4.0).

| Job | Elapsed | Script md5 | What it ran |
|---|---|---|---|
| 47390689 | 11 min 40 s | `efc827ae` | the structure sets (`matched_data.py`: Takei labels 41 s, k-means 162 s, Tan Dip-C 341 s), then the stages `imaging`, `guo` and `tan` |
| 47391568 | 2 min 15 s | `bd31a485` | the stages `seq` (74 s) and `analyze` (39 s) |

Job 47390689's `seq` stage failed: pandas 2.2 cannot build the stores' pandas >= 2.3 string dtypes. Script `bd31a485` differs from `efc827ae` only by `_pandas_compat()`, which reads those dtypes as a plain `StringDtype`. That shim touches only spot columns derived from keys, which are not used.

### Code

- The packages and `benchmarks/{_record.py, screcon}` are those of the repo copy `$SCRATCH/uchrom-nd/repo-sv` (revision 4b35f235eebe).
- The files this pilot uses are byte-identical there to ad8aa0f: `chromdata/embedded.py`, `screcon/matched_data.py`, `truth.py`, `contacts.py`, the Takei loci and the Tan cell table.
- `fea/contact_stats.py` differs only by the later addition of `chromosome_dosage`; `contact_features` is unchanged.
- The pilot script itself is uncommitted. The recorded `provenance.revision` is `repo-sv@4b35f235eebe + cross_assay/pilot.py uncommitted md5 bd31a485`.

### Data

- The atlas stores were read over HTTP.
- `tan2021_cortex` and `takei2021_brain` were read from `$SCRATCH/uchrom-nd/data`.
- Nothing was downloaded.

### Archive

The per-cell tables, offset histograms and structure sets are archived on Oak, in `$OAK/uchrom/results/cross_assay/2026-10-11_pilot_47391568/pilot_work_results.tar.gz` (104 MB).

The archive of job 47390689 in `..._pilot_47390689/` is superseded.

## Run 2026-10-11, Steps 1-2 (`cross_assay.py`)

- **Jobs**: 47401395 (`sherlock/liu2025.sbatch`, 2 min, `sh04-04n05`): `fetch liu2025_mop` (44 s) and the atlas recipe
  `build_liu2025_mop.py` -> `$SCRATCH/uchrom-nd/data/liu2025_mop/` (9,582,069 spots, 188,891 traces, 11,045 cells;
  md5 of both files equal to the registry's, printed by job 47403340).  47403340 (`sherlock/cross_assay.sbatch`,
  8 min 14 s, `sh04-04n05`, 8 CPUs, 10.4 GB peak, `venv-consensus` as above): `seq` 108 s, `tan` 134 s (pairs ->
  `.scool`), `imaging` 117 s (Liu 51 s), `check` 38 s, `analyze` 31 s.
- **Code**: the worktree at ad8aa0f with uncommitted `packages/uchrom/uchrom/fea/separation.py` (md5 `9782acd1`),
  `cross_assay.py` (`10b25b4e`) and `pilot.py` (`bd31a485`), synced through the DTN to `$SCRATCH/uchrom-nd/repo-xa`;
  `provenance.revision` records the same.
- **Check against the pilot** (`stage_logs.check`): the sequencing counts per cell (`n_cis`, `n_ge1`, `n_short`,
  `n_long`, `n_mito`) are equal for every cell of the seven atlas datasets; Tan 2021 differs by at most 3 contacts a
  cell (`pairs_to_scool` bins the 1-based positions as `(pos - 1) // 1 Mb`, the pilot `pos // 1 Mb`), its ExN - Oligo
  is unchanged (+1.449); the imaging pair counts are equal and the medians agree to 1.3e-7 (float32 distances in the
  pilot) with the pilot's closed ranges.
- **Archive**: `$OAK/uchrom/results/cross_assay/2026-10-11_full_47403340/cross_assay_work_results.tar.gz` (97 MB:
  per-cell tables, profiles at 1-Mb offsets, the Tan `.scool`).
- **Figure inputs** (stage `figure`, jobs 47405650 and 47406658, 1 min each, `ARCHIVE=0`): the Extended Data
  figure's `cross_assay_{figure.json,cells.parquet,profiles.parquet}`, written to `$SCRATCH/uchrom-nd/runs/xassay/full/figdata`
  and copied through the DTN to u-chrom-paper `manuscripts/nmeth-bc/figures/results/`.  Job 47406658 (`cross_assay.py`
  md5 `b399354d`) added `liu_lineage_pooled` (Liu's OPCs pooled with its oligodendrocytes: 13.8 % OPC; Astro against
  the lineage, Cliff's delta 0.16 [0.12, 0.20]); the per-dataset rows are identical to job 47405650's.
- **Committed code**: `cross_assay.py` as committed is md5 `b399354d` (job 47406658); job 47403340 ran `10b25b4e`, which
  differs only by the later `figure` stage (the functions `_cliff`, `_cliff_ci`, `_per_cell`, `_figdata`,
  `stage_figure`, the option `--figdata`); `fea/separation.py` (`9782acd1`) and `pilot.py` (`bd31a485`) are committed
  as run.

## Run 2026-10-11, distance space (`recon.py`, EMber)

- **Engine**: the frozen EMber build `dipfrozen` (tag ember-diploid-frozen; wheel `u_chrom_nucdyn-0.1.0`, sha256
  `93a2b33d…`), imported as `uchrom_recon` through `sherlock/engine_shim` (the build predates the rename; the screcon
  runners differ from its own only by the import name).  Every run on **CPU** (f64; `recon_cpu.sbatch`, 16 cores,
  `xiaojie,normal`), each reconstruction in its own process.  1 Mb, 2 models (model 0 analysed), seed 1.
- **GPU attempts, not used**: job 47414760 (GPU array) stopped finding a wgpu adapter after ~26 runs within one process
  ("no GPU adapter"); its ~6 cells per variant are kept aside in `$SCRATCH/uchrom-nd/runs/xassay/recon_tan_gpu_partial`.
  Device check (smoke cells cortex-p056-cb_001/002, GPU job 47414123 vs CPU job 47416684): per-cell log2 ratios differ
  by 0.005-0.04, as model 0 and model 1 of one device do.
- **Data**: Tan 2021 pairs (`tan2021_cortex`, phased); HiRES brain pairs fetched by job 47412636
  (`sherlock/hires_brain.sbatch`, registry `hires2023_brain`: 852 files, 4.3 GB, md5 list `cells_brain_md5.txt`
  next to them; GEO gives none); the atlas per-cell 1-Mb maps (stage maps: cells with >= 15,000 cis contacts, <= 300
  per class, ends drawn uniformly in their bin -- checked locally on HiRES: re-binned pixels equal the map's, 93,281
  pixels / 525,974 contacts).
- **Jobs**: Tan 2021 pairs: array 47417352 (24 x ~40 min) + collect/analyze/loci 47417353 (loci rerun with the
  stricter detrending by 47431131); HiRES: array 47424140 + 47431130; 1-Mb maps (maps / run array / collect):
  Tan 47431132 / 47431133 / 47431134, GAGE-seq 47431135 / 47431136 / 47431137, dscHi-C 47431138 / 47431139 / 47431140,
  Droplet Hi-C 47431141 / 47431142 / 47431143, scHiCAR 47431144 / 47431145 / 47431146.  Cells reconstructed: Tan 435,
  HiRES 399, GAGE-seq 1,235, dscHi-C 1,800, Droplet 1,470, scHiCAR 916.
- **Code**: `recon.py` md5 `3511152c` for every result file except `recon_tan2021.json` (`4b378a2f`: before the maps
  stage, the stricter detrending and the subprocess runs, analysis identical); `cross_assay.py` `b399354d`,
  `fea/separation.py` `9782acd1`.  The `provenance.revision` strings lost parts on submission (zsh parameter modifiers
  `$M1:c…` / `$M2:s…` in the submitting shell): `…recon.py-3511152cross_assay.py-b399354d-dipfrozen-cpu` stands for
  `ad8aa0f+uncommitted:recon.py-3511152c:cross_assay.py-b399354d:separation.py-9782acd1:engine-dipfrozen-cpu`.
- **Archives**: `$OAK/uchrom/results/cross_assay/2026-10-11_recon_<dataset>_<job>/recon_<dataset>.tar.gz` (models,
  logs, per-cell tables, locus tables) for tan2021 (47417353), hires_brain (47431130), tan2021_maps (47431134),
  gageseq_mouse_cortex (47431137), dschic_aging_cortex (47431140), droplet_hic_mouse_cortex (47431143),
  schicar_mouse_cortex (47431146); the ChromData stores stay in `$SCRATCH/uchrom-nd/runs/xassay/recon_*`.

## Run 2026-10-11/12, single cells, all class pairs, explanations, figure inputs

| File | What | Run |
|---|---|---|
| `transfer.json` | `transfer.py`: locus signatures (ExN - Oligo difference maps) scored on single cells of another source; AUROC with bootstrap CI | Sherlock job 47464126 (smoke 47463000), `transfer.py` md5 as synced (see below) |
| `recon/loci_all_<dataset>.json` | `recon.py` stage loci_all: every pair of the six classes, imaging against the dataset's reference reconstruction, imaging split-half | jobs 47463055, 47463059, 47463060, 47463061, 47463063, 47463065 (`recon.py` `3b690fc8`) |
| `biology.json` | `biology.py`: per-locus effects against the expression difference of genes within 500 kb (RNA of GAGE-seq, HiRES, scHiCAR; UCSC mm10 refGene) -- no relation | run locally (light: the locus tables and the panel copied through the DTN; `anndata` is not in the Sherlock venvs) |
| `compartments.json` | `compartments.py`: matched-depth pseudo-bulk maps of ExN and Oligo (dscHi-C, GAGE-seq), eigenvectors oriented by GC, saddle strengths; A/B explains 4 % (imaging) / 9-12 % (consensus) of the pair differences | job 47469287 (`compartments.py` `18408f74`) |

- Figure inputs: `figdata.py` (local) -> u-chrom-paper `manuscripts/nmeth-bc/figures/results/cross_assay_ed_*`, read
  by `figures/make_ed_cross_assay.py` (Extended Data Figs. 3 and 4).
- The locus panel of the local runs is `$SCRATCH/uchrom-nd/runs/xassay/liu2025_panel.parquet` (the Liu 2025 store's
  bins); the per-cell scores `$SCRATCH/uchrom-nd/runs/xassay/transfer/scores_*.parquet`.
- Example structures (Extended Data Fig. 3d): `structures.py`, job 47525959 (the first try, 47525588, required 80 %
  of chromosome 2's loci in an imaged copy and found none: detection is about half per copy) ->
  `$SCRATCH/uchrom-nd/runs/xassay/structures/cross_assay_ed_structures.parquet`, copied through the DTN to the
  paper's `figures/results/`.  Cells: imaging ExN 103 / Oligo 99 of 148 loci; Dip-C cortex-p309-bc_153 /
  cortex-p056-cb_054; scHiCAR CCCTACATCGATGGAAGA / CCCTACTTCTCCAACAGA; each at its class median score.
- The locus panel of the figure (`figures/results/cross_assay_ed_panel.parquet`: the Liu 2025 store's bins, chrom /
  start / end) is a copy of `$SCRATCH/uchrom-nd/runs/xassay/liu2025_panel.parquet`.
