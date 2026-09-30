#!/bin/bash
# KR check against Juicer's vectors over HTTP range reads (kr_check.py): the laptop set (results in
# benchmarks/bulk/results/kr_check.json) plus every IMR90 autosome + X at 1 Mb and 250 kb from the GEO
# .hic (Juicer KR computed on exactly these counts) and chr1 at 25 kb.  Needs hic-straw (setup_bulk).
#
#   sbatch benchmarks/bulk/sherlock/kr_check.sbatch
#SBATCH --job-name=bk-kr
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=03:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/bulk/sherlock/_env.sh"
CASES=()
for c in $(seq 1 22) X; do CASES+=("imr90_geo:$c:1000000" "imr90_geo:$c:250000"); done
CASES+=("imr90_geo:1:25000" "imr90_4dn:chr1:25000" "bonev_4dn:chr1:25000")
$PY $BK/kr_check.py --case "${CASES[@]}" --out "$RUNS/tables/kr_check_sherlock.json"
