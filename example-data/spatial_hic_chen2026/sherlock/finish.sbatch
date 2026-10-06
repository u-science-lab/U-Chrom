#!/bin/bash
#SBATCH --job-name=chen-finish
#SBATCH --partition=xiaojie
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --output=%x-%j.out
# Step 3: merge the chunks, deduplicate within each spot (same barcode pair), per-barcode-pair .scool + bulk .mcool,
# copy the results to Oak, then remove the run's fastq and chunks from $SCRATCH.
set -euo pipefail
source "${SLURM_SUBMIT_DIR:-$HOME/uchrom_chen2026}/common.sh"   # jobs are submitted from the scripts folder
RUN=$1; P="$WORK/$RUN/pairs"; O="$DEST/$RUN"; mkdir -p "$O"
export PATH="$ENV/bin:$PATH"
echo "[$(date)] $RUN on $(hostname)"
# pairtools dedup (1-bp tolerance, per barcode pair) needed >1 day for 4e8 pairs; pairs_to_cool.py removes
# exact duplicates within each barcode pair while it reads the position-sorted merge instead
pairtools merge --nproc 8 --memory 48G --tmpdir "$P" "$P"/chunk_*.pairs.gz | \
  python -u "$HERE/pairs_to_cool.py" $(whitelist_args "$RUN") --out "$O/$RUN" \
      --dedup-out "$O/$RUN.dedup.pairs.gz"
cat "$P"/chunk_*.parse.stats > "$O/$RUN.parse.stats.all"
cp "$WORK/$RUN/chunks/barcodes_stats.json" "$O/$RUN.barcodes_stats.json"
echo "[$(date)] results"; ls -la "$O"
if [ -z "${KEEP:-}" ]; then rm -rf "$WORK/$RUN" "$RAW/$RUN"; fi   # fastq stay on GSA; results are on Oak (KEEP=1: keep them)
echo "[$(date)] done"
