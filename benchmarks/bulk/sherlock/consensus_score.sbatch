#!/bin/bash
# Score consensus structures and baselines against the imaging medians (score.py), one line of
# benchmarks/bulk/consensus/tasks_score.tsv per array task: every listed run (and its mean_refined variant),
# the baselines of the same input, HIPPS mean distances of the same balanced matrix, the fit to the input,
# and -- when $IGM_<imaging dataset> holds a glob of IGM population zarrs (deconv jobs) -- their median
# distances.  Output: $CS/scores/<name>.json.  Needs consensus_imaging, consensus_real, consensus_baselines.
#
#   N=$(grep -v '^#' benchmarks/bulk/consensus/tasks_score.tsv | tail -n +2 | wc -l)
#   sbatch --array=1-$N [--export=ALL,IGM_su2020_genome='/path/igm_*.chromdata.zarr'] \
#       benchmarks/bulk/sherlock/consensus_score.sbatch
#SBATCH --job-name=cons-score
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo-consensus/benchmarks/bulk/sherlock/consensus_env.sh"
IFS=$'\t' read -r NAME IMG CELL RUNS BASE HIPPS <<< "$(task_line "$BC/tasks_score.tsv" "${SLURM_ARRAY_TASK_ID:-1}")"
ARGS=(--imaging "$CS/imaging/$IMG.npz" --hipps "$HIPPS" --fit-input "$CELL" --out "$CS/scores/$NAME.json")
for r in ${RUNS//,/ }; do
  [ -f "$CS/models/$r.npz" ] && ARGS+=(--model "$r=$CS/models/$r.npz")
  [ -f "$CS/models/$r.mean_refined.npz" ] && ARGS+=(--model "${r}_mean_refined=$CS/models/$r.mean_refined.npz")
done
for m in mds_full mds_chrom minimds; do
  [ -f "$CS/base/$BASE/$m.npz" ] && ARGS+=(--model "$m=$CS/base/$BASE/$m.npz")
done
IGMV=IGM_$IMG
if [ -n "${!IGMV:-}" ]; then
  for z in ${!IGMV}; do ARGS+=(--igm "igm_$(basename "$z" .chromdata.zarr)=$z"); done
fi
echo "score $NAME: ${ARGS[*]}"
$PY "$BC/score.py" "${ARGS[@]}"
