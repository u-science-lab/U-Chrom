#!/bin/bash
# Twin-truth identifiability test (twins.py): for every twin input of the manifest, the truth / twin
# pair and the reconstructions of their step / inf inputs (same S and seed): higher-order distances
# between the truths and between the reconstructions, identifiable fraction = d_R / d_T.
# Also the pairwise-only baseline pair (contact_gaussian of both inputs) as a control: its fraction
# measures what a pairwise-only method "recovers" (should be ~0 for the gaussian twin).
#
#   sbatch benchmarks/bulk/sherlock/twin_score.sbatch
#SBATCH --job-name=bk-twin
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-deconv/benchmarks/bulk/sherlock/_env.sh"
EPY=${ENGINE_PY:-$PY}
S=${S:-1000}
SEED=${SEED:-1}
for d in su2020_genome su2020_chr21; do
  for tw in gaussian chrom_shuffle; do
    T2=$SIM/$d/twin_$tw.npz
    [ -f "$T2" ] || continue
    RC=$($PY -c "import json,numpy as np; print(json.loads(str(np.load('$SIM/$d/bulk_step_inf.npz')['provenance']))['rc_nm_median'])")
    for m in "igm_S${S}_seed${SEED}.chromdata.zarr" contact_gaussian.npz hipps.npz; do
      R1=$RUNS/models/$d/step_inf/$m; R2=$RUNS/models/$d/twin_${tw}_step_inf/$m
      case $m in *.npz) R1=$RUNS/base/$d/step_inf/$m; R2=$RUNS/base/$d/twin_${tw}_step_inf/$m ;; esac
      [ -e "$R1" ] && [ -e "$R2" ] || { echo "skip $d $tw $m"; continue; }
      PYTHONPATH=$REPO $EPY $BK/score.py twin --t1 "$SIM/$d/truth.npz" --t2 "$T2" --r1 "$R1" --r2 "$R2" --rc-nm $RC \
        --out "$RUNS/twin/${d}_${tw}_${m%%.*}.json"
    done
  done
done
