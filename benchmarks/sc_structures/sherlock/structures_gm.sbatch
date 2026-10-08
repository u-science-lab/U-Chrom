#!/bin/bash
# Structures part: the tracing callers on the Tan 2018 Dip-C GM12878 structures, chr21, vs Rao 2014 GM12878
# (benchmarks/sc_structures/structures_callers.py, all sections; FISHnet with the published sweep on
# SLURM_CPUS_PER_TASK - 1 worker processes).
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-structures benchmarks/sc_structures/sherlock/structures_gm.sbatch
#SBATCH --job-name=structures-gm
#SBATCH --partition=xiaojie,normal
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=96G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-structures}/benchmarks/sc_structures/sherlock/_env.sh"
# STRUCT_PY / STRUCT_ENGINE: another interpreter / native-package dir when venv-sc / engine-sc are not usable
# (setup jobs 46944245 / 46945076 failed building numpy: venv-sc empty, no engine-sc)
PY=${STRUCT_PY:-$PY}
if [ -n "${STRUCT_ENGINE:-}" ]; then export PYTHONPATH=$STRUCT_ENGINE:$PYTHONPATH; fi
"$PY" -c "import sys, numpy, pandas, chromdata, uchrom; print(sys.executable, 'numpy', numpy.__version__, 'pandas', pandas.__version__, uchrom.__file__)"
export OMP_NUM_THREADS=8
RUN=${GM_OUT:-$OUT/structures/gm-$SLURM_JOB_ID}   # GM_OUT: continue an earlier run (its cache)
mkdir -p "$RUN"
cd "$REPO"
lscpu | grep -E "Model name|^CPU\(s\)"
/usr/bin/time -v "$PY" -u benchmarks/sc_structures/structures_callers.py --out "$RUN" --workers $((SLURM_CPUS_PER_TASK - 1)) \
    --repeats 3 --seeds 5 --fishnet-sweep default ${SECTIONS:+--sections $SECTIONS} 2>&1 \
    | grep --line-buffered -vE "^\s+(Page|Volun|Invol|Swaps|File|Socket|Signals|Exit|Average|Minor|Major|Percent|System|User|Command)"
echo "outputs: $RUN"
