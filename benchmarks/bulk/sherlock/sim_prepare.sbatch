#!/bin/bash
# Deconvolution benchmark (design.md 7(b)), step 1: truth populations, simulated population Hi-C,
# twin truths and the task manifest ($RUNS/manifest.tsv: dataset, name, truth, input[, rc_from]).
#
#   su2020_genome  1,787 cells x 2 homologs x 1,041 loci; model bins = 3 Mb centred on the loci
#   su2020_chr21   7,591 chr21 copies x 651 x 50 kb (single-chromosome model in a territory sphere)
#   takei2021_1mb  201 cells x 2 (heuristic homologs) x 2,460 loci; model bins = 1 Mb centred
# Inputs per dataset: step and gauss kernels at IGM's contact distance (occupancy 0.2, sphere of the
# truth's median nuclear radius) at infinite depth, and step at a finite depth (log-normal bias 0.2,
# 2 % noise, 10 fine bins per model bin, IGM preprocessing to the model bins with the oracle target).
# Twins (su2020_genome: gaussian + chrom_shuffle; su2020_chr21: gaussian) get the step / inf input.
# Real inputs of build_real.sbatch are appended when present (rc taken from the simulated input).
#
#   sbatch benchmarks/bulk/sherlock/sim_prepare.sbatch
#SBATCH --job-name=bk-sim-prep
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/bulk/sherlock/_env.sh"
declare -A BINS=([su2020_genome]=centered:3000000 [su2020_chr21]=loci [takei2021_1mb]=centered:1000000)
declare -A DEPTH=([su2020_genome]=100000000 [su2020_chr21]=20000000 [takei2021_1mb]=50000000)
DATASETS=${DATASETS:-"su2020_genome su2020_chr21 takei2021_1mb"}
M=$RUNS/manifest.tsv
: > "$M"
for d in $DATASETS; do
  D=$SIM/$d
  mkdir -p "$D"
  [ -f "$D/truth.npz" ] || $PY $BK/forward.py truth --dataset $d --out "$D/truth.npz"
  R=$($PY -c "import json,numpy as np; print(json.loads(str(np.load('$D/truth.npz')['meta']))['nuclear_radius_nm'])")
  for k in step gauss; do
    [ -f "$D/bulk_${k}_inf.npz" ] || $PY $BK/forward.py bulk --truth "$D/truth.npz" --bins ${BINS[$d]} --kernel $k \
      --nucleus-radius $R --depth inf --out "$D/bulk_${k}_inf.npz"
    printf '%s\t%s\t%s\t%s\n' $d ${k}_inf "$D/truth.npz" "$D/bulk_${k}_inf.npz" >> "$M"
  done
  if [ $d = su2020_genome ]; then          # 1 Mb centred bins (the real su_1mb input's geometry)
    [ -f "$D/bulk_step_inf_c1mb.npz" ] || $PY $BK/forward.py bulk --truth "$D/truth.npz" --bins centered:1000000 \
      --kernel step --nucleus-radius $R --depth inf --out "$D/bulk_step_inf_c1mb.npz"
    printf '%s\t%s\t%s\t%s\n' $d step_inf_c1mb "$D/truth.npz" "$D/bulk_step_inf_c1mb.npz" >> "$M"
  fi
  n=${DEPTH[$d]}
  [ -f "$D/bulk_step_d${n}.npz" ] || $PY $BK/forward.py bulk --truth "$D/truth.npz" --bins ${BINS[$d]} --kernel step \
    --nucleus-radius $R --depth $n --eps 0.02 --bias-sd 0.2 --fine-sub 10 --seed 1 --out "$D/bulk_step_d${n}.npz"
  printf '%s\t%s\t%s\t%s\n' $d step_d${n} "$D/truth.npz" "$D/bulk_step_d${n}.npz" >> "$M"
  # twins
  case $d in
    su2020_genome) TW="gaussian chrom_shuffle" ;;
    su2020_chr21)  TW="gaussian" ;;
    *)             TW="" ;;
  esac
  for tw in $TW; do
    [ -f "$D/twin_$tw.npz" ] || $PY $BK/twins.py --truth "$D/truth.npz" --kind $tw --input "$D/bulk_step_inf.npz" \
      --seed 1 --out "$D/twin_$tw.npz"
    [ -f "$D/bulk_twin_${tw}_step_inf.npz" ] || $PY $BK/forward.py bulk --truth "$D/twin_$tw.npz" --bins ${BINS[$d]} \
      --kernel step --nucleus-radius $R --depth inf --out "$D/bulk_twin_${tw}_step_inf.npz"
    printf '%s\t%s\t%s\t%s\n' $d twin_${tw}_step_inf "$D/twin_$tw.npz" "$D/bulk_twin_${tw}_step_inf.npz" >> "$M"
  done
done
# real inputs (build_real.sbatch), scored against the imaging of the same cell type
for r in "su2020_genome imr90 su_3mb bulk_step_inf" "su2020_genome imr90 su_1mb bulk_step_inf_c1mb" \
         "takei2021_1mb bonev takei_1mb bulk_step_inf"; do
  set -- $r
  if [ -f "$REAL/$2/$3.npz" ]; then
    printf '%s\t%s\t%s\t%s\t%s\n' $1 real_$2_$3 "$SIM/$1/truth.npz" "$REAL/$2/$3.npz" "$SIM/$1/$4.npz" >> "$M"
  fi
done
cat "$M"
