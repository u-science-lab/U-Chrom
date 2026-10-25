#!/bin/bash
#SBATCH --job-name=spacea-process
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --output=%x-%j.out
# One run, fastq -> SPRITE clusters, as the authors' Snakefile (1_Pre-processing/Snakefile, SpaceA-Paper):
#   cutadapt (their adapters, min length 50) -> parts -> BarcodeIdentification (their per-sample config) ->
#   full barcodes only (get_full_barcodes.py) -> read names reformed -> STAR (their parameters) ->
#   Picard MarkDuplicates (duplicates removed) -> MAPQ 255 (unique) -> get_clusters.py -n 6.
# Differences: STAR 2.7.10b takes two --limitIObufferSize values (input, output; the authors give one); one STAR run
# on all parts instead of one per part (same reads, same index parameters); the index is UCSC mm10 + refGene instead
# of Ensembl mm10 + ensembl2ucsc.py.  Counts of every step go to stats.tsv.
# Usage: sbatch process.sbatch <run>
set -euo pipefail
source "$SLURM_SUBMIT_DIR/common.sh"
source "${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"; conda activate "$ENV"
RUN=$1; SAMPLE=$(col "$RUN" sample); CFG="$SRC/SpaceA-Paper/1_Pre-processing/$(col "$RUN" config)"
JAR="$SRC/sprite-pipeline/scripts/java/BarcodeIdentification_v1.2.0.jar"; PYS="$SRC/sprite-pipeline/scripts/python"
N=$SLURM_CPUS_PER_TASK; P=${PARTS:-16}
[ -e "$RAW/$RUN/OK" ] || { echo "$RUN: fastq not downloaded"; exit 2; }
W="$WORK/$RUN"; mkdir -p "$W"; cd "$W"
stat() { echo -e "$1\t$2" | tee -a stats.tsv; }
: > stats.tsv; stat run "$RUN"; stat sample "$SAMPLE"; stat read_pairs "$(col "$RUN" read_pairs)"
echo "[$(date)] cutadapt"
[ -s clean_R1.fq.gz ] || cutadapt -a AAGTCGGAGGCCAAGCGGTCTTAGGAAGACAA -A AAGTCGGATCGTAGCCATGTCGTTCTGTGAGCCAAGGAGTTG \
    -j "$N" --minimum-length 50 -o clean_R1.fq.gz -p clean_R2.fq.gz \
    "$RAW/$RUN/$(col "$RUN" r1)" "$RAW/$RUN/$(col "$RUN" r2)" > cutadapt.qc.txt
stat after_cutadapt "$(grep -m1 'Pairs written' cutadapt.qc.txt | awk '{gsub(",","",$5); print $5}')"
echo "[$(date)] split"
[ -d parts ] || seqkit split2 -1 clean_R1.fq.gz -2 clean_R2.fq.gz --by-part "$P" -j "$N" -O parts -e .gz 2> split.log
mkdir -p bc
echo "[$(date)] barcodes"
ls parts/clean_R1.part_*.fq.gz | sed 's/.*part_\([0-9]*\).fq.gz/\1/' | \
  xargs -P "$((N / 2))" -I{} bash -c '[ -s bc/p{}_R1.barcoded_full.fastq.gz ] && exit 0
    java -Xmx4g -jar "'"$JAR"'" --input1 parts/clean_R1.part_{}.fq.gz --input2 parts/clean_R2.part_{}.fq.gz \
      --output1 bc/p{}_R1.barcoded.fastq.gz --output2 bc/p{}_R2.barcoded.fastq.gz --config "'"$CFG"'" > bc/p{}.bid.log 2>&1
    python "'"$PYS"'/get_full_barcodes.py" --r1 bc/p{}_R1.barcoded.fastq.gz > bc/p{}.full.log 2>&1'
stat full_barcode "$(cat bc/p*.full.log | awk '/Full reads out/{s+=$NF} END{print s}')"
stat short_barcode "$(cat bc/p*.full.log | awk '/without full barcode/{s+=$NF} END{print s}')"
echo "[$(date)] reform"
[ -s R1.full.fq.gz ] || for f in bc/p*_R1.barcoded_full.fastq.gz; do
  zcat "$f" | awk '{ if (NR % 4 == 1) { sub(/\/[1-2]/, "") } print }'; done | pigz -p "$N" > R1.full.fq.gz
echo "[$(date)] STAR"
mkdir -p star
[ -s star/Aligned.sortedByCoord.out.bam ] || STAR --outReadsUnmapped None --sjdbOverhang 149 --genomeDir "$STARIDX" \
    --readFilesIn R1.full.fq.gz --readFilesCommand zcat --runThreadN "$N" --outFileNamePrefix star/ \
    --outSAMtype BAM SortedByCoordinate --outSAMattributes All --limitOutSJcollapsed 1000000 \
    --limitIObufferSize 150000000 150000000 --limitBAMsortRAM 60000000000 --outTmpDir "${TMPDIR:-/tmp}/star_$RUN"
grep -E "Number of input reads|Uniquely mapped reads number|Number of reads mapped to multiple loci" star/Log.final.out | \
  sed 's/ *|\t/\t/; s/^ *//' | while IFS=$'\t' read k v; do stat "star: $k" "$v"; done
echo "[$(date)] dedup"
[ -s rmdup.bam ] || picard MarkDuplicates MAX_FILE_HANDLES_FOR_READ_ENDS_MAP=1000 REMOVE_DUPLICATES=true \
    METRICS_FILE=rmdup.metrics.txt I=star/Aligned.sortedByCoord.out.bam O=rmdup.bam TMP_DIR="${TMPDIR:-/tmp}" \
    > rmdup.log 2>&1
samtools view -@ 8 -b -q 255 -o "$RUN.unique.rmdup.bam" rmdup.bam
stat unique_dedup_reads "$(samtools view -@ 8 -c "$RUN.unique.rmdup.bam")"
echo "[$(date)] clusters"
python "$PYS/get_clusters.py" -i "$RUN.unique.rmdup.bam" -o "clusters_$RUN" -n 6 > clusters.log
stat clusters "$(wc -l < "clusters_$RUN")"
pigz -p "$N" -f "clusters_$RUN"
mkdir -p "$DEST/$RUN" && cp "clusters_$RUN.gz" stats.tsv cutadapt.qc.txt rmdup.metrics.txt star/Log.final.out "$DEST/$RUN/"
echo "[$(date)] done: $DEST/$RUN"; cat stats.tsv
