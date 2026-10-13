#!/bin/bash
# The null stages of spatial_variable.py on the analysis cache ($OUT/cache, read only): cnv_null (both tissues)
# and patch_null (melanoma).  Results go to $W/runs/sv-nulls/results (copied to benchmarks/spatial_variable/results
# from the laptop).    REPO=$SCRATCH/uchrom-nd/repo-<name> sbatch --export=ALL nulls.sbatch [n_random]
#SBATCH --job-name=sv-nulls
#SBATCH --partition=xiaojie,normal
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --output=%x-%j.out
source "${REPO:-$SCRATCH/uchrom-nd/repo-sv}/benchmarks/spatial_variable/sherlock/_env.sh"
cd "$REPO"
RES=$W/runs/sv-nulls/results
mkdir -p "$RES"
for tissue in melanoma brain; do
    $PY -u benchmarks/spatial_variable/spatial_variable.py --tissue $tissue --out "$OUT/cache" --results "$RES" \
        --stages cnv_null --random "${1:-1000}"
done
$PY -u benchmarks/spatial_variable/spatial_variable.py --tissue melanoma --stats "$STATS" --out "$OUT/cache" \
    --results "$RES" --stages patch_null --random "${1:-1000}"
