#!/bin/bash
# Held-out test: U-Chrom native NucDynamics on CPU (float64), one (cell, fold) per array task,
# 100 kb, 10 models, full schedule, seed 1.
#
#   sbatch --array=1-24 benchmarks/screcon/sherlock/heldout_nucdyn_cpu.sbatch
#SBATCH --job-name=sc-ho-ndcpu
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=16G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
cell_fold "${SLURM_ARRAY_TASK_ID:?}"
$PY $SC/run_nucdyn.py --contacts "$SPLIT/train.txt.gz" --res 100000 --device cpu --n-threads $SLURM_CPUS_PER_TASK \
  --n-models 10 --seed 1 --out "$MD/nucdyn_cpu.npz"
