# Settings of the dominant-cell jobs (PREREG §13): the screcon settings (_env.sh) with this analysis'
# repo copy, engine builds and output tree; the venv of the diploid jobs (numpy / scipy / pandas) is
# reused read-only, the engine comes from a pinned build (dom_setup.sbatch, ENGINE_TAG=<tag>).
#
#   $SCRATCH/uchrom-nd/repo-dominant                  repo copy (branch Nanguage/ember-dominant, rsync from the laptop)
#   $SCRATCH/uchrom-nd/engine-dominant/<tag>           pinned engine builds (PYTHONPATH)
#   $SCRATCH/uchrom-nd/runs/dominant/<dataset>/<set>   outputs
source "$SCRATCH/uchrom-nd/repo-dominant/benchmarks/screcon/sherlock/_env.sh"
REPO=$W/repo-dominant
SC=$REPO/benchmarks/screcon
PY=$BASE/venv-diploid/bin/python
DM=$W/runs/dominant
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
mkdir -p "$DM"
ENGINE=${ENGINE:-}
if [ -n "$ENGINE" ]; then
  [ -d "$W/engine-dominant/$ENGINE" ] || { echo "engine $ENGINE not found"; exit 1; }
  export PYTHONPATH=$W/engine-dominant/$ENGINE${PYTHONPATH:+:$PYTHONPATH}
fi
