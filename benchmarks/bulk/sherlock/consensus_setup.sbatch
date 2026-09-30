#!/bin/bash
# Create venv-consensus (first run) the way setup_deconv.sbatch creates venv-deconv, install U-Chrom editable
# from repo-consensus, build the native engine wheel of this branch (consensus protocol, GPU feature) into it,
# add the benchmark dependencies (cooler / h5py / fsspec for Hi-C, torch < 2.6 for the U-Chrom MDS baseline —
# the last wheels for glibc 2.17 —, scikit-learn), clone miniMDS @ 9915d21 (baseline, full mode), fetch the
# data the benchmark needs (skipped when present), and run the CPU tests.  Run after every engine change.
#
#   rsync -a --exclude .git --exclude target ./ sherlock:$SCRATCH/uchrom-nd/repo-consensus/
#   cd $SCRATCH/uchrom-nd/repo-consensus && sbatch benchmarks/bulk/sherlock/consensus_setup.sbatch
#SBATCH --job-name=cons-setup
#SBATCH --partition=xiaojie,owners,normal
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/consensus_env.sh"
ml rust/1.97.1
export XDG_CACHE_HOME=$SCRATCH/.cache CARGO_HOME=$SCRATCH/.cache/cargo CARGO_TARGET_DIR=$L_SCRATCH/cargo-target
mkdir -p "$CARGO_HOME"
[ -d "$VENV" ] || python3 -m venv "$VENV"
P=$VENV/bin/pip
$P install -q --upgrade pip maturin
$P install -q --only-binary=:all: "numpy<2.3" "pandas<2.3" "scipy<1.15" psutil "zarr>=3" "pyarrow<18" fire networkx \
    statsmodels matplotlib "h5py<3.13" fsspec aiohttp requests scikit-learn pytest
# cooler: prefer wheels but allow pure-Python sdists (its dependency asciitree is sdist only; with
# --only-binary=:all: pip backtracked to cooler 0.4.0); numpy / pandas / scipy pinned as installed
CONS=$(mktemp); $VENV/bin/python -c "import numpy, pandas, scipy; print(f'numpy=={numpy.__version__}\npandas=={pandas.__version__}\nscipy=={scipy.__version__}')" > "$CONS"
$P install -q --prefer-binary -c "$CONS" "cooler>=0.9.3"
$P install -q --only-binary=:all: "torch<2.6" || echo "WARNING: no torch wheel; the U-Chrom MDS baseline will be skipped"
$P install -q -e "$REPO" --no-deps
(cd "$REPO/native/nucdyn" && "$VENV/bin/maturin" build --release -o "$L_SCRATCH/wheels")
$P install -q --force-reinstall --no-deps "$L_SCRATCH"/wheels/u_chrom_nucdyn-*.whl
# miniMDS (Rieber & Mahony 2017; MIT) — full mode only (no --partitioned); needs numpy, scikit-learn, matplotlib
if [ ! -d "$MINIMDS" ]; then
  git clone -q https://github.com/seqcode/miniMDS "$MINIMDS"
  (cd "$MINIMDS" && git checkout -q 9915d21)   # host git 1.8 has no -C
fi
# data (download_data.py skips files that are present and md5-checks the large ones)
$PY "$REPO/example-data/download_data.py" --dest "$DATA" --su2020_genome --su2020_chr21 --takei2021_1mb
$PY "$REPO/example-data/download_data.py" --dest "$DATA" --rao2014_imr90_4dn --bonev2017_mesc_4dn
$PY - <<'EOF'
import uchrom_nucdyn as un
from uchrom.recon.bulk.consensus import native_available
print("uchrom_nucdyn", un.__version__, "gpu build:", un.HAS_GPU, "consensus:", native_available())
EOF
$PY -m pytest -q "$REPO/tests/recon/test_consensus.py" "$REPO/tests/recon/test_deconv_preprocess.py"
(cd "$REPO/native/nucdyn" && cargo test --release consensus 2>&1 | grep -E "test result|FAILED|panicked")
echo done
