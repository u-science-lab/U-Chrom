#!/bin/bash
# Tidy tables (bulk_aggregate.py): long.csv, headline.csv, gain.csv (gain over pairwise-only / oracle),
# twin.csv -> $RUNS/tables/.
#
#   sbatch benchmarks/bulk/sherlock/aggregate.sbatch
#SBATCH --job-name=bk-agg
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-deconv/benchmarks/bulk/sherlock/_env.sh"
$PY $BK/bulk_aggregate.py --scores "$SCORES" --twin "$RUNS/twin" --out "$RUNS/tables"
