"""Figure 2b — what each container can represent (capability matrix).

For every (container, data element) cell this script records a mark and its
evidence:

* ``native``      — first-class, with its own structure (a slot / table /
  element whose semantics match the data element);
* ``linked``      — kept in an external community-standard file (not copied)
  and queried through the shared index (bins + cell map);
* ``convention``  — can be stored and read back through the library's public
  API, but only in a general-purpose slot (``uns``, ``obsm``, ``varp``,
  ``attrs``, extra columns, optional columns), so the structure is lost or
  ad hoc;
* ``none``        — no place for it through the format or its API.

Where feasible the mark is backed by a **tiny test** that stores the element
with that library's own API, writes it to disk, reads it back and checks the
values (``test.ok``).  FOF-CT is a CSV specification, not a library, so its
row rests on the specification pages (v1.0) alone.  Every test also says
which kind of slot it used (``slot``: ``dedicated`` / ``generic`` /
``external``); a test that needed a generic slot can only back a
``convention`` mark, one that needed an external file only ``linked`` — the
script fails on any inconsistency.

Rules:

* the evidence decides; only where it is genuinely ambiguous does the other
  tool get the better mark, and the ``note`` says so (these are listed as
  judgement calls in Supplementary Table S1);
* AnnData has one observation axis: each element is rated in its most
  favourable orientation (spots, cells or loci as ``obs`` / ``var``), even
  though the orientations exclude each other in one object — the
  ``hierarchy`` column is where that shows (the same holds for a SpatialData
  table, which is an AnnData);
* a data table serialised to JSON text inside a descriptive metadata
  attribute (cooler's ``metadata``) does not count as a place for it: the
  slot must hold the data as data (arrays, tables, columns, AnnData ``uns``
  DataFrames).  Parameters / software records (provenance) in such an
  attribute do count, the analysis result itself must be stored as data.
  Scalar key-values describing the object that carries the attribute do
  count, as a general-purpose slot: each cell's own properties in the
  ``metadata`` of that cell's cooler in a ``.scool``.  The JSON tests that
  do not count are still run and recorded (``counted: false``);
* partial reads: ``native`` when one cell's (or one chromosome's) rows can be
  read while reading from disk only those rows plus, at most, the selection
  key column (an index, row groups or chunked arrays); ``convention`` when the
  selection is only possible by scanning every row of the data (streamed in
  chunks / partitions, so memory stays bounded) or when part of the data
  (e.g. ``obs`` / ``obsm``) is loaded whole; ``none`` when the whole file
  must be loaded.

    python benchmarks/fig2/b_capabilities.py      # seconds, < 1 GB

Writes ``u-chrom-paper/manuscripts/full/figures/fig2/results/b_capabilities.json`` and Supplementary Table S1
(``u-chrom-paper/manuscripts/full/figures/fig2/tableS_capabilities.md``).
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

warnings.filterwarnings("ignore")

ROWS = ["chromdata.zarr", "FOF-CT (4DN)", "AnnData", "SpatialData", "MuData", "cooler (.cool / .scool)"]
COLS = [
    ("coords", "spot coordinates (x, y, z)"),
    ("hierarchy", "cell › trace › spot hierarchy"),
    ("spot_signals", "per-spot signals"),
    ("bin_signals", "per-locus (bin) signals"),
    ("cells", "cell table"),
    ("cell_emb", "cell embeddings (multi-dimensional)"),
    ("cell_pos", "cell spatial position (centroid / outline)"),
    ("contacts", "contact maps"),
    ("intervals", "genomic intervals (TADs / loops)"),
    ("points", "non-genomic points (RNA spots)"),
    ("provenance", "analysis results with provenance"),
    ("partial", "partial reads by cell / chromosome"),
]

#: one-sentence definition of every column (legend, caption and Table S1)
COL_DEFS = {
    "coords": "the x, y, z position of every spot (one imaged or reconstructed locus in one trace), with its unit.",
    "hierarchy": "which trace and which cell each spot belongs to, as nested levels rather than loose labels.",
    "spot_signals": "values measured per spot, such as immunofluorescence intensity or z-scores at that spot.",
    "bin_signals": "values per genomic bin shared by all cells, such as bulk ATAC / ChIP tracks or GC content.",
    "cells": "a table of scalar properties per cell, such as cell type, volume or RNA counts.",
    "cell_emb": "a multi-dimensional vector per cell, such as a PCA, UMAP or learned embedding.",
    "cell_pos": "where each cell is in the tissue or field of view (centroid and / or outline), with unit and "
                "coordinate frame.",
    "contacts": "locus × locus contact counts (Hi-C-type maps), in bulk or per cell.",
    "intervals": "genomic intervals and interval pairs called on the data, such as TADs and loops.",
    "points": "3-D points that are not genomic loci, such as RNA spots or protein puncta.",
    "provenance": "analysis results stored as data together with the function, parameters and version that "
                  "produced them.",
    "partial": "reading one cell's or one chromosome's rows from disk without reading the rest of the data.",
}
AUDIT_DATE = "2026-09-27"
#: the changes of the previous audit (2026-09-26, PR #76), kept in Table S1
PRIOR_AUDIT = {
    "date": "2026-09-26",
    "changes": [
        ("FOF-CT (4DN)", "cell_emb", "native", "convention",
         "split from 'cells & embeddings': FOF-CT has a cell table but no multi-dimensional per-cell slot"),
        ("SpatialData", "partial", "native", "convention",
         "criterion made explicit: a full partition scan is 'by convention'"),
        ("MuData", "partial", "native", "convention",
         "criterion made explicit: backed mode loads obs / obsm (the coordinates) whole"),
    ],
    "note": "New columns: cell embeddings (split from 'cells & embeddings') and cell spatial position.",
}

RNG = np.random.default_rng(0)
N_CELL, N_TRACE_PER_CELL, N_BIN = 3, 2, 8
N_SPOT = N_CELL * N_TRACE_PER_CELL * N_BIN

DED, GEN, EXT = "dedicated", "generic", "external"


def toy():
    """A tiny tracing data set shared by all tests."""
    bins = pd.DataFrame({"chrom": ["chr1"] * 5 + ["chr2"] * 3,
                         "start": [0, 100, 200, 300, 400, 0, 100, 200]})
    bins["end"] = bins["start"] + 100
    rows = []
    for c in range(N_CELL):
        for t in range(N_TRACE_PER_CELL):
            for b in range(N_BIN):
                rows.append((f"c{c}", f"c{c}_t{t}", b))
    spots = pd.DataFrame(rows, columns=["cell_id", "trace_id", "bin_id"])
    spots["spot_id"] = np.arange(N_SPOT)
    xyz = RNG.normal(size=(N_SPOT, 3))
    spot_sig = RNG.random(N_SPOT)
    bin_sig = RNG.random(N_BIN)
    cells = pd.DataFrame({"cell_type": ["a", "b", "a"]}, index=[f"c{c}" for c in range(N_CELL)])
    emb = RNG.normal(size=(N_CELL, 2))
    cell_xy = RNG.uniform(0, 100, size=(N_CELL, 2))           # cell centroids in the tissue / FOV
    cell_z = RNG.uniform(0, 10, size=N_CELL)
    outlines = [np.array([(x - 5, y - 5), (x + 5, y - 5), (x + 5, y + 5), (x - 5, y + 5)]) for x, y in cell_xy]
    contacts = pd.DataFrame({"bin1_id": [0, 0, 1, 5], "bin2_id": [0, 1, 3, 7], "count": [5, 3, 2, 1]})
    tads = pd.DataFrame({"chrom": ["chr1", "chr1"], "start": [0, 200], "end": [200, 500]})
    rna = pd.DataFrame({"x": RNG.normal(size=20), "y": RNG.normal(size=20), "z": RNG.normal(size=20),
                        "gene": RNG.choice(["Actb", "Gapdh"], 20), "cell_id": RNG.choice(["c0", "c1", "c2"], 20)})
    return dict(bins=bins, spots=spots, xyz=xyz, spot_sig=spot_sig, bin_sig=bin_sig, cells=cells, emb=emb,
                cell_xy=cell_xy, cell_z=cell_z, outlines=outlines, contacts=contacts, tads=tads, rna=rna)


def dense(contacts, n=N_BIN):
    m = np.zeros((n, n))
    m[contacts.bin1_id, contacts.bin2_id] = contacts["count"]
    return m


def sym(contacts):
    m = dense(contacts)
    return np.triu(m) + np.triu(m, 1).T


def T(ok, slot, detail=None, **kw):
    """One test result: passed?, which kind of slot held the element, what was done."""
    out = {"ok": bool(ok), "slot": slot}
    if detail:
        out["detail"] = detail
    out.update(kw)
    return out


def run(fn, tmp):
    """Run one test; ``fn`` returns {column: T(...)}."""
    try:
        return {"ok": True, "detail": fn(tmp)}
    except Exception as exc:  # a failure is a result too
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=3)}


# --------------------------------------------------------------------------- chromdata.zarr

def t_chromdata(tmp):
    import cooler

    from uchrom.core import ChromData

    d = toy()
    spots = d["spots"][["bin_id", "trace_id", "cell_id"]]
    cd = ChromData(d["xyz"], spots, bins=d["bins"],
                   cells=d["cells"].copy(), cellm={"X_umap": d["emb"]},
                   spot_tracks=pd.DataFrame({"intensity": d["spot_sig"]}),
                   tracks=pd.DataFrame({"atac": d["bin_sig"]}),
                   points={"rna": d["rna"]})
    cd.set_cell_positions(np.c_[d["cell_xy"], d["cell_z"]], cell_ids=list(d["cells"].index), unit="um",
                          frame="fov", status="measured", source="segmentation")
    cd.set_cell_shapes(d["outlines"], cell_ids=list(d["cells"].index), unit="um", frame="fov")
    cd.intervals.add("tads", d["tads"], kind="domain")
    cd.intervals.add("loops", pd.DataFrame({"chrom1": ["chr1"], "start1": [0], "end1": [100],
                                            "chrom2": ["chr1"], "start2": [300], "end2": [400]}), kind="pair")
    cd.results.set("tads.di", d["tads"], function="uchrom.strc.tad.di", params={"window": 5})
    # a real .scool, linked (not copied): per-cell maps stay in the external file
    cooler.create_scool(str(tmp / "cells.scool"), d["bins"], {c: d["contacts"] for c in d["cells"].index})
    cd.link_scool(tmp / "cells.scool", bin_size=100)
    path = tmp / "x.chromdata.zarr"
    cd.write(path)
    r = ChromData.read(path, original_order=True)
    b = ChromData.read(path, backed=True)
    one = b.get_cell("c1")
    ch = b.get_chrom("chr2")
    c1 = r.load_linked_scool(cell="c1")
    pos = r.cell_positions()
    shp = r.cell_shapes["cell"].set_index("cell_id")
    from uchrom.core.cellspatial import polygon_rings
    loops = r.intervals["loops"]
    return {
        "coords": T(np.allclose(r.coords, cd.coords), DED, "coords (n_spots, 3)"),
        "hierarchy": T(r.spots["trace_id"].astype(str).tolist() == spots["trace_id"].tolist()
                       and r.spots["cell_id"].astype(str).tolist() == spots["cell_id"].tolist(), DED,
                       "spots.trace_id / cell_id → traces / cells"),
        "spot_signals": T(np.allclose(r.spot_tracks["intensity"], d["spot_sig"]), DED, "spot_tracks"),
        "bin_signals": T(np.allclose(r.bin_tracks["atac"], d["bin_sig"]), DED, "bins + bin_tracks"),
        "cells": T(r.cells["cell_type"].astype(str).tolist() == ["a", "b", "a"], DED, "cells table"),
        "cell_emb": T(np.allclose(r.cellm["X_umap"], d["emb"]), DED, "cellm['X_umap'] (n_cells, 2)"),
        "cell_pos": T(np.allclose(pos[["x", "y", "z"]].to_numpy(), np.c_[d["cell_xy"], d["cell_z"]])
                      and pos.attrs["cell_spatial"]["frame"] == "fov" and pos.attrs["cell_spatial"]["unit"] == "um"
                      and np.allclose(polygon_rings(shp.loc["c1", "geometry"])[0][:4], d["outlines"][1]), DED,
                      "set_cell_positions: cells centroid_x / y / z + uns['cell_spatial'] record (unit, frame, "
                      "status); set_cell_shapes: outlines as GeoParquet tables/cell_shapes/cell.parquet "
                      "(spec.md 'Cell spatial position', format 2.3)"),
        "contacts": T(np.allclose(c1.matrix(balance=False)[:], sym(d["contacts"]))
                      and r.uns["linked_scool"]["default"]["bin_size"] == 100, EXT,
                      "link_scool → uns['linked_scool'] record; load_linked_scool(cell='c1') reads the "
                      "external .scool after the round trip"),
        "intervals": T(r.intervals["tads"].kind == "domain" and loops.kind == "pair"
                       and r.intervals["tads"][["start", "end"]].to_numpy().tolist() == [[0, 200], [200, 500]],
                       DED, "intervals: IntervalTable kind='domain' (TADs) and kind='pair' (loops)"),
        "points": T(np.allclose(r.points["rna"][["x", "y", "z"]], d["rna"][["x", "y", "z"]]), DED,
                    "points['rna']"),
        "provenance": T(r.results.record("tads.di").function == "uchrom.strc.tad.di"
                        and r.results.record("tads.di").params == {"window": 5}, DED,
                        "results: ResultRecord(function, params, ...)"),
        "partial": T(one.n_spots == N_TRACE_PER_CELL * N_BIN and ch.n_spots == N_CELL * N_TRACE_PER_CELL * 3,
                     DED, "read(backed=True).get_cell / get_chrom (index/ row ranges)"),
    }


# --------------------------------------------------------------------------- AnnData

def t_anndata(tmp):
    import anndata as ad
    import scipy.sparse as sp
    from anndata.experimental import read_lazy

    d = toy()
    # spots as obs: coords in obsm, ids in obs, per-spot signal in X
    obs = d["spots"].astype({"cell_id": str, "trace_id": str}).set_index(pd.Index(d["spots"]["spot_id"].astype(str).to_numpy()))
    a = ad.AnnData(X=d["spot_sig"][:, None], obs=obs, obsm={"spatial": d["xyz"]},
                   var=pd.DataFrame(index=["intensity"]))
    a.uns["tads"] = d["tads"]
    a.uns["rna_spots"] = d["rna"]
    a.uns["tads_params"] = {"function": "di", "window": 5}
    a.write_h5ad(tmp / "spots.h5ad")
    r = ad.read_h5ad(tmp / "spots.h5ad")
    out = {
        "coords": T(np.allclose(r.obsm["spatial"], d["xyz"]), GEN, "spots as obs, obsm['spatial'] (n_obs, 3)"),
        "hierarchy": T(r.obs["trace_id"].tolist() == obs["trace_id"].tolist(), GEN, "trace_id / cell_id obs columns"),
        "spot_signals": T(np.allclose(np.asarray(r.X).ravel(), d["spot_sig"]), DED, "spots as obs, X"),
        "intervals": T(np.array_equal(r.uns["tads"][["start", "end"]].to_numpy(),
                                      d["tads"][["start", "end"]].to_numpy()), GEN, "DataFrame in uns"),
        "points": T(np.allclose(r.uns["rna_spots"][["x", "y", "z"]], d["rna"][["x", "y", "z"]]), GEN,
                    "DataFrame in uns"),
        "provenance": T(r.uns["tads_params"]["window"] == 5, GEN, "dict in uns"),
    }
    # cells as obs × loci as var: cell table, embedding, cell centroids, per-locus var table, varp contact map
    var = d["bins"].copy()
    var["atac"] = d["bin_sig"]
    var.index = [f"b{i}" for i in range(N_BIN)]
    c = ad.AnnData(X=RNG.random((N_CELL, N_BIN)), obs=d["cells"], var=var,
                   obsm={"X_umap": d["emb"], "spatial": d["cell_xy"]},
                   varp={"contacts": sp.csr_matrix(dense(d["contacts"]))})
    c.write_h5ad(tmp / "cells.h5ad")
    rc = ad.read_h5ad(tmp / "cells.h5ad")
    out["bin_signals"] = T(np.allclose(rc.var["atac"], d["bin_sig"]), DED, "loci as var, var column")
    out["cells"] = T(rc.obs["cell_type"].tolist() == ["a", "b", "a"], DED, "cells as obs, obs table")
    out["cell_emb"] = T(np.allclose(rc.obsm["X_umap"], d["emb"]), DED, "cells as obs, obsm['X_umap']")
    out["cell_pos"] = T(np.allclose(rc.obsm["spatial"], d["cell_xy"]), GEN,
                        "cells as obs, obsm['spatial'] (squidpy convention; no coordinate system, no outline)")
    out["contacts"] = T(np.allclose(rc.varp["contacts"].toarray(), dense(d["contacts"])), GEN,
                        "one locus × locus matrix in varp")
    # partial read: anndata.experimental.read_lazy, select one cell (loads the cell_id column), load only that
    a.write_zarr(tmp / "spots.zarr")
    lz = read_lazy(tmp / "spots.zarr")
    sub = lz[(lz.obs["cell_id"] == "c1").to_numpy()].to_memory()
    out["partial"] = T(sub.n_obs == N_TRACE_PER_CELL * N_BIN and np.allclose(
        sub.obsm["spatial"], d["xyz"][d["spots"]["cell_id"].to_numpy() == "c1"]), DED,
        "read_lazy: obs / obsm / X are lazy (xarray / dask); mask from the cell_id column, to_memory() reads "
        "only the selected chunks")
    return out


# --------------------------------------------------------------------------- SpatialData

def t_spatialdata(tmp):
    import anndata as ad
    import geopandas as gpd
    import scipy.sparse as sp
    import spatialdata as sd
    from shapely.geometry import Point, Polygon
    from spatialdata.models import PointsModel, ShapesModel, TableModel
    from spatialdata.transformations import Scale, get_transformation

    d = toy()
    df = d["spots"].astype({"cell_id": str, "trace_id": str}).copy()
    df[["x", "y", "z"]] = d["xyz"]
    spots = PointsModel.parse(df, coordinates={"x": "x", "y": "y", "z": "z"})
    rna = PointsModel.parse(d["rna"], coordinates={"x": "x", "y": "y", "z": "z"}, feature_key="gene")
    cid = list(d["cells"].index)
    # cell centroids (circles) and cell outlines (polygons), with a coordinate-system transformation
    circles = gpd.GeoDataFrame({"geometry": [Point(*xy) for xy in d["cell_xy"]], "radius": [5.0] * N_CELL},
                               index=cid)
    outlines = gpd.GeoDataFrame({"geometry": [Polygon([(x - 5, y - 5), (x + 5, y - 5), (x + 5, y + 5), (x - 5, y + 5)])
                                              for x, y in d["cell_xy"]]}, index=cid)
    um = {"global": Scale([0.1, 0.1], axes=("x", "y"))}
    cells_shape = ShapesModel.parse(circles, transformations=um)
    outline_shape = ShapesModel.parse(outlines, transformations=um)
    # per-spot signal: a table annotating the spots points element (region + instance_key)
    st = ad.AnnData(X=d["spot_sig"][:, None], var=pd.DataFrame(index=["intensity"]),
                    obs=pd.DataFrame({"region": pd.Categorical(["spots"] * N_SPOT),
                                      "spot_id": d["spots"]["spot_id"].to_numpy()},
                                     index=[str(i) for i in range(N_SPOT)]))
    st = TableModel.parse(st, region="spots", region_key="region", instance_key="spot_id")
    # cell table annotating the cell shapes: cells × loci (var = loci, per-locus signal as a var column),
    # an embedding in obsm, a locus × locus map in varp
    var = d["bins"].copy()
    var["atac"] = d["bin_sig"]
    var.index = [f"b{i}" for i in range(N_BIN)]
    ct = ad.AnnData(X=RNG.random((N_CELL, N_BIN)), var=var,
                    obs=d["cells"].reset_index(names="cell").assign(region="cells"),
                    obsm={"X_umap": d["emb"]}, varp={"contacts": sp.csr_matrix(dense(d["contacts"]))})
    ct.obs["region"] = pd.Categorical(ct.obs["region"])
    ct.obs.index = ct.obs.index.astype(str)
    ct = TableModel.parse(ct, region="cells", region_key="region", instance_key="cell")
    tads = ad.AnnData(obs=d["tads"].astype({"start": int, "end": int}).set_index(pd.Index(["t0", "t1"])))
    sdata = sd.SpatialData(points={"spots": spots, "rna": rna},
                           shapes={"cells": cells_shape, "cell_outlines": outline_shape},
                           tables={"spot_table": st, "cell_table": ct, "tads": TableModel.parse(tads)})
    sdata.attrs["tads_params"] = {"function": "di", "window": 5}
    sdata.write(tmp / "x.sdata.zarr")
    r = sd.read_zarr(tmp / "x.sdata.zarr")
    p = r.points["spots"].compute().sort_values("spot_id")
    rs = r.tables["spot_table"]
    rs_sig = pd.Series(np.asarray(rs.X).ravel(), index=rs.obs["spot_id"].to_numpy()).sort_index()
    # the table is an annotator of the points element: get_values joins it through instance_key
    got = sd.get_values(value_key="intensity", sdata=r, element_name="spots", table_name="spot_table")
    rct = r.tables["cell_table"]
    circ = r.shapes["cells"].loc[cid]
    poly = r.shapes["cell_outlines"].loc[cid]
    out = {
        "coords": T(np.allclose(p[["x", "y", "z"]].to_numpy(), d["xyz"]), DED, "3-D points element (x, y, z)"),
        "hierarchy": T(p["trace_id"].tolist() == df["trace_id"].tolist(), GEN, "trace_id / cell_id point columns"),
        "spot_signals": T(np.allclose(rs_sig.to_numpy(), d["spot_sig"])
                          and rs.uns["spatialdata_attrs"]["region"] == "spots"
                          and "spot_table" in sd.get_element_annotators(r, "spots")
                          and np.allclose(np.sort(got.to_numpy().ravel()), np.sort(d["spot_sig"])), DED,
                          "a table annotating the spots points (region='spots', instance_key='spot_id'); "
                          "get_element_annotators lists it and get_values joins it to the points"),
        "bin_signals": T(np.allclose(rct.var["atac"], d["bin_sig"]), DED,
                         "var column of a cells × loci table annotating the cell shapes"),
        "cells": T(rct.obs["cell_type"].tolist() == ["a", "b", "a"], DED, "table annotating the cell shapes"),
        "cell_emb": T(np.allclose(rct.obsm["X_umap"], d["emb"]), DED, "obsm['X_umap'] of the cell table"),
        "cell_pos": T(np.allclose(np.c_[circ.geometry.x, circ.geometry.y], d["cell_xy"])
                      and np.allclose(np.asarray(poly.geometry.iloc[0].exterior.coords)[0], d["cell_xy"][0] - 5)
                      and isinstance(get_transformation(r.shapes["cells"], "global"), Scale), DED,
                      "shapes elements: circles (centroid + radius) and polygons (outline), each with a "
                      "coordinate-system transformation"),
        "contacts": T(np.allclose(rct.varp["contacts"].toarray(), dense(d["contacts"])), GEN,
                      "one locus × locus matrix in varp of a table"),
        "intervals": T(r.tables["tads"].obs["end"].astype(int).tolist() == [200, 500], GEN,
                       "interval rows as obs of a table annotating no element"),
        "points": T(len(r.points["rna"].compute()) == len(d["rna"]), DED, "points element, feature_key='gene'"),
        "provenance": T(r.attrs.get("tads_params", {}).get("window") == 5, GEN, "SpatialData.attrs"),
    }
    lazy = r.points["spots"]
    one = lazy[lazy["cell_id"] == "c1"].compute()
    out["partial"] = T(len(one) == N_TRACE_PER_CELL * N_BIN, GEN,
                       "lazy dask points: a filter on cell_id streams every partition (no index)",
                       partitions=int(lazy.npartitions))
    return out


# --------------------------------------------------------------------------- MuData

def t_mudata(tmp):
    import anndata as ad
    import mudata as md
    import scipy.sparse as sp

    d = toy()
    obs = d["spots"].astype({"cell_id": str, "trace_id": str}).set_index(pd.Index(d["spots"]["spot_id"].astype(str).to_numpy()))
    spots = ad.AnnData(X=d["spot_sig"][:, None], obs=obs, obsm={"spatial": d["xyz"]},
                       var=pd.DataFrame(index=["intensity"]))
    var = d["bins"].copy()
    var["atac"] = d["bin_sig"]
    var.index = [f"b{i}" for i in range(N_BIN)]
    cells = ad.AnnData(X=RNG.random((N_CELL, N_BIN)), obs=d["cells"], var=var,
                       obsm={"X_umap": d["emb"], "spatial": d["cell_xy"]},
                       varp={"contacts": sp.csr_matrix(dense(d["contacts"]))})
    rna = ad.AnnData(obs=d["rna"][["gene", "cell_id"]].set_index(pd.Index([f"r{i}" for i in range(len(d["rna"]))])),
                     obsm={"spatial": d["rna"][["x", "y", "z"]].to_numpy()})
    m = md.MuData({"spots": spots, "cells": cells, "rna": rna})
    m.uns["tads"] = d["tads"]
    m.uns["tads_params"] = {"function": "di", "window": 5}
    m.write_h5mu(tmp / "x.h5mu")
    r = md.read_h5mu(tmp / "x.h5mu")
    out = {
        "coords": T(np.allclose(r["spots"].obsm["spatial"], d["xyz"]), GEN, "obsm['spatial'] of a spots modality"),
        "hierarchy": T(r["spots"].obs["trace_id"].tolist() == obs["trace_id"].tolist(), GEN,
                       "trace_id / cell_id obs columns of the spots modality"),
        "spot_signals": T(np.allclose(np.asarray(r["spots"].X).ravel(), d["spot_sig"]), DED, "spots modality X"),
        "bin_signals": T(np.allclose(r["cells"].var["atac"], d["bin_sig"]), DED, "var of a cells × loci modality"),
        "cells": T(r["cells"].obs["cell_type"].tolist() == ["a", "b", "a"], DED, "obs of a cells modality"),
        "cell_emb": T(np.allclose(r["cells"].obsm["X_umap"], d["emb"]), DED, "obsm['X_umap'] of a cells modality"),
        "cell_pos": T(np.allclose(r["cells"].obsm["spatial"], d["cell_xy"]), GEN,
                      "obsm['spatial'] of a cells modality (convention)"),
        "contacts": T(np.allclose(r["cells"].varp["contacts"].toarray(), dense(d["contacts"])), GEN,
                      "one locus × locus matrix in varp"),
        "intervals": T(np.array_equal(r.uns["tads"]["end"].to_numpy(), d["tads"]["end"].to_numpy()), GEN,
                       "DataFrame in uns"),
        "points": T(np.allclose(r["rna"].obsm["spatial"], d["rna"][["x", "y", "z"]].to_numpy()), GEN,
                    "an RNA-spot modality, positions in obsm['spatial']"),
        "provenance": T(r.uns["tads_params"]["window"] == 5, GEN, "dict in uns"),
    }
    b = md.read_h5mu(tmp / "x.h5mu", backed=True)
    mask = (b["spots"].obs["cell_id"] == "c1").to_numpy()
    xs = np.asarray(b["spots"].X[np.flatnonzero(mask)]).ravel()
    obsm_in_memory = isinstance(b["spots"].obsm["spatial"], np.ndarray)
    out["partial"] = T(b["spots"].isbacked and np.allclose(xs, d["spot_sig"][mask]), GEN,
                       "read_h5mu(backed=True): X is sliced from disk by row, but obs and obsm (the "
                       "coordinates) are loaded whole", obsm_loaded_whole=obsm_in_memory)
    return out


# --------------------------------------------------------------------------- cooler

def t_cooler(tmp):
    import cooler

    d = toy()
    bins = d["bins"].copy()
    bins["atac"] = d["bin_sig"]
    # one 3-D structure as extra bin columns (one structure per file)
    xyz0 = d["xyz"][:N_BIN]
    bins[["x", "y", "z"]] = xyz0
    # TAD membership as a per-bin label column (domains only; loops have no place)
    bins["tad"] = [0, 0, 1, 1, 1, -1, -1, -1]
    meta = {"tads_params": {"function": "di", "window": 5, "result_column": "tad"}}
    cooler.create_cooler(str(tmp / "x.cool"), bins, d["contacts"], metadata=meta)
    c = cooler.Cooler(str(tmp / "x.cool"))
    rb = c.bins()[:]
    out = {
        "coords": T(np.allclose(rb[["x", "y", "z"]].to_numpy(), xyz0), GEN,
                    "extra bin columns x, y, z (one structure per file)"),
        "bin_signals": T(np.allclose(rb["atac"], d["bin_sig"]), DED, "bins table column"),
        "contacts": T(np.allclose(c.matrix(balance=False)[:], sym(d["contacts"])), DED, "pixels"),
        "intervals": T(rb["tad"].tolist() == [0, 0, 1, 1, 1, -1, -1, -1], GEN, "per-bin domain label column"),
        "provenance": T(c.info["metadata"]["tads_params"]["window"] == 5 and "generated-by" in c.info
                        and rb["tad"].tolist()[0] == 0, GEN,
                        "result as a bins column, its parameters as JSON in the metadata attribute"),
    }
    # .scool: per-cell maps under named cell groups
    cooler.create_scool(str(tmp / "x.scool"), d["bins"], {f"c{i}": d["contacts"] for i in range(N_CELL)})
    cells = cooler.fileops.list_scool_cells(str(tmp / "x.scool"))
    one = cooler.Cooler(f"{tmp / 'x.scool'}::{cells[1]}")
    out["partial"] = T(c.matrix(balance=False).fetch("chr2").shape == (3, 3)
                       and one.matrix(balance=False).fetch("chr1").shape == (5, 5), DED,
                       "indexed fetch('chr2'); one cell group of a .scool")
    # Traces and spots in a .scool: create_scool accepts one bins table per cell; each trace of the cell
    # becomes a set of extra bins columns (x_<trace>, y_<trace>, z_<trace>, intensity_<trace>).
    tr = str(tmp / "traces.scool")
    sp_ = d["spots"]
    per_cell_bins = {}
    for c in d["cells"].index:
        b = d["bins"].copy()
        for t in sorted(sp_.loc[sp_["cell_id"] == c, "trace_id"].unique()):
            m = (sp_["trace_id"] == t).to_numpy()
            b[[f"x_{t}", f"y_{t}", f"z_{t}"]] = d["xyz"][m][sp_.loc[m, "bin_id"].to_numpy()]
            b[f"intensity_{t}"] = d["spot_sig"][m][sp_.loc[m, "bin_id"].to_numpy()]
        per_cell_bins[c] = b
    cooler.create_scool(tr, per_cell_bins, {c: d["contacts"] for c in d["cells"].index})
    xyz_back, sig_back, trace_back = np.zeros_like(d["xyz"]), np.zeros(N_SPOT), [None] * N_SPOT
    for g in cooler.fileops.list_scool_cells(tr):
        rb_c = cooler.Cooler(f"{tr}::{g}").bins()[:]
        for t in [col[2:] for col in rb_c.columns if col.startswith("x_")]:
            m = np.flatnonzero((sp_["trace_id"] == t).to_numpy())
            xyz_back[m] = rb_c[[f"x_{t}", f"y_{t}", f"z_{t}"]].to_numpy()[sp_.loc[m, "bin_id"].to_numpy()]
            sig_back[m] = rb_c[f"intensity_{t}"].to_numpy()[sp_.loc[m, "bin_id"].to_numpy()]
            for i in m:
                trace_back[i] = (g.rsplit("/", 1)[-1], t)
    out["hierarchy"] = T(trace_back == list(zip(sp_["cell_id"], sp_["trace_id"])) and np.allclose(xyz_back, d["xyz"]),
                         GEN, "cells = .scool cell groups (each with its own bins table); traces = sets of extra "
                              "bins columns x_<trace>, y_<trace>, z_<trace>; spots = bins rows (writes; not "
                              "counted, rule 6: not a use of the format)", counted=False)
    out["spot_signals"] = T(np.allclose(sig_back, d["spot_sig"]), GEN,
                            "one extra bins column per trace (intensity_<trace>) in each cell's bins table "
                            "(writes; not counted, rule 6)", counted=False)
    # Per-cell properties in each cell's own cooler (.scool /cells/<name>): cooler.create_cooler on the
    # cell group URI writes that cell's `metadata` attribute (scalar key-values; rule 4: counted, generic).
    sc = str(tmp / "cells_meta.scool")
    cid = list(d["cells"].index)
    cooler.create_scool(sc, d["bins"], {c: d["contacts"] for c in cid})
    for i, c in enumerate(cid):
        meta_c = {"cell_type": d["cells"].loc[c, "cell_type"],
                  "umap_1": float(d["emb"][i, 0]), "umap_2": float(d["emb"][i, 1]),
                  "centroid_x": float(d["cell_xy"][i, 0]), "centroid_y": float(d["cell_xy"][i, 1]), "xy_unit": "um"}
        cooler.create_cooler(f"{sc}::/cells/{c}", d["bins"], d["contacts"], metadata=meta_c, mode="a")
    back = {c.rsplit("/", 1)[-1]: cooler.Cooler(f"{sc}::{c}").info["metadata"]
            for c in cooler.fileops.list_scool_cells(sc)}
    valid = cooler.fileops.is_scool_file(sc) and sorted(back) == cid
    out["cells"] = T(valid and [back[c]["cell_type"] for c in cid] == ["a", "b", "a"], GEN,
                     "each cell's properties as scalar key-values in the metadata attribute of its own cooler "
                     "(/cells/<name>), written with cooler.create_cooler(uri, ..., metadata=); a scan of every "
                     "cell group rebuilds the table")
    out["cell_emb"] = T(valid and np.allclose([[back[c]["umap_1"], back[c]["umap_2"]] for c in cid], d["emb"]),
                        GEN, "one scalar key per embedding dimension (umap_1, umap_2) in each cell's metadata "
                             "(writes; not counted, rule 6)", counted=False)
    out["cell_pos"] = T(valid and np.allclose([[back[c]["centroid_x"], back[c]["centroid_y"]] for c in cid],
                                              d["cell_xy"]), GEN,
                        "centroid_x / centroid_y (+ a unit key) in each cell's metadata; no frame, no outline")
    # Data tables serialised to JSON text in one metadata attribute are recorded but NOT counted
    # (rule 4): a whole cell table and an embedding matrix in the file-level attribute, and 2e5 RNA spots.
    big = pd.DataFrame({"x": RNG.normal(size=200_000), "y": RNG.normal(size=200_000),
                        "z": RNG.normal(size=200_000)})
    for col, payload, what in (
            ("cells_table_json", {"cells": {"c0": {"cell_type": "a"}}},
             "a whole cell table as JSON text in the file-level metadata attribute"),
            ("cell_emb_matrix_json", {"X_umap": d["emb"].tolist()},
             "an embedding matrix as JSON text in the file-level metadata attribute"),
            ("points", {"rna_spots": big.to_dict("list")}, "2e5 RNA spots as JSON text in the metadata attribute")):
        try:
            cooler.create_cooler(str(tmp / f"{col}.cool"), d["bins"], d["contacts"], metadata=payload)
            back = cooler.Cooler(str(tmp / f"{col}.cool")).info["metadata"]
            ok = back == json.loads(json.dumps(payload))
            out[col] = T(ok, GEN, what + " (stored; not counted, rule 4)", counted=False)
        except Exception as exc:
            out[col] = T(False, GEN, f"{what}: {type(exc).__name__}: {exc}", counted=False)
    return out


# --------------------------------------------------------------------------- marks + evidence

AD_DOC = "https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.html"
AD_LAZY = "https://anndata.readthedocs.io/en/stable/generated/anndata.experimental.read_lazy.html"
SQ_DOC = "https://squidpy.readthedocs.io/en/stable/notebooks/tutorials/tutorial_visium_hne.html"
SD_DOC = "https://spatialdata.scverse.org/en/stable/design_doc.html"
MU_DOC = "https://mudata.readthedocs.io/stable/io/mudata.html"
CO_DOC = "https://cooler.readthedocs.io/en/latest/schema.html"
FOF = "https://fish-omics-format.readthedocs.io/en/latest/"
CD_SPEC = "uchrom/core/spec.md"
CD_CODE = "uchrom/core/cdata.py"
FAVOURABLE = ("Rated in the most favourable orientation; one AnnData has a single obs axis, so spots, cells "
              "and loci cannot all be first-class in the same object (see the hierarchy column).")
JUDGEMENT = "Judgement call: "

# (mark, note, evidence URLs[, previous mark, reason for the change])
MARKS = {
    "chromdata.zarr": {
        "coords": ("native", "coords (n_spots, 3) + layers; unit in uns", [CD_SPEC]),
        "hierarchy": ("native", "spots → traces → cells via trace_id / cell_id; traces and cells tables", [CD_SPEC]),
        "spot_signals": ("native", "spot_tracks, row-aligned with spots", [CD_SPEC]),
        "bin_signals": ("native", "bins (locus axis, bin_id) + bin_tracks / binm", [CD_SPEC]),
        "cells": ("native", "cells table indexed by cell_id", [CD_SPEC]),
        "cell_emb": ("native", "cellm: per-cell multi-dimensional arrays (embeddings, UMAP)", [CD_SPEC]),
        "cell_pos": ("native", "spec.md 'Cell spatial position' (format 2.3): cells columns centroid_x / "
                               "centroid_y [/ centroid_z] described by uns['cell_spatial'] (unit, frame fov / tissue "
                               "/ global, region, measured / inferred + source, voxel size); outlines as "
                               "cell_shapes, GeoParquet WKB polygons (tables/cell_shapes/<key>.parquet, the "
                               "SpatialData shapes representation); set_cell_positions / cell_positions / "
                               "set_cell_shapes; loaders fill it (seqFISH+, FOF-CT cell and mapping tables)",
                     [CD_SPEC, "tests/core/test_cell_spatial.py", "uchrom/core/cellspatial.py"], "convention",
                     "cell positions became a schema element (centroid columns + record, GeoParquet outlines; "
                     "format 2.3, PR #77); before: two ad-hoc 2-D cells columns, no outline"),
        "contacts": ("linked", "linked, not copied: uns['linked_scool' / 'linked_cool'] records path, bin size "
                               "and cell map; load_linked_scool / Dataset.contacts(group=) read them (test: a real "
                               ".scool read back after the round trip). Our own call: the pixels stay in the "
                               "external .scool / .cool by design.", [CD_SPEC, CD_CODE]),
        "intervals": ("native", "intervals: typed IntervalTable (domain / pair / peak / segment); TADs as domain, "
                                "loops as pair", [CD_SPEC]),
        "points": ("native", "points: non-genomic 3-D points in the coords frame", [CD_SPEC]),
        "provenance": ("native", "results: ResultsStore of ResultRecord(kind, params, function, version, inputs, "
                                 "created_utc)", [CD_SPEC]),
        "partial": ("native", "read(backed=True): get_cell / get_trace / get_chrom read only the needed row "
                              "ranges (index/ runs; Fig. 2d)", [CD_SPEC, "uchrom/core/backed.py"]),
    },
    "FOF-CT (4DN)": {
        "coords": ("native", "core table X, Y, Z (required) + ##XYZ_Unit", [FOF + "core.html"]),
        "hierarchy": ("native", "Spot_ID → Trace_ID → Cell_ID in the core table; Trace Data and Cell Data "
                                "tables indexed by Trace_ID / Cell_ID", [FOF + "core.html", FOF + "trace.html",
                                                                         FOF + "cell.html"]),
        "spot_signals": ("native", "Spot Biological Data / Spot Quality tables indexed by Spot_ID (user-defined "
                                   "columns declared with #^ lines)", [FOF + "bio.html", FOF + "quality.html"]),
        "bin_signals": ("convention", "none of the 12 tables is indexed by genomic locus; a per-locus value can only "
                                      "be repeated on every spot as an optional column", [FOF + "format_overview.html"]),
        "cells": ("native", "Cell Data table (4dn_FOF-CT_cell), mandatorily indexed by Cell_ID, with optional "
                            "user-defined columns (cell type, volume, ...)", [FOF + "cell.html"]),
        "cell_emb": ("convention", "no embedding slot: the Cell Data table's columns are scalar optional columns, "
                                   "so an embedding is one #^ column per dimension",
                     [FOF + "cell.html"]),
        "cell_pos": ("native", "Cell/ROI Mapping table (4dn_FOF-CT_mapping; conditionally required whenever a Cell "
                               "Data table is deposited): ROI_Boundaries of each Cell_ID in global coordinates, "
                               "format declared in ##ROI_Boundaries_Format (OME polygon or OBJ mesh) + ##XYZ_Unit. "
                               "Outline native; a centroid only as an optional column",
                     [FOF + "mapping.html", FOF + "cell.html"]),
        "contacts": ("none", "no contact-matrix table in the 12 FOF-CT tables", [FOF + "format_overview.html"]),
        "intervals": ("convention", "no genomic-interval table (the Sub-Cell ROI table's 'Chromosome_Domain' is a "
                                    "spatial ROI, not a genomic interval); domain labels only as an optional "
                                    "per-spot column, loops (pairs) not representable",
                      [FOF + "format_overview.html", FOF + "subcell.html"]),
        "points": ("native", "RNA Spot Data table (RNA_Spot_ID, X, Y, Z, Gene_ID, RNA_name, link ids)",
                   [FOF + "rna.html"]),
        "provenance": ("convention", "header #Software_* fields describe the tools that produced a table; analysis "
                                     "results only as optional columns", [FOF + "format_overview.html"]),
        "partial": ("convention", "plain CSV without an index: one cell or chromosome is found only by scanning "
                                  "every row (streamed, e.g. pandas chunksize, so memory stays bounded)",
                    [FOF + "format_overview.html"]),
    },
    "AnnData": {
        "coords": ("convention", "obsm['spatial'] (n_obs, 3), a community convention; no trace / unit structure",
                   [AD_DOC]),
        "hierarchy": ("convention", "one obs axis: cell_id / trace_id only as obs columns; spots and cells cannot "
                                    "both be observations", [AD_DOC]),
        "spot_signals": ("native", "spots as obs: X / layers / obs columns. " + FAVOURABLE, [AD_DOC]),
        "bin_signals": ("native", "loci as var (cells × loci, as for scATAC peaks): var table. " + FAVOURABLE,
                        [AD_DOC]),
        "cells": ("native", "cells as obs: obs table. " + FAVOURABLE, [AD_DOC]),
        "cell_emb": ("native", "cells as obs: obsm (X_umap, X_pca), the slot designed for per-observation "
                               "multi-dimensional annotations. " + FAVOURABLE, [AD_DOC]),
        "cell_pos": ("convention", "cells as obs: obsm['spatial'] (n_cells, 2), the squidpy / scanpy convention; "
                                   "not an AnnData schema element (no coordinate system, unit or outline)",
                     [AD_DOC, SQ_DOC]),
        "contacts": ("convention", "no contact-map type: one dense or sparse locus × locus matrix can be put in varp "
                                   "(loci as var), without pixel/balancing schema, resolutions or per-cell maps. "
                                   + FAVOURABLE, [AD_DOC]),
        "intervals": ("convention", "a DataFrame in uns", [AD_DOC]),
        "points": ("convention", "a DataFrame in uns (or a second AnnData)", [AD_DOC]),
        "provenance": ("convention", "free-form dicts in uns (scanpy writes uns['<tool>']['params'])", [AD_DOC]),
        "partial": ("native", JUDGEMENT + "anndata.experimental.read_lazy (0.12, experimental API) opens obs as a "
                              "lazy xarray Dataset and obsm / X as dask arrays; a cell mask reads the cell_id "
                              "column, to_memory() then reads only the selected chunks. No per-cell index.",
                    [AD_LAZY]),
    },
    "SpatialData": {
        "coords": ("native", "points element with x, y, z (3-D points are supported) and coordinate-system "
                             "transformations", [SD_DOC]),
        "hierarchy": ("convention", "cell_id / trace_id as columns of the points; a table annotates one element "
                                    "level (region + instance_key), no nested cell › trace › spot", [SD_DOC]),
        "spot_signals": ("native", "a table annotating the spots points element (region + instance_key = spot_id): "
                                   "get_element_annotators lists it and get_values joins it to the points (test); "
                                   "extra columns of the points DataFrame also work", [SD_DOC]),
        "bin_signals": ("native", JUDGEMENT + "no genomic locus axis among the spatial elements, but a table is an "
                                  "AnnData: loci as var of a cells × loci table annotating the cell shapes, var "
                                  "columns = per-locus signals, as for AnnData (test uses this orientation instead "
                                  "of a dummy table annotating no element). " + FAVOURABLE, [SD_DOC]),
        "cells": ("native", "shapes (or labels) for cells + a table annotating them", [SD_DOC]),
        "cell_emb": ("native", "obsm of the table annotating the cells", [SD_DOC]),
        "cell_pos": ("native", "shapes element: circles (centroid + radius) or polygons (outline), with "
                               "coordinate-system transformations", [SD_DOC]),
        "contacts": ("convention", "no contact-map element: a table is an AnnData, so one locus × locus matrix in "
                                   "varp, as for AnnData", [SD_DOC]),
        "intervals": ("convention", "interval rows as obs of a table annotating no element", [SD_DOC]),
        "points": ("native", "a second points element (feature_key = gene)", [SD_DOC]),
        "provenance": ("convention", "SpatialData.attrs / table uns (free-form)", [SD_DOC]),
        "partial": ("convention", "points are lazy dask DataFrames without an index on cell or chromosome: a filter "
                                  "on cell_id then compute() streams every partition (Fig. 2d, 0.75 s at 1e7 spots). "
                                  "Spatial bounding-box / polygon queries are native but select by space, not by "
                                  "cell or chromosome.", [SD_DOC]),
    },
    "MuData": {
        "coords": ("convention", "obsm['spatial'] of a spots modality", [MU_DOC]),
        "hierarchy": ("convention", "spots and cells as separate modalities; the link is an obs column, "
                                    "no parent / child relation", [MU_DOC]),
        "spot_signals": ("native", "a spots modality (spots as obs): X / obs", [MU_DOC]),
        "bin_signals": ("native", "var of a cells × loci modality (loci as var). A MuData can hold a spots and a "
                                  "cells modality side by side, but within one modality the orientations exclude "
                                  "each other, as for AnnData", [MU_DOC]),
        "cells": ("native", "global obs or the obs of a cells modality", [MU_DOC]),
        "cell_emb": ("native", "obsm of a cells modality, or the global obsm (multimodal embeddings)", [MU_DOC]),
        "cell_pos": ("convention", "obsm['spatial'] of a cells modality (the AnnData / squidpy convention)",
                     [MU_DOC, SQ_DOC]),
        "contacts": ("convention", "no contact-map type: varp of a cells × loci modality (one matrix, as for "
                                   "AnnData)", [MU_DOC]),
        "intervals": ("convention", "a DataFrame in uns", [MU_DOC]),
        "points": ("convention", "an RNA-spot modality with obsm['spatial']", [MU_DOC]),
        "provenance": ("convention", "free-form uns", [MU_DOC]),
        "partial": ("convention", "read_h5mu(backed=True) keeps only each modality's X on disk (sliced by row); "
                                  "obs and obsm, i.e. the ids and the coordinates, are loaded whole (test). MuData "
                                  "0.3 has no lazy reader.", [MU_DOC]),
    },
    "cooler (.cool / .scool)": {
        "coords": ("convention", "extra bin columns x, y, z: one structure per file (or per cell of a .scool, one "
                                 "column set per trace); no spot table", [CO_DOC]),
        "hierarchy": ("none", "no trace or spot level: a .scool has per-cell groups, but traces and spots could "
                              "only be forced in as sets of per-trace bins columns (x_<trace>, ...; the test shows "
                              "this writes), which is not a use of the format (rule 6)", [CO_DOC], "convention",
                      "rule 6: by convention needs a normal use of the format, not a technically possible "
                      "encoding; per-trace column sets in each cell's bins table are not how cooler is used"),
        "spot_signals": ("none", "no spot level; per-trace intensity columns in each cell's bins table would "
                                 "write (test) but are not a use of the format (rule 6)", [CO_DOC], "convention",
                         "rule 6, as for the hierarchy"),
        "bin_signals": ("native", "bins table, which the schema allows to carry extra columns (e.g. weight, "
                                  "signals)", [CO_DOC]),
        "cells": ("convention", "no cell table, but every cell of a .scool is a cooler with its own metadata "
                                "attribute: the cell's properties as scalar key-values there (cooler.create_cooler "
                                "on /cells/<name>, test); the table is rebuilt by opening every cell group",
                  [CO_DOC], "none", "per-cell metadata of each cell's cooler is a general-purpose slot for that "
                                    "cell's properties (rule 4: key-values describing their own object count; a "
                                    "whole table as JSON in one attribute still does not)"),
        "cell_emb": ("none", "no per-cell arrays; one scalar metadata key per dimension (umap_1, umap_2, ...) "
                             "writes (test) but is not a use of the format for a 10- to 64-dimensional "
                             "embedding (rule 6)", [CO_DOC], "convention",
                     "rule 6: a few scalar properties per cell are a normal use of the metadata attribute, "
                     "an embedding split into one key per dimension is not"),
        "cell_pos": ("convention", "centroid_x / centroid_y (+ a unit key) in each cell's metadata (test); no "
                                   "coordinate frame, no outline", [CO_DOC], "none",
                     "same slot as the cell table: a centroid is two scalar properties of the cell"),
        "contacts": ("native", "pixels (bulk .cool; per cell .scool; multi-resolution .mcool)", [CO_DOC]),
        "intervals": ("convention", "domain membership as a per-bin label column of the bins table (data, not "
                                    "JSON); loops (pairs) have no place", [CO_DOC]),
        "points": ("none", "no place for non-genomic points; JSON text in the metadata attribute works for 2e5 "
                           "spots (test) but is not counted", [CO_DOC]),
        "provenance": ("convention", "the result as data (a bins column, as for intervals) and its parameters in "
                                     "the free-form JSON metadata attribute next to generated-by / creation-date "
                                     "(provenance metadata counts under rule 4; a result table as JSON would not)",
                       [CO_DOC]),
        "partial": ("native", "indexed fetch by genomic region (bin1_offset / chrom_offset indexes); one cell group "
                              "of a .scool", [CO_DOC]),
    },
}

TESTS = {"chromdata.zarr": t_chromdata, "AnnData": t_anndata, "SpatialData": t_spatialdata,
         "MuData": t_mudata, "cooler (.cool / .scool)": t_cooler}
LIB = {"chromdata.zarr": "uchrom", "AnnData": "anndata", "SpatialData": "spatialdata", "MuData": "mudata",
       "cooler (.cool / .scool)": "cooler"}
SLOT_OK = {"native": {DED}, "linked": {EXT}, "convention": {GEN, DED}}


def check(mark, t):
    """Why a test contradicts its mark (None when consistent)."""
    if not t.get("counted", True):
        return None
    if mark == "none":
        return "stored and read back, cannot be 'none'" if t["ok"] else None
    if not t["ok"]:
        return f"test failed but marked {mark}"
    if t.get("slot") not in SLOT_OK[mark]:
        return f"a {t.get('slot')} slot cannot back '{mark}'"
    return None


def main() -> None:
    import importlib

    versions = {}
    for mod in ("uchrom", "anndata", "spatialdata", "mudata", "cooler", "zarr", "h5py"):
        try:
            versions[mod] = importlib.import_module(mod).__version__
        except Exception:  # pragma: no cover
            versions[mod] = None
    versions["FOF-CT"] = f"v1.0 (specification pages checked {AUDIT_DATE})"
    cells, failures, changes, extra_tests = {}, [], [], {}
    with tempfile.TemporaryDirectory() as td:
        for row in ROWS:
            test = {}
            if row in TESTS:
                tmp = Path(td) / LIB[row]
                tmp.mkdir()
                res = run(TESTS[row], tmp)
                if isinstance(res["detail"], dict):
                    test = res["detail"]
                else:
                    print(res.get("traceback", ""))
                    test = {c: {"ok": False, "detail": res["detail"]} for c, _ in COLS}
            cells[row] = {}
            known = {c for c, _ in COLS}
            if any(k not in known for k in test):
                extra_tests[row] = {k: v for k, v in test.items() if k not in known}
            for col, _ in COLS:
                mark, note, urls, *chg = MARKS[row][col]
                entry = {"value": mark, "note": note, "evidence": urls,
                         "version": versions["FOF-CT"] if row.startswith("FOF") else versions[LIB[row]]}
                if chg:
                    entry["audit"] = {"date": AUDIT_DATE, "before": chg[0], "reason": chg[1]}
                    changes.append({"row": row, "col": col, "before": chg[0], "after": mark, "reason": chg[1]})
                t = test.get(col)
                if t is not None:
                    entry["test"] = {"script": "benchmarks/fig2/b_capabilities.py", **t}
                    why = check(mark, t)
                    if why:
                        failures.append((row, col, mark, why))
                cells[row][col] = entry
    for f in failures:
        print("MISMATCH", *f)
    payload = {
        "panel": "b",
        "title": "What each format can represent",
        "marks": {"native": "first-class, with its own structure",
                  "linked": "held as an external community-standard file (not copied) and queried through "
                            "the shared index",
                  "convention": "representable by convention: stored and read back through the public API in a "
                                "general-purpose slot, structure lost or ad hoc",
                  "none": "not supported"},
        "rules": ["the evidence decides; only a genuinely ambiguous cell gives the other tool the better mark, "
                  "and its note starts with 'Judgement call'",
                  "AnnData / MuData (and SpatialData table) elements rated in their most favourable orientation "
                  "(spots, cells or loci as observations); these orientations exclude each other in one object "
                  "(one AnnData, one MuData modality)",
                  "a test that needed a generic slot backs at most 'by convention', an external file 'linked'",
                  "a data table serialised to JSON text in a descriptive metadata attribute does not count "
                  "(recorded with counted: false); provenance metadata there does, and so do scalar key-values "
                  "describing the object that carries the attribute (each cell's own cooler in a .scool)",
                  "partial reads: native = one cell's / chromosome's rows are read from disk without reading the "
                  "other rows (beyond the selection key column); by convention = only by scanning every row "
                  "(streamed) or with part of the data loaded whole",
                  "by convention needs a normal use of the format that just lacks the structure; an encoding that "
                  "merely writes (e.g. tracing traces as per-trace column sets of cooler bins tables, an embedding "
                  "as one metadata key per dimension) is rated not supported, with the test still reported"],
        "rows": ROWS, "cols": [c for c, _ in COLS], "col_labels": dict(COLS), "col_defs": COL_DEFS,
        "cells": cells, "versions": versions, "audit_date": AUDIT_DATE, "audit_changes": changes,
        "label_changes": [{"col": "coords", "before": "3-D coordinates", "after": dict(COLS)["coords"],
                           "reason": "per-spot, and distinct from the cell spatial position"}],
        "prior_audit": {"date": PRIOR_AUDIT["date"], "note": PRIOR_AUDIT["note"],
                        "changes": [{"row": r, "col": c, "before": b, "after": a, "reason": why}
                                    for r, c, b, a, why in PRIOR_AUDIT["changes"]]},
        "uncounted_tests": extra_tests,
        "mismatches": [list(map(str, f)) for f in failures],
    }
    print(C.write_json("b_capabilities", payload))
    print(write_table(payload))
    if failures:
        raise SystemExit(f"{len(failures)} mark / test mismatches")


SYMBOL = {"native": "● native", "linked": "◎ linked (external file, queried through the index)",
          "convention": "○ by convention", "none": "– not supported"}


def write_table(payload) -> Path:
    """Supplementary Table S1 (``u-chrom-paper/manuscripts/full/figures/fig2/tableS_capabilities.md``) from the JSON."""
    rows, cols, lab = payload["rows"], payload["cols"], payload["col_labels"]
    v = payload["versions"]
    out = [
        "# Supplementary Table S1 — What each format can represent (evidence for Fig. 2b)",
        "",
        "Generated by `benchmarks/fig2/b_capabilities.py` from `u-chrom-paper/manuscripts/full/figures/fig2/results/b_capabilities.json`; "
        "do not edit by hand.",
        "",
        "**Columns.**",
        "",
    ]
    out += [f"- *{lab[c]}*: {payload['col_defs'][c]}" for c in cols]
    out += [
        "",
        "**Marks.** ● *native*: first-class, with its own structure. ◎ *linked*: kept in an external "
        "community-standard file (not copied) and queried through the shared index. ○ *by convention*: stored "
        "and read back through the library's public API, but only in a general-purpose slot (`uns`, `obsm`, "
        "`varp`, `attrs`, metadata attributes, extra or optional columns), so the structure is lost or ad hoc. "
        "– *not supported*: no place for it in the format or its API.",
        "",
        "**Rules.** (1) The evidence decides; only where it is genuinely ambiguous does the other tool get the "
        "better mark, and the note starts with *Judgement call*. (2) AnnData and MuData are rated in their most "
        "favourable orientation (spots, cells or loci as observations), and these orientations exclude each "
        "other in one object (one AnnData, one MuData modality; a MuData can hold one modality per orientation, "
        "linked only by `obs` columns). The hierarchy column is where that shows; the same holds for a "
        "SpatialData table, which is an AnnData. (3) A test that needed a general-purpose slot can back at most "
        "*by convention*, one that needed an external file *linked*; the script fails on any inconsistency. "
        "(4) A data table serialised to JSON text inside a descriptive metadata attribute (cooler's `metadata`) "
        "does not count; such tests are still run and reported as *not counted*. Parameters / software records "
        "(provenance) there do count, and so do scalar key-values that describe the object carrying the "
        "attribute (each cell's own cooler in a `.scool`), as a general-purpose slot; the result itself must be "
        "stored as data. (5) *Partial reads*: native when one cell's or one chromosome's rows are read from "
        "disk without reading the other rows (beyond the selection key column); by convention when that is "
        "only possible by scanning every row (streamed, memory bounded) or with part of the data (e.g. `obs` / "
        "`obsm`) loaded whole. (6) *By convention* needs a normal use of the format that only lacks the "
        "dedicated structure; an encoding that merely writes (tracing traces as per-trace column sets of cooler "
        "bins tables, an embedding split into one metadata key per dimension) is rated *not supported*, and "
        "its test is still reported.",
        "",
        "**Tests.** ✓ = a tiny test in `benchmarks/fig2/b_capabilities.py` stored the element with that "
        "library's own API, wrote it to disk, read it back and compared the values; the slot it used "
        "(dedicated / generic / external) is given. FOF-CT is a CSV specification, not a library, so its row "
        "rests on the specification pages (core, trace, cell, mapping, bio, quality, rna, subcell and the "
        "format overview) alone.",
        "",
        "**Versions checked.** " + "; ".join(f"{k} {val}" for k, val in v.items() if val) + ".",
        "",
        "| Container | " + " | ".join(lab[c] for c in cols) + " |",
        "|---|" + "---|" * len(cols),
    ]
    short = {"native": "●", "linked": "◎", "convention": "○", "none": "–"}
    for r in rows:
        out.append(f"| {r} | " + " | ".join(short[payload["cells"][r][c]["value"]] for c in cols) + " |")
    jc = [(r, c) for r in rows for c in cols if payload["cells"][r][c]["note"].startswith(JUDGEMENT)]
    if jc:
        out += ["", "**Judgement calls:** " + "; ".join(f"{r} — {lab[c]}" for r, c in jc)
                + " (see the notes below)."]
    out += ["", f"## Changes after the audit of {payload.get('audit_date', AUDIT_DATE)}", ""]
    if payload.get("audit_changes"):
        out += ["| Container | Element | Before | After | Reason |", "|---|---|---|---|---|"]
        for ch in payload["audit_changes"]:
            out.append(f"| {ch['row']} | {lab[ch['col']]} | {SYMBOL[ch['before']]} | {SYMBOL[ch['after']]} | "
                       f"{ch['reason']} |")
    for lc in payload.get("label_changes", []):
        out += ["", f"Column renamed: *{lc['before']}* → *{lc['after']}* ({lc['reason']})."]
    prior = payload.get("prior_audit")
    if prior:
        out += ["", f"## Changes after the audit of {prior['date']}", "",
                "| Container | Element | Before | After | Reason |", "|---|---|---|---|---|"]
        for ch in prior["changes"]:
            out.append(f"| {ch['row']} | {lab[ch['col']]} | {SYMBOL[ch['before']]} | {SYMBOL[ch['after']]} | "
                       f"{ch['reason']} |")
        out += ["", prior["note"]]
    out += ["", "## Evidence per cell", ""]
    for r in rows:
        out += [f"### {r}", "", "| Element | Mark | Evidence | Test |", "|---|---|---|---|"]
        for c in cols:
            e = payload["cells"][r][c]
            t = e.get("test")
            if t is None:
                ts = "— (specification)"
            elif not t.get("counted", True):
                ts = ("✓ " if t["ok"] else "✗ ") + "not counted: " + t.get("detail", "")
            else:
                ts = ("✓ " if t["ok"] else "✗ ") + f"({t.get('slot', '?')} slot) " + t.get("detail", "")
            links = ", ".join(f"[{u.rsplit('/', 1)[-1] or u}]({u})" if u.startswith("http") else f"`{u}`"
                              for u in e["evidence"])
            note = e["note"].replace("|", "\\|")
            ts = ts.replace("|", "\\|")
            out.append(f"| {lab[c]} | {SYMBOL[e['value']]} | {note} ({links}) | {ts} |")
        for k, t in (payload.get("uncounted_tests") or {}).get(r, {}).items():
            ts = (("✓ " if t["ok"] else "✗ ") + "not counted: " + t.get("detail", "")).replace("|", "\\|")
            out.append(f"| (extra test: {k}) | — | — | {ts} |")
        out.append("")
    sys.path.insert(0, str(C.ROOT / "benchmarks"))
    from _paper import paper_file
    path = paper_file("manuscripts/full/figures/fig2/tableS_capabilities.md")
    path.write_text("\n".join(out))
    return path


if __name__ == "__main__":
    main()
