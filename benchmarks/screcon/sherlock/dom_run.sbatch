#!/bin/bash
# Dominant-cell mixtures (PREREG §13): every reconstruction of one dominant (array task = dominant
# index in designs.json, 1-based) on one GPU, then its scores.  Development sets only unless APPROVED=1.
#
#   sbatch --array=1-12 --export=ALL,ENGINE=<tag>,DS=nagano,SET=dev --time=03:00:00 benchmarks/screcon/sherlock/dom_run.sbatch
#   CPU (f64 engine path): add DEVICE=cpu and -p normal,xiaojie -G 0 --cpus-per-task=16 (sbatch options override the header)
#SBATCH --job-name=dom-run
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo-dominant/benchmarks/screcon/sherlock/_env_dominant.sh"
: "${DS:?}" "${ENGINE:?}"
SET=${SET:-dev}
[ "$SET" = dev ] || [ -n "${APPROVED:-}" ] || { echo "held-back set needs APPROVED=1 (user approval)"; exit 1; }
D=$DM/$DS/$SET
DOM=$($PY -c "import json,sys; print(json.load(open(sys.argv[1]))['dominants'][int(sys.argv[2]) - 1])" "$D/designs.json" "${SLURM_ARRAY_TASK_ID:-${TASK:-1}}")
if [ "${DEVICE:-gpu}" = gpu ]; then nvidia-smi --query-gpu=name --format=csv,noheader || true; fi
echo "dominant $DOM"
$PY $SC/dominant.py run --dir "$D" --dominant "$DOM" --device ${DEVICE:-gpu}
$PY $SC/dominant.py score --dir "$D" --dominant "$DOM" | tail -3
echo done
