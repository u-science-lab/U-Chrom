#!/bin/bash
# hickit 0.1.1 (haploid, -P1, Dip-C schedule to 100 kb; run_hickit.py) on the selected Nagano 2017
# cells: 2 models (seeds 1, 2) per cell; array task t takes every NTASK-th cell of serum + 2i,
# 5 cells at a time (2 threads each).
#
#   sbatch --array=1-30 benchmarks/screcon/sherlock/matched_hickit.sbatch
#SBATCH --job-name=sc-mt-hickit
#SBATCH --partition=xiaojie,normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=10
#SBATCH --mem=24G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo-matched/benchmarks/screcon/sherlock/_matched_env.sh"
NTASK=${NTASK:-30}
t=${SLURM_ARRAY_TASK_ID:?}
mkdir -p "$M/models/hickit"
mapfile -t todo < <(nagano_cells | awk -v t="$t" -v n="$NTASK" '(NR - 1) % n == t - 1')
k=0
for line in "${todo[@]}"; do
  IFS=$'\t' read -r cell table <<< "$line"
  [ -f "$M/models/hickit/$cell.npz" ] && continue
  ( $PY $SC/run_hickit.py --hickit "$HICKIT" --contacts "$table" --res 100000 --assembly mm10 --n-models 2 \
      --seed 1 --jobs 2 --out "$M/models/hickit/$cell.npz" > "$M/models/hickit/$cell.log" 2>&1 \
      || echo "FAILED $cell" ) &
  k=$((k + 1))
  if [ $((k % 5)) -eq 0 ]; then wait; fi     # bash 4.2 (CentOS 7) has no wait -n
done
wait
