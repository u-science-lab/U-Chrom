#!/bin/bash
# Once: the authors' ArcFISH (github.com/hyuyu104/ArcFISH at a21d889, pinned dependencies) in its own environment, the
# oracle of benchmarks/arcfish_parity; and the inputs ArcFISH's own tutorials use (Takei 2021 mESC replicate 2,
# 4DN 4DNFIQXONUUH; Su 2020 chromosome 2 p-arm, Zenodo 3928890) next to the registered ones already on Sherlock.
#
#   sbatch benchmarks/arcfish_parity/sherlock/setup.sbatch
#SBATCH --job-name=arcfish-setup
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/arcfish_parity/logs/%x-%j.out
set -euo pipefail
GH=$GROUP_HOME/$USER/uchrom-nd/agentbench
SIF=$GH/py312full.sif
ENV=$GH/venv-arcfish
D=$SCRATCH/uchrom-nd/data
mkdir -p "$L_SCRATCH/tmp"
rm -rf "$ENV"; mkdir -p "$ENV"
# the package's own build installs only its top-level module (no subpackages), so it runs from its source tree
# (PYTHONPATH=/opt/venv/src), with the dependencies its pyproject.toml pins
git clone -q https://github.com/hyuyu104/ArcFISH "$ENV/src" && (cd "$ENV/src" && git checkout -q a21d889321826517876c6c81e7aade10237a10ae)
apptainer exec --containall --bind "$ENV:/opt/venv" --bind "$L_SCRATCH/tmp:/tmp" --env TMPDIR=/tmp \
  --env PIP_CACHE_DIR=/tmp/pip --env HOME=/tmp "$SIF" bash -c "
python -m venv /opt/venv && /opt/venv/bin/pip install -q --upgrade pip &&
/opt/venv/bin/pip install -q 'numpy>=1.26.4' 'pandas>=2.2.1' 'scipy>=1.12.0' 'matplotlib>=3.8.3' 'seaborn>=0.13.2' \
  'statsmodels==0.14.1' 'scikit-learn>=1.4.1' 'anndata==0.10.8' 'dask==2025.1.0' 'requests>=2.31.0' pyarrow &&
PYTHONPATH=/opt/venv/src /opt/venv/bin/python -c 'import arcfish, sklearn, statsmodels, scipy, numpy, pandas, anndata, dask; print(\"arcfish\", arcfish.__version__, \"sklearn\", sklearn.__version__, \"statsmodels\", statsmodels.__version__, \"scipy\", scipy.__version__, \"numpy\", numpy.__version__, \"pandas\", pandas.__version__, \"anndata\", anndata.__version__, \"dask\", dask.__version__)'"
apptainer exec --containall --bind "$ENV:/opt/venv" "$SIF" /opt/venv/bin/pip freeze > "$GH/venv-arcfish.freeze.txt"

# inputs, fetched from their registered sources into the data directory: Takei 2021 replicate 2 (takei_rep2), Su 2020
# chr2 p-arm (su2020_chr2_parm), Bintu 2018 (bintu_imr90); replicate 1 (takei) and su2020_chr21 are there already
AP=$SCRATCH/uchrom-nd/arcfish_parity          # the repo copy (its registry knows these sources)
apptainer exec --containall --cleanenv --bind "$GH/venv-uchrom:/opt/venv:ro" --bind "$D:/data" --env UCHROM_DATA=/data \
  --bind "$AP:$AP" --env PYTHONPATH="$AP/repo/packages/uchrom:$AP/repo/packages/chromdata" \
  "$SIF" /opt/venv/bin/python -c "import uchrom.datasets as ds; [print(ds.fetch(n)) for n in ('takei_rep2', 'su2020_chr2_parm', 'bintu_imr90')]"
ls -la "$D"/4DNFI*.csv "$D"/su2020_imr90 "$D"/IMR90_chr21-18-20Mb.csv || true
