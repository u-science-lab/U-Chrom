#!/bin/bash
# Structures part, last job: the EMber comparison again on the reconstructions of an earlier run (EMBER_OUT;
# reconstructions reused, nothing re-run), then the part's unit tests and the whole uchrom suite.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-structures,EMBER_OUT=<run dir> benchmarks/sc_structures/sherlock/structures_finish.sbatch
#SBATCH --job-name=structures-finish
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:30:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-structures}/benchmarks/sc_structures/sherlock/_env.sh"
PY=${STRUCT_PY:-$PY}
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK EMBER_DEVICE=cpu
cd "$REPO"
if [ -n "${EMBER_OUT:-}" ]; then
  "$PY" -u benchmarks/sc_structures/structures_ember.py --out "$EMBER_OUT" --models 4
fi
cd "$REPO/packages/uchrom"
"$PY" -m pytest -q -p no:cacheprovider tests/io/test_dipc_3dg.py tests/strc/test_callers_whole_chrom.py \
    tests/test_load_schic_structures.py 2>&1 | tail -3
set +e
"$PY" -m pytest tests -q -p no:cacheprovider 2>&1 | tail -30
