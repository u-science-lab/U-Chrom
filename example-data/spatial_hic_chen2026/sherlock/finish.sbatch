#!/bin/bash
#SBATCH --job-name=chen-finish
#SBATCH --partition=xiaojie
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --output=%x-%j.out
# Step 3: merge the chunks, deduplicate within each spot (same barcode pair), per-spot .scool + bulk .mcool,
# copy the results to Oak, then remove the run's fastq and chunks from $SCRATCH.
set -euo pipefail
source "$HOME/uchrom_chen2026/common.sh"
RUN=$1; P="$WORK/$RUN/pairs"; O="$DEST/$RUN"; mkdir -p "$O"
export PATH="$ENV/bin:$PATH"
echo "[$(date)] $RUN on $(hostname)"
pairtools merge --nproc 8 --memory 48G --tmpdir "$P" "$P"/chunk_*.pairs.gz | \
  pairtools dedup --max-mismatch 1 --extra-col-pair readID readID --mark-dups --output-stats "$O/$RUN.dedup.stats" \
      --output "$O/$RUN.dedup.pairs.gz" --output-dups /dev/null --nproc-in 4 --nproc-out 4
pigz -dc -p 4 "$O/$RUN.dedup.pairs.gz" | \
  python -u "$HERE/pairs_to_cool.py" --grid "$(col $RUN grid)" --barcodes "$HERE" --out "$O/$RUN"
cat "$P"/chunk_*.parse.stats > "$O/$RUN.parse.stats.all"
cp "$WORK/$RUN/chunks/barcodes_stats.json" "$O/$RUN.barcodes_stats.json"
echo "[$(date)] results"; ls -la "$O"
if [ -z "${KEEP:-}" ]; then rm -rf "$WORK/$RUN" "$RAW/$RUN"; fi   # fastq stay on GSA; results are on Oak (KEEP=1: keep them)
echo "[$(date)] done"
