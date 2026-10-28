#!/bin/bash
#SBATCH --job-name=spacea-clusters
#SBATCH --time=2-00:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --output=%x-%j.out
# One sample (a section) -> SPRITE clusters, from the aligned runs of its library (process.sbatch): the reads of its
# DPM tag (a library of two sections tells them apart by DPM, as the authors' split_dpm_from_full_BC_fq.py does
# before mapping), the runs merged, Picard MarkDuplicates (duplicates removed, over all runs of the section),
# MAPQ 255 (unique), get_clusters.py -n 6 -> $DEST/<sample>/clusters_<sample>.gz with stats.tsv.
# RUNS="<run> ..." restricts the runs (a test).  Usage: sbatch clusters.sbatch <sample>
set -euo pipefail
source "$SLURM_SUBMIT_DIR/common.sh"
source "${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"; conda activate "$ENV"
SAMPLE=$1; LIB=$(scol "$SAMPLE" library); DPM=$(scol "$SAMPLE" dpm)
PYS="$SRC/sprite-pipeline/scripts/python"; N=$SLURM_CPUS_PER_TASK
[ -n "$LIB" ] || { echo "$SAMPLE: not in samples.tsv"; exit 2; }
RUNS=(${RUNS:-$(lib_runs "$LIB")})
for RUN in "${RUNS[@]}"; do [ -e "$WORK/$RUN/OK" ] || { echo "$RUN: not aligned yet"; exit 2; }; done
OUT="${SPACEA_OUT:-$DEST/$SAMPLE}"
W="$WORK/clusters_$(basename "$OUT")"; mkdir -p "$W"; cd "$W"   # a test (SPACEA_OUT) works apart
stat() { echo -e "$1\t$2" | tee -a stats.tsv; }
: > stats.tsv; stat sample "$SAMPLE"; stat library "$LIB"; stat dpm "$DPM"; stat runs "${RUNS[*]}"
echo "[$(date)] reads of [$DPM], runs merged"
for RUN in "${RUNS[@]}"; do
  samtools view -@ "$N" -b -e "qname =~ \"[[]$DPM]\"" -o "$RUN.$DPM.bam" "$WORK/$RUN/$RUN.star.bam"   # "[<dpm>]" in the name
  stat "reads $RUN" "$(samtools view -@ "$N" -c "$RUN.$DPM.bam")"
done
samtools merge -f -@ "$N" -o merged.bam "${RUNS[@]/%/.$DPM.bam}"
rm -f "${RUNS[@]/%/.$DPM.bam}"
echo "[$(date)] dedup"
picard -Xmx100g MarkDuplicates MAX_FILE_HANDLES_FOR_READ_ENDS_MAP=1000 REMOVE_DUPLICATES=true \
    METRICS_FILE=rmdup.metrics.txt I=merged.bam O=rmdup.bam TMP_DIR="${TMPDIR:-/tmp}" > rmdup.log 2>&1
samtools view -@ "$N" -b -q 255 -o "$SAMPLE.unique.rmdup.bam" rmdup.bam
rm -f merged.bam rmdup.bam
stat unique_dedup_reads "$(samtools view -@ "$N" -c "$SAMPLE.unique.rmdup.bam")"
echo "[$(date)] clusters"
python "$PYS/get_clusters.py" -i "$SAMPLE.unique.rmdup.bam" -o "clusters_$SAMPLE" -n 6 > clusters.log
stat clusters "$(wc -l < "clusters_$SAMPLE")"
pigz -p "$N" -f "clusters_$SAMPLE"
mkdir -p "$OUT" && cp "clusters_$SAMPLE.gz" stats.tsv rmdup.metrics.txt "$OUT/"
echo "[$(date)] done: $OUT"; cat stats.tsv
