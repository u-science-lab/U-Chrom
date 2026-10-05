#!/bin/bash
# Genotype cue (PREREG §12.2), development runs (one GPU): pools from the labelled development cells,
# genotype priors (label coverage / accuracy printed), mix_dev.py --diploid with the baselines (oracle =
# EMber diploid per cell, naive, IGM S=k diploid, prior-split) and the variants of VARIANTS.
#   sbatch --export=ALL,ENGINE=<tag>,VARIANTS=<json>,TAG=<name>[,PRIOR=<json>] benchmarks/screcon/sherlock/geno_dev.sbatch
#SBATCH --job-name=geno-dev
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH --time=16:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-mix/benchmarks/screcon/sherlock/_env_mix.sh"
: "${VARIANTS:?}" "${TAG:?}"
GE=$MX/geno
nvidia-smi --query-gpu=name --format=csv,noheader || true
$PY $SC/mix_geno.py pools --split "$GE/split.tsv" --tables "$GE/tables" --labels "$GE/labels" --set dev --out "$GE/pools" | tail -3
RUNS=$GE/runs_$TAG
mkdir -p "$RUNS"
for p in $(ls "$GE"/pools/dev/*_p*.txt.gz | grep -v _cell | grep -- "${ONLY:-.}"); do
  name=$(basename "$p" .txt.gz)
  [ -f "$RUNS/$name.prior.npy" ] || $PY $SC/mix_geno.py prior --score --pool "$p" --params "${PRIOR:-{\}}" --out "$RUNS/$name.prior.npy"
  $PY $SC/mix_dev.py --res 2e5 --diploid --pools "$p" --runs "$RUNS" --refs-dir "$RUNS" --device gpu \
    --baselines oracle naive igm "split:{runs}/{pool}.prior.npy" --variants "$(cat "$VARIANTS")" --table "$RUNS/table.tsv" \
    || echo "FAILED $name"
done
echo done
