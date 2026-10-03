# Settings of the `robust` (new method) jobs: the screcon settings (_env.sh: paths of the existing
# baseline runs, which are only read) with the robust repo copy, venv and output tree.
#
#   $GROUP_HOME/$USER/uchrom-nd/venv-robust     numpy / scipy / pandas + uchrom_nucdyn (robust_setup.sbatch)
#   $SCRATCH/uchrom-nd/repo-robust              repo copy (branch Nanguage/sc-robust, rsync from the laptop)
#   $SCRATCH/uchrom-nd/runs/robust              outputs
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
REPO=$W/repo-robust
SC=$REPO/benchmarks/screcon
PY=$BASE/venv-robust/bin/python
RB=$W/runs/robust
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}

# PREREG.md §2: the development set.  Simulations: truth cells 1-2; held-out / real data: cells 1-4.
dev_unit() { case $1 in truth_1_*|truth_2_*) return 0 ;; *) return 1 ;; esac; }
dev_cell() { [ "$1" -ge 1 ] && [ "$1" -le 4 ]; }

# ENGINE=<tag>: use the engine build pinned by robust_setup.sbatch (ENGINE_TAG=<tag>)
if [ -n "${ENGINE:-}" ]; then
  [ -d "$W/engine-robust/$ENGINE" ] || { echo "engine $ENGINE not found"; exit 1; }
  export PYTHONPATH=$W/engine-robust/$ENGINE${PYTHONPATH:+:$PYTHONPATH}
fi
