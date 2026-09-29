#!/bin/bash
# Real data, full tables: unified scores (precision, NucDynamics- and Si-C-style violations, distance-matrix
# r and RMSD vs the published GEO models) for every ensemble found per cell: fig3 runs
# (native_gpu_full, native_cpu_full, orig_master_full: cell<n>.npz) and screcon real_full runs.
#
#   sbatch benchmarks/screcon/sherlock/real_score.sbatch
#SBATCH --job-name=sc-real-score
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
for c in 1 2 3 4 5 6 7 8; do
  models=(); labels=()
  for run in native_gpu_full native_cpu_full orig_master_full; do
    if [ -f "$W/runs/$run/cell$c.npz" ]; then models+=("$W/runs/$run/cell$c.npz"); labels+=("$run"); fi
  done
  for m in sic hickit; do
    if [ -f "$R/models/$m/cell$c.npz" ]; then models+=("$R/models/$m/cell$c.npz"); labels+=("$m"); fi
  done
  $PY $SC/score_real.py --contacts "$GEO/${GSM[$c]}_Cell_${c}_contact_pairs.txt.gz" \
    --reference "$GEO/${GSM[$c]}_Cell_${c}_genome_structure_model.pdb.gz" \
    --models "${models[@]}" --labels "${labels[@]}" --out "$R/scores/cell$c.json"
done
$PY $SC/aggregate.py --heldout "$H/scores" --sim "$S/scores" --real "$R/scores" "$H/real_scores" --out "$W/runs/screcon/tables"
