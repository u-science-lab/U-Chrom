#!/bin/bash
#SBATCH --job-name=uchrom-cstats
#SBATCH --partition=xiaojie,normal
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
# Spatial Hi-C-RNA (GSE311199): per-spot contact statistics of one sample — cis contact-distance histograms
# (scHiCluster's bins, per chromosome and read orientation) and trans contacts per chromosome, for MAPQ >= 30
# and for all pairs (spatial_pairs_stats.py) — copied to Oak next to the sample's maps.
#   sbatch contact_stats.sbatch <sample> [max_lines]     (<sample>: a row of samples.tsv; max_lines > 0: a test)
# Reads the .pairs that process.sbatch downloaded to $SCRATCH (re-downloads from GEO if they are gone).
# Code: a repo copy synced from the laptop (tracked files + REVISION) at $REPO (default
# $SCRATCH/uchrom-nd/repo-sv); Python: the venv of uchrom-reproducibility/benchmarks/toolkit_parity/sc_structures/sherlock (numpy, pandas, uchrom deps).
# One pass over mouse_brain_r1 (129 GB, 5.1e9 pairs) took the earlier per-spot map build 3.5 h of reading.
set -euo pipefail
SAMPLE=$1
MAX_LINES=${2:-0}
ml purge
ml python/3.12.1
REPO=${REPO:-$SCRATCH/uchrom-nd/repo-sv}
HERE=$REPO/apps/atlas/recipes/spatial_hicrna/sherlock
PY=$GROUP_HOME/$USER/uchrom-nd/venv-sc/bin/python
PIGZ=$GROUP_HOME/$USER/envs/uchrom-hic/bin/pigz
export PYTHONPATH=$REPO/packages/uchrom:$REPO/packages/chromdata
export MPLBACKEND=Agg
read -r PAIRS ASM < <(awk -F'\t' -v s="$SAMPLE" '$1==s {print $2, $4}' "$HERE/samples.tsv")
[ -n "$PAIRS" ] || { echo "unknown sample $SAMPLE"; exit 2; }
GSM=${PAIRS%%_*}
RAW="$SCRATCH/uchrom_spatial/raw"
OUT="$SCRATCH/uchrom_spatial/out/$SAMPLE"
DEST="$OAK/uchrom/spatial_3dgenome/$SAMPLE"
mkdir -p "$RAW" "$OUT"
echo "[$(date)] $SAMPLE ($ASM) on $(hostname), job $SLURM_JOB_ID, code $(cat "$REPO/REVISION" 2>/dev/null || echo unknown)"
if [ ! -s "$RAW/$PAIRS" ]; then
  URL="https://ftp.ncbi.nlm.nih.gov/geo/samples/${GSM:0:7}nnn/$GSM/suppl/$PAIRS"
  echo "[$(date)] download $URL"
  wget -q -c -O "$RAW/$PAIRS.part" "$URL"
  mv "$RAW/$PAIRS.part" "$RAW/$PAIRS"
fi
TAG=$SAMPLE; [ "$MAX_LINES" -gt 0 ] && TAG="${SAMPLE}_test"
"$PIGZ" -dc -p 3 "$RAW/$PAIRS" | \
  "$PY" -u "$HERE/spatial_pairs_stats.py" --positions "$HERE/positions/$SAMPLE.csv" --out "$OUT/$TAG" \
      --max-lines "$MAX_LINES" || [ "${PIPESTATUS[1]}" -eq 0 ]      # pigz gets SIGPIPE when a test stops early
cp "$REPO/REVISION" "$OUT/$TAG.contact_stats.revision" 2>/dev/null || true
if [ "$MAX_LINES" -eq 0 ]; then
  mkdir -p "$DEST"
  rsync -a "$OUT"/"$TAG".contact_stats* "$DEST/"
  echo "[$(date)] done → $DEST"
  ls -la "$DEST"
fi
