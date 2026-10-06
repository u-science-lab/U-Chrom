#!/bin/bash
# Held-out test: hickit 0.1.1 (Dip-C schedule, haploid -P1), 100 kb, 10 seeds; one (cell, fold) per task.
#
#   sbatch --array=1-24 benchmarks/screcon/sherlock/heldout_hickit.sbatch
#SBATCH --job-name=sc-ho-hickit
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=10
#SBATCH --mem=16G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
cell_fold "${SLURM_ARRAY_TASK_ID:?}"
$PY $SC/run_hickit.py --hickit "$HICKIT" --contacts "$SPLIT/train.txt.gz" --res 100000 --assembly mm10 \
  --n-models 10 --seed 1 --jobs 10 --out "$MD/hickit.npz"
