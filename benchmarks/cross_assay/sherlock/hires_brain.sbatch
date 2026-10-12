#!/bin/bash
# HiRES adult brain (Liu et al. 2023) on Sherlock: fetch the registered `hires2023_meta` (70 MB) and
# `hires2023_brain` (the 426 brain cells' pairs + 20 kb diploid structures, 4.5 GB, GEO GSE223917) into
# $UCHROM_DATA/hires2023/raw/GSE223917 for the EMber reconstructions of benchmarks/cross_assay.  GEO gives no md5:
# the md5 of every file is written next to them (cells_md5.txt) once downloaded.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-xa benchmarks/cross_assay/sherlock/hires_brain.sbatch
#SBATCH --job-name=hires-brain-fetch
#SBATCH --partition=xiaojie,normal
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=/scratch/users/wzxu/uchrom-nd/runs/xassay/logs/%x-%j.out
set -euo pipefail
ml purge
ml python/3.12.1
W=$SCRATCH/uchrom-nd
PY=${XA_PY:-$GROUP_HOME/$USER/uchrom-nd/venv-consensus/bin/python}
export UCHROM_DATA=$W/data
export XDG_CACHE_HOME=$SCRATCH/.cache
export PYTHONPATH=$REPO/packages/uchrom:$REPO/packages/chromdata${PYTHONPATH:+:$PYTHONPATH}
echo "host=$(hostname) job=${SLURM_JOB_ID:-none} repo=$REPO data=$UCHROM_DATA"
t0=$SECONDS
"$PY" -u -m uchrom.datasets fetch hires2023_meta hires2023_brain
echo "=== fetched in $((SECONDS - t0)) s"
D=$UCHROM_DATA/hires2023/raw/GSE223917
( cd "$D/cells" && ls GSM*_Val[ab]B8w* | sort | xargs md5sum ) > "$D/cells_brain_md5.txt"
echo "files: $(wc -l < "$D/cells_brain_md5.txt"), size: $(du -ch "$D"/cells/GSM*_Val[ab]B8w* | tail -1 | cut -f1)"
ls -la "$D"
