#!/bin/bash
#SBATCH --job-name=uchrom-env
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
# One-off: the conda environment for spatial_pairs_to_cool.py (pairs → .scool / .mcool).
set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
export CONDA_PKGS_DIRS="$SCRATCH/conda_pkgs"      # $HOME is small; the package cache is disposable
ENV="$HOME/envs/uchrom-hic"
mamba create -y -p "$ENV" -c conda-forge -c bioconda python=3.12 "cooler>=0.10" pandas numpy pigz
"$ENV/bin/python" -c "import cooler, pandas, numpy; print('cooler', cooler.__version__)"
