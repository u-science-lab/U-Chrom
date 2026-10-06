# Shared settings of the bulk deconvolution jobs (IGM engine + benchmark), sourced by every *.sbatch.
#
#   $GROUP_HOME/$USER/uchrom-nd/venv-deconv       Python 3.12 env of these jobs (setup_deconv.sbatch creates it,
#                                                 builds the native engine wheel with the igm protocol + GPU;
#                                                 setup_bulk.sbatch adds cooler, h5py, hic-straw, fsspec,
#                                                 requests, aiohttp, scikit-learn, pytest; binary wheels only,
#                                                 numpy < 2.3 / pandas < 2.3 / scipy < 1.15 for CentOS 7).
#                                                 Separate from venv-main so the running Fig. 3 / screcon jobs
#                                                 keep their engine build.
#   $GROUP_HOME/$USER/uchrom-nd/vulkan-loader     Vulkan loader for wgpu on the GPU nodes (fig3 gpu_probe.sbatch)
#   $GROUP_HOME/$USER/uchrom-nd/igm-orig/         original IGM: conda env (py3.6), alabtools, igm, lammpgen (setup_igm_orig.sbatch)
#   $SCRATCH/uchrom-nd/repo-deconv                repo copy of this branch (rsync from the laptop)
#   $SCRATCH/uchrom-nd/data                       example data (su2020_imr90/, 4DNFIFLJGGNR.csv, Hi-C builds)
#   $SCRATCH/uchrom-nd/data/igm                   IGM demo input WTC11_HiC_2Mb.hcs (downloaded on demand; GPL-3, not in the repo)
#   $SCRATCH/uchrom-nd/runs/bulk/                 outputs ({sim,real,base,models,scores,twin,tables}, engine runs)
#
# The benchmark scripts need no U-Chrom install (benchmarks/bulk/_common.py loads
# packages/uchrom/uchrom/recon/bulk/deconv/preprocess.py from its file path); the deconvolution itself needs
# U-Chrom + the native engine (installed editable into venv-deconv by setup_deconv.sbatch).
set -euo pipefail
ml purge
ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd
W=$SCRATCH/uchrom-nd
VENV=${VENV:-$BASE/venv-deconv}
REPO=${REPO:-$W/repo-deconv}
BK=$REPO/benchmarks/bulk
PY=$VENV/bin/python
ENGINE_PY=${ENGINE_PY:-$PY}
IGMO=$BASE/igm-orig
DATA=$W/data
export UCHROM_EXAMPLE_DATA=$DATA
export UCHROM_IGM_CACHE=$DATA/igm
HCS=$UCHROM_IGM_CACHE/WTC11_HiC_2Mb.hcs
export PIP_CACHE_DIR=$SCRATCH/.cache/pip
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
RUNS=$W/runs/bulk
SIM=$RUNS/sim
REAL=$RUNS/real
SCORES=$RUNS/scores
mkdir -p "$RUNS" "$UCHROM_IGM_CACHE" "$SIM" "$REAL" "$SCORES" "$RUNS/base" "$RUNS/models" "$RUNS/twin" "$RUNS/tables"

# manifest line N ($RUNS/manifest.tsv: dataset, name, truth.npz, input.npz[, rc_from.npz])
#   -> DATASET NAME TRUTH INPUT RCFROM (empty for simulated inputs: rc is in their provenance),
#      RCARG (score / baseline argument), BASEDIR, MODELDIR
task() {
  local line
  line=$(sed -n "${1}p" "$RUNS/manifest.tsv")
  RCFROM=""
  IFS=$'\t' read -r DATASET NAME TRUTH INPUT RCFROM <<< "$line"
  RCARG=()
  if [ -n "$RCFROM" ]; then RCARG=(--rc-from "$RCFROM"); fi
  BASEDIR=$RUNS/base/$DATASET/$NAME
  MODELDIR=$RUNS/models/$DATASET/$NAME
  mkdir -p "$BASEDIR" "$MODELDIR"
}

cd "$REPO"
echo "host=$(hostname) job=${SLURM_JOB_ID:-} task=${SLURM_ARRAY_TASK_ID:-} cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2)"
command -v nvidia-smi > /dev/null && nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
