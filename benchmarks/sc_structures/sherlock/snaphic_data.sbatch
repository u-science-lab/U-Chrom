#!/bin/bash
# Nagano 2017 diploid serum mES cells (SnapHiC's data): download the fend-pair tables, build the 10 kb store
# (loader nagano2017_dip_serum) into $UCHROM_DATA.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-snaphic benchmarks/sc_structures/sherlock/snaphic_data.sbatch
#SBATCH --job-name=snaphic-data
#SBATCH --partition=xiaojie,normal
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-snaphic}/benchmarks/sc_structures/sherlock/_env.sh"
export OPENBLAS_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK RAYON_NUM_THREADS=$SLURM_CPUS_PER_TASK
"$PY" "$REPO/benchmarks/sc_structures/snaphic_data.py" --out "$OUT/snaphic/data"
