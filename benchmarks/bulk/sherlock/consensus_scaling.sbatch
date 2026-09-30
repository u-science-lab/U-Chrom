#!/bin/bash
# Speed and memory of the whole-genome consensus reconstruction on one H100 (GPU=1, default) or on CPU
# threads (GPU=0): Rao 2014 IMR90, whole genome (chr1-22, X) at 1 Mb (~2,900 beads), 250 kb (~11,300),
# 100 kb (~28,000), 25 kb (~112,000) and 10 kb (~280,000 beads) x n_runs.  Records per case: prepare / engine /
# wall seconds, peak host RSS (run.py + /usr/bin/time), peak GPU memory (nvidia-smi samples), restraints per
# stage.  Output: $CS/scaling/<case>.json (+ .time, .gpumem); aggregate.py -> tables/runs.csv.
# Laptop reference (Apple M5 Pro, Metal, 8 runs): 1 Mb engine 18 s, 250 kb engine 67 s (wall 97 s incl.
# HTTP range reads), peak RSS 2.6 GB.
#
#   sbatch benchmarks/bulk/sherlock/consensus_scaling.sbatch                       # H100
#   sbatch --export=ALL,GPU=0 --partition=xiaojie,normal,owners --gpus=0 -C "" \
#       --cpus-per-task=32 --time=24:00:00 benchmarks/bulk/sherlock/consensus_scaling.sbatch   # CPU threads
#SBATCH --job-name=cons-scale
#SBATCH --partition=gpu,owners
#SBATCH --gpus=1
#SBATCH -C GPU_SKU:H100_SXM5
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=256G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-consensus/benchmarks/bulk/sherlock/consensus_env.sh"
GPU=${GPU:-1}
one() {  # case-name resolution n_runs device threads
  local C=$1 RES=$2 NR=$3 DEV=$4 TH=$5
  [ -f "$CS/scaling/$C.json" ] && { echo "skip $C"; return; }
  echo "=== $C: $RES bp, $NR runs, $DEV, $TH threads"
  if [ "$DEV" = gpu ]; then
    nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -lms 500 > "$CS/scaling/$C.gpumem" &
    SMI=$!
  fi
  /usr/bin/time -v $PY "$BC/run.py" --cell imr90 --resolution "$RES" --n-runs "$NR" --device "$DEV" --threads "$TH" \
    --seed 1 --no-zarr --out "$CS/scaling/$C" 2> "$CS/scaling/$C.time" || echo "FAILED $C (see $C.time)"
  if [ "$DEV" = gpu ]; then kill $SMI 2>/dev/null || true; $PY "$BC/gpumem.py" "$CS/scaling/$C.gpumem" "$CS/scaling/$C.json"; fi
  grep -E "Maximum resident|Elapsed" "$CS/scaling/$C.time" || true
}
if [ "$GPU" = 1 ]; then
  for RES in 1000000 250000 100000 25000 10000; do one "gpu_${RES}_r8" $RES 8 gpu 16; done
  one gpu_250000_r16 250000 16 gpu 16
  one gpu_250000_r32 250000 32 gpu 16
  one gpu_100000_r16 100000 16 gpu 16
else
  for TH in 8 16 32; do
    for RES in 1000000 250000; do one "cpu_${RES}_r8_t$TH" $RES 8 cpu $TH; done
  done
  one cpu_100000_r8_t32 100000 8 cpu 32
fi
