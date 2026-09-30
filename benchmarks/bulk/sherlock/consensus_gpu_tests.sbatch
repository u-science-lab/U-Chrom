#!/bin/bash
# Engine tests on an NVIDIA H100 (wgpu / Vulkan): the whole Rust suite with the GPU feature (incl. the consensus
# GPU-vs-CPU and GPU recovery tests) and the Python consensus tests with the GPU present.
#
#   sbatch benchmarks/bulk/sherlock/consensus_gpu_tests.sbatch
#SBATCH --job-name=cons-gputest
#SBATCH --partition=xiaojie,gpu
#SBATCH -G 1
#SBATCH -C GPU_SKU:H100_SXM5
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/consensus_env.sh"
ml rust/1.97.1
export CARGO_HOME=$SCRATCH/.cache/cargo CARGO_TARGET_DIR=$L_SCRATCH/cargo-target
(cd "$REPO/native/nucdyn" && cargo test --release --features gpu -- --nocapture --test-threads=1 2>&1 \
  | grep -E "GPU|gpu\[|cpu\[|test result|panicked|FAILED|skipped")
$PY -m pytest -q -s "$REPO/tests/recon/test_consensus.py" 2>&1 | grep -E "r_all|single chromosome|passed|failed"
