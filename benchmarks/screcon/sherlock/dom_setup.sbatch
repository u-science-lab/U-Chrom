#!/bin/bash
# Pinned engine build for the dominant-cell jobs (PREREG §13) from repo-dominant: cargo tests (the
# regression tests pin the frozen protocols: robust-frozen, ember-diploid-frozen, ember-deep-frozen),
# a wheel installed with --target into $SCRATCH/uchrom-nd/engine-dominant/$ENGINE_TAG, screcon tests.
#
#   sbatch --export=ALL,ENGINE_TAG=dom-<sha> benchmarks/screcon/sherlock/dom_setup.sbatch
#SBATCH --job-name=dom-setup
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
set -euo pipefail
ml purge
ml python/3.12.1 rust/1.97.1
BASE=$GROUP_HOME/$USER/uchrom-nd
REPO=$SCRATCH/uchrom-nd/repo-dominant
VENV=$BASE/venv-diploid
: "${ENGINE_TAG:?set ENGINE_TAG}"
export PIP_CACHE_DIR=$SCRATCH/.cache/pip XDG_CACHE_HOME=$SCRATCH/.cache CARGO_HOME=$SCRATCH/.cache/cargo
export CARGO_TARGET_DIR=$SCRATCH/uchrom-nd/cargo-target-dominant
echo "host=$(hostname) job=$SLURM_JOB_ID $(python3 --version) $(rustc --version) engine=$ENGINE_TAG"
cd "$REPO/packages/uchrom-recon"
cargo test --release 2>&1 | grep -E "test result|FAILED|panicked" || true
WH=$SCRATCH/uchrom-nd/wheels-dominant/$ENGINE_TAG
rm -rf "$WH"
"$VENV/bin/maturin" build --release -o "$WH"
WHL=$(ls -t "$WH"/uchrom_recon-*.whl | head -1)
rm -rf "$SCRATCH/uchrom-nd/engine-dominant/$ENGINE_TAG"
"$VENV/bin/pip" install -q --no-deps --target "$SCRATCH/uchrom-nd/engine-dominant/$ENGINE_TAG" "$WHL"
export PYTHONPATH=$SCRATCH/uchrom-nd/engine-dominant/$ENGINE_TAG
"$VENV/bin/python" -c "import uchrom_recon as un, numpy, scipy, pandas; print('uchrom_recon', un.__version__, un.__file__, 'gpu build', un.HAS_GPU)"
cd "$REPO" && "$VENV/bin/python" -m pytest -q benchmarks/screcon/tests -p no:cacheprovider 2>&1 | tail -3
