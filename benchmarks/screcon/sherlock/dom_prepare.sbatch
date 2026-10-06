#!/bin/bash
# Dominant-cell mixtures (PREREG §13), inputs of one set (SET=dev; SET=test only after the user
# approves, APPROVED=1): cell counts, registered designs, per-dominant tables.  CPU only.
#
#   sbatch --export=ALL,SET=dev[,DATASETS="nagano stevens tan"] benchmarks/screcon/sherlock/dom_prepare.sbatch
#SBATCH --job-name=dom-prep
#SBATCH --partition=xiaojie,normal
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-dominant/benchmarks/screcon/sherlock/_env_dominant.sh"
SET=${SET:-dev}
[ "$SET" = dev ] || [ -n "${APPROVED:-}" ] || { echo "held-back set needs APPROVED=1 (user approval)"; exit 1; }
NAG=$W/runs/robust/matched/split
for ds in ${DATASETS:-nagano stevens tan}; do
  D=$DM/$ds/$SET
  if [ ! -f "$D/cells.tsv" ]; then
    case $ds in
      nagano) M=$NAG/dev_manifest.tsv; [ "$SET" = test ] && M=$NAG/heldback_manifest.tsv
              $PY $SC/dominant.py cells --dataset nagano --set $SET --manifest "$M" --out "$D" | tail -1 ;;
      stevens) $PY $SC/dominant.py cells --dataset stevens --set $SET --tables $GEO/*_contact_pairs.txt.gz --out "$D" | tail -1 ;;
      tan) $PY $SC/dominant.py cells --dataset tan --set $SET --data "$DATA" --out "$D" | tail -1 ;;
      tanu) $PY $SC/dominant.py unphased --src "$DM/tan/$SET" --out "$D" ;;   # PREREG §13.3: Tan, phases dropped
    esac
  fi
  [ -f "$D/designs.json" ] || $PY $SC/dominant.py designs --dir "$D"
  $PY $SC/dominant.py build --dir "$D"
done
echo done
