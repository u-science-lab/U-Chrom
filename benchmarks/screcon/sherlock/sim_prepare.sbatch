#!/bin/bash
# Simulation benchmark, step 1: truth cells (5 per dataset, seed 1) + population summaries, the read
# grid (depth x rc x eps, seed 1) and the task manifest ($S/manifest.tsv: dataset, name, table, truth).
#   su2020_chr21  (651 x 50 kb, one chromosome, hg38):  depth 40 / 160 / 640 reads per Mb
#   takei2021_1mb (2,460 loci genome-wide, mm10):       depth 10 / 40 / 160 reads per Mb
#   both: rc = 0.5 / 1.0 x median consecutive-locus distance, eps = 0 / 0.05 / 0.2, Gaussian kernel
# -> 2 datasets x 5 truths x 18 = 180 tables.  (Truth extraction: < 1 min per dataset on a laptop.)
#
#   sbatch benchmarks/screcon/sherlock/sim_prepare.sbatch
#SBATCH --job-name=sc-sim-prep
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
DATASETS=${DATASETS:-"su2020_chr21 takei2021_1mb"}
for d in $DATASETS; do
  [ -f "$S/truth/$d/population.npz" ] || $PY $SC/simulate.py truth --dataset $d --n 5 --seed 1 --out "$S/truth/$d"
  case $d in
    su2020_chr21) DEPTHS="40 160 640" ;;
    *)            DEPTHS="10 40 160" ;;
  esac
  $PY $SC/simulate.py grid --truth-dir "$S/truth/$d" --depths $DEPTHS --rc-rels 0.5 1.0 --eps 0 0.05 0.2 \
    --seeds 1 --out "$S/reads/$d"
done
: > "$S/manifest.tsv"
for d in $DATASETS; do
  for f in "$S/reads/$d"/*.txt.gz; do
    name=$(basename "$f" .txt.gz)
    printf '%s\t%s\t%s\t%s\n' "$d" "$name" "$f" "$S/truth/$d/${name%%_d*}.npz" >> "$S/manifest.tsv"
  done
done
wc -l "$S/manifest.tsv"
