"""HiGlass-compatible tileset API for U-Chrom contact map tiles.

Endpoints (HiGlass spec):
  GET /api/tileset_info?d=<uid>          → JSON with dataset metadata
  GET /api/tiles?d=<uid>.<z>.<x>.<y>    → JSON with dense tile data

UID format: "contact-{chrom}" e.g. "contact-chr1"

Tile format (matrix datatype):
  256×256 Float32 dense array, gzipped, base64-encoded.
  At zoom level z, the full chromatin range is divided into 2^z tiles per axis.
  Resolution: bin_size * factor, where factor = 2^(max_z - z).
"""

from __future__ import annotations

import base64
import gzip
import math
import warnings
from typing import Dict, Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

import webapp.backend.data_api as data_api

tileset_router = APIRouter()

BINS_PER_DIM = 256

# In-memory cache: uid → full NxN distance matrix (averaged across cells)
_matrix_cache: Dict[str, np.ndarray] = {}
# Tile cache: "uid.z.x.y" → encoded tile bytes
_tile_cache: Dict[str, str] = {}


def clear_cache() -> None:
    """Clear all caches (used in tests)."""
    _matrix_cache.clear()
    _tile_cache.clear()


def _get_session():
    s = data_api.current_session
    if s is None or s.chromdata is None:
        raise HTTPException(status_code=404, detail={"error": "No data loaded"})
    return s


def _parse_uid(uid: str):
    """Parse 'contact-{chrom}' → chrom string."""
    if not uid.startswith("contact-"):
        raise HTTPException(status_code=400, detail={"error": f"Unknown tileset uid: {uid}"})
    return uid[len("contact-"):]


def _flatten_ids(d):
    """Normalize the ``d`` query param into a flat list of ids.

    HiGlass batches requests using *repeated* params (``?d=a&d=b``), which
    FastAPI delivers as a list.  Older callers / our tests pass a single
    comma-separated string (``?d=a,b``).  Accept both transparently.
    """
    if d is None:
        return []
    items = d if isinstance(d, list) else [d]
    out = []
    for item in items:
        out.extend(part.strip() for part in item.split(",") if part.strip())
    return out


def _build_matrix(chrom: str) -> np.ndarray:
    """Build averaged distance matrix for chrom across all cells/traces."""
    if chrom in _matrix_cache:
        return _matrix_cache[chrom]

    s = _get_session()
    cd = s.chromdata
    spots = cd.spots
    chrom_spots = spots[spots["chrom"] == chrom]
    if chrom_spots.empty:
        raise HTTPException(status_code=404, detail={"error": f"No bins for {chrom}"})

    # Find all traces for this chrom
    trace_ids = chrom_spots["trace_id"].unique()
    n_bins = chrom_spots.groupby("trace_id").size().max()

    accum = np.zeros((n_bins, n_bins), dtype=np.float64)
    counts = np.zeros((n_bins, n_bins), dtype=np.int32)

    for tid in trace_ids:
        mask = (spots["trace_id"] == tid) & (spots["chrom"] == chrom)
        idx = np.where(mask)[0]
        if len(idx) < 2:
            continue
        coords = cd.coords[idx]  # shape (k, 3)
        k = len(coords)
        # Pairwise Euclidean distances
        diff = coords[:, None, :] - coords[None, :, :]  # (k, k, 3)
        dmat = np.sqrt((diff ** 2).sum(axis=-1))  # (k, k)
        accum[:k, :k] += dmat
        counts[:k, :k] += 1

    with np.errstate(invalid="ignore"):
        matrix = np.where(counts > 0, accum / counts, 0.0).astype(np.float32)

    _matrix_cache[chrom] = matrix
    return matrix


def _chrom_size(chrom: str) -> int:
    """Return max genomic end position for chrom."""
    s = _get_session()
    cd = s.chromdata
    spots = cd.spots
    chrom_spots = spots[spots["chrom"] == chrom]
    if chrom_spots.empty:
        return 1000000
    return int(chrom_spots["end"].max())


def _max_zoom(chrom_size: int) -> int:
    """Compute max zoom level so that at zoom 0 the whole chrom fits in one tile."""
    bins_total = chrom_size  # treat 1bp = 1 unit
    max_zoom = max(0, math.ceil(math.log2(bins_total / BINS_PER_DIM)))
    return int(max_zoom)


