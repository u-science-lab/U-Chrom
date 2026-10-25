#!/bin/bash
#SBATCH --job-name=spacea-fetch
#SBATCH --time=2-00:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --output=%x-%j.out
# Download the fastq of runs from GSA to $RAW/<run>/ and check their md5 (<run>/OK when both pass).  Resumable
# (wget -c, retried: GSA closes long transfers), in a small job.  Usage: sbatch fetch.sbatch <run> [<run> ...]
set -euo pipefail
source "$SLURM_SUBMIT_DIR/common.sh"
for RUN in "$@"; do
  D="$RAW/$RUN"; mkdir -p "$D"; cd "$D"
  [ -e OK ] && { echo "$RUN already done"; continue; }
  for k in r1 r2; do
    F=$(col "$RUN" $k); M=$(col "$RUN" ${k}_md5)
    for attempt in $(seq 1 200); do
      echo "[$(date)] $RUN $F attempt $attempt"
      wget -q -c --tries=5 --waitretry=60 --read-timeout=300 "$FTP/$RUN/$F" && break
      sleep 60
    done
    echo "$M  $F" | md5sum -c -
  done
  touch OK; echo "[$(date)] $RUN done"; ls -la "$D"
done
