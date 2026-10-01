#!/bin/bash
# `robust` on the held-out DEVELOPMENT set only (Stevens 2017 cells 1-4, folds 1-3; training
# tables of heldout.py split), one GPU, 100 kb, 10 models, seed 1 (as heldout_nucdyn_gpu.sbatch),
# then heldout.py score (1000 bootstraps) and score_real.py (precision, violations, vs GEO) for
# the robust models only.
#
#   PARAMS='{...}' sbatch --export=ALL,VARIANT=v0 benchmarks/screcon/sherlock/robust_heldout.sbatch
#   (optional CELLS="1 2" FOLDS_RUN="1"; timing runs: sbatch -C GPU_SKU:H100_SXM5)
#
# Writes $W/runs/robust/heldout/{models,scores,real_scores}/$VARIANT/...
#SBATCH --job-name=rb-ho
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-robust/benchmarks/screcon/sherlock/_env_robust.sh"
: "${VARIANT:?}" "${PARAMS:?}"
O=$RB/heldout
nvidia-smi --query-gpu=name --format=csv,noheader || true
echo "variant $VARIANT params $PARAMS"
for CELL in ${CELLS:-1 2 3 4}; do
  dev_cell "$CELL" || { echo "cell $CELL is not a development cell: skipped"; continue; }   # DEVELOPMENT SET ONLY
  for FOLD in ${FOLDS_RUN:-1 2 3}; do
    TAG=cell${CELL}_fold${FOLD}
    SPLIT=$H/split/cell$CELL/fold$FOLD
    M=$O/models/$VARIANT/$TAG
    mkdir -p "$M" "$O/scores/$VARIANT" "$O/real_scores/$VARIANT"
    if [ ! -f "$M/robust.npz" ]; then
      $PY $SC/run_robust.py --contacts "$SPLIT/train.txt.gz" --res 100000 --device gpu --n-models 10 --seed 1 \
        --params "$PARAMS" --label "robust_$VARIANT" ${SUPPORT_REL:+--support-mix $(python3 -c "print($SUPPORT_REL * 100000)")} \
        --out "$M/robust.npz" > "$M/robust.log" 2>&1 || { echo "FAILED $TAG"; tail -3 "$M/robust.log"; continue; }
    fi
    $PY $SC/heldout.py score --eval "$SPLIT/eval_pairs.npz" --models "$M/robust.npz" --labels robust \
      --n-boot 1000 --out "$O/scores/$VARIANT/$TAG.json" > /dev/null
    $PY $SC/score_real.py --contacts "$SPLIT/train.txt.gz" \
      --reference "$GEO/${GSM[$CELL]}_Cell_${CELL}_genome_structure_model.pdb.gz" \
      --models "$M/robust.npz" --labels robust --out "$O/real_scores/$VARIANT/$TAG.json" > /dev/null
    echo "$TAG $(python3 -c "import json;j=json.load(open('$M/robust.npz.json'));print(round(j['wall_seconds'],1),'s',round(j['peak_rss_mb']),'MB')")"
  done
done
