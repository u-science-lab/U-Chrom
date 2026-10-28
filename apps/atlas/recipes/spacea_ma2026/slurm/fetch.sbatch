#!/bin/bash
#SBATCH --job-name=spacea-fetch
#SBATCH --time=2-00:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --output=%x-%A_%a.out
#SBATCH --requeue
# Download the fastq of runs from GSA to $RAW/<run>/ and check their md5 (<run>/OK when both pass).  Resumable
# (aria2c with 4 connections, else wget -c; retried: GSA stalls and closes long transfers), in a small job.  Usage: sbatch fetch.sbatch <run> [<run> ...], or
# an array over runs.tsv without arguments (task i = data row i + 1): sbatch --array=0-16%4 fetch.sbatch.  GSA can
# be slow (~1 MB/s): ten minutes before its time limit the job requeues itself (same job id, so jobs that depend on
# it keep waiting) and the transfer resumes where it stopped.
set -euo pipefail
source "$SLURM_SUBMIT_DIR/common.sh"
module load system aria2 2> /dev/null || true   # where a module provides it
# seconds left in this job (squeue %L: [D-]HH:MM:SS or MM:SS); near the end, requeue
left() { squeue -h -j "${SLURM_ARRAY_JOB_ID:-$SLURM_JOB_ID}${SLURM_ARRAY_TASK_ID:+_$SLURM_ARRAY_TASK_ID}" -o %L |
  awk -F'[-:]' '{n=NF; s=$n+60*$(n-1); if (n>2) s+=3600*$(n-2); if (n>3) s+=86400*$(n-3); print s}'; }
requeue() { echo "[$(date)] time nearly up: requeued"; scontrol requeue "${SLURM_ARRAY_JOB_ID:-$SLURM_JOB_ID}${SLURM_ARRAY_TASK_ID:+_$SLURM_ARRAY_TASK_ID}"; exit 0; }
RUNS=("$@")
[ ${#RUNS[@]} -gt 0 ] || RUNS=("$(awk -F'\t' -v i="$((SLURM_ARRAY_TASK_ID + 2))" 'NR==i {print $1}' "$HERE/runs.tsv")")
for RUN in "${RUNS[@]}"; do
  [ -n "$RUN" ] || { echo "no run for task ${SLURM_ARRAY_TASK_ID:-}"; exit 2; }
  D="$RAW/$RUN"; mkdir -p "$D"; cd "$D"
  [ -e OK ] && { echo "$RUN already done"; continue; }
  for k in r1 r2; do
    F=$(col "$RUN" $k); M=$(col "$RUN" ${k}_md5)
    for attempt in $(seq 1 200); do
      echo "[$(date)] $RUN $F attempt $attempt"
      T=$(( $(left) - 600 )); [ "$T" -gt 60 ] || requeue
      if command -v aria2c > /dev/null; then   # 4 connections, a stalled one dropped and resumed (GSA stalls them)
        timeout "$T" aria2c -q -c -x 4 -s 4 -k 64M --file-allocation=none --max-tries=0 --retry-wait=30 \
          --timeout=60 --lowest-speed-limit=50K -o "$F" "$FTP/$RUN/$F" && break
      else
        timeout "$T" wget -q -c --tries=5 --waitretry=60 --read-timeout=300 "$FTP/$RUN/$F" && break
      fi
      sleep 60
    done
    echo "$M  $F" | md5sum -c -
  done
  touch OK; echo "[$(date)] $RUN done"; ls -la "$D"
done
