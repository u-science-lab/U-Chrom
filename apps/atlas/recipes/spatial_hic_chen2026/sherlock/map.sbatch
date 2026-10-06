#!/bin/bash
#SBATCH --job-name=chen-map
#SBATCH --partition=xiaojie
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --output=%x-%A_%a.out
# Step 2 (array task = chunk): bwa mem (Hi-C mode) | pairtools parse (readID -> the barcode pair) | sort.
set -euo pipefail
source "${SLURM_SUBMIT_DIR:-$HOME/uchrom_chen2026}/common.sh"   # jobs are submitted from the scripts folder
RUN=$1; K=$(printf %03d "$SLURM_ARRAY_TASK_ID")
C="$WORK/$RUN/chunks"; P="$WORK/$RUN/pairs"; mkdir -p "$P"
export PATH="$ENV/bin:$PATH"
echo "[$(date)] $RUN chunk $K on $(hostname)"
bwa mem -5SP -T0 -t "$SLURM_CPUS_PER_TASK" "$REF/mm10.fa" "$C/chunk_${K}_R1.fq.gz" "$C/chunk_${K}_R2.fq.gz" 2> "$P/chunk_$K.bwa.log" | \
  pairtools parse --min-mapq 30 --walks-policy 5unique --max-inter-align-gap 30 --add-columns mapq \
      --readid-transform "$READID_TRANSFORM" --drop-sam --drop-seq --chroms-path "$REF/mm10.chrom.sizes" \
      --output-stats "$P/chunk_$K.parse.stats" --nproc-in 4 --nproc-out 4 | \
  pairtools sort --nproc 8 --memory 24G --tmpdir "$P" -o "$P/chunk_$K.pairs.gz"
echo "[$(date)] done"; ls -la "$P/chunk_$K.pairs.gz"
