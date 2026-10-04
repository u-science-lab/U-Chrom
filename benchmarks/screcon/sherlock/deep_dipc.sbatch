#!/bin/bash
# PREREG §10 criterion C3: a candidate engine setting on the Dip-C GM12878 development cells 1-3 at
# 100 kb with the §6 development checks (dip_real.sbatch steps full / mask / heldout), reusing that
# run's inputs read-only (references, masked tables, held-out splits in runs/diploid/real/res100000)
# and scoring the frozen `ember_nbr` runs already there the same way, side by side.
#
#   sbatch --export=ALL,LABEL=commit75,PARAMS='{"robust_dip_commit":0.75}',ENGINE=dev-xxxx benchmarks/screcon/sherlock/deep_dipc.sbatch
#SBATCH --job-name=hr-dipc
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-highres/benchmarks/screcon/sherlock/_env_highres.sh"
LABEL=${LABEL:?}
PARAMS=${PARAMS:?}
CELLS=${CELLS:-"01 02 03"}
SRC=$W/runs/diploid/real/res100000
O=$HR/dipc
nvidia-smi --query-gpu=name --format=csv,noheader || true
run() {   # table out seed
  [ -f "$2" ] && return 0
  mkdir -p "$(dirname "$2")"
  $PY $SC/run_diploid.py --method ember --params "$PARAMS" --contacts "$1" --res 100000 --device gpu --n-models 10 \
    --seed $3 --label $LABEL --out "$2" > "$2.log" 2>&1 || echo "FAILED $2"
}
for k in $CELLS; do
  C=$SRC/cell$k
  IN=$DATA/tan2018_gm12878/cells/gm12878_$k/gm12878_$k.pairs.gz
  X=$O/cell$k/$LABEL
  mkdir -p "$X" "$O/cell$k/scores"
  for s in 1 2; do run "$IN" "$X/full_s$s.npz" $s; done
  run "$C/mask/masked.pairs.gz" "$X/mask.npz" 1
  for f in 1 2 3; do run "$C/heldout/split/fold$f/train.pairs.gz" "$X/heldout_fold$f.npz" 1; done
  for m in $LABEL ember_nbr; do
    if [ $m = ember_nbr ]; then F1=$C/full/ember_nbr_s1.npz; F2=$C/full/ember_nbr_s2.npz; MK=$C/mask/ember_nbr.npz; H=$C/heldout/fold%s/ember_nbr.npz
    else F1=$X/full_s1.npz; F2=$X/full_s2.npz; MK=$X/mask.npz; H=$X/heldout_fold%s.npz; fi
    S=$O/cell$k/scores/$m
    [ -f "${S}_full.json" ] || $PY $SC/diploid_real.py score --refs "$C/ref/dipc.npz" "$C/ref/hickit.npz" --models "$F1" "$F2" \
      --labels ${m}_s1 ${m}_s2 --out "${S}_full.json" > /dev/null 2>&1 || echo "score full $m failed"
    [ -f "${S}_mask.json" ] || $PY $SC/diploid_real.py score --refs "$C/ref/dipc.npz" --models "$MK" --labels $m \
      --table "$C/mask/masked.pairs.gz" --mask "$C/mask/masked.pairs.gz.mask.npz" --out "${S}_mask.json" > /dev/null 2>&1 || echo "score mask $m failed"
    for f in 1 2 3; do
      [ -f "${S}_heldout_fold$f.json" ] || $PY $SC/heldout.py score --eval "$C/heldout/split/fold$f/eval_pairs.npz" \
        --models "$(printf "$H" $f)" --labels $m --out "${S}_heldout_fold$f.json" > /dev/null 2>&1 || echo "score heldout $m $f failed"
    done
    [ -f "${S}_seeds.json" ] || $PY $SC/highres.py score --a "$F1" --b "$F2" --pairs 50000 --out "${S}_seeds.json" > /dev/null 2>&1 || true
  done
  echo "cell $k done"
done
