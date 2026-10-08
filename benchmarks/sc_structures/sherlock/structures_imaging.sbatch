#!/bin/bash
# Structures part: the same callers on imaging by number of traces (Su 2020 IMR90 chr21 vs Rao 2014 IMR90,
# Takei 2021 mESC 25 kb vs Bonev 2017) and on the Stevens 2017 mESC structures vs Bonev 2017
# (benchmarks/sc_structures/structures_imaging.py).
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-structures benchmarks/sc_structures/sherlock/structures_imaging.sbatch
#SBATCH --job-name=structures-imaging
#SBATCH --partition=xiaojie,normal
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-structures}/benchmarks/sc_structures/sherlock/_env.sh"
# STRUCT_PY / STRUCT_ENGINE: another interpreter / native-package dir when venv-sc / engine-sc are not usable
# (setup jobs 46944245 / 46945076 failed building numpy: venv-sc empty, no engine-sc)
PY=${STRUCT_PY:-$PY}
if [ -n "${STRUCT_ENGINE:-}" ]; then export PYTHONPATH=$STRUCT_ENGINE:$PYTHONPATH; fi
"$PY" -c "import sys, numpy, pandas, chromdata, uchrom; print(sys.executable, 'numpy', numpy.__version__, 'pandas', pandas.__version__, uchrom.__file__)"
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
RUN=$OUT/structures/imaging-$SLURM_JOB_ID
mkdir -p "$RUN"
cd "$REPO"
lscpu | grep -E "Model name|^CPU\(s\)"
/usr/bin/time -v "$PY" -u benchmarks/sc_structures/structures_imaging.py --out "$RUN" --seeds 5 \
    --sections ${SECTIONS:-su2020 takei25 stevens} 2>&1 \
    | grep --line-buffered -vE "^\s+(Page|Volun|Invol|Swaps|File|Socket|Signals|Exit|Average|Minor|Major|Percent|System|User|Command)"
echo "outputs: $RUN"
