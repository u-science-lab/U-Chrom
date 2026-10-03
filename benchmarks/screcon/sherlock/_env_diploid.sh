# Settings of the diploid (homolog-resolved) jobs: the screcon settings (_env.sh: paths of the
# existing baseline runs, which are only read) with the diploid repo copy, venv and output tree.
#
#   $GROUP_HOME/$USER/uchrom-nd/venv-diploid    numpy / scipy / pandas + uchrom_nucdyn (diploid_setup.sbatch)
#   $SCRATCH/uchrom-nd/repo-diploid             repo copy (branch Nanguage/ember-diploid, rsync from the laptop)
#   $SCRATCH/uchrom-nd/data/tan2018_gm12878     Dip-C GM12878 (download_diploid.sbatch)
#   $SCRATCH/uchrom-nd/runs/diploid             outputs
source "$SCRATCH/uchrom-nd/repo-diploid/benchmarks/screcon/sherlock/_env.sh"
REPO=$W/repo-diploid
SC=$REPO/benchmarks/screcon
PY=$BASE/venv-diploid/bin/python
DP=$W/runs/diploid
TAN18=$DATA/tan2018_gm12878
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
mkdir -p "$DP"
