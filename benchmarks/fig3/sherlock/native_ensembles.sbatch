#!/bin/bash
# Native engine (uchrom_nucdyn, CPU, f64) on one Stevens et al. 2017 cell: 10 models, the
# original's full schedule, same seed convention as orig_ensembles.sbatch.
#
#   sbatch --array=1-8 benchmarks/fig3/sherlock/native_ensembles.sbatch
#   (EXTRA='{"emulate_rep_list_overflow": true}' OUT=native_cpu_emul: the original's repulsion-list overflow)
#SBATCH --job-name=nd-native
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=10
#SBATCH --mem=16G
#SBATCH --output=%x-%A_%a.out

set -euo pipefail
ml purge; ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd; W=$SCRATCH/uchrom-nd
CELL=${SLURM_ARRAY_TASK_ID:?}
echo "host=$(hostname) job=${SLURM_JOB_ID} cell=$CELL cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2)"
cd "$W/repo"
"$BASE/venv-main/bin/python" -c "import sys; sys.path.insert(0, 'benchmarks/fig3'); import _nucdyn_env as e; e.print_environment('native')"
"$BASE/venv-main/bin/python" benchmarks/fig3/a_nucdyn_engine_run.py --cells "$CELL" --device cpu --n-models 10 \
  --n-threads "$SLURM_CPUS_PER_TASK" --temp-steps 500 --dyn-steps 100 --seed 1 --extra "${EXTRA:-{\}}" \
  --out "$W/runs/${OUT:-native_cpu_full}"
