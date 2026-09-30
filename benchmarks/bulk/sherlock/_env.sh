# Shared settings of the bulk (IGM) Sherlock jobs (sourced by every *.sbatch).
#
#   $GROUP_HOME/$USER/uchrom-nd/venv-main        Python 3.12 + uchrom_nucdyn (setup_deconv.sbatch rebuilds the wheel)
#   $GROUP_HOME/$USER/uchrom-nd/vulkan-loader    Vulkan loader for wgpu on the GPU nodes (fig3 gpu_probe.sbatch)
#   $GROUP_HOME/$USER/uchrom-nd/igm-orig/        original IGM: conda env (py3.6), alabtools, igm, lammpgen (setup_igm_orig.sbatch)
#   $SCRATCH/uchrom-nd/repo                      repo copy (rsync from the laptop)
#   $SCRATCH/uchrom-nd/data/igm                  IGM demo input WTC11_HiC_2Mb.hcs (downloaded on demand; GPL-3, not in the repo)
#   $SCRATCH/uchrom-nd/runs/bulk/                outputs
set -euo pipefail
ml purge
ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd
W=$SCRATCH/uchrom-nd
REPO=$W/repo
BK=$REPO/benchmarks/bulk
PY=$BASE/venv-main/bin/python
IGMO=$BASE/igm-orig
export UCHROM_IGM_CACHE=$W/data/igm
HCS=$UCHROM_IGM_CACHE/WTC11_HiC_2Mb.hcs
RUNS=$W/runs/bulk
export PIP_CACHE_DIR=$SCRATCH/.cache/pip
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
mkdir -p "$RUNS" "$UCHROM_IGM_CACHE"
cd "$REPO"
echo "host=$(hostname) job=${SLURM_JOB_ID:-} task=${SLURM_ARRAY_TASK_ID:-} cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2)"
command -v nvidia-smi > /dev/null && nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
