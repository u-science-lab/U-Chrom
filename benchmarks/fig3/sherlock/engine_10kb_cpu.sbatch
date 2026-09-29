#!/bin/bash
# The 10 kb run of engine_10kb.sbatch on CPU (float64), as a reference for the GPU's float32 and
# neighbour-list handling at high resolution: same cell, schedule, 10 models, seed.
#
#   sbatch benchmarks/fig3/sherlock/engine_10kb_cpu.sbatch
#SBATCH --job-name=nd-10kb-cpu
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out

set -euo pipefail
ml purge; ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd; W=$SCRATCH/uchrom-nd
cd "$W/repo"
$BASE/venv-main/bin/python benchmarks/fig3/a_nucdyn_engine_run.py --cells 1 --device cpu --n-models 10 \
  --n-threads 32 --particle-sizes 8,4,2,0.4,0.2,0.1,0.05,0.02,0.01 --temp-steps 500 --dyn-steps 100 --seed 1 \
  --out "$W/runs/native_cpu_10kb"
$BASE/venv-main/bin/python benchmarks/fig3/a_nucdyn_engine_compare.py "$W/runs/native_cpu_10kb/cell1.npz" \
  "$W/runs/native_gpu_10kb/cell1.npz" --labels cpu_f64 gpu_f32 --out "$W/runs/compare_10kb_cpu_vs_gpu.json"
