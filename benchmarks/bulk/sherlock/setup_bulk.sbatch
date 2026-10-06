#!/bin/bash
# One-off setup of the bulk deconvolution benchmark on top of venv-main (fig3 setup.sbatch):
# binary wheels of cooler / h5py / hic-straw / fsspec / scikit-learn (numpy, pandas, scipy kept at
# their pins), the imaging truths (Su 2020 genome-scale + chr21, Takei 2021 1 Mb; 0.5 GB from Zenodo /
# 4DN), and the unit tests.
#
#   sbatch benchmarks/bulk/sherlock/setup_bulk.sbatch
#SBATCH --job-name=bk-setup
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-deconv/benchmarks/bulk/sherlock/_env.sh"
PIP=$VENV/bin/pip
CONS=$(mktemp)
$PY -c "import numpy, pandas, scipy; print(f'numpy=={numpy.__version__}\npandas=={pandas.__version__}\nscipy=={scipy.__version__}')" > "$CONS"
cat "$CONS"
# prefer binary wheels, but allow pure-Python sdists (cooler needs asciitree, sdist only: with
# --only-binary=:all: pip backtracked to cooler 0.4.0); numpy / pandas / scipy stay at their pins
$PIP install -q --prefer-binary -c "$CONS" "cooler>=0.9.3" h5py fsspec requests aiohttp scikit-learn pytest
# hic-straw (only for .hic inputs: kr_check.py's GEO cases): optional, wheels exist for manylinux x86-64
$PIP install -q --only-binary=:all: -c "$CONS" hic-straw || echo "hic-straw: no binary wheel - .hic inputs unavailable"
$PY -c "import cooler, h5py, fsspec, sklearn, numpy, scipy, pandas; print('venv-main', cooler.__version__, h5py.__version__, sklearn.__version__, numpy.__version__, scipy.__version__, pandas.__version__)"
$PY -c "import hicstraw; print('hicstraw ok')" || true
$PY -m uchrom.datasets fetch su2020_genome su2020_chr21 takei2021_1mb --root "$DATA"
cd "$REPO" && $PY -m pytest -q benchmarks/bulk/tests benchmarks/screcon/tests -p no:cacheprovider
