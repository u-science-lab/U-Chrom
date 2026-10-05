#!/bin/bash
# Genotype cue (PREREG §12.2), step 1: references.  hs37d5 (1000 Genomes GRCh37 decoy, the contig names
# of the Tan 2018 hickit pairs) + bwa index + faidx; GIAB HG001 v3.3.2 GRCh37 high-confidence regions.
# The GIAB VCF is $DATA/giab_hg001 (staged earlier).
#   sbatch benchmarks/screcon/sherlock/geno_ref.sbatch
#SBATCH --job-name=geno-ref
#SBATCH --partition=xiaojie,normal
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-mix/benchmarks/screcon/sherlock/_env_mix.sh"
ml biology bwa/0.7.17 samtools/1.16.1
G=$DATA/geno_ref
mkdir -p "$G"
cd "$G"
[ -f hs37d5.fa ] || { curl -sSfL -o hs37d5.fa.gz https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/technical/reference/phase2_reference_assembly_sequence/hs37d5.fa.gz && gunzip hs37d5.fa.gz; }
[ -f hs37d5.fa.fai ] || samtools faidx hs37d5.fa
[ -f hs37d5.fa.bwt ] || bwa index hs37d5.fa
B=https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/NA12878_HG001/NISTv3.3.2/GRCh37
[ -f HG001_GRCh37_v3.3.2_highconf.bed ] || curl -sSfL -o HG001_GRCh37_v3.3.2_highconf.bed \
  "$B/HG001_GRCh37_GIAB_highconf_CG-IllFB-IllGATKHC-Ion-10X-SOLID_CHROM1-X_v.3.3.2_highconf_nosomaticdel.bed"
ls -la "$G"
echo done
