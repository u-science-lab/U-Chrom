# Settings of the few-cell deconvolution jobs (EMber-mix, PREREG §12): the screcon settings (_env.sh)
# with the mix repo copy and output tree; the venv of the diploid jobs (numpy / scipy / pandas) is
# reused read-only, the engine comes from a pinned build (mix_setup.sbatch, ENGINE_TAG=<tag>).
#
#   $SCRATCH/uchrom-nd/repo-mix               repo copy (branch Nanguage/ember-mix, rsync from the laptop)
#   $SCRATCH/uchrom-nd/engine-mix/<tag>        pinned engine builds (PYTHONPATH)
#   $SCRATCH/uchrom-nd/runs/mix                outputs
source "$SCRATCH/uchrom-nd/repo-mix/benchmarks/screcon/sherlock/_env.sh"
REPO=$W/repo-mix
SC=$REPO/benchmarks/screcon
PY=$BASE/venv-diploid/bin/python
MX=$W/runs/mix
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
mkdir -p "$MX"
ENGINE=${ENGINE:-}
if [ -n "$ENGINE" ]; then
  [ -d "$W/engine-mix/$ENGINE" ] || { echo "engine $ENGINE not found"; exit 1; }
  export PYTHONPATH=$W/engine-mix/$ENGINE${PYTHONPATH:+:$PYTHONPATH}
fi
