#!/bin/bash
# scMicro-C GM12878 (Wu et al. 2025, GEO GSE192759; download_data.py --wu2025_scmicroc): the hickit phased
# pairs of the 12 cells with the largest files (per GSM, ~0.4 GB) and, streamed once out of the 102 GB
# series tarball, their 5 / 10 / 20 kb hickit structures; then contacts per cell (highres.py count).
#
#   sbatch benchmarks/screcon/sherlock/highres_download.sbatch
#SBATCH --job-name=hr-download
#SBATCH --partition=xiaojie,normal
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-highres/benchmarks/screcon/sherlock/_env_highres.sh"
fetch() {   # extra args of download_data.py
  for try in 1 2 3; do
    $PY $REPO/example-data/download_data.py --wu2025_scmicroc --dest "$DATA" "$@" && return 0
    echo "download attempt $try failed"; sleep 120
  done
  return 1
}
fetch --no-extract
$PY $SC/highres.py count --out "$WU/contacts_per_cell.tsv" "$WU"/GSM*_cell_*.impute.pairs.gz
fetch
ls -la "$WU/3dg" | head -60
du -sh "$WU"
