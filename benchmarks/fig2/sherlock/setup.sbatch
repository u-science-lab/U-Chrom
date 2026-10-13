#!/bin/bash
# One-off: the Python env of the Figure 2 benchmarks on Sherlock ($GROUP_HOME/$USER/uchrom-nd/venv-fig2), with the
# library versions of the laptop series (c_access.json: numpy 2.4.3, pandas 2.3.3, pyarrow 23.0.1, zarr 3.1.6,
# AnnData 0.12.11, SpatialData 0.7.2, h5py 3.16.0) and what AnnData's lazy read needs (xarray, dask); then the
# helpers' tests and a smoke test of the lazy backends.  pip belongs in a job, not on a login node.
#   sbatch benchmarks/fig2/sherlock/setup.sbatch
#SBATCH --job-name=fig2-setup
#SBATCH --partition=owners,normal
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-fig2lazy/benchmarks/fig2/sherlock/_env.sh"
[ -x "$PY" ] || python3 -m venv "$VENV"
$PY -m pip install -q --upgrade pip
$PY -m pip install -q "numpy==2.4.3" "pandas==2.3.3" "pyarrow==23.0.1" "zarr==3.1.6" "anndata==0.12.11" \
    "spatialdata==0.7.2" "h5py==3.16.0" "scipy==1.17.1" "psutil==7.2.2" xarray dask scikit-learn pytest
$PY -m pip freeze | grep -iE "^(numpy|pandas|pyarrow|zarr|anndata|spatialdata|h5py|scipy|xarray|dask|psutil)=="
cd "$REPO"
$PY -m pytest -q benchmarks/fig2/tests
$PY benchmarks/fig2/sherlock/smoke_lazy.py "$REPO" "${L_SCRATCH:-/tmp}"
du -sh "$VENV"
