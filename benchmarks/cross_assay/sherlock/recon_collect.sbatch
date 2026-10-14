#!/bin/bash
# benchmarks/cross_assay/recon.py stages collect + analyze + loci [+ contacts] (CPU, venv-consensus with the repo's uchrom / chromdata):
# the models (METHOD=ember or nucdyn) and the published Dip-C structures as ChromData stores, separation_profile on each, the
# comparison with the imaging datasets of cross_assay.py; archive on Oak.
#
#   sbatch --dependency=afterok:<recon array job> --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-xa,UCHROM_REVISION=... \
#       benchmarks/cross_assay/sherlock/recon_collect.sbatch
#SBATCH --job-name=xa-recon-collect
#SBATCH --partition=xiaojie,normal
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/runs/xassay/logs/%x-%j.out
set -uo pipefail
ml purge
ml python/3.12.1
W=$SCRATCH/uchrom-nd
PY=$GROUP_HOME/$USER/uchrom-nd/venv-consensus/bin/python
export UCHROM_DATA=$W/data XDG_CACHE_HOME=$SCRATCH/.cache MPLBACKEND=Agg OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export PYTHONPATH=$REPO/packages/uchrom:$REPO/packages/chromdata${PYTHONPATH:+:$PYTHONPATH}
DATASET=${DATASET:-tan2021}
METHOD=${METHOD:-ember}                     # ember (the run of 2026-10-11) or nucdyn (NucDynamics 2017, 2026-10-12)
ROOT=$W/runs/xassay; [ "$METHOD" = ember ] || ROOT=$W/runs/xassay/$METHOD
case $DATASET in
  tan2021) DATA_DIR=${DATA_DIR:-$W/data/tan2021_cortex/cells}; OUT=${OUT:-$ROOT/recon_tan} ;;
  hires_brain) DATA_DIR=${DATA_DIR:-$W/data/hires2023/raw/GSE223917/cells}; OUT=${OUT:-$ROOT/recon_hires_brain} ;;
  *) OUT=${OUT:-$ROOT/recon_$DATASET}; DATA_DIR=${DATA_DIR:-$W/runs/xassay/recon_$DATASET} ;;  # pairs of stage maps
esac
XA=$W/runs/xassay/full
mkdir -p "$OUT/results"
echo "host=$(hostname) job=${SLURM_JOB_ID:-none} repo=$REPO revision=${UCHROM_REVISION:-unset}"
step() { local t0=$SECONDS; echo "=== $1 ($(date +%T))"; shift; "$@" || echo "!!! FAILED: $*"; echo "=== done in $((SECONDS - t0)) s"; }
R="$PY -u $REPO/benchmarks/cross_assay/recon.py --out $OUT --dataset $DATASET --data-dir $DATA_DIR --method $METHOD ${VARIANTS:+--variants $VARIANTS}"
for st in ${STAGES:-collect analyze loci}; do
  case $st in
    maps) step maps $R --stages maps --xa-work "$XA/work" ;;
    loci_all) step loci_all $R --stages loci_all --liu "$W/data/liu2025_mop/liu2025_mop.chromdata.zarr" --results "$OUT/results" ;;
    loci) step loci $R --stages loci --xa-sets "$W/runs/xassay/pilot/sets" --liu "$W/data/liu2025_mop/liu2025_mop.chromdata.zarr" --results "$OUT/results" ;;
    contacts) step contacts $R --stages contacts --xa-sets "$W/runs/xassay/pilot/sets" --liu "$W/data/liu2025_mop/liu2025_mop.chromdata.zarr" --results "$OUT/results" ;;
    analyze) step analyze $R --stages analyze --xa-work "$XA/work" --xa-results "$XA/results" --results "$OUT/results" ;;
    *) step "$st" $R --stages "$st" ;;
  esac
done
[ "${ARCHIVE:-1}" = 0 ] && exit 0
ARCH=$OAK/uchrom/results/cross_assay/$(date +%Y-%m-%d)_recon_${METHOD}_${DATASET}_${SLURM_JOB_ID:-none}
mkdir -p "$ARCH" && step archive tar czf "$ARCH/recon_${DATASET}.tar.gz" -C "$OUT" \
  $(cd "$OUT" && ls -d dip hap hap_c150k hap_c45k hap_c20k logs results cells.tsv cells_*.parquet loci_*.parquet 2>/dev/null)
echo "archive: $ARCH"
