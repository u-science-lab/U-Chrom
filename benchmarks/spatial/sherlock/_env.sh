# Settings of the type-deconvolution jobs (PREREG §14), sourced by every td_*.sbatch.
#
#   $GROUP_HOME/$USER/uchrom-nd/venv-main     Python env (numpy / scipy / pandas; the screcon env)
#   $SCRATCH/uchrom-nd/repo-spatial           repo copy (rsync from the laptop; separate from repo/)
#   $SCRATCH/uchrom-nd/data/tan2021_cortex    Tan 2021 Dip-C cells (fetch tan2021_cortex)
#   $SCRATCH/uchrom-nd/runs/spatial/typedecon outputs: split.tsv, cells/, truth/, tissues/, scores/, tables/
set -euo pipefail
ml purge
ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd
W=$SCRATCH/uchrom-nd
REPO=$W/repo-spatial
SP=$REPO/benchmarks/spatial
PY=$BASE/venv-main/bin/python
DATA=$W/data
OUT=$W/runs/spatial/typedecon
export PIP_CACHE_DIR=$SCRATCH/.cache/pip
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1} OPENBLAS_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}
mkdir -p "$OUT"
REGIMES=(low high)
NOISES=(exact moderate heavy)
RESS=(1000000 250000)
NREP_DEV=4
NREP_TEST=8

# array task 1..N -> REGIME REP (order: rep, regime)
td_tissue() {
  local t=$(( $1 - 1 )) set=$2 nrep
  nrep=$([ "$set" = dev ] && echo $NREP_DEV || echo $NREP_TEST)
  REGIME=${REGIMES[$(( t % 2 ))]}
  REP=$(( t / 2 ))
  [ "$REP" -lt "$nrep" ] || { echo "task $1 out of range"; exit 1; }
}

echo "host=$(hostname) job=${SLURM_JOB_ID:-} task=${SLURM_ARRAY_TASK_ID:-}"
