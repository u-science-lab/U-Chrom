#!/bin/bash
# Real-data inputs (design.md 7(c)): download a 4DN mcool (md5-checked) and run the IGM preprocessing
# (uchrom.recon.bulk.deconv.preprocess; 20 kb summed from the 10 kb level, KR at 20 kb, coarse bins):
#
#   CELL=imr90  Rao 2014 IMR90 in situ, 4DN 4DNFIR1JDZH7 (GRCh38, 4.64 GB):
#               * igm_200kb     whole genome (chr1-22, X), 200 kb coarse, 24 contacts / bin (the IGM SI protocol)
#               * su_3mb        3 Mb bins centred on the 1,041 Su 2020 genome-scale loci
#               * su_1mb        1 Mb bins centred on the same loci
#               + su_crosscheck: this cooler summed into the Su authors' 500 kb locus bins vs their
#                 Hi-C_contacts_genome-scale.tsv (the cross-check of the Hi-C input)
#   CELL=bonev  Bonev 2017 mESC (G1-sorted ES), 4DN 4DNFIC21MG3U (mm10, 12.55 GB):
#               * igm_200kb     whole genome (chr1-19, X)
#               * takei_1mb     1 Mb bins centred on the 2,460 Takei 2021 1 Mb loci
#
#   sbatch --export=ALL,CELL=imr90 benchmarks/bulk/sherlock/build_real.sbatch
#   sbatch --export=ALL,CELL=bonev --time=16:00:00 benchmarks/bulk/sherlock/build_real.sbatch
# Needs the truths of sim_prepare.sbatch for the centred bins ($SIM/<dataset>/truth.npz).
#SBATCH --job-name=bk-real
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=192G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-deconv/benchmarks/bulk/sherlock/_env.sh"
CELL=${CELL:-imr90}
case $CELL in
  imr90) KEY=rao2014_imr90_4dn; MC=$DATA/rao2014_imr90/4DNFIR1JDZH7.mcool; TRUTHS="su2020_genome:centered:3000000:su_3mb su2020_genome:centered:1000000:su_1mb" ;;
  bonev) KEY=bonev2017_mesc_4dn; MC=$DATA/bonev2017_mesc/4DNFIC21MG3U.mcool; TRUTHS="takei2021_1mb:centered:1000000:takei_1mb" ;;
esac
$PY -m uchrom.datasets fetch "$KEY" --root "$DATA"
OUT=$REAL/$CELL
mkdir -p "$OUT"
FINE=$OUT/fine_20kb.npz
if [ ! -f "$FINE" ]; then
  $PY $BK/real_inputs.py preprocess --source "$MC" --fine 20000 --coarse 200000 --target 24 \
    --fine-out "$FINE" --out "$OUT/igm_200kb.npz"
fi
for t in $TRUTHS; do
  IFS=: read -r ds kind w name <<< "$t"
  $PY $BK/real_inputs.py preprocess --fine-in "$FINE" --coarse-bins "$SIM/$ds/truth.npz:$kind:$w" \
    --target 24 --out "$OUT/$name.npz"
done
if [ "$CELL" = imr90 ]; then
  $PY $BK/real_inputs.py su_crosscheck --source "$MC" --out "$OUT/su_crosscheck.json"
fi
ls -la "$OUT"
