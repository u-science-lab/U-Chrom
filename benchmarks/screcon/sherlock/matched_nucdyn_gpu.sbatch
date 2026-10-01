#!/bin/bash
# U-Chrom native NucDynamics (nuc_dynamics_2017 protocol, GPU f32) on every selected Nagano 2017
# haploid cell: 100 kb, 2 models (seeds 1, 2), full schedule (500 x 100 steps per stage).
#
#   sbatch benchmarks/screcon/sherlock/matched_nucdyn_gpu.sbatch                      (all cells)
#   sbatch --export=ALL,COND=2i benchmarks/screcon/sherlock/matched_nucdyn_gpu.sbatch  (only the 2i cells)
#SBATCH --job-name=sc-mt-ndgpu
#SBATCH --partition=xiaojie,gpu
#SBATCH -G 1
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-matched/benchmarks/screcon/sherlock/_matched_env.sh"
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
mkdir -p "$M/models/nucdyn_gpu"
# COND=serum|2i restricts the list (a second GPU job can take the 2i cells); REVERSE=1 walks the list
# backwards and stops at the first cell another job has started (its .log exists).
nagano_cells | { if [ -n "${COND:-}" ]; then grep -F "/nagano/$COND/" || true; else cat; fi; } \
  | { if [ -n "${REVERSE:-}" ]; then tac; else cat; fi; } \
  | while IFS=$'\t' read -r cell table; do
  out=$M/models/nucdyn_gpu/$cell.npz
  [ -f "$out" ] && continue
  if [ -n "${REVERSE:-}" ] && [ -f "$M/models/nucdyn_gpu/$cell.log" ]; then break; fi
  $PY $SC/run_nucdyn.py --contacts "$table" --res 100000 --device gpu --n-models 2 --seed 1 --out "$out" \
    > "$M/models/nucdyn_gpu/$cell.log" 2>&1 || echo "FAILED $cell"
done
ls "$M"/models/nucdyn_gpu/*.npz | wc -l
