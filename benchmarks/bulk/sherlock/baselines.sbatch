#!/bin/bash
# Baseline populations for every manifest input (bulk_baselines.py): HIPPS and the contact-matched
# Gaussian (pairwise-only, same input), the DIMES oracle (truth second moments), a replicated consensus
# structure (SMACOF), the random confined polymer (floor) and the truth halves (ceiling).
# S = 1,000 structures (su2020_genome, takei2021_1mb), 2,000 (su2020_chr21).
#
#   N=$(wc -l < $SCRATCH/uchrom-nd/runs/bulk/manifest.tsv)
#   sbatch --array=1-$N benchmarks/bulk/sherlock/baselines.sbatch
#SBATCH --job-name=bk-base
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo/benchmarks/bulk/sherlock/_env.sh"
task ${SLURM_ARRAY_TASK_ID:-1}
case $DATASET in su2020_chr21) N=2000 ;; *) N=1000 ;; esac
$PY $BK/bulk_baselines.py --truth "$TRUTH" --input "$INPUT" "${RCARG[@]}" --n $N --seed 1 --out-dir "$BASEDIR"
ls -la "$BASEDIR"
