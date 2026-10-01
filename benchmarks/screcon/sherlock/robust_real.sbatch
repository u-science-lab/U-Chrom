#!/bin/bash
# `robust` on the full Stevens 2017 tables of the DEVELOPMENT cells 1-4 (100 kb, 10 models, seed 1, one
# GPU) + score_real.py (precision, NucDynamics- / Si-C-style violations, vs the published GEO models),
# next to the existing native GPU full-table runs ($W/runs/native_gpu_full/cell<c>.npz) when present.
#
#   PARAMS='{...}' sbatch --export=ALL,VARIANT=v0 benchmarks/screcon/sherlock/robust_real.sbatch
#SBATCH --job-name=rb-real
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-robust/benchmarks/screcon/sherlock/_env_robust.sh"
: "${VARIANT:?}" "${PARAMS:?}"
O=$RB/real
nvidia-smi --query-gpu=name --format=csv,noheader || true
for c in ${CELLS:-1 2 3 4}; do
  dev_cell "$c" || { echo "cell $c is not a development cell: skipped"; continue; }   # DEVELOPMENT SET ONLY
  M=$O/models/$VARIANT
  mkdir -p "$M" "$O/scores/$VARIANT"
  T="$GEO/${GSM[$c]}_Cell_${c}_contact_pairs.txt.gz"
  [ -f "$M/cell$c.npz" ] || $PY $SC/run_robust.py --contacts "$T" --res 100000 --device gpu --n-models 10 --seed 1 \
    --params "$PARAMS" --label "robust_$VARIANT" ${SUPPORT_REL:+--support-mix $(python3 -c "print($SUPPORT_REL * 100000)")} \
    --out "$M/cell$c.npz" > "$M/cell$c.log" 2>&1 || { echo "FAILED cell$c"; tail -3 "$M/cell$c.log"; continue; }
  models=("$M/cell$c.npz"); labels=(robust)
  if [ -f "$W/runs/native_gpu_full/cell$c.npz" ]; then models+=("$W/runs/native_gpu_full/cell$c.npz"); labels+=(native_gpu_full); fi
  $PY $SC/score_real.py --contacts "$T" --reference "$GEO/${GSM[$c]}_Cell_${c}_genome_structure_model.pdb.gz" \
    --models "${models[@]}" --labels "${labels[@]}" --out "$O/scores/$VARIANT/cell$c.json" > /dev/null
  echo "cell$c $(python3 -c "import json;j=json.load(open('$M/cell$c.npz.json'));print(round(j['wall_seconds'],1),'s',round(j['peak_rss_mb']),'MB')")"
done
