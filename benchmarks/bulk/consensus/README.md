# consensus — one 3-D structure per bulk Hi-C map (whole genome), validated on imaging

Benchmark of `uchrom.recon.bulk.consensus.reconstruct_consensus` (protocol `consensus` of the native
engine: hierarchical restraint annealing, whole genome, no TAD partitioning).  Design, defaults and
the evidence behind them: `design.md`.  Datasets: `example-data/README.md` (Rao 2014 IMR90 and Bonev
2017 mESC 4DN mcools; Su 2020 genome-scale and chr21; Takei 2021 1 Mb) — no new dataset.

| file | what |
| --- | --- |
| `run.py` | one reconstruction of a real input → `<out>.chromdata.zarr`, `<out>.npz` (+ `.mean_refined.npz`), `<out>.json` (timings, peak RSS, α / ν / decay fit, stage restraint counts, per-run statistics, run-to-run precision) |
| `mds_baselines.py` | same balanced input: U-Chrom PyTorch MDS full mode (genome matrix; per chromosome), miniMDS full mode per chromosome |
| `imaging.py` | imaging medians / means / counts per locus pair (cis within copies, trans all copy combinations) + mean-distance embedding |
| `calibrate.py` | imaging-calibrated α and nm scale (oracle variant) |
| `score.py` | model vs imaging medians (Spearman / Pearson, cis bands, trans, per chromosome), scale-free RMSD, fit to input; HIPPS and IGM mean distances as distance-matrix baselines |
| `aggregate.py` | `long.csv`, `headline.csv`, `runs.csv` |
| `gpumem.py` | peak GPU memory from nvidia-smi samples into a run summary |
| `tasks_real.tsv`, `tasks_baselines.tsv`, `tasks_score.tsv` | the Sherlock array tasks |
| `tests/` | `pytest benchmarks/bulk/consensus/tests` (seconds) |
| `results/` | laptop development runs (M5 Pro GPU, 8 runs, defaults; IMR90 via range reads) and their scores against 300 of the 1,787 Su 2020 cells — preliminary, the provenance of the numbers in `design.md` |

## Laptop (development, < 2 min each)

```bash
pytest tests/recon/test_consensus.py benchmarks/bulk/consensus/tests
cd native/nucdyn && cargo test --release --features gpu consensus gpu_matches
# real data at laptop scale (HTTP range reads of the 4DN mcool; Su genome-scale 200 MB download)
python example-data/download_data.py --dest DATA --su2020_genome
UCHROM_EXAMPLE_DATA=DATA python benchmarks/bulk/consensus/imaging.py --dataset su2020_genome --max-cells 300 --out su300.npz
python benchmarks/bulk/consensus/run.py --cell imr90 --resolution 1000000 --n-runs 8 --device gpu --no-zarr --out g1m
python benchmarks/bulk/consensus/mds_baselines.py --cell imr90 --resolution 1000000 --methods mds_full mds_chrom --out-dir base_1mb
python benchmarks/bulk/consensus/score.py --imaging su300.npz --model consensus=g1m.npz \
    --model mds_full=base_1mb/mds_full.npz --model mds_chrom=base_1mb/mds_chrom.npz --hipps imr90:1000000 \
    --fit-input imr90 --out score_g1m.json
```

Local results (preliminary; 300 of 1,787 Su cells; M5 Pro): `design.md` sections 2 and 8.

## Sherlock

Environment: `sherlock/consensus_env.sh` — repo copy `$SCRATCH/uchrom-nd/repo-consensus`, env
`$GROUP_HOME/$USER/uchrom-nd/venv-consensus` (new; created like venv-deconv so the deconvolution jobs
keep their engine build), data `$SCRATCH/uchrom-nd/data` (shared with the bulk jobs), outputs
`$SCRATCH/uchrom-nd/runs/consensus/{imaging,calib,models,base,scores,scaling,tables}`.

```bash
rsync -a --exclude .git --exclude target ./ sherlock:$SCRATCH/uchrom-nd/repo-consensus/
cd $SCRATCH/uchrom-nd/repo-consensus
```

| step | command | resources |
| --- | --- | --- |
| setup (venv-consensus, engine wheel of this branch, torch < 2.6, miniMDS @ 9915d21, data, CPU tests) | `sbatch benchmarks/bulk/sherlock/consensus_setup.sbatch` | 16 CPU, 32 GB, ≤ 2 h (+ 17 GB of mcool downloads if absent) |
| GPU tests (Rust suite incl. consensus GPU-vs-CPU, Python tests) | `sbatch benchmarks/bulk/sherlock/consensus_gpu_tests.sbatch` | 1 H100, 8 CPU, 32 GB, ≤ 1 h |
| imaging medians + calibration | `sbatch benchmarks/bulk/sherlock/consensus_imaging.sbatch` | 8 CPU, 96 GB, ≤ 4 h |
| real runs (21 tasks: IMR90 / mESC whole genome 1 Mb, 250 kb, 100 kb, 50 kb; chr21; seeds; Lorentzian; α fit / calibrated; no trans; mean_refined; CPU) | `sbatch --array=1-21 benchmarks/bulk/sherlock/consensus_real.sbatch` | per task 1 H100, 16 CPU, 128 GB, ≤ 6 h (expected minutes to 1 h) |
| baselines (8 tasks) | `sbatch --array=1-8 benchmarks/bulk/sherlock/consensus_baselines.sbatch` | 1 GPU, 16 CPU, 128 GB, ≤ 8 h |
| scores (8 tasks; optional IGM populations: `--export=ALL,IGM_su2020_genome='…/igm_*.chromdata.zarr'`) | `sbatch --array=1-8 benchmarks/bulk/sherlock/consensus_score.sbatch` | 8 CPU, 96 GB, ≤ 4 h |
| scaling, H100 (whole genome 1 Mb → 10 kb, 8 runs; 16 / 32 runs at 250 kb) | `sbatch benchmarks/bulk/sherlock/consensus_scaling.sbatch` | 1 H100, 16 CPU, 256 GB, ≤ 12 h |
| scaling, CPU (8 / 16 / 32 threads; 1 Mb, 250 kb, 100 kb) | `sbatch --export=ALL,GPU=0 --partition=xiaojie,normal,owners --gpus=0 -C "" --cpus-per-task=32 --time=24:00:00 benchmarks/bulk/sherlock/consensus_scaling.sbatch` | 32 CPU, 256 GB, ≤ 24 h |
| tables | `sbatch benchmarks/bulk/sherlock/consensus_aggregate.sbatch` → `tables/{long,headline,runs}.csv` | 1 CPU, 8 GB |

Order: setup → GPU tests → imaging (before the `*_acal` task) → real runs + baselines + scaling →
scores → tables.  Array sizes are the data lines of the task tables
(`grep -v '^#' TABLE | tail -n +2 | wc -l`).
