#!/bin/bash
# High-resolution diploid EMber on scMicro-C GM12878 (Wu et al. 2025): a Fig. 3 demonstration, not part of
# the pre-registered tests.  Frozen EMber diploid (run_diploid.py --method ember: engine defaults, no
# external phase prior, ploidy "auto"), one GPU, per cell of $CELLS (GSM<id>_cell_<nnn>):
#   ladder   final resolution 100 / 20 / 10 / 5 kb (the extended 2017 schedule of Fig. 3a, truncated above the
#            target, target appended), $NM models, seeds 1 and 2; wall time, peak GPU memory (nvidia-smi, 1 s)
#   ref      the authors' hickit structures (5 / 10 / 20 kb .3dg) on the same grids (diploid_real.py ref)
#   score    seed 1 vs seed 2 and each seed vs the authors' structure, per copy chain and whole genome
#            (highres.py score: random particle pairs)
#   explore  2 kb and 1 kb, $NM_EXPLORE models, seed 1 (memory / time permitting)
#   compare  the NucDynamics 2017 protocol with diploid ambiguous restraints (run_diploid.py --method nucdyn)
#            at 100 kb, seeds 1 and 2, scored like the ladder (comparator for the agreement numbers)
#   heldout  10 kb: one fold of 10 % reads held out (diploid_heldout.py split --eval-res 10000,
#            --cis-same-homolog 2 Mb as dip_real.sbatch), EMber on the training table, heldout.py score
#
#   sbatch --export=ALL,CELLS="GSM5764669_cell_035" benchmarks/screcon/sherlock/highres_run.sbatch
#SBATCH --job-name=hr-run
#SBATCH --partition=xiaojie,gpu
#SBATCH -C GPU_SKU:H100_SXM5
#SBATCH -G 1
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=200G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-highres/benchmarks/screcon/sherlock/_env_highres.sh"
CELLS=${CELLS:?CELLS=GSM..._cell_nnn}
STEPS=${STEPS:-"ladder ref score explore heldout"}
LADDER=${LADDER:-"100000 20000 10000 5000"}
EXPLORE=${EXPLORE:-"2000 1000"}
NM=${NM:-10}
NM_EXPLORE=${NM_EXPLORE:-5}
REF_TAGS=${REF_TAGS:-"100000:20kb 20000:20kb 10000:10kb 5000:5kb"}  # resolution : tag in the authors' 3dg file names
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

sizes() {   # final resolution (bp) -> schedule (Mb, comma separated)
  $PY - "$1" <<'EOF'
import sys
r = float(sys.argv[1]) / 1e6
ladder = [8, 4, 2, 0.4, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001]
print(",".join(f"{s:g}" for s in [s for s in ladder if s > r * 1.0001] + [r]))
EOF
}

run_ember() {   # table res seed n_models out [method: ember (default) | nucdyn]
  local tab=$1 res=$2 seed=$3 nm=$4 out=$5 method=${6:-ember}
  [ -f "$out" ] && return 0
  mkdir -p "$(dirname "$out")"
  nvidia-smi --query-gpu=timestamp,memory.used --format=csv,noheader,nounits -l 1 > "$out.gpumem.csv" &
  local mon=$!
  local t0=$(date +%s)
  $PY $SC/run_diploid.py --method $method --contacts "$tab" --sizes "$(sizes $res)" --device gpu --n-models $nm \
    --seed $seed --label $method --out "$out" > "$out.log" 2>&1 || echo "FAILED: $out (see $out.log)"
  kill $mon 2>/dev/null || true
  echo "$out: $(( $(date +%s) - t0 )) s, peak GPU MiB $(cut -d, -f2 "$out.gpumem.csv" | sort -n | tail -1)"
}

for cell in $CELLS; do
  IN=$WU/$cell.impute.pairs.gz
  C=$HR/$cell
  mkdir -p "$C"
  echo "== $cell $(date)"
  if [[ " $STEPS " == *" ladder "* ]]; then
    for res in $LADDER; do for s in 1 2; do run_ember "$IN" $res $s $NM "$C/ladder/res${res}_s$s.npz"; done; done
  fi
  if [[ " $STEPS " == *" ref "* ]]; then
    for rt in $REF_TAGS; do
      res=${rt%%:*}; tag=${rt##*:}
      # the authors' five hickit replicate runs (clean = Dip-C clean3 filter), one model each
      f=$(ls "$WU"/3dg/${cell}_${tag}_[0-9].clean.3dg.txt.gz 2>/dev/null || true)
      [ -n "$f" ] || { echo "no $tag 3dg for $cell"; continue; }
      [ -f "$C/ref/hickit_res$res.npz" ] || $PY $SC/diploid_real.py ref --res $res --contacts "$IN" \
        --out "$C/ref/hickit_res$res.npz" $f || echo "ref $res failed"
      [ -f "$C/scores/ref_res$res.json" ] || $PY $SC/highres.py score --a "$C/ref/hickit_res$res.npz" \
        --out "$C/scores/ref_res$res.json" || echo "ref score $res failed"
    done
  fi
  if [[ " $STEPS " == *" score "* ]]; then
    for res in $LADDER; do
      a=$C/ladder/res${res}_s1.npz; b=$C/ladder/res${res}_s2.npz; ref=$C/ref/hickit_res$res.npz
      [ -f "$a" ] || continue
      $PY $SC/highres.py score --a "$a" $( [ -f "$b" ] && echo --b "$b" ) $( [ -f "$ref" ] && echo --ref "$ref" ) \
        --out "$C/scores/res$res.json" || echo "score $res failed"
    done
  fi
  if [[ " $STEPS " == *" explore "* ]]; then
    for res in $EXPLORE; do run_ember "$IN" $res 1 $NM_EXPLORE "$C/explore/res${res}_s1.npz"; done
  fi
  if [[ " $STEPS " == *" compare "* ]]; then
    for s in 1 2; do run_ember "$IN" 100000 $s $NM "$C/compare/nucdyn_res100000_s$s.npz" nucdyn; done
    mkdir -p "$C/scores"
    [ -f "$C/ref/hickit_res100000.npz" ] && $PY $SC/highres.py score --a "$C/compare/nucdyn_res100000_s1.npz" \
      --b "$C/compare/nucdyn_res100000_s2.npz" --ref "$C/ref/hickit_res100000.npz" \
      --out "$C/scores/nucdyn_res100000.json" || echo "compare score failed"
  fi
  if [[ " $STEPS " == *" heldout "* ]]; then
    S=$C/heldout/split
    mkdir -p "$C/heldout" "$C/scores"
    [ -f "$S/fold1/eval_pairs.npz" ] || $PY $SC/diploid_heldout.py split --contacts "$IN" --out "$S" --folds 1 \
      --seed 1 --eval-res 10000 --cis-same-homolog 2000000 > "$C/heldout/split.log" 2>&1 || echo "split failed"
    run_ember "$S/fold1/train.pairs.gz" 10000 1 $NM "$C/heldout/fold1/ember.npz"
    for ev in eval_pairs eval_pairs_cis; do
      [ -f "$S/fold1/$ev.npz" ] || continue
      $PY $SC/heldout.py score --eval "$S/fold1/$ev.npz" --models "$C/heldout/fold1/ember.npz" --labels ember \
        --out "$C/scores/heldout_fold1_$ev.json" || echo "heldout score $ev failed"
    done
  fi
done
echo "done $(date)"
