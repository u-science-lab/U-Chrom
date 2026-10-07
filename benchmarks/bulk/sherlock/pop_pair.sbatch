#!/bin/bash
# Two methods on the same input, one after the other on the same GPU (runtime comparison and the
# population-size sweep, PREREG_POP.md sections 4 and 7.5).  Table lines (tab-separated): unit,
# condition, S, steps scale, seed, ploidy, then NAME METHOD PARAMS triples (any number).  The input is
# $POP/<unit>/<condition>.npz, the imaging calibration $POP/<unit>/bulk_cells.npz, the truth
# $POP/<unit>/truth.npz.
#
#   sbatch --array=1-$(wc -l < T) --export=ALL,TABLE=T benchmarks/bulk/sherlock/pop_pair.sbatch
#SBATCH --job-name=pop-pair
#SBATCH --partition=xiaojie,owners,gpu
#SBATCH -G 1
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=%x-%A_%a.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env_pop.sh"
export UCHROM_IGM_GPU_BUDGET_GB=${UCHROM_IGM_GPU_BUDGET_GB:-8}
line=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$TABLE")
IFS=$'\t' read -r -a F <<< "$line"
UNIT=${F[0]}; COND=${F[1]}; S=${F[2]}; STEPS=${F[3]}; SEED=${F[4]}; PLOIDY=${F[5]}
D=$POP/$UNIT
for ((k = 6; k + 2 < ${#F[@]}; k += 3)); do
  NAME=${F[k]}; METHOD=${F[k + 1]}; PARAMS=${F[k + 2]}
  OUT=$D/runs/$COND/${NAME}_s$SEED
  echo "== $UNIT $COND S=$S steps=$STEPS seed=$SEED $NAME $METHOD $PARAMS"
  if [ ! -f "$OUT/summary.json" ]; then
    $PY "$BK/pop_run.py" --input "$D/$COND.npz" --cells "$D/bulk_cells.npz" --method "$METHOD" --params "$PARAMS" \
      --n-structures "$S" --steps-scale "$STEPS" --seed "$SEED" --ploidy "$PLOIDY" --device gpu --out "$OUT"
  fi
  $PY "$BK/pop_score.py" score --truth "$D/truth.npz" --input "$D/$COND.npz" --pop "$OUT" \
    --out "$D/scores/$COND/${NAME}_s$SEED"
done
