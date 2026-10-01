#!/bin/bash
# `robust` on the DEVELOPMENT half of the Nagano 2017 serum cells (PREREG §6, 2026-10-01; split by
# robust_matched_split.py) + the matched-imaging comparison vs Takei 2021 mESC for robust and, on the
# same development cells, the existing NucDynamics (GPU) and hickit models.  100 kb, 2 models, seed 1,
# one GPU.  The held-back half is never touched here.
#
#   PARAMS='{...}' sbatch --export=ALL,VARIANT=v,ENGINE=e7 benchmarks/screcon/sherlock/robust_matched.sbatch
#SBATCH --job-name=rb-match
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-robust/benchmarks/screcon/sherlock/_env_robust.sh"
: "${VARIANT:?}" "${PARAMS:?}"
MT=$W/runs/screcon/matched                      # existing matched-imaging inputs (read only)
O=$RB/matched
SPL=$O/split
mkdir -p "$SPL" "$O/models/$VARIANT" "$O/sets" "$O/rows"
[ -f "$SPL/dev_manifest.tsv" ] || $PY $SC/robust_matched_split.py --manifest "$MT/nagano/serum/manifest.tsv" --out-dir "$SPL"
DEV=$SPL/dev_manifest.tsv
IMG=$MT/sets/takei2021_mesc.npz
nvidia-smi --query-gpu=name --format=csv,noheader || true
tail -n +2 "$DEV" | cut -f1,5 | while IFS=$'\t' read -r cell table; do
  out=$O/models/$VARIANT/$cell.npz
  [ -f "$out" ] && continue
  $PY $SC/run_robust.py --contacts "$table" --res 100000 --device ${DEVICE:-gpu} --n-models 2 --seed 1 --params "$PARAMS" \
    --label "robust_$VARIANT" --out "$out" > "$O/models/$VARIANT/$cell.log" 2>&1 || echo "FAILED $cell"
done
echo "models: $(ls "$O"/models/$VARIANT/*.npz | wc -l)"
set_of() {  # set_of NAME MODELS_DIR
  [ -f "$O/sets/$1.npz" ] || $PY $SC/matched_data.py models --manifest "$DEV" --models-dir "$2" --label "nagano_serum_dev_$1" --out "$O/sets/$1.npz"
}
set_of "robust_$VARIANT" "$O/models/$VARIANT"
set_of nucdyn_gpu "$MT/models/nucdyn_gpu"
set_of hickit "$MT/models/hickit"
for m in "robust_$VARIANT" nucdyn_gpu hickit; do
  out=$O/rows/$m.csv
  [ -f "$out" ] || $PY $SC/matched.py compare --a "$O/sets/$m.npz" --b "$IMG" --label "mesc/nagano_serum_dev/$m" --n-rep 5 --out "$out"
done
$PY $SC/matched.py summary --rows "$O"/rows/*.csv --out "$O/summary.csv" > "$O/summary.txt"
cat "$O/summary.txt"
