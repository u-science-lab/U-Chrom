#!/bin/bash
# Single cells across assays (benchmarks/cross_assay/transfer.py): locus signatures of ExN vs Oligo from imaging and
# from each EMber reconstruction, scored on single cells of the other kind; AUROC.  Reads the recon.py outputs
# ($SCRATCH/uchrom-nd/runs/xassay/recon_*) and the Liu 2025 store.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-xa,UCHROM_REVISION=...[,LIMIT=30] benchmarks/cross_assay/sherlock/transfer.sbatch
#SBATCH --job-name=xa-transfer
#SBATCH --partition=xiaojie,normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/runs/xassay/logs/%x-%j.out
set -uo pipefail
ml purge
ml python/3.12.1
W=$SCRATCH/uchrom-nd
PY=$GROUP_HOME/$USER/uchrom-nd/venv-consensus/bin/python
export UCHROM_DATA=$W/data XDG_CACHE_HOME=$SCRATCH/.cache OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export PYTHONPATH=$REPO/packages/uchrom:$REPO/packages/chromdata${PYTHONPATH:+:$PYTHONPATH}
OUT=${OUT:-$W/runs/xassay/transfer${LIMIT:+_smoke}}
mkdir -p "$OUT/results"
echo "host=$(hostname) job=${SLURM_JOB_ID:-none} repo=$REPO revision=${UCHROM_REVISION:-unset} out=$OUT"
"$PY" -u "$REPO/benchmarks/cross_assay/transfer.py" --liu "$W/data/liu2025_mop/liu2025_mop.chromdata.zarr" \
  --recon-root "$W/runs/xassay" --xa-work "$W/runs/xassay/full/work" --out "$OUT" --results "$OUT/results" \
  ${LIMIT:+--limit-cells $LIMIT}
