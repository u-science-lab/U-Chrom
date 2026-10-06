#!/bin/bash
# Chen et al. 2026 (PREREG §13.3): per-spot EMber (haploid, robust-frozen, seed 2) on one GPU for array task
# TASK of NTASKS of one run's manifest, then its scores.
#
#   sbatch --array=1-16 --export=ALL,ENGINE=<tag>,RUN=CRR1829219,NTASKS=16 benchmarks/screcon/sherlock/chen_run.sbatch
#SBATCH --job-name=chen-run
#SBATCH --partition=xiaojie,gpu
#SBATCH -G 1
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo-dominant/benchmarks/screcon/sherlock/_env_dominant.sh"
: "${RUN:?}" "${ENGINE:?}" "${NTASKS:?}"
D=$W/runs/chen2026/$RUN
T=${SLURM_ARRAY_TASK_ID:-1}
nvidia-smi --query-gpu=name --format=csv,noheader || true
$PY $SC/chen_spots.py run --dir "$D" --task $T --ntasks $NTASKS --device gpu
$PY $SC/chen_spots.py score --dir "$D" --task $T --ntasks $NTASKS
echo done
