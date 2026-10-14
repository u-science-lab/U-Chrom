#!/bin/bash
# Are the shared ExN - Oligo locus differences A/B compartments? (benchmarks/cross_assay/compartments.py): matched-depth
# pseudo-bulk maps of ExN and Oligo (dscHi-C, GAGE-seq), cis eigenvectors oriented by GC, saddle strengths, and the
# locus differences of imaging / the reconstructions against them.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-xa,UCHROM_REVISION=... benchmarks/cross_assay/sherlock/compartments.sbatch
#SBATCH --job-name=xa-compartments
#SBATCH --partition=xiaojie,normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/runs/xassay/logs/%x-%j.out
set -uo pipefail
ml purge
ml python/3.12.1
W=$SCRATCH/uchrom-nd
PY=$GROUP_HOME/$USER/uchrom-nd/venv-consensus/bin/python
export UCHROM_DATA=$W/data XDG_CACHE_HOME=$SCRATCH/.cache OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export PYTHONPATH=$REPO/packages/uchrom:$REPO/packages/chromdata${PYTHONPATH:+:$PYTHONPATH}
OUT=${OUT:-$W/runs/xassay/compartments}
mkdir -p "$OUT/results"
echo "host=$(hostname) job=${SLURM_JOB_ID:-none} repo=$REPO revision=${UCHROM_REVISION:-unset}"
"$PY" -u "$REPO/benchmarks/cross_assay/compartments.py" --recon-root "${RECON_ROOT:-$W/runs/xassay}" \
  --panel "$W/runs/xassay/liu2025_panel.parquet" --fasta "$UCHROM_DATA/genomes/mm10/mm10.fa.gz" \
  --xa-work "$W/runs/xassay/full/work" --out "$OUT" --results "$OUT/results"
