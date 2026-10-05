#!/bin/bash
# Cell-type-assisted deconvolution (PREREG §12.1), development pools only: type priors, then
# mix_dev.py with the baselines (oracle = references, naive, IGM S=k, prior-split) and the variants.
#   PY=<python> DATA=<data> MT=<work dir> bash benchmarks/screcon/mix_type_dev.sh <variants.json> <prior params json> <tag>
set -euo pipefail
SC=$(cd "$(dirname "$0")" && pwd)
VARIANTS=$1
PRIOR=${2:-'{}'}
TAG=${3:-r1}
POOLS=$MT/pools/dev
RUNS=$MT/runs_$TAG
mkdir -p "$RUNS"
for p in $(ls "$POOLS"/*_p*.txt.gz | grep -v _cell | grep -- "${ONLY:-.}"); do
  name=$(basename "$p" .txt.gz)
  [ -f "$RUNS/$name.prior.npy" ] || $PY "$SC/mix_type.py" prior --pool "$p" --ref "$MT/ref_1mb.npz" --params "$PRIOR" --out "$RUNS/$name.prior.npy"
  $PY "$SC/mix_dev.py" --res 2e5 --pools "$p" --runs "$RUNS" --refs-dir "$RUNS" --device gpu \
    --baselines oracle naive igm "split:{runs}/{pool}.prior.npy" --variants "$(cat "$VARIANTS")" --table "$RUNS/table.tsv" ${DIPLOID:+--diploid} \
    || echo "FAILED $name"
done
