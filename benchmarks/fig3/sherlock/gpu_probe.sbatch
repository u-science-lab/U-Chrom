#!/bin/bash
# Can the native engine's wgpu backend reach an NVIDIA GPU on Sherlock (Vulkan)?  If yes,
# run the Cell 1 ensemble (10 models, full schedule) on it; otherwise report what is missing.
#
#   sbatch benchmarks/fig3/sherlock/gpu_probe.sbatch
#SBATCH --job-name=nd-gpu
#SBATCH --partition=xiaojie,gpu
#SBATCH -G 1
#SBATCH --time=00:45:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out

ml purge; ml python/3.12.1
BASE=$GROUP_HOME/$USER/uchrom-nd; W=$SCRATCH/uchrom-nd
echo "host=$(hostname) job=$SLURM_JOB_ID"
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
for d in /usr/share/vulkan/icd.d /etc/vulkan/icd.d; do echo "$d:"; ls "$d" 2>&1; done
# The node has NVIDIA's Vulkan ICD but no Vulkan loader (libvulkan.so.1): take it from
# conda-forge (built for glibc 2.17) into a small env in $GROUP_HOME
VK=$BASE/vulkan-loader
[ -d "$VK" ] || ~/miniconda3/bin/mamba create -q -y -p "$VK" -c conda-forge --override-channels libvulkan-loader
export LD_LIBRARY_PATH=$VK/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
ls "$VK/lib" | grep -i vulkan
"$BASE/venv-main/bin/python" -c "import uchrom_nucdyn as un; print('gpu_info:', un.gpu_info())"
if "$BASE/venv-main/bin/python" -c "import uchrom_nucdyn as un, sys; sys.exit('unavailable' in str(un.gpu_info()))"; then
  cd "$W/repo" && "$BASE/venv-main/bin/python" benchmarks/fig3/a_nucdyn_engine_run.py --cells 1 --device gpu \
    --n-models 10 --temp-steps 500 --dyn-steps 100 --seed 1 --out "$W/runs/native_gpu_full"
fi
