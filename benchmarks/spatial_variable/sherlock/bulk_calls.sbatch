#!/bin/bash
# Boundaries, loops and compartments of each section's pooled map + the windows the per-spot pass counts
# (bulk_calls.py), the sections of one tissue pooled.
#   sbatch --export=ALL,NAME=mouse_brain,SAMPLES="mouse_brain_r1 mouse_brain_r2" bulk_calls.sbatch
#SBATCH --job-name=sv-bulk
#SBATCH --partition=xiaojie,normal
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-sv/benchmarks/spatial_variable/sherlock/_env.sh"
cd "$REPO"
$PY -u benchmarks/spatial_variable/bulk_calls.py --stats "$STATS" --out "$OUT/bulk_calls" --samples ${SAMPLES:?} --name ${NAME:?}
