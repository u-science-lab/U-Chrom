#!/bin/bash
# Genotype cue (PREREG §12.2), step 4 (array over the rows of split.tsv with role ROLE = dev / test):
# the authors' hickit pairs of the cell (GEO GSE117874 tarball) and its donor labels: the cell's BAM
# (geno_align.sbatch) -> hickit.js sam2seg -v donor_sites.vcf -> chronly -> hickit pairs (phase = donor)
# -> mix_geno.py label.  The BAM is deleted afterwards.
#   sbatch --array=1-12 --export=ALL,ROLE=dev,ENGINE=<tag> benchmarks/screcon/sherlock/geno_label.sbatch
#SBATCH --job-name=geno-label
#SBATCH --partition=xiaojie,normal
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo-mix/benchmarks/screcon/sherlock/_env_mix.sh"
ml biology samtools/1.16.1
: "${ROLE:?}"
GE=$MX/geno
HK=$BASE/hickit-0.1.1_x64-linux
rows=$(awk -F'\t' -v r="$ROLE" 'NR > 1 && $3 == r' "$GE/split.tsv")
row=$(echo "$rows" | sed -n "${SLURM_ARRAY_TASK_ID}p")
[ -n "$row" ] || { echo "no row"; exit 1; }
donor=$(echo "$row" | cut -f1); cell=$(echo "$row" | cut -f2); url=$(echo "$row" | cut -f10)
tag=$( [ "$donor" = GM12878 ] && printf "gm12878_%02d" "$cell" || printf "pbmc_%02d" "$cell" )
mkdir -p "$GE/tables" "$GE/labels"
cd "$GE/tables"
if [ ! -s "$tag.pairs.gz" ]; then
  curl -sSfL -o "$tag.tar.gz" "${url/ftp:\/\//https://}"
  tar xzf "$tag.tar.gz" "$tag.pairs.gz" && rm -f "$tag.tar.gz"
fi
if [ ! -s "$GE/labels/$tag.donor.pairs.gz" ]; then
  [ -s "$GE/bam/$tag.bam" ] || { echo "no BAM for $tag"; exit 1; }
  samtools view -h "$GE/bam/$tag.bam" | "$HK/k8" "$HK/hickit.js" sam2seg -v "$GE/donor_sites.vcf" - \
    | "$HK/k8" "$HK/hickit.js" chronly - | gzip > "$GE/labels/$tag.donor.seg.gz"
  "$HK/hickit" -i "$GE/labels/$tag.donor.seg.gz" -o - | gzip > "$GE/labels/$tag.donor.pairs.gz"
fi
$PY $SC/mix_geno.py label --table "$GE/tables/$tag.pairs.gz" --realigned "$GE/labels/$tag.donor.pairs.gz" \
  --out "$GE/labels/$tag.donor.npy" && rm -f "$GE/bam/$tag.bam" "$GE/labels/$tag.donor.seg.gz"
echo done
