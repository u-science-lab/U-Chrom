# Shared settings of the screcon Sherlock jobs (sourced by every *.sbatch).
#
#   $GROUP_HOME/$USER/uchrom-nd/{venv-main,venv-orig}   Python envs (fig3 setup.sbatch + setup_screcon.sbatch)
#   $GROUP_HOME/$USER/uchrom-nd/nd/master                original nuc_dynamics (built by fig3 setup.sbatch)
#   $GROUP_HOME/$USER/uchrom-nd/hickit-0.1.1_x64-linux   hickit release binary (setup_screcon.sbatch)
#   $SCRATCH/uchrom-nd/repo                             repo copy (rsync from the laptop)
#   $SCRATCH/uchrom-nd/data                             example data (stevens2017_mesc/, su2020_imr90/, 4DNFIFLJGGNR.csv)
#   $SCRATCH/uchrom-nd/sic/modeling                     Si-C HEAD 2a4d445 modeling/ directory
#   $SCRATCH/uchrom-nd/runs/screcon/{heldout,sim,real}  outputs
set -euo pipefail
ml purge
ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd
W=$SCRATCH/uchrom-nd
REPO=$W/repo
SC=$REPO/benchmarks/screcon
PY=$BASE/venv-main/bin/python
ORIG_PY=$BASE/venv-orig/bin/python
ND=$BASE/nd/master
HICKIT=$BASE/hickit-0.1.1_x64-linux/hickit
SIC=$W/sic/modeling
DATA=$W/data
GEO=$DATA/stevens2017_mesc
export UCHROM_EXAMPLE_DATA=$DATA
export PIP_CACHE_DIR=$SCRATCH/.cache/pip
H=$W/runs/screcon/heldout
S=$W/runs/screcon/sim
R=$W/runs/screcon/real
GSM=(x GSM2219497 GSM2219498 GSM2219499 GSM2219500 GSM2219501 GSM2219502 GSM2219503 GSM2219504)
FOLDS=${FOLDS:-3}

# array task 1..8*FOLDS -> CELL, FOLD, TAG, SPLIT, MD (model dir)
cell_fold() {
  local t=$1
  CELL=$(( (t - 1) / FOLDS + 1 )); FOLD=$(( (t - 1) % FOLDS + 1 ))
  TAG=cell${CELL}_fold${FOLD}
  SPLIT=$H/split/cell$CELL/fold$FOLD
  MD=$H/models/$TAG
  mkdir -p "$MD"
}

# manifest line N -> DATASET, NAME, TABLE, TRUTH, OUTM (model dir), RES (bp), SIC_RES_KB, ASM
sim_task() {
  local line
  line=$(sed -n "${1}p" "$S/manifest.tsv")
  IFS=$'\t' read -r DATASET NAME TABLE TRUTH <<< "$line"
  OUTM=$S/models/$DATASET/$NAME
  mkdir -p "$OUTM"
  case $DATASET in
    su2020_chr21)   RES=50000;   SIC_RES_KB=50;  ASM=hg38 ;;
    takei2021_1mb)  RES=1000000; SIC_RES_KB=250; ASM=mm10 ;;   # Si-C cannot run at 1 Mb (needs 2 x res < 2 Mb)
    takei2021_25kb) RES=25000;   SIC_RES_KB=25;  ASM=mm10 ;;
  esac
}

echo "host=$(hostname) job=${SLURM_JOB_ID:-} task=${SLURM_ARRAY_TASK_ID:-} cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2)"
