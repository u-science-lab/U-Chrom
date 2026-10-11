#!/bin/bash
# Liu et al. 2025 mouse MOp DNA-MERFISH on Sherlock: fetch the registered 4DN FOF-CT core + cell tables
# (`uchrom.datasets` entry liu2025_mop, md5-checked, 1.7 GB) into $UCHROM_DATA and build the store with the atlas
# recipe (apps/atlas/recipes/build_liu2025_mop.py; ~12 GB peak) -> $UCHROM_DATA/liu2025_mop/liu2025_mop.chromdata.zarr.
# The download runs in the job (compute nodes reach 4DN's public S3; the DTN only serves transfers started
# from outside).
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sv benchmarks/cross_assay/sherlock/liu2025.sbatch
#SBATCH --job-name=liu2025-fetch
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:30:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/runs/xassay/logs/%x-%j.out
set -euo pipefail
ml purge
ml python/3.12.1
W=$SCRATCH/uchrom-nd
PY=${XA_PY:-$GROUP_HOME/$USER/uchrom-nd/venv-consensus/bin/python}
export UCHROM_DATA=$W/data
export XDG_CACHE_HOME=$SCRATCH/.cache MPLBACKEND=Agg OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export PYTHONPATH=$REPO/packages/uchrom:$REPO/packages/chromdata${PYTHONPATH:+:$PYTHONPATH}
echo "host=$(hostname) job=${SLURM_JOB_ID:-none} repo=$REPO data=$UCHROM_DATA"
t0=$SECONDS
"$PY" -u -m uchrom.datasets fetch liu2025_mop
echo "=== fetched in $((SECONDS - t0)) s"; t0=$SECONDS
"$PY" -u "$REPO/apps/atlas/recipes/build_liu2025_mop.py"
echo "=== built in $((SECONDS - t0)) s"
cat "$UCHROM_DATA/liu2025_mop/build_summary.json"
ls -la "$UCHROM_DATA/liu2025_mop"
