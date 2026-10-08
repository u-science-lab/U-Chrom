#!/bin/bash
# SnapHiC (call_loops_snaphic, native) on the mES cells, chr1-19, by number of cells: array task -> (N, rep).
# Then the pseudo-bulk HiCCUPS of the same cells.  (benchmarks/sc_structures/snaphic_mesc.py run / pseudobulk)
#
#   sbatch --array=0-6 --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-snaphic,ENGINE=snaphic .../snaphic_run.sbatch
#SBATCH --job-name=snaphic-run
#SBATCH --partition=xiaojie,normal
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=96G
#SBATCH --output=%x-%A_%a.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-snaphic}/benchmarks/sc_structures/sherlock/_env.sh"
export OPENBLAS_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK RAYON_NUM_THREADS=$SLURM_CPUS_PER_TASK
CONF=("742 0" "200 0" "200 1" "100 0" "100 1" "50 0" "50 1")
read -r N REP <<< "${CONF[${SLURM_ARRAY_TASK_ID:-0}]}"
D=$OUT/snaphic/mesc
lscpu | grep "Model name" || true
"$PY" "$REPO/benchmarks/sc_structures/snaphic_mesc.py" run --out "$D" --n "$N" --rep "$REP" --threads "$SLURM_CPUS_PER_TASK"
"$PY" "$REPO/benchmarks/sc_structures/snaphic_mesc.py" pseudobulk --out "$D" --n "$N" --rep "$REP"
