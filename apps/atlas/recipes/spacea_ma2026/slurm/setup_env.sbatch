#!/bin/bash
#SBATCH --job-name=spacea-setup
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out
# One-off: the conda env, the code of the pipeline at fixed commits, and the STAR index of mm10
# (UCSC main chromosomes, the chen2026 reference) with UCSC refGene splice junctions: the authors' index is
# splice-aware (--sjdbOverhang 149), from Ensembl mm10 (their reads are renamed to UCSC by ensembl2ucsc.py).
set -euo pipefail
source "$SLURM_SUBMIT_DIR/common.sh"
source "${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
[ -x "$ENV/bin/STAR" ] || mamba create -y -p "$ENV" -c conda-forge -c bioconda \
    python=3.11 star=2.7.10b "cutadapt>=4" samtools=1.20 picard=3.1.1 pysam pigz seqkit
conda activate "$ENV"
STAR --version; cutadapt --version; samtools --version | sed -n 1p; picard MarkDuplicates --version 2>&1 | tail -1 || true
mkdir -p "$SRC"; cd "$SRC"
[ -d SpaceA-Paper ] || git clone -q https://github.com/YuetongXU/SpaceA-Paper.git
[ -d sprite-pipeline ] || git clone -q https://github.com/GuttmanLab/sprite-pipeline.git
(cd SpaceA-Paper && git checkout -q "$SPACEA_COMMIT") && (cd sprite-pipeline && git checkout -q "$SPRITE_COMMIT")
cd "$REF"
[ -s mm10.refGene.gtf.gz ] || wget -q -c https://hgdownload.soe.ucsc.edu/goldenPath/mm10/bigZips/genes/mm10.refGene.gtf.gz
if [ ! -s "$STARIDX/SA" ]; then
  mkdir -p "$STARIDX"; T=${TMPDIR:-/tmp}/gtf; mkdir -p "$T"
  zcat mm10.refGene.gtf.gz | awk '$1 ~ /^chr([0-9]+|X|Y|M)$/' > "$T/mm10.refGene.gtf"
  STAR --runMode genomeGenerate --runThreadN "$SLURM_CPUS_PER_TASK" --genomeDir "$STARIDX" \
       --genomeFastaFiles "$REF/mm10.fa" --sjdbGTFfile "$T/mm10.refGene.gtf" --sjdbOverhang 149 \
       --outTmpDir "${TMPDIR:-/tmp}/star_tmp" > "$STARIDX/genomeGenerate.out"
fi
ls -la "$STARIDX"
