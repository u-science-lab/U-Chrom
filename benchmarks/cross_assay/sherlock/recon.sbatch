#!/bin/bash
# EMber reconstructions for the cross-assay comparison in distance space (benchmarks/cross_assay/recon.py, stage run):
# Tan 2021 cortex (DATASET=tan2021, default) or HiRES brain (DATASET=hires_brain) cells at 1 Mb, variants dip / hap / hap_c150k / hap_c45k / hap_c20k, one GPU per array task, with
# the frozen engine build `dipfrozen` (EMber, tag ember-diploid-frozen) in venv-diploid.  Outputs skip when present.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-xa[,LIMIT=2] --array=0-7 benchmarks/cross_assay/sherlock/recon.sbatch
#   then recon_collect.sbatch (--dependency=afterok:<array job>)
#SBATCH --job-name=xa-recon
#SBATCH --partition=xiaojie,gpu
#SBATCH -G 1
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/runs/xassay/logs/%x-%A_%a.out
set -uo pipefail
ml purge
ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd
W=$SCRATCH/uchrom-nd
PY=$BASE/venv-diploid/bin/python
export LD_LIBRARY_PATH=$BASE/vulkan-loader/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export PYTHONPATH=$REPO/benchmarks/cross_assay/sherlock/engine_shim:$W/engine-diploid/dipfrozen
DATASET=${DATASET:-tan2021}
case $DATASET in
  tan2021) DATA_DIR=${DATA_DIR:-$W/data/tan2021_cortex/cells}; OUT=${OUT:-$W/runs/xassay/recon_tan} ;;
  hires_brain) DATA_DIR=${DATA_DIR:-$W/data/hires2023/raw/GSE223917/cells}; OUT=${OUT:-$W/runs/xassay/recon_hires_brain} ;;
  *) OUT=${OUT:-$W/runs/xassay/recon_$DATASET}; DATA_DIR=${DATA_DIR:-$OUT} ;;    # from per-cell 1-Mb maps (stage maps)
esac
N_TASKS=${N_TASKS:-${SLURM_ARRAY_TASK_COUNT:-1}}
echo "host=$(hostname) job=${SLURM_JOB_ID:-none} task=${SLURM_ARRAY_TASK_ID:-0}/$N_TASKS repo=$REPO out=$OUT"
nvidia-smi --query-gpu=name --format=csv,noheader || true
"$PY" -c 'import uchrom_recon as un; print("uchrom_recon", un.__version__, un.__file__)'
"$PY" -u "$REPO/benchmarks/cross_assay/recon.py" --out "$OUT" --stages run --task "${SLURM_ARRAY_TASK_ID:-0}" \
  --n-tasks "$N_TASKS" --dataset "$DATASET" --data-dir "$DATA_DIR" ${LIMIT:+--limit $LIMIT} ${VARIANTS:+--variants $VARIANTS}
