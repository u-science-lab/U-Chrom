#!/bin/bash
# PREREG §10 development: per scMicro-C development cell ($CELL) and variant ($VARIANTS), EMber at
# 100 kb and 20 kb, seeds 1 and 2 (10 models), scored seed vs seed and vs the authors' hickit
# (highres.py score), and the held-out check at 100 kb (one split of the original table, fold 1;
# the variant applied to the training table).  Variants:
#   frozen      the frozen table, engine defaults (100 / 20 kb runs reused from runs/highres/<cell>/ladder)
#   ds1m        down-sampled to 1.0 M contacts (diagnostic)
#   nosr        cis contacts < 20 kb removed (diagnostic)
#   cXXdrop / cXXkeep   prototype of robust_dip_commit (XX = 75: tau 0.75): deep_diploid.py derive --commit 0.XX --rest drop|keep
#   isoN        prototype of dip_isolation_nei: --iso-nei N --iso-radius 10 Mb
#   nucdyn      the NucDynamics 2017 diploid protocol on the frozen table (C2 comparator; held-out only)
#   engine:<name>:<json>  the native implementation: engine parameters <json> on the frozen table
#
#   sbatch --export=ALL,CELL=GSM5764669_cell_035,VARIANTS="ds1m nosr c075drop" benchmarks/screcon/sherlock/deep_dev.sbatch
#SBATCH --job-name=hr-dev
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-highres/benchmarks/screcon/sherlock/_env_highres.sh"
CELL=${CELL:?}
# VARIANTS: space separated; or VARIANTS_FILE: one per line (needed for engine:<name>:<json> with commas,
# which sbatch --export cannot pass)
if [ -n "${VARIANTS_FILE:-}" ]; then VARIANTS=$(grep -v '^#' "$VARIANTS_FILE" | tr '\n' ' '); fi
VARIANTS=${VARIANTS:?}
RESS=${RESS:-"100000 20000"}
NM=${NM:-10}
IN=$WU/$CELL.impute.pairs.gz
D=$HR/dev/$CELL
mkdir -p "$D"
nvidia-smi --query-gpu=name --format=csv,noheader || true

sizes() { $PY -c "import sys; r=float(sys.argv[1])/1e6; L=[8,4,2,0.4,0.2,0.1,0.05,0.02,0.01,0.005]; print(','.join(f'{s:g}' for s in [s for s in L if s>r*1.0001]+[r]))" "$1"; }
run() {   # table res seed out method params
  local tab=$1 res=$2 seed=$3 out=$4 method=${5:-ember} params=${6:-"{}"}
  [ -f "$out" ] && return 0
  mkdir -p "$(dirname "$out")"
  $PY $SC/run_diploid.py --method $method --params "$params" --contacts "$tab" --sizes "$(sizes $res)" --device gpu \
    --n-models $NM --seed $seed --label $method --out "$out" > "$out.log" 2>&1 || echo "FAILED $out"
  echo "$out $(grep -o 'in [0-9.]* s' "$out.log" | tail -1)"
}
derive() {   # variant table out
  local v=$1 tab=$2 out=$3
  [ -f "$out" ] && return 0
  case $v in
    ds1m) a="--downsample 1000000" ;;
    nosr) a="--min-cis-sep 20000" ;;
    c*drop) a="--commit 0.${v:1:2} --rest drop" ;;
    c*keep) a="--commit 0.${v:1:2} --rest keep" ;;
    iso*) a="--iso-nei ${v#iso} --iso-radius 10000000" ;;
    *) echo "unknown variant $v"; return 1 ;;
  esac
  $PY $SC/deep_diploid.py derive --contacts "$tab" $a --out "$out" | tee "$out.json"
}

# held-out split of the original table (once per cell)
S=$D/split
[ -f "$S/fold1/eval_pairs.npz" ] || $PY $SC/diploid_heldout.py split --contacts "$IN" --out "$S" --folds 1 --seed 1 \
  --eval-res 100000 --cis-same-homolog 2000000 > "$D/split.log" 2>&1 || echo "split failed"

for v in $VARIANTS; do
  echo "== $CELL $v $(date)"
  V=$D/${v%%:*}
  [ "${v%%:*}" = engine ] && V=$D/$(echo "$v" | cut -d: -f2)
  mkdir -p "$V"
  method=ember; params="{}"; tab=$IN; train=$S/fold1/train.pairs.gz
  case $v in
    frozen) ;;
    nucdyn) method=nucdyn ;;
    engine:*) params=$(echo "$v" | cut -d: -f3-) ;;
    *) derive "$v" "$IN" "$V/table.pairs.gz" && tab=$V/table.pairs.gz
       derive "$v" "$S/fold1/train.pairs.gz" "$V/train.pairs.gz" && train=$V/train.pairs.gz ;;
  esac
  if [ "$v" != nucdyn ]; then
    for res in $RESS; do
      for s in 1 2; do
        out=$V/res${res}_s$s.npz
        if [ "$v" = frozen ] && [ -f "$HR/$CELL/ladder/res${res}_s$s.npz" ]; then
          for f in "" .json .log; do [ -e "$out$f" ] || ln -s "$HR/$CELL/ladder/res${res}_s$s.npz$f" "$out$f"; done
        fi
        run "$tab" $res $s "$out" $method "$params"
      done
      ref=$HR/$CELL/ref/hickit_res$res.npz
      [ -f "$V/score_res$res.json" ] || $PY $SC/highres.py score --a "$V/res${res}_s1.npz" --b "$V/res${res}_s2.npz" \
        $( [ -f "$ref" ] && echo --ref "$ref" ) --pairs 50000 --out "$V/score_res$res.json" || echo "score failed"
    done
  fi
  run "$train" 100000 1 "$V/heldout_res100000.npz" $method "$params"
  for ev in eval_pairs eval_pairs_cis; do
    [ -f "$V/heldout_$ev.json" ] || $PY $SC/heldout.py score --eval "$S/fold1/$ev.npz" --models "$V/heldout_res100000.npz" \
      --labels "$v" --out "$V/heldout_$ev.json" > /dev/null 2>&1 || echo "heldout score $ev failed"
  done
done
echo "done $(date)"
