#!/bin/bash
# Type deconvolution (PREREG §14): one task = one (tissue, resolution, composition noise); every method + scoring.
#
#   sbatch --array=1-48 benchmarks/spatial/sherlock/td_fit.sbatch                         (dev: 4 reps x 2 regimes x 2 res x 3 noise)
#   sbatch --array=1-96 --export=ALL,SET=test,VARIANTS=<frozen.json> benchmarks/spatial/sherlock/td_fit.sbatch
#SBATCH --job-name=td-fit
#SBATCH --partition=xiaojie,normal
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo-spatial/benchmarks/spatial/sherlock/_env.sh"
SET=${SET:-dev}
VARIANTS=${VARIANTS:-$SP/variants_dev.json}
td_task "${SLURM_ARRAY_TASK_ID:?}" "$SET"
tissue=$OUT/tissues/${SET}_${REGIME}_r${REP}.npz
stem=${SET}_${REGIME}_r${REP}_${RES}_${NOISE}
[ -f "$OUT/scores/$SET/$stem.json" ] && { echo "done: $stem"; exit 0; }
spatial=$([ "$RES" = 1000000 ] && echo --spatial || true)
save=$([ "$RES" = 1000000 ] && [ "$NOISE" = moderate ] && echo --save-profiles || true)
/usr/bin/time -v $PY $SP/run_typedecon.py fit --tissue "$tissue" --truth "$OUT/truth" --res "$RES" --noise "$NOISE" \
  --variants "$VARIANTS" $spatial $save --out "$OUT/scores/$SET" 2> >(tail -n 25 >&2)
