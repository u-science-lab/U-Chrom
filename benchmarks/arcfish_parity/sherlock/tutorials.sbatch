#!/bin/bash
# Execute tutorial notebooks of the repo copy on a compute node; executed copies go to $AP/executed/.
#   NBS="tad_calling loop_calling" sbatch --export=ALL benchmarks/arcfish_parity/sherlock/tutorials.sbatch
# (REPO=<another repo copy> runs its notebooks instead of $AP/repo's; EXTRA_PIP="leidenalg umap-learn" adds packages
# the notebooks need beyond the agents' environment)
#SBATCH --job-name=tut-nb
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:30:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/arcfish_parity/logs/%x-%j.out
set -uo pipefail
AP=$SCRATCH/uchrom-nd/arcfish_parity
R=${REPO:-$AP/repo}
GH=$GROUP_HOME/$USER/uchrom-nd/agentbench
D=$SCRATCH/uchrom-nd/data
ENG=$SCRATCH/uchrom-nd/engine-sc/final          # uchrom_maps / uchrom_recon wheels built earlier (abi3)
echo "host=$(hostname) job=$SLURM_JOB_ID cpus=$SLURM_CPUS_PER_TASK repo=$R notebooks=$NBS"
mkdir -p "$L_SCRATCH/tmp" "$L_SCRATCH/pylib" "$AP/executed"
apptainer exec --containall --cleanenv --bind "$L_SCRATCH/tmp:/tmp" --bind "$L_SCRATCH/pylib:/pylib" \
  --bind "$AP:$AP" --bind "$D:$D" --bind "$ENG:/engine:ro" \
  --bind "$GH/venv-uchrom:/opt/venv:ro" --env TMPDIR=/tmp --env HOME=/tmp --env PIP_CACHE_DIR=/tmp/pip \
  --env OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK --env SLURM_CPUS_PER_TASK=$SLURM_CPUS_PER_TASK --env UCHROM_DATA=$D \
  "$GH/py312full.sif" bash -c "
set -uo pipefail
/opt/venv/bin/pip install -q --target /pylib nbconvert nbclient ipykernel nbformat openpyxl ${EXTRA_PIP:-} >/tmp/pip.log 2>&1 || { tail -20 /tmp/pip.log; exit 1; }
export PYTHONPATH=$R/packages/uchrom:$R/packages/chromdata:$R/packages/uchrom-browser:/engine:/pylib
/opt/venv/bin/python -m ipykernel install --prefix /pylib/jup --name python3 --display-name 'Python 3' >/dev/null
export JUPYTER_PATH=/pylib/jup/share/jupyter
/opt/venv/bin/python -c 'import uchrom, chromdata, nbconvert, ipykernel, matplotlib; print(\"uchrom\", uchrom.__file__); print(\"nbconvert\", nbconvert.__version__, \"ipykernel\", ipykernel.__version__, \"mpl\", matplotlib.__version__)'
/opt/venv/bin/python -c 'import uchrom_maps; print(\"uchrom_maps\", uchrom_maps.__file__)' || echo 'no uchrom_maps'
cd $R/tutorials
for nb in $NBS; do
  t0=\$(date +%s)
  /opt/venv/bin/python -m nbconvert --to notebook --execute --output-dir $AP/executed \
      --ExecutePreprocessor.timeout=7200 --ExecutePreprocessor.kernel_name=python3 \$nb.ipynb 2>&1 | tail -5
  echo \"== \$nb: \$(( \$(date +%s) - t0 )) s\"
done"
