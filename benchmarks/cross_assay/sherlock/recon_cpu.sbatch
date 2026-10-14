#!/bin/bash
# Reconstructions (METHOD=ember, the default, or nucdyn) on CPU (f64, rayon; recon.sbatch is the GPU version) for the cross-assay comparison in distance space (benchmarks/cross_assay/recon.py, stage run):
# Tan 2021 cortex (DATASET=tan2021, default) or HiRES brain (DATASET=hires_brain) cells at 1 Mb, variants dip / hap / hap_c150k / hap_c45k / hap_c20k, one GPU per array task, with
# the frozen engine build `dipfrozen` (EMber, tag ember-diploid-frozen) in venv-diploid.  Outputs skip when present.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-xa[,LIMIT=2] --array=0-7 benchmarks/cross_assay/sherlock/recon.sbatch
#   then recon_collect.sbatch (--dependency=afterok:<array job>)
#SBATCH --job-name=xa-recon-cpu
#SBATCH --partition=xiaojie,normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=16
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
METHOD=${METHOD:-ember}                     # ember (the run of 2026-10-11) or nucdyn (NucDynamics 2017, 2026-10-12)
ROOT=$W/runs/xassay; [ "$METHOD" = ember ] || ROOT=$W/runs/xassay/$METHOD
case $DATASET in
  tan2021) DATA_DIR=${DATA_DIR:-$W/data/tan2021_cortex/cells}; OUT=${OUT:-$ROOT/recon_tan} ;;
  hires_brain) DATA_DIR=${DATA_DIR:-$W/data/hires2023/raw/GSE223917/cells}; OUT=${OUT:-$ROOT/recon_hires_brain} ;;
  *) OUT=${OUT:-$ROOT/recon_$DATASET}; DATA_DIR=${DATA_DIR:-$W/runs/xassay/recon_$DATASET} ;;  # pairs of stage maps
esac
N_TASKS=${N_TASKS:-${SLURM_ARRAY_TASK_COUNT:-1}}
echo "host=$(hostname) job=${SLURM_JOB_ID:-none} task=${SLURM_ARRAY_TASK_ID:-0}/$N_TASKS repo=$REPO method=$METHOD out=$OUT"
lscpu | grep "Model name" || true
"$PY" -c 'import uchrom_recon as un; print("uchrom_recon", un.__version__, un.__file__)'
"$PY" -u "$REPO/benchmarks/cross_assay/recon.py" --out "$OUT" --stages run --device cpu --task "${SLURM_ARRAY_TASK_ID:-0}" \
  --n-tasks "$N_TASKS" --dataset "$DATASET" --data-dir "$DATA_DIR" --method "$METHOD" ${LIMIT:+--limit $LIMIT} \
  ${VARIANTS:+--variants $VARIANTS}
