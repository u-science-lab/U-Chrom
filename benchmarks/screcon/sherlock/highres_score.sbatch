#!/bin/bash
# CPU part of highres_run.sbatch (steps "ref score": the authors' structures on the grids, agreement scores),
# run without a GPU after the reconstructions:
#
#   sbatch -d afterok:<run job> --export=ALL,CELLS="GSM5764669_cell_035 ..." benchmarks/screcon/sherlock/highres_score.sbatch
#SBATCH --job-name=hr-score
#SBATCH --partition=xiaojie,normal
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --output=%x-%j.out
export STEPS=${STEPS:-"ref score"}
bash "$SCRATCH/uchrom-nd/repo-highres/benchmarks/screcon/sherlock/highres_run.sbatch"
