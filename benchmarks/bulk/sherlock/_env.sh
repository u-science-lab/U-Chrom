# Shared settings of the bulk deconvolution benchmark jobs (sourced by every *.sbatch).
#
#   $GROUP_HOME/$USER/uchrom-nd/venv-main     Python 3.12 env of the Fig. 3 / screcon jobs (numpy<2.3,
#                                             pandas<2.3, scipy<1.15, psutil); setup_bulk.sbatch adds
#                                             cooler, h5py, hic-straw, fsspec, requests, aiohttp,
#                                             scikit-learn, pytest (binary wheels only, numpy pinned)
#   $SCRATCH/uchrom-nd/repo                   repo copy (rsync from the laptop)
#   $SCRATCH/uchrom-nd/data                   example data (su2020_imr90/, 4DNFIFLJGGNR.csv, Hi-C builds)
#   $SCRATCH/uchrom-nd/runs/bulk/{sim,real,base,models,scores,twin,tables}   outputs
#
# The benchmark scripts need no U-Chrom install: benchmarks/bulk/_common.py loads
# uchrom/recon/bulk/deconv/preprocess.py from its file path.  Only run_deconv.py (the deconvolution
# itself) needs U-Chrom + the native engine (the GPU env of the engine branch).
set -euo pipefail
ml purge
ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd
W=$SCRATCH/uchrom-nd
REPO=$W/repo
BK=$REPO/benchmarks/bulk
PY=$BASE/venv-main/bin/python
DATA=$W/data
export UCHROM_EXAMPLE_DATA=$DATA
export PIP_CACHE_DIR=$SCRATCH/.cache/pip
RUNS=$W/runs/bulk
SIM=$RUNS/sim
REAL=$RUNS/real
SCORES=$RUNS/scores
mkdir -p "$SIM" "$REAL" "$SCORES" "$RUNS/base" "$RUNS/models" "$RUNS/twin" "$RUNS/tables"

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

echo "host=$(hostname) job=${SLURM_JOB_ID:-} task=${SLURM_ARRAY_TASK_ID:-} cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2)"
