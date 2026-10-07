#!/bin/bash
# Real IMR90 input of the EMber-pop test (PREREG_POP.md section 3): Rao 2014 IMR90, 4DN 4DNFIR1JDZH7
# (GRCh38), the IGM SI preprocessing (20 kb from the 10 kb level, KR at 20 kb) onto 3 Mb bins centred on
# the 1,041 Su 2020 loci, target = the mean row sum of the exact C1 matrix of the 894 Su development
# cells (32.885, pop_bench: su_devall).  Builds the input only; no method is run on it before the freeze.
#
#   sbatch --export=ALL,LOCI=$SCRATCH/uchrom-nd/runs/pop/su_dev/truth.npz benchmarks/bulk/sherlock/pop_build_real.sbatch
#SBATCH --job-name=pop-real
#SBATCH --partition=normal,owners
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=192G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env_pop.sh"
$VENV/bin/pip install -q --prefer-binary cooler
MC=$UCHROM_DATA/rao2014_imr90/4DNFIR1JDZH7.mcool
OUT=$POP/real_imr90
mkdir -p "$OUT"
FINE=$OUT/fine_20kb.npz
TARGET=${TARGET:-32.885442022798166}
if [ ! -f "$FINE" ]; then
  $PY $BK/real_inputs.py preprocess --source "$MC" --fine 20000 --coarse-bins "$LOCI:centered:3000000" \
    --target "$TARGET" --fine-out "$FINE" --out "$OUT/input_3mb.npz"
else
  $PY $BK/real_inputs.py preprocess --fine-in "$FINE" --coarse-bins "$LOCI:centered:3000000" \
    --target "$TARGET" --out "$OUT/input_3mb.npz"
fi
ls -la "$OUT"
