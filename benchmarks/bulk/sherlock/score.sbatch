#!/bin/bash
# Score every population of one manifest input (deconvolution outputs in $MODELDIR, baselines in
# $BASEDIR) against its truth with all metrics of bulk_metrics.py; all loci pairs for the per-pair
# distributions, KS on 20,000 pairs, 20,000 triplets (+ the restrained set at sigma = 0.01), nearest
# true cell for 500 structures (20 candidates each).  Reading ChromData outputs needs U-Chrom: set
# ENGINE_PY (the engine env) when models exist; baselines alone run in venv-main.
#
#   N=$(wc -l < $SCRATCH/uchrom-nd/runs/bulk/manifest.tsv)
#   sbatch --array=1-$N benchmarks/bulk/sherlock/score.sbatch
#SBATCH --job-name=bk-score
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo-deconv/benchmarks/bulk/sherlock/_env.sh"
task ${SLURM_ARRAY_TASK_ID:-1}
EPY=${ENGINE_PY:-$PY}
mkdir -p "$SCORES/$DATASET"
PYTHONPATH=$REPO/packages/uchrom:$REPO/packages/chromdata $EPY $BK/score.py score --truth "$TRUTH" --input "$INPUT" "${RCARG[@]}" \
  --pop-dir "$BASEDIR" --pop-dir "$MODELDIR" --out "$SCORES/$DATASET/$NAME.json"
