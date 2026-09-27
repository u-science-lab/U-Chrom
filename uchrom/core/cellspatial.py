"""Cell spatial position: centroids, outlines and linked SpatialData.

Where each *cell* sits in the tissue / field of view is cell-level data.
It is kept apart from the chromatin ``coords`` (one row per spot):

* **Centroids** are columns of ``cd.cells`` — ``centroid_x``,
  ``centroid_y`` and optionally ``centroid_z`` (a second set under key
  ``k``: ``k_centroid_x`` …) — described by a record in
  ``uns['cell_spatial'][key]``::

      {"x_col": "centroid_x", "y_col": "centroid_y", "z_col": "centroid_z",
       "ndim": 3, "unit": "um", "frame": "fov", "region_col": "fov",
       "in_coords_frame": True, "status": "measured" | "inferred",
       "source": "...", "method": "...", "shapes": "cell"}

  ``frame`` names the coordinate system (``"fov"``: local to one field of
  view, which ``region_col`` names; ``"tissue"`` / ``"global"``: one
  stitched frame per section / sample; any other string is kept);
  ``in_coords_frame`` says that the positions share the frame of
  ``cd.coords``; ``status`` is ``"measured"`` (imaged / segmented) or
  ``"inferred"`` (mapped, e.g. Tangram), in which case ``source`` is
  required.
* **Outlines** (polygons) are ``cd.cell_shapes[key]`` — a DataFrame with
  ``cell_id`` and ``geometry`` (WKB bytes), one row per cell, stored as
  GeoParquet (``tables/cell_shapes/<key>.parquet``), the representation
  SpatialData uses for shapes.  Their frame / unit / status live in
  ``uns['cell_shapes'][key]``.  Storage needs no geometry library;
  ``shapely`` / ``geopandas`` are optional and only needed to turn the WKB
  into geometry objects.
* **Linked SpatialData**: ``uns['linked_spatialdata'][key]`` records the
  path of an external SpatialData zarr store and the cell map (the table's
  ``region`` / ``instance_key`` ↔ ``cell_id``), like ``link_scool``.

This module holds the helpers; the public API is on
:class:`~uchrom.core.cdata.ChromData` (``set_cell_positions``,
``cell_positions``, ``set_cell_shapes``, ``cell_shapes_geodataframe``,
``link_spatialdata``, ``load_linked_spatialdata``, ``to_spatialdata``).
"""

from __future__ import annotations

import json
import struct
import warnings
from collections.abc import Mapping
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

#: canonical centroid columns of ``cd.cells`` (key "default")
CENTROID_COLUMNS = ("centroid_x", "centroid_y", "centroid_z")
#: allowed ``status`` values of a cell-position / cell-shape record
STATUSES = ("measured", "inferred")
#: suggested ``frame`` values (any string is accepted)
FRAMES = ("fov", "tissue", "global")
#: centroid column sets recognised when a store has no ``uns['cell_spatial']``
#: record (older loaders / the 1.x ``set_cell_spatial_coordinates``)
LEGACY_COLUMNS = (
    ("x_centroid", "y_centroid", "z_centroid"),   # read_seqfish_multiomics before 2.3
    ("spatial_x", "spatial_y", None),             # set_cell_spatial_coordinates before 2.3
)
#: record family names in ``uns``
POSITIONS_FAMILY = "cell_spatial"
SHAPES_FAMILY = "cell_shapes"
SPATIALDATA_FAMILY = "linked_spatialdata"
#: GeoParquet version written into the ``geo`` metadata of the shape tables
GEOPARQUET_VERSION = "1.0.0"


# ----------------------------------------------------------------------
# optional dependencies
# ----------------------------------------------------------------------

def require_shapely():
    try:
        import shapely
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            "shapely is required to turn cell outlines into geometry objects "
            "(storage does not need it).  Install it with `pip install shapely` "
            "or `pip install u-chrom[spatial]`."
        ) from exc
    return shapely


def require_geopandas():
    try:
        import geopandas
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            "geopandas is required for cell_shapes_geodataframe() / to_spatialdata().  "
            "Install it with `pip install geopandas` or `pip install u-chrom[spatial]`."
        ) from exc
    return geopandas


def require_spatialdata():
    try:
        import spatialdata
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            "spatialdata is required to load linked SpatialData stores or export to "
            "SpatialData.  Install it with `pip install spatialdata` or "
            "`pip install u-chrom[spatialdata]`."
        ) from exc
    return spatialdata


