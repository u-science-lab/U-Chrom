#!/bin/bash
# Original nuc_dynamics (master, 2017) on one Stevens et al. 2017 cell: 10 models, full
# schedule (500 x 100 steps per stage), its own parallel mode (one process per model).
# Gives the reference ensembles for the validation table AND the measured (not
# extrapolated) per-model time of the original.
#
#   sbatch --array=1-8 benchmarks/fig3/sherlock/orig_ensembles.sbatch
#SBATCH --job-name=nd-orig
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=16:00:00
#SBATCH --cpus-per-task=10
#SBATCH --mem=24G
#SBATCH --output=%x-%A_%a.out

set -euo pipefail
ml purge; ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd; W=$SCRATCH/uchrom-nd
CELL=${SLURM_ARRAY_TASK_ID:?}
echo "host=$(hostname) job=${SLURM_JOB_ID} cell=$CELL cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2)"
cd "$W/repo"
"$BASE/venv-orig/bin/python" benchmarks/fig3/a_nucdyn_engine_original_run.py --nd-dir "$BASE/nd/master" \
  --cell "$CELL" --models 10 --cpu 10 --temps 500 --dyns 100 --seed 1 --out "$W/runs/orig_master_full"
