#!/bin/bash
# Tidy tables of the consensus benchmark (aggregate.py): tables/long.csv, headline.csv (per imaging set,
# input and model), runs.csv (every run.py summary: real runs and scaling cases).
#
#   sbatch benchmarks/bulk/sherlock/consensus_aggregate.sbatch
#SBATCH --job-name=cons-agg
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-consensus/benchmarks/bulk/sherlock/consensus_env.sh"
$PY "$BC/aggregate.py" --scores "$CS/scores" --runs "$CS/models" "$CS/scaling" --out "$CS/tables"
