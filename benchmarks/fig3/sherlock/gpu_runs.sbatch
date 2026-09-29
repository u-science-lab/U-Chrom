#!/bin/bash
# Native engine on one NVIDIA H100 (wgpu / Vulkan): the 10-model ensembles of all 8 Stevens
# cells (full schedule, seed 1; validation) and GPU throughput vs ensemble size (1..64
# models, full schedule, Cell 1; speed).
#
#   sbatch benchmarks/fig3/sherlock/gpu_runs.sbatch
#SBATCH --job-name=nd-gpuruns
#SBATCH --partition=xiaojie
#SBATCH -G 1
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out

set -euo pipefail
ml purge; ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd; W=$SCRATCH/uchrom-nd
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}   # see gpu_probe.sbatch
PY=$BASE/venv-main/bin/python
cd "$W/repo"
echo "host=$(hostname) job=$SLURM_JOB_ID"; nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
$PY -c "import sys; sys.path.insert(0, 'benchmarks/fig3'); import _nucdyn_env as e; e.print_environment('gpu')"
$PY benchmarks/fig3/a_nucdyn_engine_run.py --cells 1-8 --device gpu --n-models 10 --temp-steps 500 \
  --dyn-steps 100 --seed 1 --out "$W/runs/native_gpu_full"
$PY benchmarks/fig3/a_nucdyn_engine_speed.py --suite models particles --devices gpu --temp-steps 500 \
  --out "$W/runs/speed_gpu_h100.json"
