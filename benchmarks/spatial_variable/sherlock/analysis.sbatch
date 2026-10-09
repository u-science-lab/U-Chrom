#!/bin/bash
# Stages of spatial_variable.py (cache: $OUT/cache; figure data: $OUT/figdata, copied to the paper repository
# from the laptop).    sbatch --export=ALL,STAGES=regions,compartments analysis.sbatch
#SBATCH --job-name=sv-analysis
#SBATCH --partition=xiaojie,normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-sv/benchmarks/spatial_variable/sherlock/_env.sh"
cd "$REPO"
$PY -u benchmarks/spatial_variable/spatial_variable.py --stats "$STATS" --out "$OUT/cache" --figdata "$OUT/figdata" \
    --stages "${STAGES:?}" --workers "${SLURM_CPUS_PER_TASK:-8}"
