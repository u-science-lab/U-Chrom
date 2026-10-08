#!/bin/bash
# scA/B on the dscHi-C aging cortex atlas store (32,777 cells, 1 Mb, read over HTTP): run time / memory (best of
# 3), cell-type pseudo-bulk E1, separation of the cell types next to scHiCluster.  Needs scab_prep (CpG cache).
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-scab benchmarks/sc_structures/sherlock/scab_dschic.sbatch
#SBATCH --job-name=scab-dschic
#SBATCH --partition=xiaojie,normal
#SBATCH --time=02:30:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-scab}/benchmarks/sc_structures/sherlock/_env.sh"
# SCAB_PY: another existing Python env (e.g. venv-consensus) while venv-sc is not usable
PY=${SCAB_PY:-$PY}
"$PY" -c 'import sys, numpy, pandas, scipy, cooler, sklearn, zarr; print(sys.executable, "numpy", numpy.__version__, "pandas", pandas.__version__, "scipy", scipy.__version__, "cooler", cooler.__version__, "sklearn", sklearn.__version__, "zarr", zarr.__version__)'
export SCAB_CACHE=$OUT/scab/cache OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
mkdir -p "$OUT/scab/dschic"
cd "$REPO" && "$PY" -u benchmarks/sc_structures/scab_dschic.py --out "$OUT/scab/dschic" --runs 3 --subsample 500
