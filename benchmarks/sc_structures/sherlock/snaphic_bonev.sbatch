#!/bin/bash
# The bulk mESC reference: HiCCUPS loops and insulation boundaries of Bonev et al. 2017 (4DN mcool, 10 kb,
# chr1-19), read directly from $UCHROM_DATA/bonev2017_mesc (benchmarks/sc_structures/snaphic_mesc.py bonev).
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-snaphic,ENGINE=snaphic .../snaphic_bonev.sbatch
#SBATCH --job-name=snaphic-bonev
#SBATCH --partition=xiaojie,normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-snaphic}/benchmarks/sc_structures/sherlock/_env.sh"
export OPENBLAS_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK RAYON_NUM_THREADS=$SLURM_CPUS_PER_TASK
"$PY" "$REPO/benchmarks/sc_structures/snaphic_mesc.py" bonev --out "$OUT/snaphic/mesc"
