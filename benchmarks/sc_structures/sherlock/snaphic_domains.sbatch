#!/bin/bash
# Single-cell domain boundaries (single_cell_boundaries) of the mES cells against the Bonev bulk insulation
# (benchmarks/sc_structures/impute_domains.py), then the GM12878 check (SnapHiC + boundaries on chr21 vs Rao
# 2014; benchmarks/sc_structures/snaphic_gm12878.py).
#
#   sbatch --dependency=afterok:<bonev> --export=ALL,REPO=...,ENGINE=snaphic .../snaphic_domains.sbatch
#SBATCH --job-name=snaphic-domains
#SBATCH --partition=xiaojie,normal
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-snaphic}/benchmarks/sc_structures/sherlock/_env.sh"
export OPENBLAS_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK RAYON_NUM_THREADS=$SLURM_CPUS_PER_TASK
lscpu | grep "Model name" || true
"$PY" "$REPO/benchmarks/sc_structures/impute_domains.py" --out "$OUT/snaphic/domains" --mesc "$OUT/snaphic/mesc" \
  --n 742 200 50 --threads "$SLURM_CPUS_PER_TASK"
"$PY" "$REPO/benchmarks/sc_structures/snaphic_gm12878.py" --out "$OUT/snaphic/gm12878"
