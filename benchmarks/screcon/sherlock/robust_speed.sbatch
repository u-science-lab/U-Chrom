#!/bin/bash
# One-model wall time of `robust` (Fig. 3d protocol, benchmarks/fig3/speed_one_model.py): Stevens 2017 Cell 1
# (a development cell), 1 model, seed 1, 500 kb ... 1 kb, on the AMD EPYC 9754 nodes of the hickit /
# NucDynamics records (CPU) or one H100 (GPU).  Records -> $RB/speed/<VARIANT>/records.
#
#   ROBUST_PARAMS='{...}' sbatch --export=ALL,VARIANT=v,ENGINE=e8,METHOD=robust_cpu,THREADS=1 robust_speed.sbatch
#   ... METHOD=robust_cpu,THREADS=16 --cpus-per-task=16
#   ... METHOD=robust_gpu -p xiaojie,gpu,owners -G 1 -C GPU_SKU:H100_SXM5 --cpus-per-task=8
#SBATCH --job-name=rb-speed
#SBATCH --partition=xiaojie,owners
#SBATCH --constraint=CPU_SKU:9754
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-robust/benchmarks/screcon/sherlock/_env_robust.sh"
: "${VARIANT:?}" "${METHOD:?}"
export ROBUST_PARAMS=${ROBUST_PARAMS:-"{}"} ROBUST_REPO=$REPO ROBUST_PY=$PY
export CONTACTS=$DATA/stevens2017_mesc/GSM2219497_Cell_1_contact_pairs.txt.gz
echo "host=$(hostname) cpus=${SLURM_CPUS_PER_TASK} cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2) params=$ROBUST_PARAMS"
command -v nvidia-smi > /dev/null && nvidia-smi --query-gpu=name --format=csv,noheader || true
$PY $REPO/benchmarks/fig3/speed_one_model.py run --method "$METHOD" ${THREADS:+--threads $THREADS} --res "${RES:-all}" \
  --python "$PY" --robust-python "$PY" --robust-repo "$REPO" --out-dir "$RB/speed/$VARIANT"
