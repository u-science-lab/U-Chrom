#!/bin/bash
# Real IMR90 unit of the EMber-pop test (PREREG_POP.md section 10): the imaging calibration from the 894
# Su 2020 development cells, the truth = the 893 test-half cells, the input = pop_build_real.sbatch's
# input_3mb.npz.  Builds files only; runs no method.
#
#   sbatch benchmarks/bulk/sherlock/pop_prepare_real.sbatch
#SBATCH --job-name=pop-prep-real
#SBATCH --partition=normal,owners
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env_pop.sh"
D=$POP/real_imr90
[ -f "$D/bulk_cells.npz" ] || $PY "$BK/forward.py" truth --dataset su2020_genome --split-set dev_bulk dev_truth --out "$D/bulk_cells.npz"
[ -f "$D/truth.npz" ] || $PY "$BK/forward.py" truth --dataset su2020_genome --split-set test_bulk test_truth --out "$D/truth.npz"
[ -f "$D/real.npz" ] || cp "$D/input_3mb.npz" "$D/real.npz"
ls -la "$D"
