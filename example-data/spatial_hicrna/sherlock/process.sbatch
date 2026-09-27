#!/bin/bash
#SBATCH --job-name=uchrom-pairs
#SBATCH --partition=normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out
# Spatial Hi-C-RNA (GSE311199): download one sample's .pairs to $SCRATCH, build per-spot .scool +
# pseudo-bulk .mcool, copy the results to Oak.  Usage: sbatch process.sbatch <sample> [max_lines]
#   <sample> is a row of samples.tsv; max_lines > 0 processes only the first pairs (tests).
set -euo pipefail
SAMPLE=$1
MAX_LINES=${2:-0}
HERE="$HOME/uchrom_spatial"
ENV="$GROUP_HOME/$USER/envs/uchrom-hic"
read -r PAIRS ASM < <(awk -F'\t' -v s="$SAMPLE" '$1==s {print $2, $4}' "$HERE/samples.tsv")
[ -n "$PAIRS" ] || { echo "unknown sample $SAMPLE"; exit 2; }
GSM=${PAIRS%%_*}
URL="https://ftp.ncbi.nlm.nih.gov/geo/samples/${GSM:0:7}nnn/$GSM/suppl/$PAIRS"
RAW="$SCRATCH/uchrom_spatial/raw"
OUT="$SCRATCH/uchrom_spatial/out/$SAMPLE"
DEST="$OAK/uchrom/spatial_3dgenome/$SAMPLE"
mkdir -p "$RAW" "$OUT"
echo "[$(date)] $SAMPLE ($ASM) on $(hostname), job $SLURM_JOB_ID"
if [ ! -s "$RAW/$PAIRS" ]; then
  echo "[$(date)] download $URL"
  wget -q -c -O "$RAW/$PAIRS.part" "$URL"
  mv "$RAW/$PAIRS.part" "$RAW/$PAIRS"
fi
ls -l "$RAW/$PAIRS"
TAG=$SAMPLE; [ "$MAX_LINES" -gt 0 ] && TAG="${SAMPLE}_test"
"$ENV/bin/pigz" -dc -p 4 "$RAW/$PAIRS" | \
  "$ENV/bin/python" -u "$HERE/spatial_pairs_to_cool.py" --positions "$HERE/positions/$SAMPLE.csv" \
      --out "$OUT/$TAG" --spot-res 1000000 --bulk-res 25000 --max-lines "$MAX_LINES" || \
  [ "${PIPESTATUS[1]}" -eq 0 ]            # pigz gets SIGPIPE when a test stops early
mkdir -p "$DEST"
rsync -a "$OUT/" "$DEST/"
echo "[$(date)] done → $DEST"
ls -la "$DEST"
