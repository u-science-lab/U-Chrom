#!/bin/bash
# Structures part: EMber (frozen, as is; CPU engine) on the 14 Tan 2018 GM12878 cells vs the authors' Dip-C
# structures through the compartment caller (benchmarks/sc_structures/structures_ember.py).
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-structures benchmarks/sc_structures/sherlock/structures_ember.sbatch
#SBATCH --job-name=structures-ember
#SBATCH --partition=xiaojie,normal
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-structures}/benchmarks/sc_structures/sherlock/_env.sh"
# STRUCT_PY / STRUCT_ENGINE: another interpreter / native-package dir when venv-sc / engine-sc are not usable
# (setup jobs 46944245 / 46945076 failed building numpy: venv-sc empty, no engine-sc)
PY=${STRUCT_PY:-$PY}
if [ -n "${STRUCT_ENGINE:-}" ]; then export PYTHONPATH=$STRUCT_ENGINE:$PYTHONPATH; fi
"$PY" -c "import sys, numpy, pandas, chromdata, uchrom; print(sys.executable, 'numpy', numpy.__version__, 'pandas', pandas.__version__, uchrom.__file__)"
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK EMBER_DEVICE=cpu
RUN=${EMBER_OUT:-$OUT/structures/ember-$SLURM_JOB_ID}   # EMBER_OUT: reuse the reconstructions of an earlier run
mkdir -p "$RUN"
cd "$REPO"
lscpu | grep -E "Model name|^CPU\(s\)"
"$PY" -u benchmarks/sc_structures/structures_ember.py --out "$RUN" --models 4 ${CELLS:+--cells $CELLS}
echo "outputs: $RUN"