# ----------------------------------------------------------------------
# centroid records
# ----------------------------------------------------------------------

def centroid_columns(key: str, ndim: int) -> Tuple[str, ...]:
    """Default ``cells`` column names of position set ``key``."""
    prefix = "" if key == "default" else f"{key}_"
    return tuple(prefix + c for c in CENTROID_COLUMNS[:ndim])


def check_status(status: Optional[str], source: Optional[str], what: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"{what}: status must be one of {STATUSES}, got {status!r}")
    if status == "inferred" and not source:
        raise ValueError(f"{what}: inferred positions need source= (what they were inferred from)")


def normalize_record(rec: Mapping[str, Any]) -> Dict[str, Any]:
    """A ``uns['cell_spatial']`` record in the current schema (1.x records
    — ``coordinate_system``, ``inferred`` — are mapped; nothing is dropped)."""
    out = dict(rec)
    if "frame" not in out and out.get("coordinate_system"):
        out["frame"] = out["coordinate_system"]
    if "status" not in out and "inferred" in out:
        out["status"] = "inferred" if out["inferred"] else "measured"
    if "ndim" not in out and out.get("x_col"):
        out["ndim"] = 3 if out.get("z_col") else 2
    return out


def legacy_columns(cells: pd.DataFrame) -> Optional[Tuple[str, str, Optional[str]]]:
    """The first known centroid column set present in ``cells`` (canonical
    names first), for data without a ``uns['cell_spatial']`` record."""
    for cols in (CENTROID_COLUMNS, *LEGACY_COLUMNS):
        x, y, z = cols
        if x in cells.columns and y in cells.columns:
            return x, y, (z if z is not None and z in cells.columns else None)
    return None


def position_record(columns: Sequence[str], **fields: Any) -> Dict[str, Any]:
    """A ``uns['cell_spatial']`` record for existing ``cells`` columns (for
    loaders that build ``cells`` before the ChromData exists)."""
    cols = [str(c) for c in columns]
    if len(cols) not in (2, 3):
        raise ValueError("columns must name 2 or 3 columns (x, y[, z])")
    check_status(fields.get("status", "measured"), fields.get("source"), "position_record")
    rec = {"x_col": cols[0], "y_col": cols[1], "z_col": cols[2] if len(cols) == 3 else None,
           "ndim": len(cols), "status": "measured", **fields}
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in rec.items() if v is not None and v != ""}


def positions_frame(cells: pd.DataFrame, cell_ids: pd.Index, rec: Mapping[str, Any],
                    physical: bool = False) -> pd.DataFrame:
    """``x, y[, z]`` of the cells as a DataFrame indexed by ``cell_id``;
    ``physical`` multiplies by the record's ``voxel_size`` (positions stored
    in voxels) and reports ``voxel_unit`` as the unit."""
    cols = {"x": rec["x_col"], "y": rec["y_col"]}
    if rec.get("z_col"):
        cols["z"] = rec["z_col"]
    missing = [c for c in cols.values() if c not in cells.columns]
    if missing:
        raise KeyError(f"cell position columns {missing} are not in cd.cells")
    out = pd.DataFrame({k: pd.to_numeric(cells[c], errors="coerce").to_numpy(dtype=np.float64)
                        for k, c in cols.items()}, index=pd.Index(cell_ids, name="cell_id"))
    rec = dict(rec)
    if physical and rec.get("voxel_size") is not None:
        size = list(rec["voxel_size"])
        if len(size) < len(cols):
            raise ValueError(f"voxel_size {size} has fewer axes than the positions")
        for j, k in enumerate(cols):
            out[k] = out[k] * float(size[j])
        rec["stored_unit"] = rec.get("unit")
        rec["unit"] = rec.get("voxel_unit")
    if rec.get("region_col") and rec["region_col"] in cells.columns:
        out["region"] = cells[rec["region_col"]].astype(str).to_numpy()
    out.attrs["cell_spatial"] = rec
    return out


# ----------------------------------------------------------------------
# WKB (no geometry library needed)
# ----------------------------------------------------------------------

_WKB_TYPES = {1: "Point", 2: "LineString", 3: "Polygon", 4: "MultiPoint", 5: "MultiLineString",
              6: "MultiPolygon", 7: "GeometryCollection"}


