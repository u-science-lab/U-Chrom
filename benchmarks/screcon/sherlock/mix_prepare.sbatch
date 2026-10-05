#!/bin/bash
# Few-cell deconvolution (PREREG §12), inputs of one set (SET=dev, default; SET=test only after the
# freeze is approved): pseudo-haploid truths of takei2021_1mb and su2020_genome with the registered
# split, the simulated pools (k 2, 3, 5, 10, 20 x pools x depth 10 / 40 x eps 0.05 / 0.2), and the
# real pools (Nagano 2017 serum halves of robust_matched_split.py, Stevens 2017 cells 1-4 / 5-8).
#
#   sbatch --export=ALL,ENGINE=<tag> benchmarks/screcon/sherlock/mix_prepare.sbatch
#SBATCH --job-name=mix-prep
#SBATCH --partition=xiaojie,normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-mix/benchmarks/screcon/sherlock/_env_mix.sh"
SET=${SET:-dev}
for ds in takei2021_1mb su2020_genome; do
  [ -f "$MX/truth/$ds/split.json" ] || $PY $SC/mix_sim.py truths --dataset $ds --out "$MX/truth/$ds"
  $PY $SC/mix_sim.py pools --truth-dir "$MX/truth/$ds" --set $SET --out "$MX/pools/$ds" | tail -2
done
NAG=$W/runs/robust/matched/split
case $SET in dev) NM=$NAG/dev_manifest.tsv ;; test) NM=$NAG/heldback_manifest.tsv ;; esac
$PY $SC/mix_sim.py real --dataset nagano --manifest "$NM" --set $SET --out "$MX/real/nagano" | tail -2
$PY $SC/mix_sim.py real --dataset stevens --tables $GEO/*_contact_pairs.txt.gz --set $SET --out "$MX/real/stevens" | tail -2
echo done
