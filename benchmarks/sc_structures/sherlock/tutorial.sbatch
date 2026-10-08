#!/bin/bash
# Execute a tutorial notebook on a compute node (the heavy ones: tutorials/sc_structures.ipynb); the executed
# notebook replaces the one in the repo copy and is copied back to the laptop through the DTN.
#
#   sbatch --export=ALL,NB=sc_structures[,REPO=...,ENGINE=final] benchmarks/sc_structures/sherlock/tutorial.sbatch
#SBATCH --job-name=sc-tutorial
#SBATCH --partition=xiaojie,normal
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=96G
#SBATCH --output=%x-%j.out
export ENGINE=${ENGINE:-final}
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc}/benchmarks/sc_structures/sherlock/_env.sh"
unset MPLBACKEND                       # _env.sh sets Agg for scripts; a notebook needs its inline backend
"$PY" -m pip install -q nbconvert ipykernel openpyxl
"$PY" -c "import uchrom_maps, uchrom_recon; print('native:', uchrom_maps.__file__)"
cd "$REPO/tutorials"
"$PY" -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=6000 "${NB:?}.ipynb"
echo "executed $NB.ipynb"
