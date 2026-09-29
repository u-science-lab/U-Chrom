#!/bin/bash
# Fair CPU speed comparison on ONE node (sh04-05n13, AMD EPYC 9754), Stevens Cell 1, full schedule
# (500 x 100 steps per stage, 8 Mb -> 100 kb).  MODE selects the run:
#   orig1    original nuc_dynamics, 1 model, 1 core            (per-model cost of the original)
#   orig10   original nuc_dynamics, 10 models, its parallel mode on 10 cores
#   native   U-Chrom native engine: 1 model on 1 thread, then 10 models on 10 threads
#
#   for m in orig1 orig10 native; do sbatch --export=ALL,MODE=$m --cpus-per-task=... speed_cpu.sbatch; done
#SBATCH --job-name=nd-speed
#SBATCH --partition=xiaojie
#SBATCH --nodelist=sh04-05n13
#SBATCH --time=10:00:00
#SBATCH --mem=24G
#SBATCH --output=%x-%j.out

set -euo pipefail
ml purge; ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd; W=$SCRATCH/uchrom-nd; O=$W/runs/speed_cpu
cd "$W/repo"
echo "host=$(hostname) job=$SLURM_JOB_ID mode=$MODE cpus=$SLURM_CPUS_PER_TASK cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2)"
case "$MODE" in
  orig1)  "$BASE/venv-orig/bin/python" benchmarks/fig3/a_nucdyn_engine_original_run.py --nd-dir "$BASE/nd/master" \
            --cell 1 --models 1 --cpu 1 --temps 500 --dyns 100 --seed 1 --out "$O/orig_1model_1core" ;;
  orig10) "$BASE/venv-orig/bin/python" benchmarks/fig3/a_nucdyn_engine_original_run.py --nd-dir "$BASE/nd/master" \
            --cell 1 --models 10 --cpu 10 --temps 500 --dyns 100 --seed 1 --out "$O/orig_10models_10cores" ;;
  native) P=$BASE/venv-main/bin/python
          $P benchmarks/fig3/a_nucdyn_engine_run.py --cells 1 --device cpu --n-models 1 --n-threads 1 \
            --temp-steps 500 --dyn-steps 100 --seed 1 --out "$O/native_1model_1thread"
          $P benchmarks/fig3/a_nucdyn_engine_run.py --cells 1 --device cpu --n-models 10 --n-threads 10 \
            --temp-steps 500 --dyn-steps 100 --seed 1 --out "$O/native_10models_10threads" ;;
esac
echo done
