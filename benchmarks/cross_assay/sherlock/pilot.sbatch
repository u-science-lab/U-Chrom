#!/bin/bash
# Cross-assay pilot (benchmarks/cross_assay/pilot.py) on Sherlock: the imaging structure sets
# (benchmarks/screcon/matched_data.py: Takei 2021 brain with the authors' DBSCAN homologs and with the k-means split,
# Tan 2021 Dip-C models of replicate 1, all on the 2,460 Takei 1-Mb loci), then the stages
# imaging / guo / tan / seq / analyze (the atlas stores are read over HTTP), then an archive on Oak.
#
#   XA=$SCRATCH/uchrom-nd/xassay  (benchmarks/{_record.py, screcon} of $REPO linked, cross_assay/pilot.py added)
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sv,XA=$XA,UCHROM_REVISION=...[,STAGES="seq analyze"] \
#       $XA/benchmarks/cross_assay/sherlock/pilot.sbatch     (no comma inside an --export value)
#SBATCH --job-name=xassay-pilot
#SBATCH --partition=xiaojie,normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/runs/xassay/logs/%x-%j.out
set -uo pipefail
ml purge
ml python/3.12.1
W=$SCRATCH/uchrom-nd
PY=${XA_PY:-$GROUP_HOME/$USER/uchrom-nd/venv-consensus/bin/python}
export UCHROM_DATA=$W/data
export PIP_CACHE_DIR=$SCRATCH/.cache/pip XDG_CACHE_HOME=$SCRATCH/.cache MPLBACKEND=Agg OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export PYTHONPATH=$REPO/packages/uchrom:$REPO/packages/chromdata${PYTHONPATH:+:$PYTHONPATH}
RUN=${RUN:-$W/runs/xassay/pilot}
mkdir -p "$RUN/work" "$RUN/sets" "$RUN/results"
echo "host=$(hostname) job=${SLURM_JOB_ID:-none} repo=$REPO xa=$XA revision=${UCHROM_REVISION:-unset}"
"$PY" -c 'import sys, numpy, pandas, scipy, zarr; print(sys.executable, sys.version.split()[0], "numpy", numpy.__version__, "pandas", pandas.__version__, "scipy", scipy.__version__, "zarr", zarr.__version__)'
MD=$REPO/benchmarks/screcon/matched_data.py
S7=$UCHROM_DATA/takei2021_brain/TableS7_brain_DNAseqFISH_1Mb_voxel_coordinates_2762cells.csv
step() { local t0=$SECONDS; echo "=== $1 ($(date +%T))"; shift; "$@" || echo "!!! FAILED: $*"; echo "=== done in $((SECONDS - t0)) s"; }
[ -s "$RUN/sets/takei2021_brain_labels.npz" ] || step sets-takei-labels "$PY" -u "$MD" takei-brain --s7 "$S7" --split labels --min-detect 0.2 --out "$RUN/sets/takei2021_brain_labels.npz"
[ -s "$RUN/sets/takei2021_brain_kmeans.npz" ] || step sets-takei-kmeans "$PY" -u "$MD" takei-brain --s7 "$S7" --split kmeans --min-detect 0.2 --out "$RUN/sets/takei2021_brain_kmeans.npz"
[ -s "$RUN/sets/tan2021_dipc_rep1.npz" ] || step sets-tan-dipc "$PY" -u "$MD" dipc --dir "$UCHROM_DATA/tan2021_cortex/cells" --rep 1 --out "$RUN/sets/tan2021_dipc_rep1.npz"
P="$PY -u $XA/benchmarks/cross_assay/pilot.py --work $RUN/work --results $RUN/results --workers 6"
for st in ${STAGES:-imaging guo tan seq analyze}; do
  case $st in
    imaging) step imaging $P --stages imaging --sets "$RUN/sets" ;;
    tan) step tan $P --stages tan --tan-dir "$UCHROM_DATA/tan2021_cortex/cells" ;;
    *) step "$st" $P --stages "$st" ;;
  esac
done
ARCH=$OAK/uchrom/results/cross_assay/$(date +%Y-%m-%d)_pilot_${SLURM_JOB_ID:-none}
mkdir -p "$ARCH" && step archive tar czf "$ARCH/pilot_work_results.tar.gz" -C "$RUN" work results sets
echo "archive: $ARCH"
