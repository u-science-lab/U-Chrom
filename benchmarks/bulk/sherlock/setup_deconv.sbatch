#!/bin/bash
# Rebuild the native engine wheel (with the igm protocol, GPU feature) into venv-main,
# add h5py, and fetch the IGM demo input (GPL-3 data file; download on demand, never
# committed).  Run after every engine change (after the fig3 setup.sbatch created venv-main).
#
#   sbatch benchmarks/bulk/sherlock/setup_deconv.sbatch
#SBATCH --job-name=bulk-setup
#SBATCH --partition=xiaojie,owners,normal
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env.sh"   # submit from $SCRATCH/uchrom-nd/repo
ml rust/1.97.1
export XDG_CACHE_HOME=$SCRATCH/.cache CARGO_HOME=$SCRATCH/.cache/cargo CARGO_TARGET_DIR=$L_SCRATCH/cargo-target
mkdir -p "$CARGO_HOME"
P=$BASE/venv-main/bin/pip
$P install -q --upgrade maturin
$P install -q --only-binary=:all: "h5py<3.13"
(cd "$REPO/native/nucdyn" && "$BASE/venv-main/bin/maturin" build --release -o "$L_SCRATCH/wheels")
$P install -q --force-reinstall --no-deps "$L_SCRATCH"/wheels/u_chrom_nucdyn-*.whl
$PY - <<'EOF'
import sys
sys.path.insert(0, "benchmarks/bulk")
import uchrom_nucdyn as un, h5py, numpy
import _igm_bench as B
print("uchrom_nucdyn", un.__version__, "gpu build:", un.HAS_GPU, "igm:", hasattr(un, "calc_population"),
      "h5py", h5py.__version__, "numpy", numpy.__version__)
p = B.fetch_igm_demo()
print("IGM demo input:", p, B.md5(p))
EOF
echo done
