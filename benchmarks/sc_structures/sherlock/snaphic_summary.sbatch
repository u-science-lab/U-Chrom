#!/bin/bash
# Precision / recall / F1 / APA of every call set of snaphic_run against the references, and the agreement
# with the authors' published calls (benchmarks/sc_structures/snaphic_mesc.py summary --apa).
#
#   sbatch --dependency=afterok:<run>:<bonev> --export=ALL,REPO=...,ENGINE=snaphic .../snaphic_summary.sbatch
#SBATCH --job-name=snaphic-summary
#SBATCH --partition=xiaojie,normal
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-snaphic}/benchmarks/sc_structures/sherlock/_env.sh"
export OPENBLAS_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK RAYON_NUM_THREADS=$SLURM_CPUS_PER_TASK
"$PY" "$REPO/benchmarks/sc_structures/snaphic_mesc.py" summary --out "$OUT/snaphic/mesc" --apa
