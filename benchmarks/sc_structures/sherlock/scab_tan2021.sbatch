#!/bin/bash
# scA/B on Tan 2021 adult cortex Dip-C (510 cells): the original Dip-C (Python 2.7, pinned commit) against
# single_cell_compartments on 20 cells (scab_dipc_reference.py), then structure types, depth, scHiCluster
# (scab_tan2021.py); the original scHiCluster compartment score (pinned commit) against the cis / raw form on
# Tan 2021 and Kim 2020 maps (scab_schicluster_reference.py).  Needs scab_prep (CpG cache, kim2020 store).
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-scab benchmarks/sc_structures/sherlock/scab_tan2021.sbatch
#SBATCH --job-name=scab-tan2021
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:30:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-scab}/benchmarks/sc_structures/sherlock/_env.sh"
# SCAB_PY: another existing Python env (e.g. venv-consensus) while venv-sc is not usable
PY=${SCAB_PY:-$PY}
"$PY" -c 'import sys, numpy, pandas, scipy, cooler, sklearn, zarr; print(sys.executable, "numpy", numpy.__version__, "pandas", pandas.__version__, "scipy", scipy.__version__, "cooler", cooler.__version__, "sklearn", sklearn.__version__, "zarr", zarr.__version__)'
export SCAB_CACHE=$OUT/scab/cache OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
RUN=$OUT/scab/tan2021
REF=$OUT/scab/ref
mkdir -p "$RUN" "$REF"
# the original: Dip-C (github.com/tanlongzhi/dip-c) at a pinned commit, Python 2.7 + numpy / scipy modules
DIPC=$REF/dip-c
# (the compute nodes' git has no -C)
[ -d "$DIPC" ] || git clone -q https://github.com/tanlongzhi/dip-c "$DIPC"
(cd "$DIPC" && git checkout -q 289c1a4bc0f2fe845b524716d74ff058fa4676e6)
PY2=$REF/python2
(
  set +u
  unset PYTHONPATH
  ml purge
  ml devel math python/2.7.13 py-scipy/1.1.0_py27          # numpy 1.14.3, scipy 1.1.0
  { echo '#!/bin/bash'; echo "export PATH='$PATH'"; echo "export LD_LIBRARY_PATH='${LD_LIBRARY_PATH:-}'"
    echo "export PYTHONPATH='${PYTHONPATH:-}'"; echo 'exec python "$@"'; } > "$PY2"
)
chmod +x "$PY2"
"$PY2" -c 'import sys, numpy, scipy; print("python", sys.version.split()[0], "numpy", numpy.__version__, "scipy", scipy.__version__)'
echo "dip-c $(cd "$DIPC" && git rev-parse HEAD)"
SCHIC=$REF/scHiCluster
[ -d "$SCHIC" ] || git clone -q https://github.com/zhoujt1994/scHiCluster "$SCHIC"
(cd "$SCHIC" && git checkout -q d566046071badb48f95305987fae189d0201ae30)
echo "scHiCluster $(cd "$SCHIC" && git rev-parse HEAD)"
cd "$REPO"
"$PY" -u benchmarks/sc_structures/scab_dipc_reference.py --dipc "$DIPC" --python2 "$PY2" --cells 20 --out "$RUN/dipc"
"$PY" -u benchmarks/sc_structures/scab_tan2021.py --out "$RUN"
"$PY" -u benchmarks/sc_structures/scab_schicluster_reference.py --schicluster "$SCHIC" --genome mm10 --cells 20 \
  --scool "$RUN/tan2021_cortex_1Mb.scool" --label tan2021_1Mb --out "$RUN/schicluster"
"$PY" -u benchmarks/sc_structures/scab_schicluster_reference.py --schicluster "$SCHIC" --genome hg19 --cells 50 \
  --scool "$UCHROM_DATA/kim2020_scihic/kim2020_scihic_500kb.scool" --label kim2020_500kb --out "$RUN/schicluster"
