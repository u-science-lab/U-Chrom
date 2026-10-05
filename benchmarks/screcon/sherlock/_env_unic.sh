# Settings of the Uni-C GM12878 QC jobs (unic_qc.py; exploratory, PREREG §12): the screcon settings (_env.sh)
# with their own repo copy and output tree.
#
#   $GROUP_HOME/$USER/uchrom-nd/venv-diploid     numpy / pandas (diploid_setup.sbatch)
#   $SCRATCH/uchrom-nd/repo-unic                 repo copy (branch Nanguage/unic-gm12878, rsync from the laptop)
#   $SCRATCH/uchrom-nd/data/unic2025             Uni-C pairs (download_data.py --unic2025_gm12878)
#   $SCRATCH/uchrom-nd/data/giab_hg001           GIAB NA12878 phased VCFs (download_data.py --giab_hg001)
#   $SCRATCH/uchrom-nd/runs/unic                 outputs
source "$SCRATCH/uchrom-nd/repo-unic/benchmarks/screcon/sherlock/_env.sh"
REPO=$W/repo-unic
SC=$REPO/benchmarks/screcon
PY=$BASE/venv-diploid/bin/python
UN=$W/runs/unic
UNIC=$DATA/unic2025
GIAB=$DATA/giab_hg001
TAN18=$DATA/tan2018_gm12878
WU=$DATA/wu2025_scmicroc
mkdir -p "$UN"
