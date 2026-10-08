#!/bin/bash
# Small representative test before the full runs: SnapHiC on 50 of the 742 cells, chr19 only, with the numpy
# reference and the native kernel; the two call tables are compared.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-snaphic,ENGINE=snaphic .../snaphic_test.sbatch
#SBATCH --job-name=snaphic-test
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:30:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-snaphic}/benchmarks/sc_structures/sherlock/_env.sh"
export OPENBLAS_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK RAYON_NUM_THREADS=$SLURM_CPUS_PER_TASK
D=$OUT/snaphic/test
mkdir -p "$D"
B="$REPO/benchmarks/sc_structures"
"$PY" -c "import uchrom_maps; print(uchrom_maps.__file__, hasattr(uchrom_maps, 'snaphic_chrom'), uchrom_maps.default_threads())"
"$PY" "$B/snaphic_mesc.py" run --out "$D" --n 50 --chrom chr19 --backend native --threads "$SLURM_CPUS_PER_TASK" --tag chr19_native
"$PY" "$B/snaphic_mesc.py" run --out "$D" --n 50 --chrom chr19 --backend numpy --tag chr19_numpy
"$PY" - "$D" <<'PYEOF'
import sys, pandas as pd, numpy as np
d = sys.argv[1]
a = pd.read_csv(f"{d}/snaphic_N50_r0_chr19_native.tsv", sep="\t")
b = pd.read_csv(f"{d}/snaphic_N50_r0_chr19_numpy.tsv", sep="\t")
key = ["chrom1", "start1", "start2"]
print("native", len(a), "numpy", len(b), "same loops:", a[key].equals(b[key]))
if a[key].equals(b[key]) and len(a):
    for c in ("tstat", "fdr_dist", "case_avg", "control_avg"):
        print(c, "max rel diff", float(np.max(np.abs(a[c] - b[c]) / np.abs(b[c]))))
    print("outlier_count equal", a["outlier_count"].equals(b["outlier_count"]))
PYEOF
