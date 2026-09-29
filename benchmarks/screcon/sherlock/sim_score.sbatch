#!/bin/bash
# Simulation benchmark: score every method present for every manifest table against its truth, plus the
# structure-free baselines (random polymer, population mean, population P(s)).  Seconds per table.
#
#   sbatch benchmarks/screcon/sherlock/sim_score.sbatch
#SBATCH --job-name=sc-sim-score
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
N=$(wc -l < "$S/manifest.tsv")
for t in $(seq 1 $N); do
  sim_task $t
  models=(); labels=()
  for m in nucdyn_gpu nucdyn_cpu orig sic hickit; do
    if [ -f "$OUTM/$m.npz" ]; then models+=("$OUTM/$m.npz"); labels+=("$m"); fi
  done
  $PY $SC/simulate.py score --truth "$TRUTH" --population "$S/truth/$DATASET/population.npz" \
    --models "${models[@]}" --labels "${labels[@]}" --out "$S/scores/$DATASET/$NAME.json" > /dev/null
  echo "$DATASET $NAME ${labels[*]}"
done
