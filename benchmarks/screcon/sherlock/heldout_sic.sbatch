#!/bin/bash
# Held-out test: Si-C (shipped binaries, HEAD 2a4d445), 100 kb, 10 replicas in parallel; one
# (cell, fold) per array task; work directory on node-local scratch.  Wall time is a guess
# (fig3 sic_run.sbatch reserves 48 h for 20 replicas on 20 cores) - check the smoke / first task.
#
#   sbatch --array=1-24 benchmarks/screcon/sherlock/heldout_sic.sbatch
#SBATCH --job-name=sc-ho-sic
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=10
#SBATCH --mem=48G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
cell_fold "${SLURM_ARRAY_TASK_ID:?}"
$PY $SC/run_sic.py --sic-dir "$SIC" --contacts "$SPLIT/train.txt.gz" --res-kb 100 --assembly mm10 \
  --replicas 10 --jobs 10 --workdir "$L_SCRATCH/sic_$TAG" --out "$MD/sic.npz"
