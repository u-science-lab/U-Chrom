#!/bin/bash
# Fig. 3d: one-model wall time per method x resolution (benchmarks/fig3/speed_one_model.py).
# Array over the lines of a task file (method, threads, resolution; GPU methods: one task for all
# resolutions); repeats run inside the task when a run is cheap.  Input: Stevens 2017 Cell 1.
#
# CPU runs: AMD EPYC 9754 only (-C CPU_SKU:9754: sh04-05n13 in xiaojie, the CSCALE nodes in
# owners), --cpus-per-task = thread count.  GPU runs: one H100 SXM5.  Records ->
# $SCRATCH/uchrom-nd/runs/speed_one_model/records/.  From $SCRATCH/uchrom-nd/repo-speed:
#
#   P=$GROUP_HOME/$USER/uchrom-nd/venv-main/bin/python; S=benchmarks/fig3/speed_one_model.py
#   $P $S manifest --methods hickit,nucdyn_cpu,orig,sic --out tasks_cpu.tsv       # 30 tasks
#   # 1-thread tasks (lines with threads 1), 16-thread tasks: --cpus-per-task=16
#   sbatch --array=<1-thread lines> --export=ALL,TASKS=tasks_cpu.tsv benchmarks/fig3/sherlock/speed_one_model.sbatch
#   sbatch --array=<16-thread lines> --cpus-per-task=16 --export=ALL,TASKS=tasks_cpu.tsv benchmarks/fig3/sherlock/speed_one_model.sbatch
#   $P $S manifest --methods nucdyn_gpu --out tasks_gpu.tsv
#   sbatch --array=1 -p xiaojie,gpu -G 1 -C GPU_SKU:H100_SXM5 --cpus-per-task=8 --mem=64G --time=12:00:00 \
#     --export=ALL,TASKS=tasks_gpu.tsv benchmarks/fig3/sherlock/speed_one_model.sbatch
#   # robust, once Nanguage/sc-robust exposes it (its venv / repo copy):
#   $P $S manifest --methods robust_cpu,robust_gpu --out tasks_robust.tsv
#   sbatch ... --export=ALL,TASKS=tasks_robust.tsv,ROBUST_REPO=...,ROBUST_PY=... (same resources as above)
#   $P $S aggregate --records $SCRATCH/uchrom-nd/runs/speed_one_model/records --out speed_one_model.json
#SBATCH --job-name=speed1
#SBATCH --partition=xiaojie,owners
#SBATCH --constraint=CPU_SKU:9754
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --requeue
#SBATCH --output=%x-%A_%a.out

set -euo pipefail
ml purge; ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd; W=$SCRATCH/uchrom-nd
export PY=$BASE/venv-main/bin/python ORIG_PY=$BASE/venv-orig/bin/python ND=$BASE/nd/master
export HICKIT=$BASE/hickit-0.1.1_x64-linux/hickit SIC=$W/sic/modeling
export CONTACTS=$W/data/stevens2017_mesc/GSM2219497_Cell_1_contact_pairs.txt.gz
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}   # wgpu needs the Vulkan loader
REPO=${REPO:-$W/repo-speed}
cd "$REPO"
echo "host=$(hostname) job=$SLURM_JOB_ID task=${SLURM_ARRAY_TASK_ID} restarts=${SLURM_RESTART_COUNT:-0} cpus=$SLURM_CPUS_PER_TASK cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2)"
command -v nvidia-smi > /dev/null && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
$PY benchmarks/fig3/speed_one_model.py run --task-file "${TASKS:?}" --task "$SLURM_ARRAY_TASK_ID" \
  --out-dir "${OUTDIR:-$W/runs/speed_one_model}"
echo done
