#!/bin/bash
# Diploid simulation, step 1: diploid truth cells (5 per dataset, seed 1) and the phased read grid
# (depth 20 / 80 reads per Mb of the diploid span x rc 0.5 / 1.0 x eps 0.05 / 0.2 x phased ends 0.1 / 0.2 / 0.4,
# phase errors 1 %, seed 1) -> $DS/manifest.tsv (dataset, name, table, truth).
#   su2020_genome  (1,041 loci x 2 homologs, hg38)   takei2021_1mb (2,460 loci, homolog split, mm10; chrX single)
# 2 datasets x 5 truths x 24 = 240 tables (Dip-C GM12878 has 8 % of the ends phased; hence 0.1).
#
#   sbatch benchmarks/screcon/sherlock/dip_sim_prepare.sbatch
#SBATCH --job-name=dp-sim-prep
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-diploid/benchmarks/screcon/sherlock/_env_diploid.sh"
DS=$DP/sim
for d in su2020_genome takei2021_1mb; do
  [ -f "$DS/truth/$d/truth_5.npz" ] || $PY $SC/diploid_sim.py truth --dataset $d --n 5 --seed 1 --out "$DS/truth/$d"
  $PY $SC/diploid_sim.py grid --truth-dir "$DS/truth/$d" --depths 20 80 --rc-rels 0.5 1.0 --eps 0.05 0.2 \
    --phased 0.1 0.2 0.4 --phase-err 0.01 --seeds 1 --out "$DS/reads/$d"
done
: > "$DS/manifest.tsv"
for d in su2020_genome takei2021_1mb; do
  for f in "$DS/reads/$d"/*.pairs.gz; do
    name=$(basename "$f" .pairs.gz)
    printf '%s\t%s\t%s\t%s\n' "$d" "$name" "$f" "$DS/truth/$d/${name%%_d*}.npz" >> "$DS/manifest.tsv"
  done
done
wc -l "$DS/manifest.tsv"
