#!/bin/bash
# Rust test suite of the engine on an NVIDIA H100 (wgpu / Vulkan): the IGM GPU-vs-CPU
# agreement tests (MD, energies / violation counts, CG, A-step + assignment) run on the
# production GPU, not only on the laptop's Metal GPU.
#
#   sbatch benchmarks/bulk/sherlock/gpu_tests.sbatch
#SBATCH --job-name=bulk-gputest
#SBATCH --partition=xiaojie
#SBATCH -G 1
#SBATCH --time=00:45:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --output=%x-%j.out

source "$SLURM_SUBMIT_DIR/benchmarks/bulk/sherlock/_env.sh"
ml rust/1.97.1
export CARGO_HOME=$SCRATCH/.cache/cargo CARGO_TARGET_DIR=$L_SCRATCH/cargo-target
cd "$REPO/packages/uchrom-nucdyn"
cargo test --release --features gpu -- --nocapture --test-threads=1 2>&1 | grep -E "GPU|CPU|A-step|assignment|test result|panicked|FAILED|skipped"
