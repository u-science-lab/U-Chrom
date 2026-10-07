#!/bin/bash
# Create venv-pop (first run) and (re)build the native engine wheel (GPU feature) into it.  Run after
# every engine change; submit from $SCRATCH/uchrom-nd/repo-pop.
#
#   sbatch benchmarks/bulk/sherlock/pop_setup.sbatch
#SBATCH --job-name=pop-setup
#SBATCH --partition=normal,owners
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env_pop.sh"
ml rust/1.97.1
export XDG_CACHE_HOME=$SCRATCH/.cache CARGO_HOME=$SCRATCH/.cache/cargo CARGO_TARGET_DIR=$L_SCRATCH/cargo-target
mkdir -p "$CARGO_HOME"
[ -d "$VENV" ] || python3 -m venv "$VENV"
P=$VENV/bin/pip
$P install -q --upgrade pip maturin
$P install -q --only-binary=:all: "numpy<2.3" "pandas<2.3" "scipy<1.15" "zarr>=3" "pyarrow<18" "h5py<3.13" \
    "scikit-learn<1.6" pytest
$P install -q --prefer-binary cooler
$P install -q --no-deps -e "$REPO/packages/chromdata" -e "$REPO/packages/uchrom"
(cd "$REPO/packages/uchrom-recon" && "$VENV/bin/maturin" build --release -o "$L_SCRATCH/wheels")
$P install -q --force-reinstall --no-deps "$L_SCRATCH"/wheels/uchrom_recon-*.whl
$PY - <<'EOF'
import uchrom_recon as un, numpy, json
p = un.default_igm_params()
print("uchrom_recon", un.__version__, "gpu build:", un.HAS_GPU, "ember-pop options:",
      all(k in p for k in ("noncontact_kspring", "assignment", "rg_cap")), "numpy", numpy.__version__)
EOF
echo done
