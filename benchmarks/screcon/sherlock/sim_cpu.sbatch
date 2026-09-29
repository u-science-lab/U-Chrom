#!/bin/bash
# Simulation benchmark: one CPU method on one manifest table per array task (5 models / replicas,
# seed 1).  METHOD = nucdyn_cpu | orig | hickit | sic.  Resolutions: su2020_chr21 50 kb;
# takei2021_1mb 1 Mb (Si-C: 250 kb - it cannot model at 1 Mb; scored at the truth loci by position).
# Expected per task: nucdyn_cpu / hickit minutes; orig < 2 h; sic unknown (hours) - check the smoke job.
#
#   sbatch --array=1-180%60 --export=ALL,METHOD=orig   benchmarks/screcon/sherlock/sim_cpu.sbatch
#   sbatch --array=1-180%60 --export=ALL,METHOD=hickit --time=01:00:00 benchmarks/screcon/sherlock/sim_cpu.sbatch
#   sbatch --array=1-180%40 --export=ALL,METHOD=sic --time=24:00:00 benchmarks/screcon/sherlock/sim_cpu.sbatch
#SBATCH --job-name=sc-sim-cpu
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=5
#SBATCH --mem=16G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
sim_task "${SLURM_ARRAY_TASK_ID:?}"
out="$OUTM/${METHOD:?}.npz"
[ -f "$out" ] && { echo "exists $out"; exit 0; }
case $METHOD in
  nucdyn_cpu) $PY $SC/run_nucdyn.py --contacts "$TABLE" --res $RES --device cpu --n-threads 5 --n-models 5 --seed 1 --out "$out" ;;
  orig)       $ORIG_PY $SC/run_nucdyn_original.py --nd-dir "$ND" --contacts "$TABLE" --res $RES --models 5 --cpu 5 --seed 1 --out "$out" ;;
  hickit)     $PY $SC/run_hickit.py --hickit "$HICKIT" --contacts "$TABLE" --res $RES --assembly $ASM --n-models 5 --seed 1 --out "$out" ;;
  sic)        $PY $SC/run_sic.py --sic-dir "$SIC" --contacts "$TABLE" --res-kb $SIC_RES_KB --assembly $ASM --replicas 5 \
                --workdir "$L_SCRATCH/sic_${DATASET}_$NAME" --out "$out" ;;
  *) echo "unknown METHOD=$METHOD"; exit 1 ;;
esac
