#!/bin/bash
# scA/B of GM12878 single cells (Tan 2018 Dip-C, Wu 2025 scMicro-C) against Rao 2014 GM12878 E1 on chr21, and of
# Kim 2020 sci-Hi-C H1 / HFF (separation).  Needs scab_prep (stores, CpG cache).
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-scab benchmarks/sc_structures/sherlock/scab_gm12878_kim.sbatch
#SBATCH --job-name=scab-gm-kim
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:30:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-scab}/benchmarks/sc_structures/sherlock/_env.sh"
# SCAB_PY: another existing Python env (e.g. venv-consensus) while venv-sc is not usable
PY=${SCAB_PY:-$PY}
"$PY" -c 'import sys, numpy, pandas, scipy, cooler, sklearn, zarr; print(sys.executable, "numpy", numpy.__version__, "pandas", pandas.__version__, "scipy", scipy.__version__, "cooler", cooler.__version__, "sklearn", sklearn.__version__, "zarr", zarr.__version__)'
export SCAB_CACHE=$OUT/scab/cache OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
mkdir -p "$OUT/scab/gm12878" "$OUT/scab/kim2020"
cd "$REPO"
"$PY" -u benchmarks/sc_structures/scab_gm12878.py --out "$OUT/scab/gm12878"
"$PY" -u benchmarks/sc_structures/scab_kim2020.py --out "$OUT/scab/kim2020"
