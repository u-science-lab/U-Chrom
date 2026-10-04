# Settings of the high-resolution diploid EMber demonstration (Fig. 3, scMicro-C GM12878, Wu et al. 2025):
# the screcon settings (_env.sh) with their own repo copy, pinned engine and output tree.  Not part of the
# pre-registered tests; frozen defaults only.
#
#   $GROUP_HOME/$USER/uchrom-nd/venv-diploid      numpy / scipy / pandas (diploid_setup.sbatch); the engine is
#                                                 NOT taken from this venv but from the pinned copy below
#   $SCRATCH/uchrom-nd/repo-highres               repo copy (branch Nanguage/fig3-highres, rsync from the laptop)
#   $SCRATCH/uchrom-nd/engine-highres/$ENGINE     uchrom_nucdyn built from repo-highres (highres_setup.sbatch)
#   $SCRATCH/uchrom-nd/data/wu2025_scmicroc       scMicro-C pairs + the authors' 3dg (highres_download.sbatch)
#   $SCRATCH/uchrom-nd/runs/highres               outputs
source "$SCRATCH/uchrom-nd/repo-highres/benchmarks/screcon/sherlock/_env.sh"
REPO=$W/repo-highres
SC=$REPO/benchmarks/screcon
PY=$BASE/venv-diploid/bin/python
HR=$W/runs/highres
WU=$DATA/wu2025_scmicroc
ENGINE=${ENGINE:-main-3658fdb}
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export PYTHONPATH=$W/engine-highres/$ENGINE${PYTHONPATH:+:$PYTHONPATH}
mkdir -p "$HR"
