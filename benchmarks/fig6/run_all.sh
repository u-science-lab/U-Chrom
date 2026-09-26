#!/usr/bin/env bash
# Fig 6c benchmarks.  Run on an idle machine: each script waits (up to 30 min) for load < 2.0, then refuses;
# close browsers, games, VMs.
#   bash benchmarks/fig6/run_all.sh <example-data dir>
set -euo pipefail
cd "$(dirname "$0")/../.."
DATA=${1:-example-data}
PY=${PY:-.venv/bin/python}
EXTRA=${EXTRA:-}   # e.g. EXTRA=--force to skip the idle-machine check (the load is still recorded)
D=benchmarks/fig6/_data
[ -f $D/takei2025_fov0_x30.h5cd ] || \
    $PY benchmarks/fig6/make_scaled.py --src "$DATA/takei2025_fov0/takei2025_fov0.h5cd" --factors 1 3 10 30
$PY -u benchmarks/fig6/bench_frontend.py $D/takei2025_fov0_x{1,3,10,30}.h5cd --reps 5 $EXTRA --out paper/fig6/results/frontend.json
cd benchmarks/fig6
../../$PY -u bench_server.py $EXTRA --imaging "../../$DATA/takei2025_fov0/takei2025_fov0.h5cd" \
    --scaled _data/takei2025_fov0_x10.h5cd _data/takei2025_fov0_x30.h5cd \
    --hic "../../$DATA/schicar_mop/schicar_mop.h5cd" --out ../../paper/fig6/results/server.json
