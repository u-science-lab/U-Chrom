#!/bin/bash
# Real data, full contact tables: Si-C or hickit on the 8 Stevens 2017 cells at 100 kb (10 replicas /
# seeds), next to the fig3 NucDynamics runs ($W/runs/native_gpu_full, $W/runs/orig_master_full).
#
#   sbatch --array=1-8 --export=ALL,METHOD=hickit --time=02:00:00 benchmarks/screcon/sherlock/real_full.sbatch
#   sbatch --array=1-8 --export=ALL,METHOD=sic benchmarks/screcon/sherlock/real_full.sbatch
#SBATCH --job-name=sc-real
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=10
#SBATCH --mem=48G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
c=${SLURM_ARRAY_TASK_ID:?}
tab="$GEO/${GSM[$c]}_Cell_${c}_contact_pairs.txt.gz"
mkdir -p "$R/models/${METHOD:?}"
case $METHOD in
  hickit) $PY $SC/run_hickit.py --hickit "$HICKIT" --contacts "$tab" --res 100000 --assembly mm10 --n-models 10 \
            --seed 1 --jobs 10 --out "$R/models/hickit/cell$c.npz" ;;
  sic)    $PY $SC/run_sic.py --sic-dir "$SIC" --contacts "$tab" --res-kb 100 --assembly mm10 --replicas 10 --jobs 10 \
            --workdir "$L_SCRATCH/sic_full_cell$c" --out "$R/models/sic/cell$c.npz" ;;
  *) echo "unknown METHOD=$METHOD"; exit 1 ;;
esac
