# Shared settings of the Figure 2 benchmark jobs on Sherlock (sourced by the *.sbatch here).
#
#   $GROUP_HOME/$USER/uchrom-nd/venv-fig2   Python env (setup.sbatch): zarr / AnnData / SpatialData at the laptop
#                                           series' versions, the compiled libraries as wheels for glibc 2.17
#   $SCRATCH/uchrom-nd/repo-fig2lazy        repo copy synced from the laptop (tracked files + REVISION)
#   $SCRATCH/uchrom-nd/data                 UCHROM_DATA: takei2025_cerebellum (fetched and built by access.sbatch)
#   $L_SCRATCH/fig2_work                    UCHROM_FIG2_WORK: staged subsets and the files read (node-local)
#   $SCRATCH/uchrom-nd/runs/fig2            outputs
set -euo pipefail
ml purge
ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd
W=$SCRATCH/uchrom-nd
REPO=${REPO:-$W/repo-fig2lazy}
VENV=$BASE/venv-fig2
PY=$VENV/bin/python
export UCHROM_DATA=$W/data
export UCHROM_FIG2_WORK=${UCHROM_FIG2_WORK:-${L_SCRATCH:-/tmp}/fig2_work}
export PIP_CACHE_DIR=$SCRATCH/.cache/pip XDG_CACHE_HOME=$SCRATCH/.cache MPLBACKEND=Agg
export PYTHONPATH=$REPO/packages/uchrom:$REPO/packages/chromdata${PYTHONPATH:+:$PYTHONPATH}
# the code revision as the job starts (benchmarks/_record.py records it; a later sync does not change it)
export UCHROM_REVISION=$(cat "$REPO/REVISION" 2>/dev/null || echo unknown)
OUT=$W/runs/fig2
mkdir -p "$OUT"
echo "host=$(hostname) job=${SLURM_JOB_ID:-none} repo=$REPO revision=$UCHROM_REVISION work=$UCHROM_FIG2_WORK"
