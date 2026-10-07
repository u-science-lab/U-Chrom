#!/bin/bash
# EMber-pop development runs (PREREG_POP.md section 8): one line of a variant table per array task.
# Table (tab-separated, no header): unit, name, method, params JSON, S, steps scale, condition, seed.
# Runs pop_run.py on $POP/<unit>/<condition>.npz and scores against $POP/<unit>/truth.npz.
#
#   sbatch --array=1-$(wc -l < T) --export=ALL,TABLE=T benchmarks/bulk/sherlock/pop_dev.sbatch
#SBATCH --job-name=pop-dev
#SBATCH --partition=xiaojie,owners,gpu
#SBATCH -G 1
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --requeue
#SBATCH --output=%x-%A_%a.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env_pop.sh"
export UCHROM_IGM_GPU_BUDGET_GB=${UCHROM_IGM_GPU_BUDGET_GB:-30}
line=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$TABLE")
IFS=$'\t' read -r UNIT NAME METHOD PARAMS S STEPS COND SEED <<< "$line"
D=$POP/$UNIT
OUT=$D/runs/$COND/${NAME}_s$SEED
DEVICE=${DEVICE:-gpu}
echo "$UNIT $NAME $METHOD $PARAMS S=$S steps=$STEPS $COND seed=$SEED device=$DEVICE"
if [ ! -f "$OUT/summary.json" ]; then
  $PY "$BK/pop_run.py" --input "$D/$COND.npz" --cells "$D/bulk_cells.npz" --method "$METHOD" --params "$PARAMS" \
    --n-structures "$S" --steps-scale "$STEPS" --seed "$SEED" --device "$DEVICE" --out "$OUT"
fi
$PY "$BK/pop_score.py" score --truth "$D/truth.npz" --input "$D/$COND.npz" --pop "$OUT" \
  --out "$D/scores/$COND/${NAME}_s$SEED"
