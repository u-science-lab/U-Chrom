#!/bin/bash
# Uni-C GM12878 pilot cells 1-3 (GSE267873, GSM8280638-GSM8280640; cells 1-2 may already be present) and the
# GIAB HG001 pedigree-phased VCFs (GRCh37, GRCh38; md5-checked), then the phased het SNVs of each build
# (unic_qc.py hets -> $GIAB/hets_<build>.npz).
#
#   sbatch benchmarks/screcon/sherlock/unic_download.sbatch
#SBATCH --job-name=unic-dl
#SBATCH --partition=xiaojie,normal
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-unic/benchmarks/screcon/sherlock/_env_unic.sh"
for ds in giab_hg001 unic2025_gm12878; do
  for try in 1 2 3; do
    if $PY $REPO/example-data/download_data.py --$ds --dest "$DATA"; then break; fi
    echo "download $ds attempt $try failed"; sleep 120
  done
done
for b in GRCh37 GRCh38; do
  [ -f "$GIAB/hets_$b.npz" ] || $PY $SC/unic_qc.py hets --strip-chr --out "$GIAB/hets_$b.npz" \
    --vcf "$(ls "$GIAB"/HG001_${b}_GIAB_highconf_*_PGandRTGphasetransfer.vcf.gz)"
done
md5sum "$UNIC"/GSM828063[89]_*.pairs.gz "$UNIC"/GSM8280640_*.pairs.gz "$GIAB"/*.vcf.gz
ls -la "$UNIC" "$GIAB"
