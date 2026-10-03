#!/bin/bash
# Native IGM protocol on the IGM demo input on CPU cores (f64 reference path), 100
# structures: CPU-core-hours of our engine next to the original IGM's (orig_demo.sbatch
# with S=100) and a CPU-vs-GPU check of the full pipeline (ours_demo_gpu.sbatch with S=100).
# Estimate: 3,008 x 100 x 47,000 particle-steps per M-step at ~6e7 /s on 32 cores
# -> ~4 min per round, ~25 rounds.
#
#   sbatch benchmarks/bulk/sherlock/ours_demo_cpu.sbatch
#SBATCH --job-name=bulk-ours-cpu
#SBATCH --partition=xiaojie,owners,normal
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env.sh"
S=${S:-100}
$PY "$BK/igm_demo_run.py" --hcs "$HCS" --device cpu --n-structures "$S" --seed 1 \
  --out "$RUNS/igm_demo/ours_cpu_S${S}_s1"
