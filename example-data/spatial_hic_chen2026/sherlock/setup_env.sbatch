#!/bin/bash
#SBATCH --job-name=chen-setup
#SBATCH --partition=xiaojie
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
# One-off: conda env for mapping + pairs (in $GROUP_HOME); mm10 (UCSC, 0.9 GB: small enough for a job)
# main chromosomes, its bwa index and chrom sizes (on Oak).
set -euo pipefail
source "$HOME/uchrom_chen2026/common.sh"
source "$HOME/miniconda3/etc/profile.d/conda.sh"
export CONDA_PKGS_DIRS="$SCRATCH/conda_pkgs"
[ -x "$ENV/bin/pairtools" ] || mamba create -y -p "$ENV" -c conda-forge -c bioconda \
    python=3.11 bwa=0.7.17 samtools=1.20 "pairtools>=1.1" pigz "cooler>=0.10" pandas numpy
# (bwa without arguments exits 1, and head closes pipes early: these checks must not trip pipefail)
"$ENV/bin/pairtools" --version
{ "$ENV/bin/bwa" 2>&1 || true; } | grep Version
"$ENV/bin/samtools" --version | sed -n 1p
"$ENV/bin/pairtools" parse --help | grep -q readid-transform && echo "pairtools parse: --readid-transform ok"
"$ENV/bin/pairtools" dedup --help | grep -q extra-col-pair && echo "pairtools dedup: --extra-col-pair ok"
mkdir -p "$REF"; cd "$REF"
[ -s mm10.fa.gz ] || wget -q -c https://hgdownload.soe.ucsc.edu/goldenPath/mm10/bigZips/mm10.fa.gz
[ -s mm10.fa ] || zcat mm10.fa.gz | awk '/^>/{keep = ($1 ~ /^>chr([0-9]+|X|Y|M)$/)} keep' > mm10.fa
grep -c '^>' mm10.fa
[ -s mm10.fa.fai ] || "$ENV/bin/samtools" faidx mm10.fa
cut -f1,2 mm10.fa.fai > mm10.chrom.sizes
[ -s mm10.fa.bwt ] || "$ENV/bin/bwa" index mm10.fa
ls -la "$REF"
