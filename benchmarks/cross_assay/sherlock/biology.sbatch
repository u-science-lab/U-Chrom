#!/bin/bash
# What the shared ExN - Oligo locus differences are (benchmarks/cross_assay/biology.py): per-locus structural effects
# in imaging and every reconstruction against the expression difference of the genes around each locus (RNA of the
# atlas stores, UCSC mm10 refGene); the figure inputs of the locus panels.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-xa,UCHROM_REVISION=... benchmarks/cross_assay/sherlock/biology.sbatch
#SBATCH --job-name=xa-biology
#SBATCH --partition=xiaojie,normal
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/runs/xassay/logs/%x-%j.out
set -uo pipefail
ml purge
ml python/3.12.1
W=$SCRATCH/uchrom-nd
PY=$GROUP_HOME/$USER/uchrom-nd/venv-consensus/bin/python
export UCHROM_DATA=$W/data XDG_CACHE_HOME=$SCRATCH/.cache OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export PYTHONPATH=$REPO/packages/uchrom:$REPO/packages/chromdata${PYTHONPATH:+:$PYTHONPATH}
OUT=${OUT:-$W/runs/xassay/biology}
mkdir -p "$OUT/results" "$OUT/figdata"
echo "host=$(hostname) job=${SLURM_JOB_ID:-none} repo=$REPO revision=${UCHROM_REVISION:-unset}"
"$PY" -u "$REPO/benchmarks/cross_assay/biology.py" --recon-root "$W/runs/xassay" \
  --liu "$W/data/liu2025_mop/liu2025_mop.chromdata.zarr" --out "$OUT" --figdata "$OUT/figdata" --results "$OUT/results"
