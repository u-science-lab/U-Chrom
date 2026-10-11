# benchmarks/cross_assay/results

| File | What | Run |
|---|---|---|
| `pilot.json` | Cross-assay pilot (Step 0 of Analysis A): per dataset, the class medians, ExN - Oligo (bootstrap CI, Cliff's delta, depth-adjusted, thinned, without the top mitotic decile), the rankings, the Guo histogram checks, the imaging variants; across datasets, the signs and Kendall's W.  `{"results", "provenance"}` | 2026-10-11, Sherlock jobs 47390689 + 47391568 (see below) |
| `pilot.md` | The summary table of `pilot.json` | same |
| `cross_assay.json` | Steps 1-2 (`cross_assay.py`): the same statistics with every per-cell value from `uchrom.fea.separation_profile`, Liu 2025 added, Astro - Oligo per dataset; Kendall's W with Liu.  `{"results", "provenance"}`; `results.stage_logs.check` = the library against the pilot's tables | 2026-10-11, Sherlock job 47403340 (see below) |
| `cross_assay.md` | The summary tables of `cross_assay.json` | same |

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
