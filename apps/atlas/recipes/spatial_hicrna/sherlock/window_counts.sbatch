#!/bin/bash
#SBATCH --job-name=uchrom-wcounts
#SBATCH --partition=xiaojie,normal
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
# Spatial Hi-C-RNA (GSE311199): per-spot contacts in the windows of the pooled-map boundaries and loops of one
# sample (spatial_pairs_windows.py), copied to Oak next to the sample's maps.
#   sbatch window_counts.sbatch <sample> <windows.parquet> [max_lines]
# windows.parquet: uchrom-reproducibility/benchmarks/spatial_variable/bulk_calls.py.  Code and Python as contact_stats.sbatch.
set -euo pipefail
SAMPLE=$1
WINDOWS=$2
MAX_LINES=${3:-0}
ml purge
ml python/3.12.1
REPO=${REPO:-$SCRATCH/uchrom-nd/repo-sv}
HERE=$REPO/apps/atlas/recipes/spatial_hicrna/sherlock
PY=$GROUP_HOME/$USER/uchrom-nd/venv-sc/bin/python
PIGZ=$GROUP_HOME/$USER/envs/uchrom-hic/bin/pigz
export PYTHONPATH=$HERE:$REPO/packages/uchrom:$REPO/packages/chromdata
read -r PAIRS ASM < <(awk -F'\t' -v s="$SAMPLE" '$1==s {print $2, $4}' "$HERE/samples.tsv")
[ -n "$PAIRS" ] || { echo "unknown sample $SAMPLE"; exit 2; }
RAW="$SCRATCH/uchrom_spatial/raw"
OUT="$SCRATCH/uchrom_spatial/out/$SAMPLE"
DEST="$OAK/uchrom/spatial_3dgenome/$SAMPLE"
mkdir -p "$OUT"
echo "[$(date)] $SAMPLE ($ASM) on $(hostname), job $SLURM_JOB_ID, code $(cat "$REPO/REVISION" 2>/dev/null || echo unknown)"
[ -s "$RAW/$PAIRS" ] || { echo "missing $RAW/$PAIRS (run contact_stats.sbatch first: it downloads)"; exit 3; }
TAG=$SAMPLE; [ "$MAX_LINES" -gt 0 ] && TAG="${SAMPLE}_test"
cp "$WINDOWS" "$OUT/$TAG.windows.parquet"
"$PIGZ" -dc -p 3 "$RAW/$PAIRS" | \
  "$PY" -u "$HERE/spatial_pairs_windows.py" --positions "$HERE/positions/$SAMPLE.csv" --windows "$OUT/$TAG.windows.parquet" \
      --out "$OUT/$TAG" --max-lines "$MAX_LINES" || [ "${PIPESTATUS[1]}" -eq 0 ]
if [ "$MAX_LINES" -eq 0 ]; then
  mkdir -p "$DEST"
  rsync -a "$OUT/$TAG".window_counts* "$OUT/$TAG.windows.parquet" "$DEST/"
  echo "[$(date)] done → $DEST"
fi
