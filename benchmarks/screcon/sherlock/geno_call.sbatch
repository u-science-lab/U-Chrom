#!/bin/bash
# Genotype cue (PREREG §12.2), step 3: PBMC donor genotype from the 6 genotyping cells (pooled BAMs),
# and the donor-distinguishing sites (mix_geno.py sites) -> $MX/geno/donor_sites.vcf.
#   sbatch benchmarks/screcon/sherlock/geno_call.sbatch
#SBATCH --job-name=geno-call
#SBATCH --partition=xiaojie,normal
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=24
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-mix/benchmarks/screcon/sherlock/_env_mix.sh"
ml biology samtools/1.16.1 bcftools/1.16
GE=$MX/geno
REF=$DATA/geno_ref/hs37d5.fa
GIAB=$DATA/giab_hg001/HG001_GRCh37_GIAB_highconf_CG-IllFB-IllGATKHC-Ion-10X-SOLID_CHROM1-X_v.3.3.2_highconf_PGandRTGphasetransfer.vcf.gz
BED=$DATA/geno_ref/HG001_GRCh37_v3.3.2_highconf.bed
bams=$(awk -F'\t' 'NR > 1 && $3 == "genotype" {printf "%s/bam/pbmc_%02d.bam ", g, $2}' g="$GE" "$GE/split.tsv")
echo "$bams"
# (a) discovery calls, per chromosome in parallel, inside the GIAB high-confidence regions
mkdir -p "$GE/calls"
for c in $(seq 1 22) X; do
  [ -s "$GE/calls/calls_$c.vcf.gz" ] && continue
  ( awk -v c="$c" '$1 == c' "$BED" > "$GE/calls/bed_$c.bed"
    bcftools mpileup -f "$REF" -r "$c" -R "$GE/calls/bed_$c.bed" -a AD,DP -q 20 -Q 13 -d 500 $bams 2>/dev/null \
      | bcftools call -mv -Oz -o "$GE/calls/calls_$c.vcf.gz" 2>/dev/null ) &
  while [ $(jobs -r | wc -l) -ge 22 ]; do sleep 5; done
done
wait
# (b) PBMC read counts at the GIAB hom-alt SNVs
bcftools view -i 'GT="AA" && TYPE="snp"' "$GIAB" | bcftools query -f '%CHROM\t%POS\n' > "$GE/calls/gm_homalt.tsv"
for c in $(seq 1 22) X; do
  [ -s "$GE/calls/homalt_$c.vcf.gz" ] && continue
  ( awk -v c="$c" '$1 == c' "$GE/calls/gm_homalt.tsv" > "$GE/calls/homalt_sites_$c.tsv"
    bcftools mpileup -f "$REF" -r "$c" -T "$GE/calls/homalt_sites_$c.tsv" -a AD,DP -q 20 -Q 13 -d 500 $bams 2>/dev/null \
      | bcftools call -m -Oz -o "$GE/calls/homalt_$c.vcf.gz" 2>/dev/null ) &
  while [ $(jobs -r | wc -l) -ge 22 ]; do sleep 5; done
done
wait
# one sample per merged pileup: bcftools merges the BAMs as separate samples -> sum AD over samples
for kind in calls homalt; do
  bcftools concat -Oz -o "$GE/pbmc_$kind.vcf.gz" $(for c in $(seq 1 22) X; do echo "$GE/calls/${kind}_$c.vcf.gz"; done)
done
$PY $SC/mix_geno.py sites --giab-vcf "$GIAB" --giab-bed "$BED" --pbmc-calls "$GE/pbmc_calls.vcf.gz" \
  --pbmc-homref "$GE/pbmc_homalt.vcf.gz" --out "$GE/donor_sites.vcf"
echo done
