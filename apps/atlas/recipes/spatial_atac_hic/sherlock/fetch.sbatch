#!/bin/bash -l
#SBATCH --job-name=atachic-fetch
#SBATCH --partition=xiaojie
#SBATCH --time=2-00:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
# SRA runs of a section -> $SCRATCH/atachic/raw/<section>/<run>_1/2.fastq.gz (prefetch + vdb-validate +
# fasterq-dump + pigz); <section>/OK when all runs are done.  Usage: sbatch fetch.sbatch <section>
set -euo pipefail
source "${SLURM_SUBMIT_DIR:-$HOME/uchrom_atachic}/common.sh"
ml biology sra-tools/3.0.7
SEC=$1; D="$RAW/$SEC"; mkdir -p "$D"; cd "$D"
[ -e OK ] && { echo "$SEC already done"; exit 0; }
for RUN in $(col "$SEC" runs | tr , ' '); do
  [ -s "${RUN}_2.fastq.gz" ] && [ -e "$RUN.done" ] && continue
  echo "[$(date)] $SEC $RUN prefetch"
  prefetch --max-size 200G -O "$D" "$RUN"
  vdb-validate "$D/$RUN"
  echo "[$(date)] fasterq-dump"
  fasterq-dump --split-files -e "$SLURM_CPUS_PER_TASK" -t "$D/tmp" -O "$D" "$D/$RUN"
  "$ENV/bin/pigz" -p "$SLURM_CPUS_PER_TASK" "${RUN}_1.fastq" "${RUN}_2.fastq"
  rm -rf "$D/$RUN" "$D/tmp"; touch "$RUN.done"
  ls -la "$D"
done
touch OK; echo "[$(date)] $SEC done"
