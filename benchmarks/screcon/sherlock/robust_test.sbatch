#!/bin/bash
# TEST SET of the frozen `robust` method (PREREG §2-§5; tag robust-frozen), run once.
# Engine: the pinned build of the frozen commit (ENGINE=frozen); run_robust.py without --params.
#
#   MODE=sim      simulations, truth cells 3-5, all conditions (Su 2020 chr21 50 kb, Takei 2021 1 Mb), 5 models
#   MODE=heldout  held-out cells 5-8 x folds 1-3, 100 kb, 10 models, + heldout.py score + score_real.py
#   MODE=real     full Stevens tables cells 5-8, 100 kb, 10 models, score_real.py (+ native_gpu_full)
#   MODE=matched  held-back Nagano serum half (202 cells), 100 kb, 2 models (array: STEP=models / compare)
#
#   sbatch --export=ALL,MODE=sim,ENGINE=frozen,DEVICE=cpu -p normal,owners -G 0 -c 16 robust_test.sbatch
#SBATCH --job-name=rb-test
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --output=%x-%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo-robust/benchmarks/screcon/sherlock/_env_robust.sh"
: "${MODE:?}"
DEV_=${DEVICE:-gpu}
T=$RB/test
test_unit() { case $1 in truth_3_*|truth_4_*|truth_5_*) return 0 ;; *) return 1 ;; esac; }
test_cell() { [ "$1" -ge 5 ] && [ "$1" -le 8 ]; }
NT=${SLURM_ARRAY_TASK_COUNT:-1}; TI=$(( ${SLURM_ARRAY_TASK_ID:-1} - ${SLURM_ARRAY_TASK_MIN:-1} ))
case $MODE in
  sim)
    N=$(wc -l < "$S/manifest.tsv")
    for t in $(seq 1 $N); do
      sim_task $t
      test_unit "$NAME" || continue
      [ $(( (t - 1) % NT )) -eq $TI ] || continue
      Mo=$T/sim/models/$DATASET/$NAME; mkdir -p "$Mo" "$T/sim/scores/$DATASET"
      [ -f "$Mo/robust.npz" ] || $PY $SC/run_robust.py --contacts "$TABLE" --res $RES --device $DEV_ --n-models 5 --seed 1 \
        --label robust_frozen --out "$Mo/robust.npz" > "$Mo/robust.log" 2>&1 || { echo "FAILED $NAME"; continue; }
      $PY $SC/simulate.py score --truth "$TRUTH" --population "$S/truth/$DATASET/population.npz" --no-baselines \
        --models "$Mo/robust.npz" --labels robust --out "$T/sim/scores/$DATASET/$NAME.json" > /dev/null
      echo "$DATASET $NAME done"
    done ;;
  heldout)
    k=0
    for CELL in 5 6 7 8; do for FOLD in 1 2 3; do
      k=$((k + 1)); [ $(( (k - 1) % NT )) -eq $TI ] || continue
      test_cell $CELL || continue
      TAG=cell${CELL}_fold${FOLD}; SPLIT=$H/split/cell$CELL/fold$FOLD; Mo=$T/heldout/models/$TAG
      mkdir -p "$Mo" "$T/heldout/scores" "$T/heldout/real_scores"
      [ -f "$Mo/robust.npz" ] || $PY $SC/run_robust.py --contacts "$SPLIT/train.txt.gz" --res 100000 --device $DEV_ --n-models 10 \
        --seed 1 --label robust_frozen --out "$Mo/robust.npz" > "$Mo/robust.log" 2>&1 || { echo "FAILED $TAG"; continue; }
      $PY $SC/heldout.py score --eval "$SPLIT/eval_pairs.npz" --models "$Mo/robust.npz" --labels robust --n-boot 1000 \
        --out "$T/heldout/scores/$TAG.json" > /dev/null
      $PY $SC/score_real.py --contacts "$SPLIT/train.txt.gz" --reference "$GEO/${GSM[$CELL]}_Cell_${CELL}_genome_structure_model.pdb.gz" \
        --models "$Mo/robust.npz" --labels robust --out "$T/heldout/real_scores/$TAG.json" > /dev/null
      echo "$TAG done"
    done; done ;;
  real)
    for c in 5 6 7 8; do
      test_cell $c || continue
      Mo=$T/real/models; mkdir -p "$Mo" "$T/real/scores"
      G="$GEO/${GSM[$c]}_Cell_${c}_contact_pairs.txt.gz"
      [ -f "$Mo/cell$c.npz" ] || $PY $SC/run_robust.py --contacts "$G" --res 100000 --device $DEV_ --n-models 10 --seed 1 \
        --label robust_frozen --out "$Mo/cell$c.npz" > "$Mo/cell$c.log" 2>&1 || { echo "FAILED cell$c"; continue; }
      models=("$Mo/cell$c.npz"); labels=(robust)
      [ -f "$W/runs/native_gpu_full/cell$c.npz" ] && { models+=("$W/runs/native_gpu_full/cell$c.npz"); labels+=(native_gpu_full); }
      $PY $SC/score_real.py --contacts "$G" --reference "$GEO/${GSM[$c]}_Cell_${c}_genome_structure_model.pdb.gz" \
        --models "${models[@]}" --labels "${labels[@]}" --out "$T/real/scores/cell$c.json" > /dev/null
      echo "cell$c done"
    done ;;
  matched)
    MT=$W/runs/screcon/matched; HB=$RB/matched/split/heldback_manifest.tsv; O=$T/matched
    mkdir -p "$O/models" "$O/sets" "$O/rows"
    if [ "${STEP:-models}" = models ]; then
      tail -n +2 "$HB" | cut -f1,5 | awk -v n=$NT -v i=$TI '(NR - 1) % n == i' | while IFS=$'\t' read -r cell table; do
        out=$O/models/$cell.npz; [ -f "$out" ] && continue
        $PY $SC/run_robust.py --contacts "$table" --res 100000 --device $DEV_ --n-models 2 --seed 1 --label robust_frozen \
          --out "$out" > "$O/models/$cell.log" 2>&1 || echo "FAILED $cell"
      done
    else
      for pair in "robust:$O/models" "nucdyn_gpu:$MT/models/nucdyn_gpu" "hickit:$MT/models/hickit"; do
        m=${pair%%:*}; d=${pair#*:}
        [ -f "$O/sets/$m.npz" ] || $PY $SC/matched_data.py models --manifest "$HB" --models-dir "$d" --label "nagano_serum_heldback_$m" --out "$O/sets/$m.npz"
        [ -f "$O/rows/$m.csv" ] || $PY $SC/matched.py compare --a "$O/sets/$m.npz" --b "$MT/sets/takei2021_mesc.npz" \
          --label "mesc/nagano_serum_heldback/$m" --n-rep 5 --out "$O/rows/$m.csv"
      done
      $PY $SC/matched.py summary --rows "$O"/rows/*.csv --out "$O/summary.csv" > "$O/summary.txt"; cat "$O/summary.txt"
    fi ;;
esac
