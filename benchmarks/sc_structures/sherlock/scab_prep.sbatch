#!/bin/bash
# scA/B inputs: the registered genome FASTAs (UCSC) and small references, the kim2020 / tan2018 / wu2025 stores,
# the CpG tracks (parallel) into $SCAB_CACHE; the scA/B unit tests on the repo copy; smoke runs on 300 cells.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-scab benchmarks/sc_structures/sherlock/scab_prep.sbatch
#SBATCH --job-name=scab-prep
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:30:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-scab}/benchmarks/sc_structures/sherlock/_env.sh"
# SCAB_PY: another existing Python env (e.g. venv-consensus) while venv-sc is not usable
PY=${SCAB_PY:-$PY}
"$PY" -c 'import sys, numpy, pandas, scipy, cooler, sklearn, zarr; print(sys.executable, "numpy", numpy.__version__, "pandas", pandas.__version__, "scipy", scipy.__version__, "cooler", cooler.__version__, "sklearn", sklearn.__version__, "zarr", zarr.__version__)'
export SCAB_CACHE=$OUT/scab/cache
mkdir -p "$SCAB_CACHE"
cd "$REPO/packages/uchrom" && "$PY" -m pytest tests/strc/test_single_cell_compartments.py -q -p no:cacheprovider 2>&1 | tail -3
cd "$REPO" && "$PY" -u benchmarks/sc_structures/scab_prep.py --workers 8 --smoke-cells 300
