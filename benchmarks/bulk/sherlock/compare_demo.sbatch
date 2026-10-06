#!/bin/bash
# Score / compare every finished demo population (ours GPU / CPU, original IGM) on the
# input and against each other (seed-to-seed spread of each code as the reference).
#
#   sbatch benchmarks/bulk/sherlock/compare_demo.sbatch
#SBATCH --job-name=bulk-compare
#SBATCH --partition=xiaojie,owners,normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env.sh"
S=${S:-1000}
OURS=$(ls -d "$RUNS"/igm_demo/ours_gpu_S${S}_s* 2>/dev/null || true)
IGM=$(ls "$RUNS"/igm_demo/orig_S${S}_s*/igm-model.hss 2>/dev/null || true)
echo "ours: $OURS"; echo "igm: $IGM"
$PY "$BK/igm_demo_compare.py" --hcs "$HCS" --ours $OURS --igm $IGM --out "$RUNS/igm_demo/compare_S${S}.json"
