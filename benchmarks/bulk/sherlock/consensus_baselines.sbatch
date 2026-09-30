#!/bin/bash
# Consensus baselines on the same balanced input (mds_baselines.py), one line of
# benchmarks/bulk/consensus/tasks_baselines.tsv per array task: U-Chrom PyTorch MDS full mode (genome-wide
# matrix when <= 15,000 bins; and per chromosome) and miniMDS full mode per chromosome (no partitioning).
# Output: $CS/base/<tag>/{mds_full,mds_chrom,minimds}.npz + baselines.json.  HIPPS and IGM mean distances are
# computed inside consensus_score.sbatch.
#
#   N=$(grep -v '^#' benchmarks/bulk/consensus/tasks_baselines.tsv | tail -n +2 | wc -l)
#   sbatch --array=1-$N benchmarks/bulk/sherlock/consensus_baselines.sbatch
# Estimated: MDS full at 250 kb (~11,300 bins, dense SMACOF on the GPU) minutes; miniMDS full mode per
# chromosome at 100 kb (chr1 ~2,300 bins, sklearn SMACOF on the CPU) the longest, <= 6 h.
#SBATCH --job-name=cons-base
#SBATCH --partition=gpu,owners
#SBATCH --gpus=1
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo-consensus/benchmarks/bulk/sherlock/consensus_env.sh"
IFS=$'\t' read -r TAG CELL RES CHR METHODS <<< "$(task_line "$BC/tasks_baselines.tsv" "${SLURM_ARRAY_TASK_ID:-1}")"
echo "baselines $TAG: $CELL $RES $CHR [$METHODS]"
ARGS=(--cell "$CELL" --resolution "$RES" --methods $METHODS --minimds-dir "$MINIMDS" --device auto --out-dir "$CS/base/$TAG")
[ "$CHR" != genome ] && ARGS+=(--chroms ${CHR//,/ })
/usr/bin/time -v $PY "$BC/mds_baselines.py" "${ARGS[@]}"
