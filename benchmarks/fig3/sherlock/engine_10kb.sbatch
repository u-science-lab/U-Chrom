#!/bin/bash
# Native engine on one H100 at 10 kb: Stevens 2017 Cell 1, 10 models, the NucDynamics schedule
# (500 x 100 steps per stage) extended below 100 kb (8, 4, 2, 0.4, 0.2, 0.1, 0.05, 0.02, 0.01 Mb).
# First scale test for the Si-C comparison (Si-C: 28 CPU-h per 10 kb structure, paper).
#
#   sbatch benchmarks/fig3/sherlock/engine_10kb.sbatch
#SBATCH --job-name=nd-10kb
#SBATCH --partition=xiaojie
#SBATCH -G 1
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out

set -euo pipefail
ml purge; ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd; W=$SCRATCH/uchrom-nd
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
cd "$W/repo"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
$BASE/venv-main/bin/python benchmarks/fig3/a_nucdyn_engine_run.py --cells 1 --device gpu --n-models 10 \
  --particle-sizes 8,4,2,0.4,0.2,0.1,0.05,0.02,0.01 --temp-steps 500 --dyn-steps 100 --seed 1 \
  --out "$W/runs/native_gpu_10kb"
nvidia-smi --query-gpu=memory.used --format=csv,noheader
