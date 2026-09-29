#!/bin/bash
# Build the Fig. 3a NucDynamics benchmark environments on Sherlock (run once).
#
#   $GROUP_HOME/$USER/uchrom-nd/venv-main   Python 3.12 module + U-Chrom (CPU torch) + uchrom_nucdyn (maturin, GPU feature)
#   $GROUP_HOME/$USER/uchrom-nd/venv-orig   Python 3.12 module + numpy<2 + cython<3 for the original code
#   $GROUP_HOME/$USER/uchrom-nd/nd/{master,release_1.3}   tjs23/nuc_dynamics, built in place
#
# The repo copy lives in $SCRATCH/uchrom-nd/repo (rsync from the laptop).
#
#   sbatch benchmarks/fig3/sherlock/setup.sbatch
#SBATCH --job-name=nd-setup
#SBATCH --partition=xiaojie,owners,normal
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out

set -euo pipefail
ml purge
ml python/3.12.1 rust/1.97.1

BASE=$GROUP_HOME/$USER/uchrom-nd
REPO=$SCRATCH/uchrom-nd/repo
export PIP_CACHE_DIR=$SCRATCH/.cache/pip XDG_CACHE_HOME=$SCRATCH/.cache CARGO_HOME=$SCRATCH/.cache/cargo
export CARGO_TARGET_DIR=$L_SCRATCH/cargo-target
mkdir -p "$BASE/nd" "$PIP_CACHE_DIR" "$CARGO_HOME"
echo "host=$(hostname) job=$SLURM_JOB_ID $(python3 --version) $(rustc --version)"

# --- original nuc_dynamics (pinned commits) --------------------------------------------
for br in master release_1.3; do
  d=$BASE/nd/$br
  [ -d "$d" ] || git clone -q -b "$br" https://github.com/tjs23/nuc_dynamics "$d"
done
# host git is 1.8 (no -C)
(cd "$BASE/nd/master" && git checkout -q 778697a && git log --oneline -1)
(cd "$BASE/nd/release_1.3" && git checkout -q 00eaf0b && git log --oneline -1)

[ -d "$BASE/venv-orig" ] || python3 -m venv "$BASE/venv-orig"
"$BASE/venv-orig/bin/pip" install -q --upgrade pip
"$BASE/venv-orig/bin/pip" install -q "numpy<2" "cython<3" setuptools
for br in master release_1.3; do
  (cd "$BASE/nd/$br" && "$BASE/venv-orig/bin/python" setup_cython.py build_ext --inplace > build.log 2>&1 && echo "built $br")
done

# --- native engine + benchmark deps --------------------------------------------------------------
[ -d "$BASE/venv-main" ] || python3 -m venv "$BASE/venv-main"
P=$BASE/venv-main/bin/pip
$P install -q --upgrade pip maturin
# CentOS 7 (glibc 2.17): recent numpy / pandas / taichi have no compatible wheels and
# the system assembler cannot build them.  The Fig. 3a benchmark scripts need only
# numpy, pandas and psutil (plus uchrom_nucdyn), so U-Chrom itself is not installed here.
$P install -q --only-binary=:all: "numpy<2.3" "pandas<2.3" psutil
(cd "$REPO/native/nucdyn" && "$BASE/venv-main/bin/maturin" build --release -o "$L_SCRATCH/wheels")
$P install -q --force-reinstall --no-deps "$L_SCRATCH"/wheels/u_chrom_nucdyn-*.whl

"$BASE/venv-main/bin/python" - <<'EOF'
import uchrom_nucdyn as un, numpy
print("uchrom_nucdyn", un.__version__, "gpu build:", un.HAS_GPU, "numpy", numpy.__version__)
try:
    print("gpu_info:", un.gpu_info())
except Exception as e:
    print("gpu_info failed (no GPU on this node is expected):", e)
EOF
echo done
