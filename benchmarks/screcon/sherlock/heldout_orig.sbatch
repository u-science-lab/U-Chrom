#!/bin/bash
# Held-out test: original NucDynamics (master 778697a, Cython), 10 models in its own parallel mode,
# 100 kb, full schedule; one (cell, fold) per array task.  (fig3 orig_ensembles: <= 16 h per cell.)
#
#   sbatch --array=1-24 benchmarks/screcon/sherlock/heldout_orig.sbatch
#SBATCH --job-name=sc-ho-orig
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=16:00:00
#SBATCH --cpus-per-task=10
#SBATCH --mem=24G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
cell_fold "${SLURM_ARRAY_TASK_ID:?}"
$ORIG_PY $SC/run_nucdyn_original.py --nd-dir "$ND" --contacts "$SPLIT/train.txt.gz" --res 100000 \
  --models 10 --cpu 10 --temps 500 --dyns 100 --seed 1 --out "$MD/orig.npz"
