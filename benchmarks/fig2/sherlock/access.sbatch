#!/bin/bash
# Panel c on one cluster node: the single-cell read of chromdata.zarr (backed) against AnnData read whole
# (read_h5ad), AnnData read lazily (anndata.experimental.read_lazy, on Zarr and on the .h5ad) and SpatialData (lazy
# points + filter), on the Takei 2025 cerebellum subsets of 1e6 and 1e7 spots, files on node-local disk.  A
# separate results file (--out-json): another machine than the laptop series of c_access.json.  The data are
# fetched and built here when missing (Zenodo 7693825; apps/atlas/recipes/build_takei2025_cerebellum.py).
#   sbatch [--dependency=afterok:<setup job>] benchmarks/fig2/sherlock/access.sbatch
#SBATCH --job-name=fig2-access
#SBATCH --partition=owners,normal
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --output=%x-%j.out
source "$SCRATCH/uchrom-nd/repo-fig2lazy/benchmarks/fig2/sherlock/_env.sh"
cd "$REPO"
TK=$UCHROM_DATA/takei2025_cerebellum
if [ ! -f "$TK/takei2025_cerebellum_rep1.chromdata.zarr/zarr.json" ]; then
    $PY -m uchrom.datasets fetch takei2025_cerebellum
    /usr/bin/time -v $PY apps/atlas/recipes/build_takei2025_cerebellum.py --drop-raw 2>&1 | tail -40
fi
mkdir -p "$UCHROM_FIG2_WORK"
BACKENDS=${BACKENDS:-zarr-backed,anndata-memory,anndata-lazy,anndata-lazy-h5ad,spatialdata-lazy}
RES=$OUT/c_access_sherlock_${SLURM_JOB_ID:-local}.json
$PY -u benchmarks/fig2/c_access.py --sizes "${SIZES:-1e6,1e7}" --queries 20 --repeats 3 --backends "$BACKENDS" \
    --out-json "$RES"
# how the AnnData Zarr store is chunked (what a lazy read of one cell has to touch)
$PY - "$UCHROM_FIG2_WORK/c_access" "$OUT/anndata_zarr_chunks_${SLURM_JOB_ID:-local}.json" <<'PY'
import json, sys
from pathlib import Path
import zarr
out = {}
for p in sorted(Path(sys.argv[1]).glob("*.anndata.zarr")):
    g = zarr.open_group(str(p), mode="r")
    arrs = {}
    def walk(grp, pre):
        for k, v in grp.members():
            name = f"{pre}{k}"
            if isinstance(v, zarr.Array):
                arrs[name] = {"shape": list(v.shape), "chunks": list(v.chunks), "dtype": str(v.dtype)}
            else:
                walk(v, name + "/")
    walk(g, "")
    out[p.name] = {k: v for k, v in arrs.items() if k.startswith(("obs/", "obsm/"))}
Path(sys.argv[2]).write_text(json.dumps(out, indent=1))
print(json.dumps(out)[:3000])
PY
ls -la "$UCHROM_FIG2_WORK/c_access"
du -sh "$UCHROM_FIG2_WORK"/c_access/* 2>/dev/null
echo "results: $RES"
