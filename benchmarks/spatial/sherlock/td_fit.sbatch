#!/bin/bash
# Type deconvolution (PREREG §14): one task = one tissue; every (resolution, composition noise), every method,
# scoring.  Finished (tissue, res, noise) outputs are skipped, so a requeued / preempted task resumes.
#
#   sbatch --array=1-8 benchmarks/spatial/sherlock/td_fit.sbatch                              (dev: 4 reps x 2 regimes)
#   sbatch --array=1-16 --export=ALL,SET=test,VARIANTS=<frozen.json> benchmarks/spatial/sherlock/td_fit.sbatch
#SBATCH --job-name=td-fit
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --requeue
#SBATCH --time=05:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo-spatial/benchmarks/spatial/sherlock/_env.sh"
SET=${SET:-dev}
VARIANTS=${VARIANTS:-$SP/variants_dev.json}
td_tissue "${SLURM_ARRAY_TASK_ID:?}" "$SET"
tissue=$OUT/tissues/${SET}_${REGIME}_r${REP}.npz
for RES in "${RESS[@]}"; do
  for NOISE in "${NOISES[@]}"; do
    stem=${SET}_${REGIME}_r${REP}_${RES}_${NOISE}
    [ -f "$OUT/scores/$SET/$stem.json" ] && { echo "done: $stem"; continue; }
    spatial=$([ "$RES" = 1000000 ] && echo --spatial || true)
    save=$([ "$RES" = 1000000 ] && [ "$NOISE" = moderate ] && echo --save-profiles || true)
    /usr/bin/time -v $PY $SP/run_typedecon.py fit --tissue "$tissue" --truth "$OUT/truth" --res "$RES" \
      --noise "$NOISE" --variants "$VARIANTS" $spatial $save --out "$OUT/scores/$SET" 2> >(grep -E "Elapsed|Maximum resident" >&2)
  done
done
