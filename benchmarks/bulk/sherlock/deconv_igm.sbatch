#!/bin/bash
# The deconvolution itself: uchrom.recon.bulk.deconv.deconvolve(method="igm") on one manifest input,
# for every seed / population size (design.md 7(b): 3 seeds x S in {1000, 5000, 10000}).
# Needs U-Chrom + the native engine with the IGM protocol (engine branch); set ENGINE_PY to its Python
# (e.g. the GPU env built by the engine branch's setup job).  Output:
#   $RUNS/models/<dataset>/<name>/igm_S<S>_seed<seed>.chromdata.zarr   (scored by score.sbatch)
# Nucleus of the forward model: the input's provenance (nucleus_radius_nm, occupancy) is passed as
# keyword arguments NUCLEUS_KW (default: nucleus_radius=<R>, occupancy=<occ>; adapt the names to the
# engine's API when it lands).
#
#   N=$(wc -l < $SCRATCH/uchrom-nd/runs/bulk/manifest.tsv)
#   sbatch --array=1-$N --export=ALL,ENGINE_PY=/path/to/python benchmarks/bulk/sherlock/deconv_igm.sbatch
#SBATCH --job-name=bk-igm
#SBATCH --partition=gpu,owners
#SBATCH --gpus=1
#SBATCH -C GPU_SKU:H100_SXM5
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --output=%x-%A_%a.out
source "$SCRATCH/uchrom-nd/repo-deconv/benchmarks/bulk/sherlock/_env.sh"
task ${SLURM_ARRAY_TASK_ID:-1}
EPY=${ENGINE_PY:-$PY}
SIZES=${SIZES:-"1000 5000 10000"}
SEEDS=${SEEDS:-"1 2 3"}
PROV=${RCFROM:-$INPUT}
read -r RN OCC < <($PY -c "
import json, numpy as np
p = json.loads(str(np.load('$PROV')['provenance']))
p = p.get('simulation', p)
print(p.get('nucleus_radius_nm', 'null'), p.get('occupancy', 0.2))")
KW=${NUCLEUS_KW:-"--kw nucleus_radius=$RN --kw occupancy=$OCC"}
cd "$REPO"
for S in $SIZES; do
  for seed in $SEEDS; do
    out=$MODELDIR/igm_S${S}_seed${seed}.chromdata.zarr
    [ -e "$out" ] && continue
    PYTHONPATH=$REPO $EPY $BK/run_deconv.py --input "$INPUT" --method igm --n-structures $S --seed $seed $KW --out "$out"
  done
done
