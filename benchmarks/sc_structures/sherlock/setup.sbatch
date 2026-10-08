#!/bin/bash
# Python env venv-sc (created once, refreshed) and the native packages (uchrom_maps, uchrom_recon) built from
# a repo copy into $SCRATCH/uchrom-nd/engine-sc/$ENGINE; then the uchrom unit tests on that copy.
#
#   sbatch [--export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-x,ENGINE=x] benchmarks/sc_structures/sherlock/setup.sbatch
#SBATCH --job-name=sc-setup
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:30:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc}/benchmarks/sc_structures/sherlock/_env.sh"
ml rust/1.97.1
export CARGO_HOME=$SCRATCH/.cache/cargo CARGO_TARGET_DIR=$W/cargo-target-sc
if [ ! -x "$PY" ]; then python3 -m venv "$BASE/venv-sc"; fi
"$PY" -m pip install -q -U pip
# binary wheels only for the compiled dependencies: the newest releases need a newer glibc than Sherlock's and
# their source builds fail here (numpy's AVX-512 assembly: "no such instruction: endbr64"); pip then picks the
# newest release that has a wheel for this system
BIN=numpy,scipy,pandas,pyarrow,h5py,scikit-learn,statsmodels,torch,matplotlib,zarr,numcodecs,cooler,pillow,contourpy,kiwisolver
"$PY" -m pip install -q --only-binary="$BIN" -e "$REPO/packages/chromdata[contacts,anndata,remote]" \
    -e "$REPO/packages/uchrom" pytest maturin
rm -rf "$W/engine-sc/$ENGINE" "$W/wheels-sc/$ENGINE"
for pkg in uchrom-maps uchrom-recon; do
  (cd "$REPO/packages/$pkg" && "$BASE/venv-sc/bin/maturin" build --release --features python -o "$W/wheels-sc/$ENGINE")
done
"$PY" -m pip install -q --no-deps --target "$W/engine-sc/$ENGINE" "$W"/wheels-sc/"$ENGINE"/*.whl
"$PY" - <<'PYEOF'
import numpy, scipy, pandas, cooler, uchrom, uchrom_maps, uchrom_recon
print("numpy", numpy.__version__, "scipy", scipy.__version__, "pandas", pandas.__version__, "cooler", cooler.__version__)
print("uchrom", uchrom.__file__); print("uchrom_maps", uchrom_maps.__file__, uchrom_maps.default_threads())
print("uchrom_recon", uchrom_recon.__version__)
PYEOF
cd "$REPO/packages/uchrom" && "$PY" -m pytest tests -q -p no:cacheprovider 2>&1 | tail -15
cd "$REPO/packages/chromdata" && "$PY" -m pytest tests -q -p no:cacheprovider 2>&1 | tail -3
cd "$REPO/packages/uchrom-maps" && cargo test --release 2>&1 | grep -E "^test result|FAILED|panicked" | head -10
