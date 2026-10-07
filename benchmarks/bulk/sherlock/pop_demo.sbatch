#!/bin/bash
# IGM demo input (WTC11 2 Mb, male; GPL-3 data file fetched on demand) with the demo configuration:
# native IGM and EMber-pop one after the other on the same GPU (fit to the input and runtime; no truth).
# EMber-pop without imaging: an isotropic gyration prior of the demo nucleus (sigma = R / sqrt(5)).
#
#   sbatch --export=ALL,S=1000,SEED=1 benchmarks/bulk/sherlock/pop_demo.sbatch
#SBATCH --job-name=pop-demo
#SBATCH --partition=xiaojie,owners,gpu
#SBATCH -G 1
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env_pop.sh"
export UCHROM_IGM_GPU_BUDGET_GB=${UCHROM_IGM_GPU_BUDGET_GB:-8}
export UCHROM_IGM_CACHE=$UCHROM_DATA/igm
S=${S:-1000}
SEED=${SEED:-1}
STEPS=${STEPS:-1.0}
OUT=$POP/igm_demo
R=5500
SIG=$(python3 -c "print($R / 5 ** 0.5)")
MAXIT=${MAXIT:-10}
EP="{\"nucleus_shape\":\"none\",\"gyration_prior\":[$SIG,$SIG,$SIG],\"gyration_kspring\":0.1,\"advance_on_max_iterations\":true,\"noncontact_from_sigma\":5,\"noncontact_kspring\":1.0,\"max_iterations\":$MAXIT}"
if [ "${SKIP_IGM:-0}" != 1 ]; then
  $PY "$BK/igm_demo_run.py" --device gpu --n-structures "$S" --seed "$SEED" --steps-scale "$STEPS" \
    --out "$OUT/igm_S${S}_x${STEPS}_s$SEED"
fi
$PY "$BK/igm_demo_run.py" --device gpu --n-structures "$S" --seed "$SEED" --steps-scale "$STEPS" --params "$EP" \
  --out "$OUT/emberpop${TAG:-}_S${S}_x${STEPS}_s$SEED"
