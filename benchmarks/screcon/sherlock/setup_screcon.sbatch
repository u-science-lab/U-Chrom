#!/bin/bash
# One-off setup for the screcon benchmark on top of the Fig. 3a environments (fig3/sherlock/setup.sbatch):
# scipy in venv-main (metrics), the hickit 0.1.1 release binary, executable Si-C binaries, data check,
# and the unit tests (pytest in venv-main).
#
#   sbatch benchmarks/screcon/sherlock/setup_screcon.sbatch
#SBATCH --job-name=sc-setup
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
$PY -c "import scipy" 2>/dev/null || $BASE/venv-main/bin/pip install -q --only-binary=:all: "scipy<1.15"
$PY -c "import pytest" 2>/dev/null || $BASE/venv-main/bin/pip install -q --only-binary=:all: pytest
$PY -c "import numpy, scipy, pandas, uchrom_recon; print('venv-main', numpy.__version__, scipy.__version__, pandas.__version__, uchrom_recon.__version__)"
if [ ! -x "$HICKIT" ]; then
  (cd "$BASE" && curl -sL https://github.com/lh3/hickit/releases/download/v0.1.1/hickit-0.1.1_x64-linux.tar.bz2 | tar -jxf -)
fi
"$HICKIT" 2>&1 | head -2 || true
find "$SIC" -name '*.o' -exec chmod +x {} +
ls -la "$SIC/contact/1kb_prepare/gettargetcontact.o" "$SIC/MD_simulation/replica/bk/doall.sh"
for f in "$GEO/GSM2219497_Cell_1_contact_pairs.txt.gz" "$DATA/su2020_imr90/chromosome21.tsv" "$DATA/4DNFIFLJGGNR.csv"; do
  if [ -f "$f" ]; then echo "ok $f"; else echo "MISSING $f (rsync from the laptop's data directory, $UCHROM_DATA)"; fi
done
cd "$REPO" && $PY -m pytest -q benchmarks/screcon/tests -p no:cacheprovider
