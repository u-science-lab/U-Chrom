# Settings of the EMber-pop jobs (PREREG_POP.md), sourced by every pop_*.sbatch.
#
#   $GROUP_HOME/$USER/uchrom-nd/venv-pop        Python 3.12 env (pop_setup.sbatch: binary wheels for CentOS 7,
#                                               chromdata + uchrom editable without dependencies, the native
#                                               engine wheel with the GPU feature)
#   $GROUP_HOME/$USER/uchrom-nd/vulkan-loader   Vulkan loader for wgpu on the GPU nodes
#   $SCRATCH/uchrom-nd/repo-pop                 repo copy of branch Nanguage/ember-pop (rsync from the laptop)
#   $SCRATCH/uchrom-nd/data                     data directory (su2020_imr90/, 4DNFIFLJGGNR.csv, rao2014_imr90/)
#   $SCRATCH/uchrom-nd/runs/pop/                inputs (<unit>/C1.npz ...), runs, scores
set -euo pipefail
ml purge
ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd
W=$SCRATCH/uchrom-nd
VENV=${VENV:-$BASE/venv-pop}
REPO=${REPO:-$W/repo-pop}
BK=$REPO/benchmarks/bulk
PY=$VENV/bin/python
export UCHROM_DATA=$W/data
export PIP_CACHE_DIR=$SCRATCH/.cache/pip
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
POP=$W/runs/pop
mkdir -p "$POP"
cd "$REPO"
echo "host=$(hostname) job=${SLURM_JOB_ID:-} task=${SLURM_ARRAY_TASK_ID:-} cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2)"
command -v nvidia-smi > /dev/null && nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
