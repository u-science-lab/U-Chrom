#!/bin/bash
# Build a pinned engine for the few-cell deconvolution jobs (EMber-mix, PREREG §12) from repo-mix:
# cargo tests (CPU; GPU tests skip without an adapter; the regression tests print this platform's
# golden hashes), a wheel, installed with --target into $SCRATCH/uchrom-nd/engine-mix/$ENGINE_TAG
# (jobs select it with ENGINE=<tag>).  BASELINE_REPO=<dir>: also print the regression hashes of
# another checkout (e.g. origin/main) for the bit-identity check.
#
#   sbatch --export=ALL,ENGINE_TAG=dev-<sha> benchmarks/screcon/sherlock/mix_setup.sbatch
#SBATCH --job-name=mix-setup
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
set -euo pipefail
ml purge
ml python/3.12.1 rust/1.97.1
BASE=$GROUP_HOME/$USER/uchrom-nd
REPO=$SCRATCH/uchrom-nd/repo-mix
VENV=$BASE/venv-diploid
: "${ENGINE_TAG:?set ENGINE_TAG}"
export PIP_CACHE_DIR=$SCRATCH/.cache/pip XDG_CACHE_HOME=$SCRATCH/.cache CARGO_HOME=$SCRATCH/.cache/cargo
export CARGO_TARGET_DIR=$SCRATCH/uchrom-nd/cargo-target-mix
echo "host=$(hostname) job=$SLURM_JOB_ID $(python3 --version) $(rustc --version) engine=$ENGINE_TAG"
if [ -n "${BASELINE_REPO:-}" ]; then
  (cd "$BASELINE_REPO/native/nucdyn" && CARGO_TARGET_DIR=$SCRATCH/uchrom-nd/cargo-target-mix-base \
    UCHROM_NUCDYN_PRINT_GOLDEN=1 cargo test --release --test regression -- --nocapture 2>&1 | grep -E "golden|test result|panicked" | sed 's/^/baseline: /') || true
fi
cd "$REPO/native/nucdyn"
UCHROM_NUCDYN_PRINT_GOLDEN=1 cargo test --release -- --nocapture 2>&1 | grep -E "golden|test result|FAILED|panicked" || true
WH=$SCRATCH/uchrom-nd/wheels-mix/$ENGINE_TAG
rm -rf "$WH"
"$VENV/bin/maturin" build --release -o "$WH"
WHL=$(ls -t "$WH"/u_chrom_nucdyn-*.whl | head -1)
rm -rf "$SCRATCH/uchrom-nd/engine-mix/$ENGINE_TAG"
"$VENV/bin/pip" install -q --no-deps --target "$SCRATCH/uchrom-nd/engine-mix/$ENGINE_TAG" "$WHL"
export PYTHONPATH=$SCRATCH/uchrom-nd/engine-mix/$ENGINE_TAG
"$VENV/bin/python" -c "import uchrom_nucdyn as un, numpy, scipy, pandas; print('uchrom_nucdyn', un.__version__, un.__file__, 'gpu build', un.HAS_GPU)"
cd "$REPO" && "$VENV/bin/python" -m pytest -q benchmarks/screcon/tests -p no:cacheprovider 2>&1 | tail -3