def polygon_wkb(vertices) -> bytes:
    """ISO WKB of a polygon from its exterior ring ``(n, 2)`` or ``(n, 3)``
    (closed automatically), or a list of rings (exterior first, then holes)."""
    if len(vertices) == 0:
        raise ValueError("empty polygon")
    rings = [vertices] if np.ndim(vertices[0]) == 1 else list(vertices)
    rings = [np.asarray(r, dtype=np.float64) for r in rings]
    dims = {r.shape[1] if r.ndim == 2 else -1 for r in rings}
    if len(dims) != 1 or dims.pop() not in (2, 3):
        raise ValueError("polygon rings must be (n, 2) or (n, 3) vertex arrays")
    dim = rings[0].shape[1]
    parts = [struct.pack("<BII", 1, 3 if dim == 2 else 1003, len(rings))]
    for r in rings:
        if len(r) < 3:
            raise ValueError("a polygon ring needs at least 3 vertices")
        if not np.array_equal(r[0], r[-1]):
            r = np.vstack([r, r[:1]])
        parts.append(struct.pack("<I", len(r)))
        parts.append(np.ascontiguousarray(r, dtype="<f8").tobytes())
    return b"".join(parts)


def wkb_type(wkb: bytes) -> str:
    """GeoParquet geometry type name of one WKB value (e.g. ``"Polygon"``,
    ``"Polygon Z"``)."""
    if not isinstance(wkb, (bytes, bytearray, memoryview)) or len(wkb) < 5:
        raise ValueError("not a WKB value")
    b = bytes(wkb[:5])
    code = struct.unpack("<I" if b[0] == 1 else ">I", b[1:5])[0]
    z = bool(code & 0x80000000) or 1000 <= (code & 0xFFFF) < 2000 or 3000 <= (code & 0xFFFF) < 4000
    base = (code & 0xFFFF) % 1000
    if base not in _WKB_TYPES:
        raise ValueError(f"unknown WKB geometry type {code}")
    return _WKB_TYPES[base] + (" Z" if z else "")


def to_wkb(shapes, cell_ids=None) -> pd.DataFrame:
    """Normalise outlines to a ``cell_id`` / ``geometry`` (WKB) DataFrame.

    ``shapes`` may be a GeoDataFrame / GeoSeries (index = cell ids unless a
    ``cell_id`` column is present), a DataFrame with ``cell_id`` and a WKB
    ``geometry`` column, a mapping ``cell_id → shape``, or a sequence of
    shapely geometries, WKB bytes or vertex arrays (``(n, 2)`` / ``(n, 3)``
    exterior rings; no shapely needed) aligned with ``cell_ids``.
    """
    extra = None
    if isinstance(shapes, Mapping) and not isinstance(shapes, pd.DataFrame):
        cell_ids = list(shapes.keys()) if cell_ids is None else cell_ids
        shapes = list(shapes.values())
    if isinstance(shapes, pd.DataFrame):
        df = shapes
        if "geometry" not in df.columns:
            raise ValueError("a shape table needs a 'geometry' column")
        ids = (df["cell_id"] if "cell_id" in df.columns else
               (pd.Series(cell_ids) if cell_ids is not None else pd.Series(df.index)))
        extra = df.drop(columns=[c for c in ("cell_id", "geometry") if c in df.columns]).reset_index(drop=True)
        values = list(df["geometry"])
        cell_ids = list(ids)
    elif isinstance(shapes, pd.Series):
        values = list(shapes)
        cell_ids = list(shapes.index) if cell_ids is None else cell_ids
    else:
        values = list(shapes)
    if cell_ids is None:
        raise ValueError("cell_ids are required for a plain sequence of shapes")
    cell_ids = [str(c) for c in cell_ids]
    if len(cell_ids) != len(values):
        raise ValueError(f"{len(values)} shapes but {len(cell_ids)} cell ids")
    wkb: List[bytes] = []
    for v in values:
        if isinstance(v, (bytes, bytearray, memoryview)):
            wkb.append(bytes(v))
        elif hasattr(v, "wkb") and hasattr(v, "geom_type"):     # a shapely geometry
            shapely = require_shapely()
            wkb.append(shapely.to_wkb(v, output_dimension=3 if getattr(v, "has_z", False) else 2,
                                      flavor="iso"))
        else:
            wkb.append(polygon_wkb(v))
    for w in wkb:
        wkb_type(w)                               # validates
    out = pd.DataFrame({"cell_id": pd.Series(cell_ids, dtype=object),
                        "geometry": pd.Series(wkb, dtype=object)})
    if pd.Index(out["cell_id"]).has_duplicates:
        raise ValueError("cell shapes: duplicate cell_id (one outline per cell and key)")
    if extra is not None and len(extra.columns):
        out = pd.concat([out, extra], axis=1)
    return out


