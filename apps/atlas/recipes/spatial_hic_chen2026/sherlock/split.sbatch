#!/bin/bash
#SBATCH --job-name=chen-split
#SBATCH --partition=xiaojie
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=12
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
# Step 1 of a run: read-1 barcodes -> chunks of 60 M read pairs; then submits the mapping array (one task
# per chunk) and the finishing job after it.  Usage: [KEEP=1] sbatch split.sbatch <run> [max_pairs]
# (KEEP=1: the finishing job keeps the fastq and chunks, e.g. for the pilot)
set -euo pipefail
source "${SLURM_SUBMIT_DIR:-$HOME/uchrom_chen2026}/common.sh"   # jobs are submitted from the scripts folder
RUN=$1; MAX=${2:-0}
[ -e "$RAW/$RUN/OK" ] || { echo "fastq of $RUN not downloaded (fetch_dtn.sh)"; exit 2; }
OUT="$WORK/$RUN"; mkdir -p "$OUT"
echo "[$(date)] $RUN on $(hostname), job $SLURM_JOB_ID"
export PATH="$ENV/bin:$PATH"
python -u "$HERE/barcodes.py" "$RAW/$RUN/$(col $RUN r1)" "$RAW/$RUN/$(col $RUN r2)" "$OUT/chunks" \
    --chunk 60000000 --threads 4 --max-pairs "$MAX"
N=$(ls "$OUT"/chunks/chunk_*_R1.fq.gz | wc -l)
M=$(sbatch --parsable --array=0-$((N - 1))%6 "$HERE/map.sbatch" "$RUN")   # at most 6 chunks at once (shared partition)
F=$(sbatch --parsable --dependency=afterok:$M "$HERE/finish.sbatch" "$RUN")
echo "[$(date)] $N chunks; map array $M, finish $F"
