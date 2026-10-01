#!/bin/bash
# `robust` (new method, PREREG.md §7) on the simulation DEVELOPMENT set only (truth cells 1-2 of
# su2020_chr21 and takei2021_1mb, all conditions): one GPU, 5 models, seed 1, full schedule (as
# sim_nucdyn_gpu.sbatch), then the truth scores (simulate.py score, no baselines) and the
# noise diagnostics (robust_diag.py).  A variant = a name + engine parameters (JSON):
#
#   PARAMS='{"robust_segments": 2}' sbatch --export=ALL,VARIANT=v0 benchmarks/screcon/sherlock/robust_sim.sbatch
#   (optional DEVICE=cpu, ONLY=<grep pattern on the table name>; timing runs: sbatch -C GPU_SKU:H100_SXM5)
#
# Writes $W/runs/robust/sim/{models,scores,diag}/$VARIANT/<dataset>/<name>...
#SBATCH --job-name=rb-sim
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-robust/benchmarks/screcon/sherlock/_env_robust.sh"
: "${VARIANT:?}" "${PARAMS:?}"
DEVICE=${DEVICE:-gpu}
O=$RB/sim
N=$(wc -l < "$S/manifest.tsv")
nvidia-smi --query-gpu=name --format=csv,noheader || true
echo "variant $VARIANT params $PARAMS device $DEVICE"
for t in $(seq 1 $N); do
  sim_task $t
  dev_unit "$NAME" || continue                     # DEVELOPMENT SET ONLY (truth 1-2)
  [ -n "${ONLY:-}" ] && ! echo "$NAME" | grep -q -- "$ONLY" && continue
  M=$O/models/$VARIANT/$DATASET/$NAME
  mkdir -p "$M" "$O/scores/$VARIANT/$DATASET" "$O/diag/$VARIANT/$DATASET"
  if [ ! -f "$M/robust.npz" ]; then
    $PY $SC/run_robust.py --contacts "$TABLE" --res $RES --device $DEVICE --n-models 5 --seed 1 \
      --params "$PARAMS" --label "robust_$VARIANT" --out "$M/robust.npz" > "$M/robust.log" 2>&1 || { echo "FAILED $NAME"; tail -3 "$M/robust.log"; continue; }
  fi
  $PY $SC/simulate.py score --truth "$TRUTH" --population "$S/truth/$DATASET/population.npz" --no-baselines \
    --models "$M/robust.npz" --labels robust --out "$O/scores/$VARIANT/$DATASET/$NAME.json" > /dev/null
  $PY $SC/robust_diag.py --table "$TABLE" --truth "$TRUTH" --models "$M/robust.npz" "$S/models/$DATASET/$NAME/nucdyn_gpu.npz" \
    --out "$O/diag/$VARIANT/$DATASET/$NAME.json" > /dev/null
  echo "$DATASET $NAME $(python3 -c "import json;print(round(json.load(open('$M/robust.npz.json'))['wall_seconds'],1))") s"
done
