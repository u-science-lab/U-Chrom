#!/bin/bash
# Few-cell deconvolution (PREREG §12) development runs, one GPU: mix_dev.py over the pools of a
# directory (development pools only) with the baselines and the variants of a JSON file.
#
#   sbatch --export=ALL,ENGINE=<tag>,POOLS=$MX/pools/takei2021_1mb/dev,RES=1e6,VARIANTS=<json file>,\
#          BASELINES="naive oracle igm",TAG=<run name>[,ONLY=<grep pattern>] benchmarks/screcon/sherlock/mix_dev.sbatch
#   real pools: RES=2e5, REFS=1 (the per-cell EMber runs, baseline "oracle", are the references)
#SBATCH --job-name=mix-dev
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-mix/benchmarks/screcon/sherlock/_env_mix.sh"
: "${POOLS:?}" "${TAG:?}" "${VARIANTS:?}"
case "$POOLS" in */test*) echo "test pools are not run during development"; exit 1 ;; esac
RES=${RES:-1e6}
RUNS=$MX/dev/$TAG/$(basename "$(dirname "$POOLS")")
mkdir -p "$RUNS"
nvidia-smi --query-gpu=name --format=csv,noheader || true
list=$(ls "$POOLS"/k*.txt.gz | grep -v _cell)
[ -n "${ONLY:-}" ] && list=$(echo "$list" | grep -- "$ONLY")
extra=()
[ -n "${REFS:-}" ] && extra=(--refs-dir "$RUNS")
for p in $list; do
  $PY $SC/mix_dev.py --pools "$p" --runs "$RUNS" --res "$RES" --device gpu --baselines ${BASELINES:-} \
    --variants "$(cat "$VARIANTS")" --table "$RUNS/table.tsv" ${extra[@]+"${extra[@]}"} || echo "FAILED $p"
done
echo done
