#!/bin/bash
# Consensus reconstructions of real Hi-C (run.py), one line of benchmarks/bulk/consensus/tasks_real.tsv per array
# task: Rao 2014 IMR90 and Bonev 2017 mESC, whole genome at 1 Mb / 250 kb / 100 kb / 50 kb (+ chr21 single-
# chromosome runs), seeds, Lorentzian, alpha fitted / imaging-calibrated, no trans, mean_refined, CPU path.
# Output: $CS/models/<tag>.{npz,mean_refined.npz,json,chromdata.zarr}.  The alpha=@<cell> line needs
# consensus_imaging.sbatch first (calib/<cell>.json).  GPU memory is sampled with nvidia-smi (<tag>.gpumem).
#
#   N=$(grep -v '^#' benchmarks/bulk/consensus/tasks_real.tsv | tail -n +2 | wc -l)
#   sbatch --array=1-$N benchmarks/bulk/sherlock/consensus_real.sbatch
# Estimated: <= 10 min per 1 Mb / 250 kb run, <= 1 h at 100 kb / 50 kb whole genome (most of it reading and
# balancing); the CPU line (16 threads) <= 4 h.
#SBATCH --job-name=cons-real
#SBATCH --partition=gpu,owners
#SBATCH --gpus=1
#SBATCH -C GPU_SKU:H100_SXM5
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo-consensus/benchmarks/bulk/sherlock/consensus_env.sh"
IFS=$'\t' read -r TAG CELL RES CHR NRUN DEV SEED SETS <<< "$(task_line "$BC/tasks_real.tsv" "${SLURM_ARRAY_TASK_ID:-1}")"
echo "task $TAG: $CELL $RES $CHR runs=$NRUN $DEV seed=$SEED sets=$SETS"
ARGS=(--cell "$CELL" --resolution "$RES" --n-runs "$NRUN" --device "$DEV" --seed "$SEED" --out "$CS/models/$TAG")
[ "$CHR" != genome ] && ARGS+=(--chroms ${CHR//,/ })
[ "$DEV" = cpu ] && ARGS+=(--threads "${SLURM_CPUS_PER_TASK:-16}")
if [ "$SETS" != "-" ]; then
  SETL=()
  for s in $SETS; do
    if [[ $s == alpha=@* ]]; then
      s="alpha=$($PY -c "import json; print(json.load(open('$CS/calib/${s#alpha=@}.json'))['alpha'])")"
    fi
    SETL+=("$s")
  done
  ARGS+=(--set "${SETL[@]}")
fi
nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -lms 500 > "$CS/models/$TAG.gpumem" 2>/dev/null &
SMI=$!
/usr/bin/time -v $PY "$BC/run.py" "${ARGS[@]}" 2> >(tee "$CS/models/$TAG.time" >&2)
kill $SMI 2>/dev/null || true
$PY "$BC/gpumem.py" "$CS/models/$TAG.gpumem" "$CS/models/$TAG.json"
