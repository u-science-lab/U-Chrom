#!/bin/bash
# Dip-C GM12878 (Tan et al. 2018, GSE117876; 17 cells, ~0.7 GB) into $DATA/tan2018_gm12878 (download_data.py
# --tan2018_gm12878), then each hickit tarball unpacked to cells/gm12878_<k>/ (pairs.gz: hickit's imputed
# phased pairs, phase0 / phase1 = raw SNP phases, phase_prob00..11 = hickit -u; 3dg.gz: hickit's structure).
#
#   sbatch benchmarks/screcon/sherlock/download_diploid.sbatch
#SBATCH --job-name=dp-download
#SBATCH --partition=xiaojie,normal
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-diploid/benchmarks/screcon/sherlock/_env_diploid.sh"
$PY $REPO/example-data/download_data.py --tan2018_gm12878 --dest "$DATA" || echo "some downloads failed (see above)"
mkdir -p "$TAN18/cells"
for k in $(seq -w 1 17); do
  t=$(ls "$TAN18"/GSM*_gm12878_$k.tar.gz 2>/dev/null | head -1)
  [ -n "$t" ] || { echo "missing tarball of cell $k"; continue; }
  d=$TAN18/cells/gm12878_$k
  [ -f "$d/gm12878_$k.pairs.gz" ] || { mkdir -p "$d" && tar -xzf "$t" -C "$d"; }
  echo "cell $k: $(zcat "$d/gm12878_$k.pairs.gz" | grep -vc '^#') contacts; Dip-C 3dg: $(ls "$TAN18"/GSM*_gm12878_$k.impute3.round4.clean.3dg.txt.gz 2>/dev/null | wc -l)"
done
du -sh "$TAN18"
