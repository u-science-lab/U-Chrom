#!/bin/bash
# Held-out test: score every method present for one (cell, fold): held-out ROC / PR (heldout.py score,
# 1000 bootstraps) and the real-data metrics on the training table vs the published GEO models
# (score_real.py: precision, both violation definitions, distance-matrix r).
#
#   sbatch --array=1-24 benchmarks/screcon/sherlock/heldout_score.sbatch
#SBATCH --job-name=sc-ho-score
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
cell_fold "${SLURM_ARRAY_TASK_ID:?}"
models=(); labels=()
for m in nucdyn_gpu nucdyn_cpu orig sic hickit random_polymer; do
  if [ -f "$MD/$m.npz" ]; then models+=("$MD/$m.npz"); labels+=("$m"); fi
done
$PY $SC/heldout.py score --eval "$SPLIT/eval_pairs.npz" --models "${models[@]}" --labels "${labels[@]}" \
  --n-boot 1000 --out "$H/scores/$TAG.json"
$PY $SC/score_real.py --contacts "$SPLIT/train.txt.gz" \
  --reference "$GEO/${GSM[$CELL]}_Cell_${CELL}_genome_structure_model.pdb.gz" \
  --models "${models[@]}" --labels "${labels[@]}" --out "$H/real_scores/$TAG.json"
