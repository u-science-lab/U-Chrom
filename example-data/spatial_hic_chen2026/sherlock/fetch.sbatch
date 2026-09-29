#!/bin/bash
#SBATCH --job-name=chen-fetch
#SBATCH --partition=xiaojie
#SBATCH --time=2-00:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --output=%x-%j.out
# Download the fastq of runs from GSA (FTP) to $SCRATCH/chen2026/raw/<run>/ and check their md5
# (<run>/OK when both files pass).  Resumable (wget -c).  Usage: sbatch fetch.sbatch <run> [<run> …]
# The DTN only takes transfer commands (scp / rsync / sftp) and GSA offers no Globus endpoint, so the
# download runs in a small job, as the GEO downloads of the spatial Hi-C-RNA data did.
set -euo pipefail
source "$HOME/uchrom_chen2026/common.sh"
for RUN in "$@"; do
  D="$RAW/$RUN"; mkdir -p "$D"; cd "$D"
  [ -e OK ] && { echo "$RUN already done"; continue; }
  for k in r1 r2; do
    F=$(col "$RUN" $k); M=$(col "$RUN" ${k}_md5)
    echo "[$(date)] $RUN $F ($(col "$RUN" ${k}_bytes) bytes)"
    wget -q -c --tries=20 --waitretry=60 "$FTP/$RUN/$F"
    echo "$M  $F" | md5sum -c -
  done
  touch OK; echo "[$(date)] $RUN done"; ls -la "$D"
done
