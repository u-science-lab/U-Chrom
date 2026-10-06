#!/bin/bash
# Create venv-deconv (first run), install U-Chrom editable from repo-deconv (without taichi: no
# CentOS 7 wheel; the deconvolution does not use it) and rebuild the native engine wheel (igm
# protocol, GPU feature) into it; add h5py; fetch the IGM demo input (GPL-3 data file; download on
# demand, never committed).  Run after every engine change.
#
#   sbatch benchmarks/bulk/sherlock/setup_deconv.sbatch
#SBATCH --job-name=bulk-setup
#SBATCH --partition=xiaojie,owners,normal
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env.sh"   # submit from $SCRATCH/uchrom-nd/repo-deconv
ml rust/1.97.1
export XDG_CACHE_HOME=$SCRATCH/.cache CARGO_HOME=$SCRATCH/.cache/cargo CARGO_TARGET_DIR=$L_SCRATCH/cargo-target
mkdir -p "$CARGO_HOME"
[ -d "$VENV" ] || python3 -m venv "$VENV"
P=$VENV/bin/pip
$P install -q --upgrade pip maturin
# binary wheels for glibc 2.17 (CentOS 7); U-Chrom's own dependencies except taichi / torch
$P install -q --only-binary=:all: "numpy<2.3" "pandas<2.3" "scipy<1.15" psutil "zarr>=3" "pyarrow<18" fire networkx statsmodels matplotlib
$P install -q -e "$REPO" --no-deps
$P install -q --only-binary=:all: "h5py<3.13"
(cd "$REPO/packages/uchrom-nucdyn" && "$VENV/bin/maturin" build --release -o "$L_SCRATCH/wheels")
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
