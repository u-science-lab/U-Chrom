#!/bin/bash
# Score the Fig. 3a ensembles (ED Table 2 metrics, vs the GEO models, violations) and compare
# engines model by model.  RUNS = run directories under $SCRATCH/uchrom-nd/runs.
#
#   sbatch --export=ALL,RUNS="native_cpu_full native_gpu_full",TAG=native benchmarks/fig3/sherlock/score.sbatch
#SBATCH --job-name=nd-score
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out

set -euo pipefail
ml purge; ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd; W=$SCRATCH/uchrom-nd; PY=$BASE/venv-main/bin/python
cd "$W/repo"
read -ra R <<< "${RUNS:?}"
paths=(); for r in "${R[@]}"; do paths+=("$W/runs/$r"); done
$PY benchmarks/fig3/a_nucdyn_engine_score.py --runs "${paths[@]}" --labels "${R[@]}" --out "$W/runs/score_${TAG:-x}.json"
# pairwise engine comparison per cell (first run vs each other run)
for c in 1 2 3 4 5 6 7 8; do
  for r in "${R[@]:1}"; do
    $PY benchmarks/fig3/a_nucdyn_engine_compare.py "$W/runs/${R[0]}/cell$c.npz" "$W/runs/$r/cell$c.npz" \
      --labels "${R[0]}" "$r" --out "$W/runs/compare_${R[0]}_vs_${r}_cell$c.json"
  done
done
echo done
