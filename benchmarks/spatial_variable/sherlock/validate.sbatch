#!/bin/bash
# uchrom.spatial against SPARK (R) and esda on the spot RNA of Guo et al. 2026 mouse brain r1 (validate_stats.py);
# the numbers go to benchmarks/spatial_variable/results/validate_stats.json of the repo copy.
#   sbatch benchmarks/spatial_variable/sherlock/validate.sbatch       (after setup.sbatch)
#SBATCH --job-name=sv-validate
#SBATCH --partition=xiaojie,normal
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-sv/benchmarks/spatial_variable/sherlock/_env.sh"
cd "$REPO"
$PY -u benchmarks/spatial_variable/validate_stats.py --out "$OUT/validate"
