#!/bin/bash
# Archive the large outputs of a benchmark run from $SCRATCH (purged after 90 days) to Oak, one tar per part
# (Oak counts files: bundle them), with a manifest.  The headline numbers are committed in
# benchmarks/<name>/results/; this keeps what they were computed from (call tables, maps, models, logs).
#
#   sbatch --export=ALL,RUN=sc,DEST=sc_structures/2026-10-08_ad141a7 benchmarks/sc_structures/sherlock/archive.sbatch
#SBATCH --job-name=archive
#SBATCH --partition=xiaojie,normal
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --output=%x-%j.out
set -euo pipefail
SRC=$SCRATCH/uchrom-nd/runs/${RUN:?}
OUT=$OAK/uchrom/results/${DEST:?}
mkdir -p "$OUT" "$OAK/uchrom/results/hic_structures"
cd "$SRC"
for part in */; do
  part=${part%/}
  # SnapHiC's own run (the reference implementation): its final loops and log, not its 19 GB of per-cell files
  tar -cf "$OUT/$part.tar" --exclude="reference/*/input" --exclude="reference/*/snaphic_out/binned" \
      --exclude="reference/*/snaphic_out/hic" --exclude="reference/*/snaphic_out/interactions" \
      --exclude="reference/*/snaphic_out/rwr" "$part"
done
{
  echo "# $DEST — archived $(date -u +%FT%TZ) from \$SCRATCH/uchrom-nd/runs/$RUN (job $SLURM_JOB_ID)"
  echo "# headline numbers: benchmarks/$(dirname "$DEST")/results/ in the U-Chrom repository"
  for t in "$OUT"/*.tar; do echo "$(basename "$t")  $(du -h "$t" | cut -f1)  $(tar -tf "$t" | wc -l) files"; done
} > "$OUT/MANIFEST.txt"
cat "$OUT/MANIFEST.txt"
