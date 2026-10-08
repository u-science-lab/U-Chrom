#!/bin/bash
# The whole uchrom test suite (without stopping at the first failure) and the uchrom-maps Rust tests on the
# snaphic repo copy.
#
#   sbatch --export=ALL,REPO=$SCRATCH/uchrom-nd/repo-sc-snaphic,ENGINE=snaphic .../snaphic_tests.sbatch
#SBATCH --job-name=snaphic-tests
#SBATCH --partition=xiaojie,normal
#SBATCH --time=01:30:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sc-snaphic}/benchmarks/sc_structures/sherlock/_env.sh"
export OPENBLAS_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK RAYON_NUM_THREADS=$SLURM_CPUS_PER_TASK
ml rust/1.97.1
export CARGO_HOME=$SCRATCH/.cache/cargo CARGO_TARGET_DIR=$W/cargo-target-snaphic
(cd "$REPO/packages/uchrom-maps" && cargo test --release 2>&1 | tail -4)
cd "$REPO/packages/uchrom" && "$PY" -m pytest tests -q -p no:cacheprovider 2>&1 | tail -40
