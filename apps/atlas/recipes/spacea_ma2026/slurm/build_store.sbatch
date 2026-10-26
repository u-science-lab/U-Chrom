#!/bin/bash
#SBATCH --job-name=spacea-store
#SBATCH --time=1-00:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=360G
#SBATCH --output=%x-%j.out
# The clusters of a section (clusters.sbatch) as a .chromdata.zarr store with ChromData.clusters per spot, then
# derive.py (filtered clusters, their maps, the spot embedding); copied to $DEST/<sample>/.  The fragments-per-spot
# grid (the tissue must show) is build_store.py --figure.  PY is a Python with chromdata >= format 2.4 and uchrom.
# Usage: sbatch build_store.sbatch <sample>
set -euo pipefail
source "$SLURM_SUBMIT_DIR/common.sh"
PY="${PY:?set PY: a Python with chromdata (format 2.4) and uchrom}"
export MPLBACKEND=Agg
SAMPLE=$1; RUNS=$(lib_runs "$(scol "$SAMPLE" library)" | paste -sd, -)
OUT="$WORK/$SAMPLE/spacea_${SAMPLE}.chromdata.zarr"; D="${SPACEA_OUT:-$DEST/$SAMPLE}"
"$PY" -u "$HERE/build_store.py" "$D/clusters_$SAMPLE.gz" "$OUT" --runs "${RUNS_USED:-$RUNS}" --sample "$SAMPLE" \
    --figure "$D/fragments_per_spot.png" | tee "$D/build_store.log"
"$PY" -u "$HERE/derive.py" "$OUT" --threads "${SLURM_CPUS_PER_TASK:-4}" | tee -a "$D/build_store.log"
du -sh "$OUT"
rm -rf "$D/$(basename "$OUT")" && cp -r "$OUT" "$D/"      # kept next to the clusters
cp "${OUT%.chromdata.zarr}"_1mb.scool "${OUT%.chromdata.zarr}"_pooled.mcool "$D/"
