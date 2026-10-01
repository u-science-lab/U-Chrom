#!/bin/bash
# Cost of `robust` vs NucDynamics (PREREG §4-5: one H100, same input, 10 models, same resolution): both on
# the same node, same engine build, alternating, on development training tables (cells 1-2) at 100 kb.
#
#   PARAMS='{...}' sbatch --export=ALL,VARIANT=es4,ENGINE=e5 benchmarks/screcon/sherlock/robust_timing.sbatch
#SBATCH --job-name=rb-time
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH -C GPU_SKU:H100_SXM5
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-robust/benchmarks/screcon/sherlock/_env_robust.sh"
: "${VARIANT:?}" "${PARAMS:?}"
O=$RB/timing/$VARIANT
mkdir -p "$O"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
for tag in cell1/fold1 cell1/fold2 cell2/fold1; do
  T=$H/split/$tag/train.txt.gz
  n=${tag/\//_}
  /usr/bin/time -v $PY $SC/run_nucdyn.py --contacts "$T" --res 100000 --device gpu --n-models 10 --seed 1 \
    --out "$O/$n.nucdyn.npz" > "$O/$n.nucdyn.log" 2>&1
  /usr/bin/time -v $PY $SC/run_robust.py --contacts "$T" --res 100000 --device gpu --n-models 10 --seed 1 \
    --params "$PARAMS" --out "$O/$n.robust.npz" > "$O/$n.robust.log" 2>&1
  for m in nucdyn robust; do
    echo "$n $m wall $(python3 -c "import json;print(round(json.load(open('$O/$n.$m.npz.json'))['wall_seconds'],1))") s" \
      "maxrss $(grep 'Maximum resident' "$O/$n.$m.log" | awk '{print $NF}') kB"
  done
done
