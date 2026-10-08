# Shared settings of the single-cell structure-calling jobs on Sherlock (sourced by every *.sbatch here).
#
#   $GROUP_HOME/$USER/uchrom-nd/venv-sc          Python env: chromdata + u-chrom (editable, repo-sc) and their
#                                                dependencies, pytest (setup.sbatch)
#   $SCRATCH/uchrom-nd/repo-sc[-<part>]           repo copies, synced from the laptop (tracked + new files only:
#                                                `git ls-files -z --cached --others --exclude-standard | rsync ...`);
#                                                REPO= picks one (default repo-sc)
#   $SCRATCH/uchrom-nd/engine-sc/<tag>           uchrom_maps + uchrom_recon built from a repo copy (setup.sbatch)
#   $SCRATCH/uchrom-nd/data                      UCHROM_DATA (shared with the other uchrom-nd jobs)
#   $SCRATCH/uchrom-nd/runs/sc                   outputs
set -euo pipefail
ml purge
ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd
W=$SCRATCH/uchrom-nd
REPO=${REPO:-$W/repo-sc}
PY=$BASE/venv-sc/bin/python
ENGINE=${ENGINE:-sc}
export UCHROM_DATA=$W/data
export PIP_CACHE_DIR=$SCRATCH/.cache/pip XDG_CACHE_HOME=$SCRATCH/.cache MPLBACKEND=Agg
# the repo copy's packages first, then its native kernels
export PYTHONPATH=$REPO/packages/uchrom:$REPO/packages/chromdata:$W/engine-sc/$ENGINE${PYTHONPATH:+:$PYTHONPATH}
OUT=$W/runs/sc
mkdir -p "$OUT"
echo "host=$(hostname) job=${SLURM_JOB_ID:-none} repo=$REPO engine=$ENGINE $($PY -c 'import sys; print(sys.version.split()[0])')"
