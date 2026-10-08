#!/bin/bash
# Structures part, first (small) job: the unit tests of the part, the datasets built once into UCHROM_DATA
# (tan2018_gm12878 v2 with the Dip-C structures, su2020_chr21, takei2021_mesc; the hg19 / mm10 genomes for GC
# phasing), then the one-call path on the backed Tan 2018 store (structures_onecall.py) and the Takei 25 kb
# section of structures_imaging.py — a representative check before the long jobs.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-structures benchmarks/sc_structures/sherlock/structures_smoke.sbatch
#SBATCH --job-name=structures-smoke
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:30:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-structures}/benchmarks/sc_structures/sherlock/_env.sh"
# STRUCT_PY / STRUCT_ENGINE: another interpreter / native-package dir when venv-sc / engine-sc are not usable
# (setup jobs 46944245 / 46945076 failed building numpy: venv-sc empty, no engine-sc)
PY=${STRUCT_PY:-$PY}
if [ -n "${STRUCT_ENGINE:-}" ]; then export PYTHONPATH=$STRUCT_ENGINE:$PYTHONPATH; fi
"$PY" -c "import sys, numpy, pandas, chromdata, uchrom; print(sys.executable, 'numpy', numpy.__version__, 'pandas', pandas.__version__, uchrom.__file__)"
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
RUN=$OUT/structures/smoke-$SLURM_JOB_ID
mkdir -p "$RUN"
cd "$REPO/packages/uchrom"
"$PY" -m pytest -q -p no:cacheprovider tests/io/test_dipc_3dg.py tests/strc/test_callers_whole_chrom.py \
    tests/strc/test_callers.py tests/strc/test_streaming_callers.py 2>&1 | tail -5
cd "$REPO"
/usr/bin/time -v "$PY" - <<'PYEOF' 2>&1 | grep -E "^(tan|su|takei|hg19|mm10|done)|Maximum resident|Elapsed"
import time
import uchrom.datasets as ds
for name in ("tan2018_gm12878", "su2020_chr21", "takei2021_mesc"):
    t = time.time(); cd = ds.load(name, backed=True); print(name, cd.n_spots, cd.n_traces, round(time.time() - t, 1), "s", flush=True)
for name in ("hg19_genome", "mm10_genome"):
    t = time.time(); p = ds.fetch(name); print(name, p, round(time.time() - t, 1), "s", flush=True)
print("done")
PYEOF
cd "$REPO/packages/uchrom" && "$PY" -m pytest -q -p no:cacheprovider tests/test_load_schic_structures.py tests/test_load_schic_pairs.py 2>&1 | tail -3
cd "$REPO"
/usr/bin/time -v "$PY" -u benchmarks/sc_structures/structures_onecall.py --out "$RUN" 2>&1 | grep --line-buffered -vE "^\s+(Page|Volun|Invol|Swaps|File|Socket|Signals|Exit|Average|Minor|Major|Percent|System|User|Command)"
"$PY" -u benchmarks/sc_structures/structures_imaging.py --out "$RUN" --sections takei25 --seeds 5
echo "outputs: $RUN"
