#!/bin/bash
# Example structures for the paper's Extended Data Fig. 3d (benchmarks/cross_assay/structures.py): one typical ExN and
# Oligo cell per source (imaging, Dip-C and scHiCAR reconstructions), chosen by the single-cell scores of transfer.py.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-xa[,RECON_ROOT=...,SCORES=...,OUT=...] \
#       benchmarks/cross_assay/sherlock/structures.sbatch
#SBATCH --job-name=xa-structures
#SBATCH --partition=xiaojie,normal
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/runs/xassay/logs/%x-%j.out
set -uo pipefail
ml purge
ml python/3.12.1
W=$SCRATCH/uchrom-nd
PY=$GROUP_HOME/$USER/uchrom-nd/venv-consensus/bin/python
export UCHROM_DATA=$W/data XDG_CACHE_HOME=$SCRATCH/.cache OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export PYTHONPATH=$REPO/packages/uchrom:$REPO/packages/chromdata${PYTHONPATH:+:$PYTHONPATH}
RECON_ROOT=${RECON_ROOT:-$W/runs/xassay}
SCORES=${SCORES:-$RECON_ROOT/transfer}
OUT=${OUT:-$RECON_ROOT/structures}
mkdir -p "$OUT"
echo "host=$(hostname) job=${SLURM_JOB_ID:-none} repo=$REPO recon_root=$RECON_ROOT scores=$SCORES out=$OUT"
"$PY" -u "$REPO/benchmarks/cross_assay/structures.py" --liu "$W/data/liu2025_mop/liu2025_mop.chromdata.zarr" \
  --recon-root "$RECON_ROOT" --scores "$SCORES" --out "$OUT"
