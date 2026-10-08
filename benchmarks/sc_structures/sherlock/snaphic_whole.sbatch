#!/bin/bash
# SnapHiC with the RWR of whole chromosomes (SnapHiC 1.0's "inverse" method, the paper's) instead of SnapHiC2's
# sliding windows, on N of the mES cells (NCELLS, default 100; snaphic_mesc.py run --window none): how much the
# windows change.
# A whole chromosome's profile factor holds every long-range contact (~0.5 GB per cell on chr1): 32 cells at a time.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-snaphic,ENGINE=snaphic,NCELLS=742 .../snaphic_whole.sbatch
#SBATCH --job-name=snaphic-whole
#SBATCH --partition=xiaojie,normal
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-snaphic}/benchmarks/sc_structures/sherlock/_env.sh"
export OPENBLAS_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK RAYON_NUM_THREADS=$SLURM_CPUS_PER_TASK
lscpu | grep "Model name" || true
"$PY" "$REPO/benchmarks/sc_structures/snaphic_mesc.py" run --out "$OUT/snaphic/mesc" --n "${NCELLS:-100}" --rep 0 --window none \
  --batch 32 --threads "$SLURM_CPUS_PER_TASK" --tag whole
