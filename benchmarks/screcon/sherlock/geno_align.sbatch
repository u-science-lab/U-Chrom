#!/bin/bash
# Genotype cue (PREREG §12.2), step 2 (array over the rows of split.tsv with role ROLE): SRA reads ->
# bwa mem -5SP (hs37d5).  ROLE=genotype: the first 7.5 M spots of every run, coordinate-sorted BAM
# (PBMC genotype); ROLE=dev / test: all reads, unsorted BAM (re-labelled later by geno_label.sbatch,
# then deleted).  The .sra files are deleted after use.
#   sbatch --array=1-6 --export=ALL,ROLE=genotype benchmarks/screcon/sherlock/geno_align.sbatch
#SBATCH --job-name=geno-align
#SBATCH --partition=xiaojie,normal
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo-mix/benchmarks/screcon/sherlock/_env_mix.sh"
ml biology bwa/0.7.17 samtools/1.16.1 sra-tools/3.0.7
: "${ROLE:?}"
GE=$MX/geno
REF=$DATA/geno_ref/hs37d5.fa
row=$(awk -F'\t' -v r="$ROLE" 'NR > 1 && $3 == r' "$GE/split.tsv" | sed -n "${SLURM_ARRAY_TASK_ID}p")
[ -n "$row" ] || { echo "no row ${SLURM_ARRAY_TASK_ID} for role $ROLE"; exit 1; }
donor=$(echo "$row" | cut -f1); cell=$(echo "$row" | cut -f2); srr=$(echo "$row" | cut -f7)
tag=$( [ "$donor" = GM12878 ] && printf "gm12878_%02d" "$cell" || printf "pbmc_%02d" "$cell" )
out=$GE/bam/$tag.bam
mkdir -p "$GE/bam" "$GE/sra/$tag"
[ -s "$out" ] && { echo "$out exists"; exit 0; }
echo "$tag $srr role=$ROLE"
cd "$GE/sra/$tag"
for r in ${srr//,/ }; do
  [ -s "$r/$r.sra" ] || [ -s "$r/$r.sralite" ] || prefetch --max-size 100G -O . "$r"
done
dump() {
  for r in ${srr//,/ }; do
    f=$(ls "$r"/"$r".sra* | head -1)
    if [ "$ROLE" = genotype ]; then fastq-dump -X 7500000 --split-spot --stdout "$f"; else fastq-dump --split-spot --stdout "$f"; fi
  done
}
if [ "$ROLE" = genotype ]; then
  dump | bwa mem -5SP -p -t 30 "$REF" - 2> "$GE/bam/$tag.bwa.log" | samtools sort -@ 4 -m 2G -o "$out.tmp" - && mv "$out.tmp" "$out"
  samtools index "$out"
else
  dump | bwa mem -5SP -p -t 30 "$REF" - 2> "$GE/bam/$tag.bwa.log" | samtools view -@ 2 -b -o "$out.tmp" - && mv "$out.tmp" "$out"
fi
rm -rf "$GE/sra/$tag"
ls -la "$out"
echo done
