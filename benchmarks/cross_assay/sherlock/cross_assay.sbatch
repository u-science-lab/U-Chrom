#!/bin/bash
# Cross-assay analysis (benchmarks/cross_assay/cross_assay.py, Steps 1-2) on Sherlock: every per-cell value from
# uchrom.fea.separation_profile — the atlas sequencing stores (per-cell maps over HTTP), Tan 2021 pairs binned into
# a .scool, the Liu 2025 MOp store (liu2025.sbatch builds it) and the pilot's structure sets — then the check against
# the pilot's tables, the statistics, and an archive on Oak.
#
#   REPO = a copy of the repository (tracked + new files, synced through the DTN)
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-xa,UCHROM_REVISION=...[,STAGES=figure,ARCHIVE=0] \
#       $REPO/benchmarks/cross_assay/sherlock/cross_assay.sbatch      (no comma inside an --export value)
#SBATCH --job-name=xassay
#SBATCH --partition=xiaojie,normal
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/runs/xassay/logs/%x-%j.out
set -uo pipefail
ml purge
ml python/3.12.1
W=$SCRATCH/uchrom-nd
PY=${XA_PY:-$GROUP_HOME/$USER/uchrom-nd/venv-consensus/bin/python}
export UCHROM_DATA=$W/data
export XDG_CACHE_HOME=$SCRATCH/.cache MPLBACKEND=Agg OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export PYTHONPATH=$REPO/packages/uchrom:$REPO/packages/chromdata${PYTHONPATH:+:$PYTHONPATH}
RUN=${RUN:-$W/runs/xassay/full}
PILOT=$W/runs/xassay/pilot
mkdir -p "$RUN/work" "$RUN/results"
echo "host=$(hostname) job=${SLURM_JOB_ID:-none} repo=$REPO revision=${UCHROM_REVISION:-unset}"
"$PY" -c 'import sys, numpy, pandas, scipy, zarr, uchrom.fea; print(sys.executable, sys.version.split()[0], "numpy", numpy.__version__, "pandas", pandas.__version__, "scipy", scipy.__version__, "zarr", zarr.__version__, uchrom.fea.__file__)'
md5sum "$UCHROM_DATA/liu2025_mop/4DNFID46OABK.csv" "$UCHROM_DATA/liu2025_mop/4DNFICX8IVEK.csv"
step() { local t0=$SECONDS; echo "=== $1 ($(date +%T))"; shift; "$@" || echo "!!! FAILED: $*"; echo "=== done in $((SECONDS - t0)) s"; }
X="$PY -u $REPO/benchmarks/cross_assay/cross_assay.py --work $RUN/work --results $RUN/results --workers 6"
for st in ${STAGES:-seq tan imaging check analyze figure}; do
  case $st in
    tan) step tan $X --stages tan --tan-dir "$UCHROM_DATA/tan2021_cortex/cells" ;;
    imaging) step imaging $X --stages imaging --sets "$PILOT/sets" --liu "$UCHROM_DATA/liu2025_mop/liu2025_mop.chromdata.zarr" ;;
    check) step check $X --stages check --pilot-work "$PILOT/work" --sets "$PILOT/sets" ;;
    figure) step figure $X --stages figure --figdata "$RUN/figdata" ;;
    *) step "$st" $X --stages "$st" ;;
  esac
done
[ "${ARCHIVE:-1}" = 0 ] && exit 0                 # ARCHIVE=0: a rerun of late stages only (e.g. STAGES=figure)
ARCH=$OAK/uchrom/results/cross_assay/$(date +%Y-%m-%d)_full_${SLURM_JOB_ID:-none}
mkdir -p "$ARCH" && step archive tar czf "$ARCH/cross_assay_work_results.tar.gz" -C "$RUN" work results \
  $( [ -d "$RUN/figdata" ] && echo figdata )
echo "archive: $ARCH"
