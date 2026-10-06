#!/bin/bash
# Build the environment of the `robust` protocol runs (new single-cell method, PREREG.md §7):
# venv-robust (numpy / scipy / pandas + uchrom_nucdyn from repo-robust, GPU feature), and run the
# native engine's unit tests (CPU; `--features gpu` tests skip without an adapter).  Separate from
# venv-main / repo so the baseline environment stays untouched.
#
#   sbatch benchmarks/screcon/sherlock/robust_setup.sbatch
#SBATCH --job-name=rb-setup
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
set -euo pipefail
ml purge
ml python/3.12.1 rust/1.97.1
BASE=$GROUP_HOME/$USER/uchrom-nd
REPO=$SCRATCH/uchrom-nd/repo-robust
VENV=$BASE/venv-robust
export PIP_CACHE_DIR=$SCRATCH/.cache/pip XDG_CACHE_HOME=$SCRATCH/.cache CARGO_HOME=$SCRATCH/.cache/cargo
export CARGO_TARGET_DIR=$SCRATCH/uchrom-nd/cargo-target-robust
echo "host=$(hostname) job=$SLURM_JOB_ID $(python3 --version) $(rustc --version)"
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip maturin
"$VENV/bin/pip" install -q --only-binary=:all: --prefer-binary "numpy<2.3" "pandas<2.3" "scipy<1.15" psutil pytest
cd "$REPO/packages/uchrom-nucdyn"
UCHROM_NUCDYN_PRINT_GOLDEN=1 cargo test --release ${CARGO_FEATURES:-} -- --nocapture 2>&1 | grep -E "golden|test result|FAILED|panicked" || true
"$VENV/bin/maturin" build --release -o "$SCRATCH/uchrom-nd/wheels-robust"
"$VENV/bin/pip" install -q --force-reinstall --no-deps "$(ls -t "$SCRATCH"/uchrom-nd/wheels-robust/u_chrom_nucdyn-*.whl | head -1)"
"$VENV/bin/python" -c "import uchrom_nucdyn as un, numpy, scipy, pandas; print('uchrom_nucdyn', un.__version__, 'gpu build', un.HAS_GPU, numpy.__version__, scipy.__version__, pandas.__version__)"
cd "$REPO" && "$VENV/bin/python" -m pytest -q benchmarks/screcon/tests -p no:cacheprovider 2>&1 | tail -3
# a pinned copy of this engine build for jobs that set ENGINE=<tag> (see _env_robust.sh), so a later
# rebuild does not change the engine under running sweeps
if [ -n "${ENGINE_TAG:-}" ]; then
  rm -rf "$SCRATCH/uchrom-nd/engine-robust/$ENGINE_TAG"
  "$VENV/bin/pip" install -q --no-deps --target "$SCRATCH/uchrom-nd/engine-robust/$ENGINE_TAG" \
    "$(ls -t "$SCRATCH"/uchrom-nd/wheels-robust/u_chrom_nucdyn-*.whl | head -1)"
  echo "engine pinned as $ENGINE_TAG"
fi
