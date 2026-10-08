#!/bin/bash
# Only the comparison step of snaphic_reference.sbatch (the authors' run already in $OUT/snaphic/reference/N$NCELLS).
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-snaphic,ENGINE=snaphic,NCELLS=100 .../snaphic_refcompare.sbatch
#SBATCH --job-name=snaphic-refcmp
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-snaphic}/benchmarks/sc_structures/sherlock/_env.sh"
export OPENBLAS_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK RAYON_NUM_THREADS=$SLURM_CPUS_PER_TASK
NCELLS=${NCELLS:-100}
"$PY" "$REPO/benchmarks/sc_structures/snaphic_reference.py" compare --out "$OUT/snaphic/reference/N$NCELLS" \
  --n "$NCELLS" --chrom chr17 chr18 chr19