def geo_metadata(df: pd.DataFrame) -> Dict[str, Any]:
    """The GeoParquet ``geo`` file metadata of a shape table."""
    types = sorted({wkb_type(w) for w in df["geometry"]}) if len(df) else []
    return {"version": GEOPARQUET_VERSION, "primary_column": "geometry",
            "columns": {"geometry": {"encoding": "WKB", "geometry_types": types, "crs": None}}}


def write_shapes_parquet(df: pd.DataFrame, path, level: int) -> List[str]:
    """Write a shape table as GeoParquet (WKB ``geometry`` + ``geo`` metadata);
    returns its geometry types."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    df = df.reset_index(drop=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    i = table.schema.get_field_index("geometry")
    table = table.set_column(i, pa.field("geometry", pa.binary()),
                             pa.array([bytes(w) for w in df["geometry"]], type=pa.binary()))
    geo = geo_metadata(df)
    meta = dict(table.schema.metadata or {})
    meta[b"geo"] = json.dumps(geo).encode()
    pq.write_table(table.replace_schema_metadata(meta), path, compression="zstd", compression_level=level)
    return geo["columns"]["geometry"]["geometry_types"]


def read_shapes_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.reset_index(drop=True)
    frame["cell_id"] = frame["cell_id"].astype(str).astype(object)
    frame["geometry"] = [bytes(w) for w in frame["geometry"]]
    return frame


def shapes_geodataframe(df: pd.DataFrame, meta: Optional[Mapping[str, Any]] = None):
    """A shape table as a GeoDataFrame indexed by ``cell_id``."""
    gpd = require_geopandas()
    shapely = require_shapely()
    geoms = shapely.from_wkb(np.asarray(list(df["geometry"]), dtype=object))
    extra = df.drop(columns=["cell_id", "geometry"])
    gdf = gpd.GeoDataFrame(extra.reset_index(drop=True), geometry=list(geoms))
    gdf.index = pd.Index(df["cell_id"].astype(str).to_numpy(), name="cell_id")
    if meta:
        gdf.attrs["cell_shapes"] = dict(meta)
    return gdf


# ----------------------------------------------------------------------
# SpatialData
# ----------------------------------------------------------------------

def spatialdata_table_attrs(path, table: Optional[str]) -> Tuple[Optional[str], Dict[str, Any], List[str]]:
    """``(table name, spatialdata_attrs, table names)`` of a SpatialData store
    (reads only the tables)."""
    sd = require_spatialdata()
    with warnings.catch_warnings():   # "table annotating an element not present" (tables only)
        warnings.simplefilter("ignore", UserWarning)
        sdata = sd.read_zarr(path, selection=("tables",))
    names = list(sdata.tables.keys())
    if table is None:
        if len(names) != 1:
            return None, {}, names
        table = names[0]
    if table not in sdata.tables:
        return table, {}, names
    return table, dict(sdata.tables[table].uns.get("spatialdata_attrs", {}) or {}), names


def spatialdata_instances(path, table: str, instance_key: str, region_key: Optional[str],
                          region: Any) -> pd.Series:
    """Instance ids of the rows of ``table`` that annotate ``region``."""
    sd = require_spatialdata()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        t = sd.read_zarr(path, selection=("tables",)).tables[table]
    obs = t.obs
    if instance_key not in obs.columns:
        raise KeyError(f"table {table!r} has no instance_key column {instance_key!r}")
    mask = np.ones(len(obs), dtype=bool)
    if region_key and region is not None and region_key in obs.columns:
        regions = [region] if isinstance(region, str) else list(region)
        mask = obs[region_key].astype(str).isin([str(r) for r in regions]).to_numpy()
    return obs.loc[mask, instance_key].astype(str)


def _instances_for(cd, record: Mapping[str, Any], cells: Optional[Iterable[Any]]) -> Optional[set]:
    if cells is None:
        return None
    wanted = [str(c) for c in cells]
    col = record.get("cell_col")
    if not col:
        return set(wanted)
    ids = cd._cells_axis_ids()
    ids = pd.Index(ids if ids is not None else cd.cells.index.astype(str))
    pos = ids.get_indexer(wanted)
    if (pos < 0).any():
        raise KeyError(f"cells not in cd.cells: {[w for w, p in zip(wanted, pos) if p < 0][:5]}")
    return set(cd.cells[col].astype(str).to_numpy()[pos])


def load_spatialdata(cd, record: Mapping[str, Any], *, cells=None, elements: Optional[Sequence[str]] = None):
    """The linked SpatialData object; ``cells`` subsets the annotating table
    (and the elements it annotates) to those ChromData cells."""
    sd = require_spatialdata()
    path = cd.resolve_link_path(record["path"])
    selection = None
    if elements is not None:
        selection = tuple(dict.fromkeys(list(elements) + ["tables"]))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        sdata = sd.read_zarr(path, selection=selection)
    keep = _instances_for(cd, record, cells)
    if keep is None:
        return sdata
    table = record.get("table")
    if table is None or table not in sdata.tables:
        raise KeyError(f"linked SpatialData has no table {table!r}; cannot subset by cell")
    t = sdata.tables[table]
    mask = t.obs[record["instance_key"]].astype(str).isin(keep).to_numpy()
    if record.get("region_key") and record.get("region") is not None:
        regions = [record["region"]] if isinstance(record["region"], str) else list(record["region"])
        mask &= t.obs[record["region_key"]].astype(str).isin([str(r) for r in regions]).to_numpy()
    return sd.match_sdata_to_table(sdata, table_name=table, table=t[mask].copy())


def to_spatialdata(cd, *, positions_key: str = "default", shapes_key: Optional[str] = None,
                   spots: bool = True, points: bool = True, cell_table: bool = True,
                   coordinate_system: Optional[str] = None):
    """Export spots, cell centroids / outlines, the cell table and ``points``
    as a :class:`spatialdata.SpatialData` (one coordinate system, identity
    transformations; the unit is recorded in ``attrs``)."""
    sd = require_spatialdata()
    import anndata as ad
    from spatialdata.models import PointsModel, ShapesModel, TableModel
    from spatialdata.transformations import Identity

    pos_rec = None
    try:
        pos = cd.cell_positions(positions_key)
        pos_rec = pos.attrs.get("cell_spatial", {})
    except KeyError:
        pos = None
    cs = coordinate_system or (pos_rec or {}).get("frame") or "global"
    tf = {cs: Identity()}
    out_points, out_shapes, tables = {}, {}, {}
    if spots and cd.n_spots:
        df = cd.spots_with_loci()[["chrom", "start", "end", "bin_id", "trace_id"]
                                  + (["cell_id"] if "cell_id" in cd.spots.columns else [])].copy()
        for c in ("chrom", "trace_id", "cell_id"):
            if c in df.columns:
                df[c] = df[c].astype(str)
        xyz = np.asarray(cd.coords)
        df["x"], df["y"], df["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
        # a spot frame of its own: spot coordinates need not share the cells' frame
        out_points["spots"] = PointsModel.parse(df, coordinates={"x": "x", "y": "y", "z": "z"},
                                                transformations={"spots": Identity()})
    if points:
        for key, p in cd.points.items():
            p = p.copy()
            for c in p.columns:
                if p[c].dtype == object or isinstance(p[c].dtype, pd.CategoricalDtype):
                    p[c] = p[c].astype(str)
            out_points[f"points_{key}"] = PointsModel.parse(
                p, coordinates={"x": "x", "y": "y", "z": "z"}, transformations={"spots": Identity()})
    region = None
    if pos is not None:
        cols = [c for c in ("x", "y", "z") if c in pos.columns]
        cen = pos[cols].reset_index()
        cen = cen[np.isfinite(cen[cols].to_numpy()).all(axis=1)]
        out_points["cell_centroids"] = PointsModel.parse(
            cen, coordinates={c: c for c in cols}, transformations=tf)
    skey = shapes_key if shapes_key is not None else (next(iter(cd.cell_shapes), None))
    if skey is not None and skey in cd.cell_shapes:
        gdf = cd.cell_shapes_geodataframe(skey)
        gdf = gdf[["geometry"]].copy()
        gdf.index = gdf.index.astype(str)
        name = f"cell_shapes_{skey}"
        out_shapes[name] = ShapesModel.parse(gdf, transformations=tf)
        region = name
    if cell_table and len(cd.cells):
        ids = cd._cells_axis_ids()
        ids = pd.Index(ids if ids is not None else cd.cells.index.astype(str))
        obs = cd.cells.copy()
        obs.index = ids.astype(str)
        for c in obs.columns:
            if obs[c].dtype == object:
                obs[c] = obs[c].astype(str)
        obs["cell_id"] = obs.index.to_numpy()
        adata = ad.AnnData(obs=obs, obsm={k: np.asarray(v) for k, v in cd.cellm.items()})
        if region is not None:
            known = set(out_shapes[region].index)
            adata = adata[adata.obs["cell_id"].isin(known)].copy()
            adata.obs["region"] = pd.Categorical([region] * adata.n_obs)
            tables["cells"] = TableModel.parse(adata, region=region, region_key="region", instance_key="cell_id")
        else:
            tables["cells"] = TableModel.parse(adata)
    sdata = sd.SpatialData(points=out_points, shapes=out_shapes, tables=tables)
    sdata.attrs["uchrom"] = {
        "exported_from": "ChromData",
        "xyz_unit": cd.uns.get("xyz_unit"),
        "cell_spatial": pos_rec or None,
        "cell_shapes": (cd.uns.get(SHAPES_FAMILY) or {}).get(skey) if skey is not None else None,
    }
    return sdata


# ----------------------------------------------------------------------
# FOF-CT Cell/ROI Mapping table (ROI_Boundaries, OME polygon)
# ----------------------------------------------------------------------

def polygon_rings(wkb: bytes) -> List[np.ndarray]:
    """Rings (exterior first) of a WKB Polygon, as ``(n, 2)`` / ``(n, 3)`` arrays."""
    b = bytes(wkb)
    order = "<" if b[0] == 1 else ">"
    code = struct.unpack(order + "I", b[1:5])[0]
    kind = wkb_type(b)
    if not kind.startswith("Polygon"):
        raise ValueError(f"expected a Polygon, got {kind}")
    dim = 3 if kind.endswith("Z") else 2
    if code & 0x40000000 or 2000 <= (code & 0xFFFF) < 4000:
        raise ValueError("polygons with M values are not supported")
    off = 5 + (4 if code & 0x20000000 else 0)          # EWKB SRID
    (n_rings,) = struct.unpack_from(order + "I", b, off)
    off += 4
    rings = []
    for _ in range(n_rings):
        (n,) = struct.unpack_from(order + "I", b, off)
        off += 4
        arr = np.frombuffer(b, dtype=np.dtype(order + "f8"), count=n * dim, offset=off).reshape(n, dim)
        off += 8 * n * dim
        rings.append(arr.astype(np.float64))
    return rings


def parse_ome_polygon(text: str) -> np.ndarray:
    """``"x1,y1 x2,y2 …"`` (or ``x,y,z`` triples; the OME ROI Polygon points
    string of FOF-CT ``ROI_Boundaries``) → ``(n, 2)`` / ``(n, 3)`` array."""
    pts = [p for p in str(text).strip().strip('"').replace(";", " ").split() if p]
    arr = [tuple(float(v) for v in p.split(",") if v != "") for p in pts]
    if not arr or len({len(a) for a in arr}) != 1 or len(arr[0]) not in (2, 3):
        raise ValueError(f"not an OME polygon points string: {str(text)[:60]!r}")
    return np.asarray(arr, dtype=np.float64)


def format_ome_polygon(wkb: bytes) -> str:
    """The exterior ring of a WKB polygon as an OME points string (the
    closing vertex dropped)."""
    ring = polygon_rings(wkb)[0]
    if len(ring) > 1 and np.array_equal(ring[0], ring[-1]):
        ring = ring[:-1]
    return " ".join(",".join(repr(float(v)) for v in p) for p in ring)


OME_POLYGON_FORMAT = ("Cell boundaries are reported in global coordinates following the OME Data Model "
                      "for Polygon - ROI: lists of comma separated x,y (or x,y,z) coordinates separated by "
                      "spaces (\"x1,y1 x2,y2 x3,y3\")")
