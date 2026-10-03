#!/bin/bash
# Downloads for the matched-modality comparison (benchmarks/screcon/matched.py), catalogued in
# example-data/README.md ("matched imaging" section).  Idempotent: existing complete files are kept.
#
#   PART=mesc   Nagano 2017 haploid contacts (schic2 S3; 2i 502 MB + serum ~0.84 GB), the mm9 GATC
#               fend table streamed out of schic2_mm9_db.tar.gz (5.0 GB read, ~0.1 GB kept), the UCSC
#               mm9ToMm10 chain, GEO feature table; Takei 2021 Nature DNAseqFISH+.zip (Zenodo 3735329)
#   PART=brain  Takei 2021 Science tables S5 / S7 / S8 / S10 (Zenodo 4708112, ~0.6 GB); Tan 2021 Dip-C
#               adult cortex cells (P56 / P309 / P347, >= 100 k contacts; 510 cells): per GSM
#               contacts.pairs, impute.pairs and the five 20k.*.clean.3dg (~15 GB) - never GSE146397_RAW.tar
#
#   sbatch --export=ALL,PART=mesc benchmarks/screcon/sherlock/download_matched.sbatch
#   sbatch --export=ALL,PART=brain --time=08:00:00 benchmarks/screcon/sherlock/download_matched.sbatch
#SBATCH --job-name=sc-dl-matched
#SBATCH --partition=xiaojie,normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --output=%x-%j.out
set -uo pipefail
W=$SCRATCH/uchrom-nd
DATA=$W/data
REPO=${REPO:-$W/repo-matched}
get() {  # get URL DEST: resume-safe download (skip when the size matches the server's)
  local url=$1 dest=$2 n
  n=$(curl -sIL "$url" | tr -d '\r' | awk 'tolower($1)=="content-length:"{v=$2} END{print v}')
  if [ -s "$dest" ] && [ -n "$n" ] && [ "$(stat -c %s "$dest")" = "$n" ]; then return 0; fi
  mkdir -p "$(dirname "$dest")"
  curl -sSL --retry 5 --retry-delay 10 -C - -o "$dest" "$url" || curl -sSL --retry 5 -o "$dest" "$url"
}
case ${PART:?} in
  mesc)
    N=$DATA/nagano2017_hap
    mkdir -p "$N"
    S3=https://schic2.s3.eu-west-1.amazonaws.com
    get $S3/schic_hap_serum_adj_files.tar.gz "$N/schic_hap_serum_adj_files.tar.gz"
    get $S3/schic_hap_2i_adj_files.tar.gz "$N/schic_hap_2i_adj_files.tar.gz"
    G=https://ftp.ncbi.nlm.nih.gov/geo/series/GSE94nnn/GSE94489/suppl
    get $G/GSE94489_haploids_features_table.txt.gz "$N/GSE94489_haploids_features_table.txt.gz"
    get $G/GSE94489_README.txt "$N/GSE94489_README.txt"
    get https://hgdownload.soe.ucsc.edu/goldenPath/mm9/liftOver/mm9ToMm10.over.chain.gz "$N/mm9ToMm10.over.chain.gz"
    if [ ! -s "$N/GATC.fends" ]; then          # stream the 5 GB db archive, keep only the fend table
      curl -sSL --retry 5 $S3/schic2_mm9_db.tar.gz | tar -xzf - -C "$N" --wildcards '*seq/redb/GATC.fends' \
        && find "$N" -name GATC.fends -path '*seq/redb*' -exec mv {} "$N/GATC.fends" \;
    fi
    for t in serum 2i; do
      [ -d "$N/adj_$t" ] || { mkdir -p "$N/adj_$t" && tar -xzf "$N/schic_hap_${t}_adj_files.tar.gz" -C "$N/adj_$t"; }
    done
    get "https://zenodo.org/records/3735329/files/DNAseqFISH%2B.zip?download=1" "$DATA/DNAseqFISH+.zip"
    ls -la "$N" "$DATA/DNAseqFISH+.zip"; ls "$N/adj_serum" | wc -l; ls "$N/adj_2i" | wc -l
    ;;
  brain)
    T=$DATA/takei2021_brain
    Z=https://zenodo.org/records/4708112/files
    for f in TableS5_brain_RNA_profiles_2762cells.csv TableS7_brain_DNAseqFISH_1Mb_voxel_coordinates_2762cells.csv \
             TableS8_brain_DNAseqFISH_25kb_voxel_coordinates_2762cells.csv \
             TableS10-median-radial-score-per-celltype-1Mb-resolution.csv; do
      get "$Z/$f?download=1" "$T/$f"
    done
    D=$DATA/tan2021_cortex
    G=https://ftp.ncbi.nlm.nih.gov/geo/series/GSE146nnn/GSE146397/suppl
    for f in GSE146397_00README.md.txt GSE146397_metadata.cells_contacts_100k.txt.gz \
             GSE146397_metadata.cells_contacts_100k_rmsd_1.5.txt.gz GSE146397_metadata.excluded_samples.txt.gz; do
      get "$G/$f" "$D/meta/$f"
    done
    dl_cell() {
      local gsm=$1 name=$2 suf base=https://ftp.ncbi.nlm.nih.gov/geo/samples/${1:0:7}nnn/$1/suppl/${1}_$2
      for suf in contacts.pairs impute.pairs 20k.1.clean.3dg 20k.2.clean.3dg 20k.3.clean.3dg 20k.4.clean.3dg 20k.5.clean.3dg; do
        get "$base.$suf.txt.gz" "$D/cells/$name/$name.$suf.txt.gz" || echo "FAILED $name $suf"
      done
    }
    k=0
    while IFS=$'\t' read -r gsm name age cross ctype; do
      dl_cell "$gsm" "$name" &
      k=$((k + 1))
      if [ $((k % 6)) -eq 0 ]; then wait; fi          # 6 cells at a time (bash 4.2: no wait -n)
    done < <(tail -n +2 "$REPO/benchmarks/screcon/data/tan2021_adult_cortex_cells.tsv")
    wait
    du -sh "$T" "$D"; ls "$D/cells" | wc -l
    ;;
  *) echo "unknown PART=$PART"; exit 1 ;;
esac
