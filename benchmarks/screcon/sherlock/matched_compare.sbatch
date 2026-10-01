#!/bin/bash
# Matched-modality comparison: model sets on the Takei 1 Mb loci, then matched.py compare against the
# imaging set (+ size-matched imaging ceiling, random-polymer and P(s)-only baselines), summary table.
#
#   sbatch --export=ALL,PART=mesc  benchmarks/screcon/sherlock/matched_compare.sbatch   (METHODS="hickit" for a subset)
#   sbatch --export=ALL,PART=brain benchmarks/screcon/sherlock/matched_compare.sbatch
#SBATCH --job-name=sc-mt-cmp
#SBATCH --partition=xiaojie,normal
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-matched/benchmarks/screcon/sherlock/_matched_env.sh"
S=$M/sets
cmp() {  # cmp LABEL A B [extra args]
  local label=$1 a=$2 b=$3; shift 3
  local out=$M/rows/${label//\//__}.csv
  [ -f "$out" ] && return 0
  [ -f "$a" ] || { echo "missing $a"; return 0; }
  echo "== $label"
  $PY $SC/matched.py compare --a "$a" --b "$b" --label "$label" --n-rep 5 --out "$out" "$@"
}
case ${PART:?} in
  mesc)
    IMG=$S/takei2021_mesc.npz
    # Stevens 2017 (8 haploid G1 cells): fig3 native GPU runs and the screcon hickit runs, model 0
    for m in ${METHODS:-nucdyn_gpu hickit}; do
      man=$M/sets/stevens_$m.tsv
      printf 'cell\tmodels\n' > "$man"
      for c in 1 2 3 4 5 6 7 8; do
        if [ $m = nucdyn_gpu ]; then f=$W/runs/native_gpu_full/cell$c.npz; else f=$R/models/hickit/cell$c.npz; fi
        printf 'stevens_cell%s\t%s\n' "$c" "$f" >> "$man"
      done
      [ -f "$S/stevens_$m.npz" ] || $PY $SC/matched_data.py models --manifest "$man" --label "stevens2017_$m" --out "$S/stevens_$m.npz"
    done
    for m in ${METHODS:-nucdyn_gpu hickit}; do
      for cond in serum 2i; do
        [ -f "$S/nagano_${cond}_$m.npz" ] || $PY $SC/matched_data.py models --manifest "$M/nagano/$cond/manifest.tsv" \
          --models-dir "$M/models/$m" --label "nagano2017_${cond}_$m" --out "$S/nagano_${cond}_$m.npz"
        [ -f "$S/nagano_${cond}_${m}_m1.npz" ] || $PY $SC/matched_data.py models --manifest "$M/nagano/$cond/manifest.tsv" \
          --models-dir "$M/models/$m" --model 1 --label "nagano2017_${cond}_${m}_model1" --out "$S/nagano_${cond}_${m}_m1.npz"
      done
    done
    for m in ${METHODS:-nucdyn_gpu hickit}; do
      cmp "mesc/stevens/$m" "$S/stevens_$m.npz" "$IMG"
      cmp "mesc/nagano_serum/$m" "$S/nagano_serum_$m.npz" "$IMG"
      cmp "mesc/nagano_serum_G1/$m" "$S/nagano_serum_$m.npz" "$IMG" --a-where group=G1
      cmp "mesc/nagano_2i/$m" "$S/nagano_2i_$m.npz" "$IMG"
      cmp "mesc/nagano_serum/${m}_model1" "$S/nagano_serum_${m}_m1.npz" "$IMG"
    done
    # method vs method on the same contacts (B = hickit; its "ceiling" is hickit split in two)
    cmp "mesc/check/nagano_serum_nucdyn_vs_hickit" "$S/nagano_serum_nucdyn_gpu.npz" "$S/nagano_serum_hickit.npz" \
      --no-mask --no-baselines
    ;;
  brain)
    IMG=$S/takei2021_brain.npz
    D=$S/tan2021_dipc_rep1.npz
    cmp "brain/all/dipc" "$D" "$IMG"
    cmp "brain/all/dipc_diploid" "$D" "$IMG" --nucleus diploid
    cmp "brain/all/dipc_rep2" "$S/tan2021_dipc_rep2.npz" "$IMG"
    for cls in Excitatory Inhibitory Astrocyte Microglia Oligodendrocyte; do
      cmp "brain/$cls/dipc" "$D" "$IMG" --a-where "cell_class=$cls" --b-where "cell_class=$cls"
    done
    # cross-type control: does matching the cell type matter?  Dip-C excitatory vs imaging non-neuronal, ...
    cmp "brain/x_Excitatory_vs_Oligodendrocyte/dipc" "$D" "$IMG" --a-where cell_class=Excitatory --b-where cell_class=Oligodendrocyte
    cmp "brain/x_Oligodendrocyte_vs_Excitatory/dipc" "$D" "$IMG" --a-where cell_class=Oligodendrocyte --b-where cell_class=Excitatory
    # imaging vs imaging across types (how different are the types in imaging itself)
    cmp "brain/img_Excitatory_vs_Oligodendrocyte" "$IMG" "$IMG" --a-where cell_class=Excitatory --b-where cell_class=Oligodendrocyte --no-baselines --no-mask
    ;;
esac
$PY $SC/matched.py summary --rows "$M"/rows/*.csv --out "$M/tables/summary.csv" > "$M/tables/summary.txt"
cat "$M/tables/summary.txt"