def _build_tile_array(matrix: np.ndarray, zoom: int, tx: int, ty: int,
                      max_zoom: int) -> np.ndarray:
    """Build a 256×256 float32 tile via vectorized downsampling."""
    n = matrix.shape[0]
    factor = max(1, math.ceil(n / (BINS_PER_DIM * (2 ** zoom))))
    # Pad matrix to multiple of (BINS_PER_DIM * factor)
    target = BINS_PER_DIM * factor
    pad = (target - n % target) % target
    if pad > 0:
        mat = np.pad(matrix, ((0, pad), (0, pad)), constant_values=np.nan)
    else:
        mat = matrix
    # Slice the tile region
    row_start = ty * BINS_PER_DIM * factor
    col_start = tx * BINS_PER_DIM * factor
    row_end = row_start + BINS_PER_DIM * factor
    col_end = col_start + BINS_PER_DIM * factor
    chunk = mat[row_start:row_end, col_start:col_end]
    # Pad chunk if smaller than expected (out-of-range tile)
    if chunk.shape[0] < BINS_PER_DIM * factor or chunk.shape[1] < BINS_PER_DIM * factor:
        chunk = np.pad(chunk,
                       ((0, BINS_PER_DIM * factor - chunk.shape[0]),
                        (0, BINS_PER_DIM * factor - chunk.shape[1])),
                       constant_values=np.nan)
    # Vectorized downsample: reshape → mean over factor blocks.
    # All-NaN blocks (padding past the chrom edge) collapse to NaN — that's
    # the intended "no data" sentinel HiGlass renders transparent, so silence
    # the resulting "Mean of empty slice" warning.
    reshaped = chunk.reshape(BINS_PER_DIM, factor, BINS_PER_DIM, factor)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        out = np.nanmean(reshaped, axis=(1, 3)).astype(np.float32)
    return out


def _encode_tile(matrix: np.ndarray, z: int, x: int, y: int, max_z: int) -> str:
    """Extract a 256×256 tile from the full matrix and return base64-gzipped float32."""
    out = _build_tile_array(matrix, z, x, y, max_z)
    raw = out.flatten().tobytes()  # little-endian float32
    compressed = gzip.compress(raw)
    return base64.b64encode(compressed).decode("ascii")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@tileset_router.get("/api/tileset_info")
def tileset_info(d: list[str] | None = Query(default=None)):
    """Return HiGlass tileset metadata for one or more datasets.

    Accepts repeated (``?d=a&d=b``) or comma-separated (``?d=a,b``) ids.
    """
    uids = _flatten_ids(d)
    result: Dict[str, Any] = {}
    for uid in uids:
        chrom = _parse_uid(uid)
        size = _chrom_size(chrom)
        max_z = _max_zoom(size)
        max_width = BINS_PER_DIM * (2 ** max_z)
        result[uid] = {
            "name": uid,
            "datatype": "matrix",
            "bins_per_dimension": BINS_PER_DIM,
            "max_zoom": max_z,
            "max_width": max_width,
            "min_pos": [0, 0],
            "max_pos": [max_width, max_width],
            "chromsizes": [[chrom, size]],
        }
    return JSONResponse(result)


@tileset_router.get("/api/tiles")
def tiles(d: list[str] | None = Query(default=None)):
    """Return one or more tiles.

    Each id has the form ``uid.z.x.y``.  Accepts repeated (``?d=a&d=b``) or
    comma-separated (``?d=a,b``) ids — HiGlass uses the repeated form.
    """
    tile_ids = _flatten_ids(d)
    result: Dict[str, Any] = {}
    for tile_id in tile_ids:
        parts = tile_id.rsplit(".", 3)
        if len(parts) != 4:
            raise HTTPException(status_code=400, detail={"error": f"Bad tile id: {tile_id}"})
        uid, z_s, x_s, y_s = parts
        z, x, y = int(z_s), int(x_s), int(y_s)

        cache_key = tile_id
        if cache_key in _tile_cache:
            dense, actual_max = _tile_cache[cache_key]
        else:
            chrom = _parse_uid(uid)
            matrix = _build_matrix(chrom)
            size = _chrom_size(chrom)
            max_z = _max_zoom(size)
            arr = _build_tile_array(matrix, z, x, y, max_z)
            actual_max = float(np.nanmax(arr)) if not np.all(np.isnan(arr)) else 1.0
            raw = arr.flatten().tobytes()
            compressed = gzip.compress(raw)
            dense = base64.b64encode(compressed).decode("ascii")
            _tile_cache[cache_key] = (dense, actual_max)

        result[tile_id] = {
            "dense": dense,
            "min_value": 0.0,
            "max_value": actual_max,
        }
    return JSONResponse(result)
