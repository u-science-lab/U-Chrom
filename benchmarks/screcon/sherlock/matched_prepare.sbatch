#!/bin/bash
# Matched-modality inputs: imaging sets (Takei 2021 mESC, Takei 2021 brain), Nagano 2017 haploid
# contact tables (mm9 fends -> mm10), the Tan 2021 Dip-C set (published clean.3dg, rep 1).
#
#   sbatch --export=ALL,PART=mesc  benchmarks/screcon/sherlock/matched_prepare.sbatch
#   sbatch --export=ALL,PART=brain benchmarks/screcon/sherlock/matched_prepare.sbatch   (Takei 2021 Science set)
#   sbatch --export=ALL,PART=dipc  benchmarks/screcon/sherlock/matched_prepare.sbatch   (after the Tan 2021 download)
#SBATCH --job-name=sc-mt-prep
#SBATCH --partition=xiaojie,normal
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-matched/benchmarks/screcon/sherlock/_matched_env.sh"
case ${PART:?} in
  mesc)
    [ -f "$M/sets/takei2021_mesc.npz" ] || $PY $SC/matched_data.py takei-mesc --zip "$DATA/DNAseqFISH+.zip" --out "$M/sets/takei2021_mesc.npz"
    for cond in serum 2i; do
      if [ $cond = serum ]; then rule=$NAGANO_SERUM_RULE; max=""; else rule=$NAGANO_2I_RULE; max="--max-cells $NAGANO_2I_MAX"; fi
      [ -f "$M/nagano/$cond/manifest.tsv" ] && continue
      $PY $SC/matched_data.py nagano --features "$NAG/GSE94489_haploids_features_table.txt.gz" --fends "$NAG/GATC.fends" \
        --chain "$NAG/mm9ToMm10.over.chain.gz" --adj-dirs "$NAG/adj_serum" "$NAG/adj_2i" --rule "$rule" $max \
        --seed 1 --out-dir "$M/nagano/$cond"
    done
    ;;
  brain)
    $PY $SC/matched_data.py takei-brain --s7 "$TKB/TableS7_brain_DNAseqFISH_1Mb_voxel_coordinates_2762cells.csv" \
      --out "$M/sets/takei2021_brain.npz"
    ;;
  dipc)
    $PY $SC/matched_data.py dipc --dir "$TAN/cells" --rep 1 --out "$M/sets/tan2021_dipc_rep1.npz"
    $PY $SC/matched_data.py dipc --dir "$TAN/cells" --rep 2 --out "$M/sets/tan2021_dipc_rep2.npz"
    ;;
esac
