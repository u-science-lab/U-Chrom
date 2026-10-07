#!/bin/bash
# Inputs of one EMber-pop unit (PREREG_POP.md section 3): the bulk cells and the truth cells of a split
# (pop_split.py) and the bulk inputs C1-C3 made from the bulk cells only.  Builds inputs; runs no method.
#
#   sbatch --export=ALL,UNIT=su_test,DATASET=su2020_genome,BULK=test_bulk,TRUTH=test_truth,BINS=centered:3000000 \
#       benchmarks/bulk/sherlock/pop_prepare.sbatch
#   sbatch --export=ALL,UNIT=takei_test,DATASET=takei2021_1mb,BULK=test_bulk,TRUTH=test_truth,BINS=centered:1000000 \
#       benchmarks/bulk/sherlock/pop_prepare.sbatch
#SBATCH --job-name=pop-prep
#SBATCH --partition=normal,owners
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env_pop.sh"
D=$POP/$UNIT
mkdir -p "$D"
case $DATASET in
  su2020_genome) DATA_FILE=$UCHROM_DATA/su2020_imr90/genomic-scale.tsv ;;
  takei2021_1mb) DATA_FILE=$UCHROM_DATA/4DNFIFLJGGNR.csv ;;
esac
[ -f "$D/bulk_cells.npz" ] || $PY "$BK/forward.py" truth --dataset "$DATASET" --data "$DATA_FILE" --split-set "$BULK" --out "$D/bulk_cells.npz"
[ -f "$D/truth.npz" ] || $PY "$BK/forward.py" truth --dataset "$DATASET" --data "$DATA_FILE" --split-set "$TRUTH" --out "$D/truth.npz"
L=$($PY -c "import numpy as np; print(len(np.load('$D/bulk_cells.npz')['chrom']))")
READS=$((200 * L * (L - 1) / 2))
[ -f "$D/C1.npz" ] || $PY "$BK/forward.py" bulk --truth "$D/bulk_cells.npz" --bins "$BINS" --kernel step --depth inf --out "$D/C1.npz"
[ -f "$D/C2.npz" ] || $PY "$BK/forward.py" bulk --truth "$D/bulk_cells.npz" --bins "$BINS" --kernel gauss --depth inf --out "$D/C2.npz"
[ -f "$D/C3.npz" ] || $PY "$BK/forward.py" bulk --truth "$D/bulk_cells.npz" --bins "$BINS" --kernel step --depth "$READS" \
    --eps 0.1 --bias-sd 0.2 --fine-sub 10 --seed 1 --out "$D/C3.npz"
ls -la "$D"
