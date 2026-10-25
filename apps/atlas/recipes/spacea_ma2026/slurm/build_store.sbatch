#!/bin/bash
#SBATCH --job-name=spacea-store
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=128G
#SBATCH --output=%x-%j.out
# The clusters of a run (process.sbatch) as a .chromdata.zarr store with ChromData.clusters per spot, copied to
# $DEST/<run>/.  The fragments-per-spot grid (the tissue must show) is build_store.py --figure, where matplotlib is
# installed.  PY is a Python with chromdata >= format 2.4 (ChromData.clusters).  Usage: sbatch build_store.sbatch <run>
set -euo pipefail
source "$SLURM_SUBMIT_DIR/common.sh"
PY="${PY:?set PY: a Python with chromdata (format 2.4)}"
export MPLBACKEND=Agg
RUN=$1; SAMPLE=$(col "$RUN" sample)
OUT="$WORK/$RUN/spacea_${SAMPLE}_${RUN}.chromdata.zarr"
"$PY" -u "$HERE/build_store.py" "$DEST/$RUN/clusters_$RUN.gz" "$OUT" --run "$RUN" --sample "$SAMPLE" \
    | tee "$DEST/$RUN/build_store.log"
du -sh "$OUT"
rm -rf "$DEST/$RUN/$(basename "$OUT")" && cp -r "$OUT" "$DEST/$RUN/"      # kept next to the clusters
