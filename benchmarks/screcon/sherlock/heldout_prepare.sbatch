#!/bin/bash
# Held-out contact test, step 1: split the 8 Stevens 2017 cells (10 % of reads held out, 3 disjoint
# folds, seed 1), fix the evaluation pairs at 100 kb, and build the random-polymer baseline per fold.
# (Cell 1 split + eval pairs: ~5 s on a laptop.)
#
#   sbatch benchmarks/screcon/sherlock/heldout_prepare.sbatch
#SBATCH --job-name=sc-ho-prep
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
for c in 1 2 3 4 5 6 7 8; do
  $PY $SC/heldout.py split --contacts "$GEO/${GSM[$c]}_Cell_${c}_contact_pairs.txt.gz" --out "$H/split/cell$c" \
    --frac 0.1 --folds $FOLDS --seed 1 --eval-res 100000
  for f in $(seq 1 $FOLDS); do
    mkdir -p "$H/models/cell${c}_fold$f"
    $PY $SC/baselines.py random_polymer --contacts "$H/split/cell$c/fold$f/train.txt.gz" --res 100000 \
      --n-models 10 --seed $f --out "$H/models/cell${c}_fold$f/random_polymer.npz"
  done
done
echo done
