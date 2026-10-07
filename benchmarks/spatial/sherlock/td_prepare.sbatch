#!/bin/bash
# Type deconvolution (PREREG §14): split, per-cell contact bins, truth pseudo-bulks, the development tissues.
#
#   sbatch benchmarks/spatial/sherlock/td_prepare.sbatch                      (SET=dev, the default)
#   sbatch --export=ALL,SET=test,APPROVED=1 benchmarks/spatial/sherlock/td_prepare.sbatch   (after the freeze)
#SBATCH --job-name=td-prep
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-spatial/benchmarks/spatial/sherlock/_env.sh"
SET=${SET:-dev}
[ -f "$OUT/split.tsv" ] || $PY $SP/run_typedecon.py split --out "$OUT/split.tsv"
[ -f "$OUT/cells/cells.tsv" ] || $PY $SP/run_typedecon.py cells --split "$OUT/split.tsv" --data "$DATA" \
  --out "$OUT/cells" --workers 8
[ -f "$OUT/truth/truth_250000.npz" ] || $PY $SP/run_typedecon.py truth --split "$OUT/split.tsv" \
  --cells "$OUT/cells" --out "$OUT/truth" --res 1e6 2.5e5
nrep=$([ "$SET" = dev ] && echo $NREP_DEV || echo $NREP_TEST)
extra=$([ "$SET" = test ] && [ "${APPROVED:-0}" = 1 ] && echo --approved || true)
for regime in "${REGIMES[@]}"; do
  for rep in $(seq 0 $(( nrep - 1 ))); do
    [ -f "$OUT/tissues/${SET}_${regime}_r${rep}.npz" ] && continue
    $PY $SP/run_typedecon.py tissue --split "$OUT/split.tsv" --cells "$OUT/cells" --set "$SET" \
      --regime "$regime" --rep "$rep" --out "$OUT/tissues" $extra
  done
done
