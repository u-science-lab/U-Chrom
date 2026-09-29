#!/bin/bash
# Held-out test: U-Chrom native NucDynamics on one GPU, all 8 cells x 3 folds (training tables),
# 100 kb, 10 models, full schedule (500 x 100 steps per stage), seed 1.  (fig3 gpu_runs: the 8 full
# cells in well under 2 h on one H100.)
#
#   sbatch benchmarks/screcon/sherlock/heldout_nucdyn_gpu.sbatch
#SBATCH --job-name=sc-ho-ndgpu
#SBATCH --partition=xiaojie
#SBATCH -G 1
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
for t in $(seq 1 $((8 * FOLDS))); do
  cell_fold $t
  [ -f "$MD/nucdyn_gpu.npz" ] && continue
  $PY $SC/run_nucdyn.py --contacts "$SPLIT/train.txt.gz" --res 100000 --device gpu --n-models 10 --seed 1 \
    --out "$MD/nucdyn_gpu.npz"
done
