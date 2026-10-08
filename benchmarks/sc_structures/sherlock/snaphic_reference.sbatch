#!/bin/bash
# The authors' SnapHiC (github.com/HuMingLab/SnapHiC @782dc2b, GPL-3.0; its own Python 3.9 env in $GROUP_HOME,
# never imported by U-Chrom) on the same cells and contacts as U-Chrom's call_loops_snaphic, chr17-19 (the code
# holds a dense chromosome x chromosome matrix per process), then the comparison
# (benchmarks/sc_structures/snaphic_reference.py).
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-snaphic,ENGINE=snaphic,NCELLS=100 .../snaphic_reference.sbatch
#SBATCH --job-name=snaphic-ref
#SBATCH --partition=xiaojie,normal
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-snaphic}/benchmarks/sc_structures/sherlock/_env.sh"
export OPENBLAS_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK RAYON_NUM_THREADS=$SLURM_CPUS_PER_TASK
NCELLS=${NCELLS:-100}
CHROMS="chr17 chr18 chr19"
D=$OUT/snaphic/reference/N$NCELLS
SNAP=$W/snaphic-ref/SnapHiC
REFENV=$BASE/venv-snaphic-ref
B="$REPO/benchmarks/sc_structures"
if [ ! -d "$SNAP/.git" ]; then git clone -q https://github.com/HuMingLab/SnapHiC "$SNAP"; fi
(cd "$SNAP" && git checkout -q 782dc2bc7e5a9e3c376bac4a61666a1a02d061b8 && git log -1 --format="SnapHiC %H %cd")
"$PY" "$B/snaphic_reference.py" prepare --out "$D" --n "$NCELLS"
(
  ml purge; ml python/3.9.0
  unset PYTHONPATH                                  # nothing of U-Chrom in the reference's environment
  if [ ! -x "$REFENV/bin/python" ]; then python3 -m venv "$REFENV"; fi
  "$REFENV/bin/python" -m pip install -q "numpy<1.25" "pandas<2" "scipy<1.11" "networkx<3" "scikit-image<0.22" \
    "statsmodels<0.15" h5py "cooler<0.10"
  export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
  rm -rf "$D/snaphic_out"
  TIMEV=""; [ -x /usr/bin/time ] && TIMEV="/usr/bin/time -v"
  $TIMEV "$REFENV/bin/python" "$SNAP/snap.py" -i "$D/input" -s contacts.txt -o "$D/snaphic_out" \
    -c 2 4 -p 3 5 -l "$SNAP/ext/mm10.chrom.sizes" -g mm10 --chrom "$CHROMS" --dist 1000000 \
    --candidate-upper-distance 1000000 --filter-file "$UCHROM_DATA/snaphic/mm10_filter_regions.txt" \
    --rwr-method sliding_window --threaded -n "$SLURM_CPUS_PER_TASK" --no-hic --no-cool --prefix ref
)
"$PY" "$B/snaphic_reference.py" compare --out "$D" --n "$NCELLS" --chrom $CHROMS
