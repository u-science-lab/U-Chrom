#!/bin/bash
#SBATCH --job-name=atachic-split
#SBATCH --partition=xiaojie
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=12
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
# Step 1 of a section: spot barcodes of both SRA runs (read 2) -> chunks of 60 M read pairs; then submits
# the mapping array and the finishing job (shared with Chen 2026).  Usage: [KEEP=1] sbatch split.sbatch <section>
set -euo pipefail
source "${SLURM_SUBMIT_DIR:-$HOME/uchrom_atachic}/common.sh"
SEC=$1; MAX=${2:-0}
[ -e "$RAW/$SEC/OK" ] || { echo "fastq of $SEC not downloaded (fetch.sbatch)"; exit 2; }
OUT="$WORK/$SEC"; mkdir -p "$OUT"
echo "[$(date)] $SEC on $(hostname), job $SLURM_JOB_ID"
export PATH="$ENV/bin:$PATH"
set -- $(for r in $(col "$SEC" runs | tr , ' '); do echo "$RAW/$SEC/${r}_1.fastq.gz $RAW/$SEC/${r}_2.fastq.gz"; done)
R1=$1; R2=$2; shift 2
python -u "$HERE/barcodes.py" "$R1" "$R2" "$OUT/chunks" --layout atachic --more "$@" --chunk 60000000 --threads 4 --max-pairs "$MAX"
N=$(ls "$OUT"/chunks/chunk_*_R1.fq.gz | wc -l)
M=$(sbatch --parsable --array=0-$((N - 1)) "$HERE/map.sbatch" "$SEC")
F=$(sbatch --parsable --dependency=afterok:$M "$HERE/finish.sbatch" "$SEC")
echo "[$(date)] $N chunks; map array $M, finish $F"
