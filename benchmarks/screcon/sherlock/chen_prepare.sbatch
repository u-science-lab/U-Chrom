#!/bin/bash
# Chen et al. 2026 spatial Hi-C (PREREG §13.3): per-spot tables of the cortex / hippocampus 10 um sections
# from the reprocessed deduplicated pairs on Oak (read-only), and the secondary in-silico spot mixtures.
#
#   sbatch benchmarks/screcon/sherlock/chen_prepare.sbatch
#SBATCH --job-name=chen-prep
#SBATCH --partition=xiaojie,normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-dominant/benchmarks/screcon/sherlock/_env_dominant.sh"
CH=$W/runs/chen2026
SRC=$OAK/uchrom/spatial_hic_chen2026
for pair in cortex_adult_10um:CRR1829219 hippocampus_adult_10um:CRR1829220; do
  store=${pair%%:*}; run=${pair##*:}
  if [ ! -f "$CH/$run/spots.tsv" ]; then
    $PY $SC/chen_spots.py split --pairs "$SRC/$run/$run.dedup.pairs.gz" \
      --spots "$SC/data/chen2026_${store}_${run}_spots.tsv.gz" --out "$CH/$run" | tail -2
  fi
  grep -q mix2 "$CH/$run/manifest.tsv" || $PY $SC/chen_spots.py mixtures --dir "$CH/$run"
done
echo done
