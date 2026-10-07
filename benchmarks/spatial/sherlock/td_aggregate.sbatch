#!/bin/bash
# Type deconvolution (PREREG §14): tables of one set.
#
#   sbatch benchmarks/spatial/sherlock/td_aggregate.sbatch            (SET=dev)
#SBATCH --job-name=td-agg
#SBATCH --partition=xiaojie,normal
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-spatial/benchmarks/spatial/sherlock/_env.sh"
SET=${SET:-dev}
$PY $SP/run_typedecon.py aggregate --scores "$OUT/scores/$SET" --out "$OUT/tables/$SET"
