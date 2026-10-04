#!/bin/bash
# Build uchrom_nucdyn (GPU feature) from repo-highres into a pinned directory
# $SCRATCH/uchrom-nd/engine-highres/$ENGINE (no venv is changed; other jobs keep their engines).
#
#   sbatch --export=ALL,ENGINE=main-3658fdb benchmarks/screcon/sherlock/highres_setup.sbatch
#SBATCH --job-name=hr-setup
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
set -euo pipefail
ml purge
ml python/3.12.1 rust/1.97.1
BASE=$GROUP_HOME/$USER/uchrom-nd
REPO=$SCRATCH/uchrom-nd/repo-highres
ENGINE=${ENGINE:-main-3658fdb}
export PIP_CACHE_DIR=$SCRATCH/.cache/pip XDG_CACHE_HOME=$SCRATCH/.cache CARGO_HOME=$SCRATCH/.cache/cargo
export CARGO_TARGET_DIR=$SCRATCH/uchrom-nd/cargo-target-highres
echo "host=$(hostname) job=$SLURM_JOB_ID $(rustc --version) engine=$ENGINE"
cd "$REPO/native/nucdyn"
"$BASE/venv-diploid/bin/maturin" build --release -o "$SCRATCH/uchrom-nd/wheels-highres"
WHL=$(ls -t "$SCRATCH"/uchrom-nd/wheels-highres/u_chrom_nucdyn-*.whl | head -1)
rm -rf "$SCRATCH/uchrom-nd/engine-highres/$ENGINE"
"$BASE/venv-diploid/bin/pip" install -q --no-deps --target "$SCRATCH/uchrom-nd/engine-highres/$ENGINE" "$WHL"
PYTHONPATH=$SCRATCH/uchrom-nd/engine-highres/$ENGINE "$BASE/venv-diploid/bin/python" -c \
  "import uchrom_nucdyn as un; print('uchrom_nucdyn', un.__version__, un.__file__, 'gpu build', un.HAS_GPU)"
