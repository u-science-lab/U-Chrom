#!/bin/bash
#SBATCH --job-name=arcfish-compare
#SBATCH --partition=xiaojie,normal
#SBATCH --time=00:20:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/arcfish_parity/logs/%x-%j.out
AP=$SCRATCH/uchrom-nd/arcfish_parity
GH=$GROUP_HOME/$USER/uchrom-nd/agentbench
apptainer exec --containall --cleanenv --bind "$AP:$AP" --bind "$GH/venv-uchrom:/opt/venv:ro" \
  --env PYTHONPATH="$AP/repo/packages/uchrom:$AP/repo/packages/chromdata:$AP/repo/benchmarks" \
  "$GH/py312full.sif" /opt/venv/bin/python -u "$AP/repo/benchmarks/arcfish_parity/compare.py" --runs "$AP/runs/$RUN" --out "$AP/runs/$RUN/parity.json"
