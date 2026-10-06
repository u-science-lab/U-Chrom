#!/bin/bash
# Smoke test of every runner on Sherlock (minutes): Su chr21 truth 1, one simulated table, 2 models each,
# reduced schedules; Si-C and hickit run their real binaries here for the first time (not testable on
# the macOS laptop), so check this job's log before submitting the big arrays.
#
#   sbatch benchmarks/screcon/sherlock/smoke.sbatch        (after sim_prepare.sbatch)
#SBATCH --job-name=sc-smoke
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/screcon/sherlock/_env.sh"
O=$W/runs/screcon/smoke; mkdir -p $O
T=$S/truth/su2020_chr21/truth_1.npz
$PY $SC/simulate.py reads --truth $T --reads-per-mb 160 --rc-rel 1.0 --eps 0.05 --seed 1 --out $O/su_t1.txt.gz
$PY $SC/run_nucdyn.py --contacts $O/su_t1.txt.gz --res 50000 --device cpu --n-models 2 --temp-steps 100 \
  --dyn-steps 50 --out $O/nucdyn_cpu.npz
$ORIG_PY $SC/run_nucdyn_original.py --nd-dir "$ND" --contacts $O/su_t1.txt.gz --res 50000 --models 2 --cpu 2 \
  --temps 50 --dyns 50 --out $O/orig.npz
$PY $SC/run_hickit.py --hickit "$HICKIT" --contacts $O/su_t1.txt.gz --res 50000 --assembly hg38 --n-models 2 \
  --out $O/hickit.npz
$PY $SC/run_sic.py --sic-dir "$SIC" --contacts $O/su_t1.txt.gz --res-kb 50 --assembly hg38 --replicas 2 \
  --workdir "$L_SCRATCH/sic_smoke" --keep --out $O/sic.npz || echo "SI-C FAILED - see $L_SCRATCH/sic_smoke"
$PY $SC/simulate.py score --truth $T --population $S/truth/su2020_chr21/population.npz \
  --models $O/nucdyn_cpu.npz $O/orig.npz $O/hickit.npz $O/sic.npz --labels nucdyn_cpu orig hickit sic \
  --out $O/score.json
# held-out plumbing on cell 1 fold 1 with the hickit / random models
cell_fold 1
if [ -f "$SPLIT/eval_pairs.npz" ]; then
  $PY $SC/heldout.py score --eval "$SPLIT/eval_pairs.npz" --models "$MD/random_polymer.npz" --labels random_polymer \
    --n-boot 100 --out $O/heldout_random.json
fi
