#!/bin/bash
# Model 1 of each high-resolution GPU run as a small float32 npz (for rendering on the laptop).
#SBATCH --job-name=nd-extract
#SBATCH --partition=xiaojie,normal,owners
#SBATCH --time=00:20:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
set -euo pipefail
ml purge; ml python/3.12.1
W=$SCRATCH/uchrom-nd; mkdir -p $W/runs/render
$GROUP_HOME/$USER/uchrom-nd/venv-main/bin/python - <<'PY'
import numpy as np, os
W = os.environ["SCRATCH"] + "/uchrom-nd/runs"
for run, tag in (("native_gpu_full", "100kb"), ("native_gpu_10kb", "10kb"), ("native_gpu_1kb", "1kb")):
    z = np.load(f"{W}/{run}/cell1.npz")
    np.savez_compressed(f"{W}/render/cell1_{tag}_model1.npz", chrom=z["chrom"], pos=z["pos"],
                        coords=z["coords"][0].astype(np.float32))
    print(tag, z["coords"].shape)
PY
ls -la $W/runs/render
