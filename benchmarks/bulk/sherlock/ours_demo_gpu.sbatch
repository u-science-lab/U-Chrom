#!/bin/bash
# Native IGM protocol on the IGM demo input (WTC11 Hi-C, 2 Mb, male, demo configuration),
# 1,000 structures on one H100, one seed per array task (seed spread = noise floor of the
# comparison with the original IGM).  Estimate: ~25 A/M rounds x (3,008 beads x 1,000
# structures x 47,000 MD steps) -> 1-3 h per seed.
#
#   sbatch --array=1-3 benchmarks/bulk/sherlock/ours_demo_gpu.sbatch
#SBATCH --job-name=bulk-ours-demo
#SBATCH --partition=xiaojie
#SBATCH -G 1
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --output=%x-%A_%a.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env.sh"
SEED=${SLURM_ARRAY_TASK_ID:-1}
S=${S:-1000}
export UCHROM_IGM_GPU_BUDGET_GB=60
$PY "$BK/igm_demo_run.py" --hcs "$HCS" --device gpu --n-structures "$S" --seed "$SEED" \
  --out "$RUNS/igm_demo/ours_gpu_S${S}_s${SEED}"
