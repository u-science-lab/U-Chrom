#!/bin/bash
# Dip-C GM12878 (Tan 2018): diploid reconstructions at $RES (default 100 kb) on one GPU, per cell of $CELLS
# (default: the development cells 1 2 3, PREREG.md §6), input = the authors' hickit phased pairs
# (cells/gm12878_<k>/gm12878_<k>.pairs.gz).  Steps per cell (each skipped when its output exists):
#   ref       published structures on the grid: Dip-C impute3.round4.clean.3dg (+ rep1, rep2) and hickit 3dg
#   full      $METHODS on all contacts, 10 models, seeds 1 and 2 (agreement with the published structures,
#             precision, run-to-run)
#   mask      phase hold-back: 10 % of the phased ends unphased (seed 1); $METHODS + hickit's imputation
#   heldout   3 folds x 10 % reads (diploid_heldout.py; strict + cis < 2 Mb same-homolog positives);
#             $METHODS + hickit (Dip-C pipeline) on each training table, scored with heldout.py
#   METHODS: ember (diploid split), ember_nosplit, nucdyn (2017 ambiguous restraints)
#
#   sbatch benchmarks/screcon/sherlock/dip_real.sbatch                 # dev cells
#   sbatch --export=ALL,CELLS="1",STEPS="full" ...
#SBATCH --job-name=dp-real
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=10
#SBATCH --mem=96G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-diploid/benchmarks/screcon/sherlock/_env_diploid.sh"
CELLS=${CELLS:-"1 2 3"}
RES=${RES:-100000}
STEPS=${STEPS:-"ref full mask heldout"}
METHODS=${METHODS:-"ember ember_nosplit nucdyn"}
NM=${NM:-10}
O=$DP/real/res$RES
nvidia-smi --query-gpu=name --format=csv,noheader || true

run_method() {   # method table out seed
  local m=$1 tab=$2 out=$3 seed=$4
  [ -f "$out" ] && return 0
  mkdir -p "$(dirname "$out")"
  case $m in
    ember)         $PY $SC/run_diploid.py --method ember --contacts "$tab" --res $RES --device gpu --n-models $NM --seed $seed --label $m --out "$out" ;;
    ember_nosplit) $PY $SC/run_diploid.py --method ember --params '{"robust_dip_split": false}' --contacts "$tab" --res $RES --device gpu --n-models $NM --seed $seed --label $m --out "$out" ;;
    nucdyn)        $PY $SC/run_diploid.py --method nucdyn --contacts "$tab" --res $RES --device gpu --n-models $NM --seed $seed --label $m --out "$out" ;;
    hickit)        $PY $SC/run_hickit.py --hickit "$HICKIT" --diploid --contacts "$tab" --res $RES --n-models $NM --seed $seed --jobs 10 --out "$out" ;;
  esac > "${out%.npz}.log" 2>&1 || echo "FAILED $m $tab: $(tail -2 "${out%.npz}.log")"
}

for k in $CELLS; do
  kk=$(printf %02d $k)
  IN=$TAN18/cells/gm12878_$kk/gm12878_$kk.pairs.gz
  [ -f "$IN" ] || { echo "no input for cell $k"; continue; }
  C=$O/cell$kk
  mkdir -p "$C"/{ref,full,mask,heldout,scores}
  dipc=$(ls "$TAN18"/GSM*_gm12878_$kk.impute3.round4.clean.3dg.txt.gz 2>/dev/null | sort -u || true)   # main + rep1 + rep2
  if [[ " $STEPS " == *" ref "* ]]; then
    [ -f "$C/ref/dipc.npz" ] || $PY $SC/diploid_real.py ref --res $RES --contacts "$IN" --out "$C/ref/dipc.npz" $dipc
    [ -f "$C/ref/hickit.npz" ] || $PY $SC/diploid_real.py ref --res $RES --contacts "$IN" --out "$C/ref/hickit.npz" "$TAN18/cells/gm12878_$kk/gm12878_$kk.3dg.gz"
  fi
  if [[ " $STEPS " == *" full "* ]]; then
    for m in $METHODS; do for s in 1 2; do run_method $m "$IN" "$C/full/${m}_s$s.npz" $s; done; done
    models=(); labels=()
    for m in $METHODS; do for s in 1 2; do [ -f "$C/full/${m}_s$s.npz" ] && { models+=("$C/full/${m}_s$s.npz"); labels+=("${m}_s$s"); }; done; done
    [ ${#models[@]} -gt 0 ] && $PY $SC/diploid_real.py score --refs "$C/ref/dipc.npz" "$C/ref/hickit.npz" --models "${models[@]}" --labels "${labels[@]}" \
      --out "$C/scores/full.json" > "$C/scores/full.log" 2>&1 || echo "score full failed"
  fi
  if [[ " $STEPS " == *" mask "* ]]; then
    MT=$C/mask/masked.pairs.gz
    [ -f "$MT" ] || $PY $SC/diploid_real.py mask --contacts "$IN" --frac 0.1 --seed 1 --out "$MT"
    for m in $METHODS hickit; do run_method $m "$MT" "$C/mask/$m.npz" 1; done
    models=(); labels=()
    for m in $METHODS hickit; do [ -f "$C/mask/$m.npz" ] && { models+=("$C/mask/$m.npz"); labels+=("$m"); }; done
    [ ${#models[@]} -gt 0 ] && $PY $SC/diploid_real.py score --refs "$C/ref/dipc.npz" "$C/ref/hickit.npz" --models "${models[@]}" --labels "${labels[@]}" \
      --table "$MT" --mask "$MT.mask.npz" --out "$C/scores/mask.json" > "$C/scores/mask.log" 2>&1 || echo "score mask failed"
  fi
  if [[ " $STEPS " == *" heldout "* ]]; then
    [ -f "$C/heldout/split/fold3/eval_pairs.npz" ] || $PY $SC/diploid_heldout.py split --contacts "$IN" --out "$C/heldout/split" \
      --folds 3 --seed 1 --cis-same-homolog 2000000 > "$C/heldout/split.log" 2>&1
    for f in 1 2 3; do
      F=$C/heldout/split/fold$f
      for m in $METHODS hickit; do run_method $m "$F/train.pairs.gz" "$C/heldout/fold$f/$m.npz" 1; done
      models=(); labels=()
      for m in $METHODS hickit; do [ -f "$C/heldout/fold$f/$m.npz" ] && { models+=("$C/heldout/fold$f/$m.npz"); labels+=("$m"); }; done
      [ ${#models[@]} -gt 0 ] || continue
      for ev in eval_pairs eval_pairs_cis; do
        $PY $SC/heldout.py score --eval "$F/$ev.npz" --models "${models[@]}" --labels "${labels[@]}" \
          --out "$C/scores/heldout_fold${f}_$ev.json" > /dev/null 2>&1 || echo "score heldout fold $f $ev failed"
      done
    done
  fi
  echo "cell $k done"
done
