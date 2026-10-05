#!/bin/bash
# Cell-type-assisted deconvolution (PREREG §12.1), development only, one GPU: split, reference maps,
# development pools (Tan 2021 cortex, data already staged), then mix_type_dev.sh (priors, baselines,
# variants).  DIPLOID=1: phased pools, diploid runs (cells x copies).
#   sbatch --export=ALL,ENGINE=<tag>,VARIANTS=<json>,TAG=<name>[,DIPLOID=1][,ONLY=<pattern>] benchmarks/screcon/sherlock/mix_type.sbatch
#SBATCH --job-name=mix-type
#SBATCH --partition=xiaojie,gpu,owners
#SBATCH -G 1
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-mix/benchmarks/screcon/sherlock/_env_mix.sh"
: "${VARIANTS:?}" "${TAG:?}"
MT=$MX/type
mkdir -p "$MT"
nvidia-smi --query-gpu=name --format=csv,noheader || true
[ -f "$MT/split.tsv" ] || $PY $SC/mix_type.py split --out "$MT/split.tsv"
[ -f "$MT/ref_1mb.npz" ] || $PY $SC/mix_type.py reference --split "$MT/split.tsv" --data "$DATA" --res 1e6 --out "$MT/ref_1mb.npz"
$PY $SC/mix_type.py pools --split "$MT/split.tsv" --data "$DATA" --set dev --out "$MT/pools" | tail -2
export PY MT DIPLOID ONLY
bash $SC/mix_type_dev.sh "$VARIANTS" "${PRIOR:-{\}}" "$TAG"
echo done
