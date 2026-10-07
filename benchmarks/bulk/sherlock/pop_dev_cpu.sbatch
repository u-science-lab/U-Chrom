#!/bin/bash
# As pop_dev.sbatch on the CPU engine (f64, rayon; CPU partitions are often faster to get than GPUs).
#
#   sbatch --array=1-$(wc -l < T) --export=ALL,TABLE=T benchmarks/bulk/sherlock/pop_dev_cpu.sbatch
#SBATCH --job-name=pop-dev-cpu
#SBATCH --partition=owners,normal
#SBATCH --time=16:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=48G
#SBATCH --requeue
#SBATCH --output=%x-%A_%a.out

export DEVICE=cpu
source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env_pop.sh"
line=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$TABLE")
IFS=$'\t' read -r UNIT NAME METHOD PARAMS S STEPS COND SEED <<< "$line"
D=$POP/$UNIT
OUT=$D/runs/$COND/${NAME}_s$SEED
echo "$UNIT $NAME $METHOD $PARAMS S=$S steps=$STEPS $COND seed=$SEED device=cpu"
if [ ! -f "$OUT/summary.json" ]; then
  $PY "$BK/pop_run.py" --input "$D/$COND.npz" --cells "$D/bulk_cells.npz" --method "$METHOD" --params "$PARAMS" \
    --n-structures "$S" --steps-scale "$STEPS" --seed "$SEED" --device cpu --out "$OUT"
fi
$PY "$BK/pop_score.py" score --truth "$D/truth.npz" --input "$D/$COND.npz" --pop "$OUT" \
  --out "$D/scores/$COND/${NAME}_s$SEED"
