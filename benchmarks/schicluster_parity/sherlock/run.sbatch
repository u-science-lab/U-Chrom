#!/bin/bash
# The scHiCluster parity check (benchmarks/schicluster_parity/run.py) on the 5,313 scHiCAR cells at 1 Mb: the authors'
# code (venv-schicluster, schicluster 1.3.2), U-Chrom (the repo copy on the agents' environment), the comparison.
#SBATCH --job-name=schic-parity
#SBATCH --partition=xiaojie,normal
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/arcfish_parity/logs/%x-%j.out
set -uo pipefail
AP=$SCRATCH/uchrom-nd/arcfish_parity                       # the repo copy of benchmark work (shared)
GH=$GROUP_HOME/$USER/uchrom-nd/agentbench
SCOOL=$SCRATCH/uchrom-nd/agentbench/data/schicar_mop/contacts_cells_1Mb.scool
OUT=$SCRATCH/uchrom-nd/schicluster_parity/${RUN:-$SLURM_JOB_ID}; mkdir -p "$OUT"    # RUN=<job id>: compare that run again
R=$AP/repo-schic/benchmarks/schicluster_parity/run.py
REV=$(cat "$AP/repo-schic/REVISION" 2>/dev/null || echo unknown)        # written before the sync (benchmarks/_record.py)
C=(--containall --cleanenv --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 --env UCHROM_REVISION="$REV"
   --env SLURM_JOB_ID="${RUN:-$SLURM_JOB_ID}" --bind "$SCRATCH:$SCRATCH" --bind "$AP:$AP")
if [ -z "${RUN:-}" ]; then
apptainer exec "${C[@]}" --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 --bind "$GH/venv-schicluster:/opt/venv:ro" \
  "$GH/py312full.sif" /opt/venv/bin/python -u "$R" --side authors --scool "$SCOOL" --out "$OUT" --workers 8 ${NCELLS:+--n-cells $NCELLS}
apptainer exec "${C[@]}" --bind "$GH/venv-uchrom:/opt/venv:ro" \
  --env PYTHONPATH="$AP/repo-schic/packages/uchrom:$AP/repo-schic/packages/chromdata" \
  "$GH/py312full.sif" /opt/venv/bin/python -u "$R" --side uchrom --scool "$SCOOL" --out "$OUT" ${NCELLS:+--n-cells $NCELLS}
fi
apptainer exec "${C[@]}" --bind "$GH/venv-uchrom:/opt/venv:ro" \
  --env PYTHONPATH="$AP/repo-schic/packages/uchrom:$AP/repo-schic/packages/chromdata:$AP/repo-schic/benchmarks" \
  "$GH/py312full.sif" /opt/venv/bin/python -u "$R" --compare --out "$OUT"
cp $AP/repo-schic/benchmarks/schicluster_parity/results/parity.json "$OUT/" 2>/dev/null || true
