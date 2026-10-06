#!/bin/bash
# Physical sanity + cross-resolution checks of the high-resolution GPU runs (nucdyn_sanity.py):
# published 100 kb (baseline), U-Chrom 100 kb, 10 kb and 1 kb (vs the 100 kb U-Chrom models).
#
#   sbatch benchmarks/fig3/sherlock/sanity.sbatch
#SBATCH --job-name=nd-sanity
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out

set -euo pipefail
ml purge; ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd; W=$SCRATCH/uchrom-nd; PY=$BASE/venv-main/bin/python
export PIP_CACHE_DIR=$SCRATCH/.cache/pip
$PY -c "import scipy" 2>/dev/null || $BASE/venv-main/bin/pip install -q --only-binary=:all: "scipy<1.15"
cd "$W/repo"; S=benchmarks/fig3/nucdyn_sanity.py; O=$W/runs/sanity; mkdir -p $O
$PY $S "${UCHROM_DATA:-$HOME/.cache/uchrom}"/stevens2017_mesc/GSM2219497_Cell_1_genome_structure_model.pdb.gz --out $O/published_100kb.json
$PY $S $W/runs/native_gpu_full --out $O/uchrom_gpu_100kb.json
$PY $S $W/runs/native_gpu_10kb --coarse $W/runs/native_gpu_full --out $O/uchrom_gpu_10kb.json
$PY $S $W/runs/native_gpu_1kb --coarse $W/runs/native_gpu_full --out $O/uchrom_gpu_1kb.json
