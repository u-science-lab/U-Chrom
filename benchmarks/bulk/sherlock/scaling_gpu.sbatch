#!/bin/bash
# Speed / memory of the native IGM protocol on one 80 GB H100: one A-step at sigma 0.01 +
# one full M-step (47,000 MD steps + CG) per case.
#   demo (3,008 beads)              x S = 100, 1,000, 10,000
#   synthetic 1 Mb (6,088 beads)    x S = 100, 1,000, 10,000   (user default: 1 Mb x 10,000 must fit)
#   synthetic 200 kb (~30,900 beads) x S = 100, 1,000           (IGM paper setting: 200 kb x 1,000)
# The synthetic matrices are timing inputs only (see igm_scaling.py).  Estimated total
# ~6-10 GPU-h (the 1 Mb x 10,000 M-step alone ~0.5-1.5 h).
#
#   sbatch benchmarks/bulk/sherlock/scaling_gpu.sbatch
#SBATCH --job-name=bulk-scaling
#SBATCH --partition=xiaojie
#SBATCH -G 1
#SBATCH --time=16:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env.sh"
export UCHROM_IGM_GPU_BUDGET_GB=60
OUT=$RUNS/scaling/igm_scaling_h100.json
$PY "$BK/igm_scaling.py" --hcs "$HCS" --device gpu --inputs demo synthetic:1000000 --structures 100 1000 10000 --out "$OUT"
$PY "$BK/igm_scaling.py" --hcs "$HCS" --device gpu --inputs synthetic:200000 --structures 100 1000 --out "$OUT"
