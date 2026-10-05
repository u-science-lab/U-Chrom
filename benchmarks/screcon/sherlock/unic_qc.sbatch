#!/bin/bash
# Uni-C GM12878 contact QC next to Dip-C (Tan 2018) and scMicro-C (Wu 2025) GM12878, one pipeline for all
# (unic_qc.py; exploratory, PREREG §12).  Per input pairs file:
#   Uni-C (pairtools pairs, GRCh37): pair types counted, trimmed to 7 columns (node-local copy), then hickit -i
#     with every close-legged contact removed (--all-close-leg, legs < 1 kb) and --dup-dist 100 (hickit default)
#     or 1000 (Dip-C-style: both ends within 1 kb); plus hickit's default close-leg rule at 1000 for reference
#   Dip-C / scMicro-C (hickit phased pairs): hickit -i --all-close-leg --dup-dist 1000 (phases kept)
#   all: isolated-contact filters on the dd1000 table (hickit -r1m -c1 and -r10m -c5: rows kept), unic_qc.py stats
#     on the dd1000 table (phased het SNVs of the build: GRCh37 for Uni-C / Dip-C, GRCh38 for scMicro-C); for the
#     references also on the published table (actual phases, calibration); finally unic_qc.py project.
#   The dd100 / dd1000 tables of Uni-C are kept in $UN/<label>/; the raw copy is node-local and deleted.
#
#   sbatch -d afterok:<download job> benchmarks/screcon/sherlock/unic_qc.sbatch
#SBATCH --job-name=unic-qc
#SBATCH --partition=xiaojie,normal
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=96G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-unic/benchmarks/screcon/sherlock/_env_unic.sh"
TMP=${L_SCRATCH_JOB:-$UN/tmp}
mkdir -p "$TMP"
nrows() { zcat -f "$1" | grep -vc '^#' || true; }

hick() {   # in out [hickit options]
  local in=$1 out=$2
  shift 2
  if [ ! -f "$out" ]; then
    "$HICKIT" -i "$in" "$@" -o - 2> "$out.log" | gzip -1 > "$out.part"
    mv "$out.part" "$out"
  fi
}

qc() {   # label input(pairs) build is_unic
  local label=$1 in=$2 build=$3 unic=$4
  local D=$UN/$label
  mkdir -p "$D"
  echo "== $label $(date)"
  if [ "$unic" = 1 ]; then
    if [ ! -f "$D/dd1000.pairs.gz" ]; then
      local src=$TMP/$label.raw.pairs
      zcat "$in" | awk -v OFS='\t' -v types="$D/pair_types.tsv" '
        /^#/ { if ($1 == "##" || $1 == "#chromsize:") print; next }
        !h { print "#columns: readID chr1 pos1 chr2 pos2 strand1 strand2"; h = 1 }
        { n[$8]++; print $1, $2, $3, $4, $5, $6, $7 }
        END { for (t in n) print t "\t" n[t] > types }' > "$src"
      echo "$(grep -vc '^#' "$src")" > "$D/raw_rows.txt"
      hick "$src" "$D/dd100.pairs.gz" --all-close-leg --dup-dist=100
      hick "$src" "$D/dd1000_defaultclose.pairs.gz" --dup-dist=1000
      hick "$src" "$D/dd1000.pairs.gz" --all-close-leg --dup-dist=1000
      rm -f "$src"
    fi
  else
    hick "$in" "$D/dd1000.pairs.gz" --all-close-leg --dup-dist=1000
  fi
  hick "$D/dd1000.pairs.gz" "$D/iso_r1m_c1.pairs.gz" -r1m -c1
  hick "$D/dd1000.pairs.gz" "$D/iso_r10m_c5.pairs.gz" -r10m -c5
  {
    echo "{"
    if [ -f "$D/raw_rows.txt" ]; then echo "\"raw\": $(cat "$D/raw_rows.txt"),"; fi
    echo "\"input\": $(nrows "$in"),"
    for f in dd100 dd1000_defaultclose dd1000 iso_r1m_c1 iso_r10m_c5; do
      if [ -f "$D/$f.pairs.gz" ]; then echo "\"$f\": $(nrows "$D/$f.pairs.gz"),"; fi
    done
    echo "\"build\": \"$build\"}"
  } > "$D/counts.json"
  cat "$D/counts.json"
  $PY $SC/unic_qc.py stats --pairs "$D/dd1000.pairs.gz" --hets "$GIAB/hets_$build.npz" --label "$label" \
    --counts "$D/counts.json" --out "$D/stats.json"
  if [ "$unic" = 0 ]; then
    $PY $SC/unic_qc.py stats --pairs "$in" --hets "$GIAB/hets_$build.npz" --label "${label}_orig" \
      --out "$D/stats_orig.json"
  fi
  rm -f "$D"/iso_*.pairs.gz "$D/dd1000_defaultclose.pairs.gz"
}

for k in 01 02 03; do
  qc dipc_cell$k "$TAN18/cells/gm12878_$k/gm12878_$k.pairs.gz" GRCh37 0
done
for c in GSM5764669_cell_035 GSM5764658_cell_024 GSM5764954_cell_320; do
  qc scmc_${c##*_} "$WU/$c.impute.pairs.gz" GRCh38 0
done
for k in 1 2 3; do
  qc unic_cell$k "$(ls "$UNIC"/GSM*_GM12878-Cell$k.pairs.gz)" GRCh37 1
done
$PY $SC/unic_qc.py project --unic "$UN"/unic_cell*/stats.json --ref "$UN"/dipc_cell*/stats_orig.json \
  "$UN"/scmc_*/stats_orig.json --out "$UN/projection.json"
echo "done $(date)"
