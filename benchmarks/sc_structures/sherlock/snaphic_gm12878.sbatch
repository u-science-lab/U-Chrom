#!/bin/bash
# The GM12878 check alone (SnapHiC + single-cell boundaries on chr21 vs Rao 2014;
# benchmarks/sc_structures/snaphic_gm12878.py).
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-snaphic,ENGINE=snaphic2 .../snaphic_gm12878.sbatch
#SBATCH --job-name=snaphic-gm12878
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-snaphic}/benchmarks/sc_structures/sherlock/_env.sh"
export OPENBLAS_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK RAYON_NUM_THREADS=$SLURM_CPUS_PER_TASK
"$PY" "$REPO/benchmarks/sc_structures/snaphic_gm12878.py" --out "$OUT/snaphic/gm12878"
