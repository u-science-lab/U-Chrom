#!/bin/bash
# Diploid simulation, step 2 (one GPU): the native methods on the manifest tables, 5 models, seed 1,
# final particle size 1 Mb (schedule 8, 4, 2, 1 Mb), then hickit (Dip-C pipeline, CPU threads of this job)
# and the scores (diploid_sim.py score).
#   ember            EMber, frozen haploid parameters + diploid default (each candidate copy pair its own restraint)
#   ember_nosplit    ... candidates one ambiguous restraint weighted by P(true)       (robust_dip_split false)
#   ember_prior      ember + hickit's 2-D imputed phase probabilities as candidate prior
#   ember_nosplit_prior
#   ember_nbr        ember_nosplit + the native 2-D neighbourhood phase prior (robust_dip_nbr_prior)
#   nucdyn           NucDynamics 2017 with diploid ambiguous restraints
#   hickit           hickit 0.1.1, -u -S + Dip-C schedule
# SET=dev (default): truth cells 1-2 only (PREREG.md §6 diploid development set); SET=test: cells 3-5
# (only after the diploid parameters are frozen).  ONLY=<grep pattern> restricts the tables.
#
#   sbatch benchmarks/screcon/sherlock/dip_sim_run.sbatch
#SBATCH --job-name=dp-sim
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=10
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-diploid/benchmarks/screcon/sherlock/_env_diploid.sh"
DS=$DP/sim
SET=${SET:-dev}
METHODS=${METHODS:-"ember ember_nosplit ember_prior ember_nosplit_prior nucdyn hickit"}
nvidia-smi --query-gpu=name --format=csv,noheader || true
N=$(wc -l < "$DS/manifest.tsv")
for t in $(seq 1 $N); do
  IFS=$'\t' read -r DATASET NAME TABLE TRUTH <<< "$(sed -n "${t}p" "$DS/manifest.tsv")"
  case $NAME in truth_1_*|truth_2_*) unit=dev ;; *) unit=test ;; esac
  [ "$unit" = "$SET" ] || continue
  [ -n "${ONLY:-}" ] && ! echo "$NAME" | grep -q -- "$ONLY" && continue
  M=$DS/models/$DATASET/$NAME
  mkdir -p "$M" "$DS/scores/$DATASET"
  for m in $METHODS; do
    [ -f "$M/$m.npz" ] && continue
    case $m in
      ember)               $PY $SC/run_diploid.py --method ember --contacts "$TABLE" --res 1000000 --device gpu --n-models 5 --seed 1 --label $m --out "$M/$m.npz" > "$M/$m.log" 2>&1 ;;
      ember_nosplit)       $PY $SC/run_diploid.py --method ember --params '{"robust_dip_split": false}' --contacts "$TABLE" --res 1000000 --device gpu --n-models 5 --seed 1 --label $m --out "$M/$m.npz" > "$M/$m.log" 2>&1 ;;
      ember_prior)         $PY $SC/run_diploid.py --method ember --hickit-prior "$HICKIT" --contacts "$TABLE" --res 1000000 --device gpu --n-models 5 --seed 1 --label $m --out "$M/$m.npz" > "$M/$m.log" 2>&1 ;;
      ember_nosplit_prior) $PY $SC/run_diploid.py --method ember --params '{"robust_dip_split": false}' --hickit-prior "$HICKIT" --contacts "$TABLE" --res 1000000 --device gpu --n-models 5 --seed 1 --label $m --out "$M/$m.npz" > "$M/$m.log" 2>&1 ;;
      ember_nbr)           $PY $SC/run_diploid.py --method ember --params '{"robust_dip_split": false, "robust_dip_nbr_prior": true}' --contacts "$TABLE" --res 1000000 --device gpu --n-models 5 --seed 1 --label $m --out "$M/$m.npz" > "$M/$m.log" 2>&1 ;;
      nucdyn)              $PY $SC/run_diploid.py --method nucdyn --contacts "$TABLE" --res 1000000 --device gpu --n-models 5 --seed 1 --label $m --out "$M/$m.npz" > "$M/$m.log" 2>&1 ;;
      hickit)              $PY $SC/run_hickit.py --hickit "$HICKIT" --diploid --contacts "$TABLE" --res 1000000 --n-models 5 --seed 1 --jobs 5 --out "$M/$m.npz" > "$M/$m.log" 2>&1 ;;
    esac || echo "FAILED $m $NAME: $(tail -2 "$M/$m.log")"
  done
  models=(); labels=()
  for m in $METHODS; do
    if [ -f "$M/$m.npz" ]; then models+=("$M/$m.npz"); labels+=("$m"); fi
  done
  $PY $SC/diploid_sim.py score --truth "$TRUTH" --table "$TABLE" --table-truth "${TABLE%.pairs.gz}.truth.npz" \
    --models "${models[@]}" --labels "${labels[@]}" --out "$DS/scores/$DATASET/$NAME.json" > /dev/null
  echo "$DATASET $NAME done"
done
