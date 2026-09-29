#!/bin/bash
# Simulation benchmark: U-Chrom native NucDynamics on one GPU over every manifest table (5 models,
# full schedule, seed 1; 50 kb for su2020_chr21, 1 Mb for takei2021_1mb).  Tables are small
# (<= 2,600 particles), so one job loops over all of them.
#
#   sbatch benchmarks/screcon/sherlock/sim_nucdyn_gpu.sbatch
#SBATCH --job-name=sc-sim-ndgpu
#SBATCH --partition=xiaojie
#SBATCH -G 1
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
N=$(wc -l < "$S/manifest.tsv")
for t in $(seq 1 $N); do
  sim_task $t
  [ -f "$OUTM/nucdyn_gpu.npz" ] && continue
  $PY $SC/run_nucdyn.py --contacts "$TABLE" --res $RES --device gpu --n-models 5 --seed 1 --out "$OUTM/nucdyn_gpu.npz"
done
