#!/bin/bash
# One-off: the Python env of the Figure 2 benchmarks on Sherlock ($GROUP_HOME/$USER/uchrom-nd/venv-fig2).  The
# pure-Python libraries at the laptop series' versions (c_access.json: zarr 3.1.6, AnnData 0.12.11, SpatialData
# 0.7.2); the compiled ones (numpy, pandas, pyarrow, h5py) as binary wheels for the nodes' glibc 2.17 (CentOS 7:
# numpy >= 2.3 and the laptop's pandas / pyarrow have no such wheels), recorded with every result; xarray and dask
# for AnnData's lazy read.  Then the helpers' tests and a smoke test of the lazy backends.  pip belongs in a job,
# not on a login node.
#   sbatch benchmarks/fig2/sherlock/setup.sbatch
#SBATCH --job-name=fig2-setup
#SBATCH --partition=owners,normal
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-fig2lazy/benchmarks/fig2/sherlock/_env.sh"
if ! "$PY" -c "import anndata, spatialdata, xarray, dask, pytest" 2>/dev/null; then
    rm -rf "$VENV"                                     # this env only (a failed install leaves a partial one)
    python3 -m venv "$VENV"
    $PY -m pip install -q --upgrade pip
    $PY -m pip install -q --only-binary=:all: "zarr==3.1.6" "anndata==0.12.11" "spatialdata==0.7.2" numpy pandas \
        pyarrow h5py scipy psutil xarray dask scikit-learn pytest
fi
$PY -m pip freeze | grep -iE "^(numpy|pandas|pyarrow|zarr|anndata|spatialdata|h5py|scipy|xarray|dask|psutil)=="
cd "$REPO"
$PY -m pytest -q benchmarks/fig2/tests
$PY benchmarks/fig2/sherlock/smoke_lazy.py "$REPO" "${L_SCRATCH:-/tmp}"
du -sh "$VENV"
