"""Figure 2b — what each container can represent (capability matrix).

For every (container, data element) cell this script records a mark and its
evidence:

* ``native``      — first-class, with its own structure (a slot / table /
  element whose semantics match the data element);
* ``convention``  — can be stored and read back through the library's public
  API, but only in a general-purpose slot (``uns``, ``obsm``, extra columns,
  a JSON metadata attribute), so the structure is lost or ad hoc;
* ``none``        — no place for it through the format or its API.

Where feasible the mark is backed by a **tiny test** that stores the element
with that library's own API, writes it to disk, reads it back and checks the
values (``test.ok``).  FOF-CT is a CSV specification, not a library, so its
row rests on the specification pages (v1.0) alone.

Rules (fair and conservative toward the other tools):

* if in doubt, the other tool gets the better mark, and a ``note`` says so;
* AnnData has one observation axis: each element is rated in its most
  favourable orientation (spots, cells or loci as ``obs`` / ``var``), even
  though the orientations exclude each other in one object — the
  ``hierarchy`` column is where that shows;
* a data table serialised to JSON text inside a descriptive metadata
  attribute (cooler's ``metadata``) does not count as a place for it: the
  slot must hold the data as data (arrays, tables, columns, AnnData ``uns``
  DataFrames).  Provenance-like metadata in such an attribute does count.
  The JSON tests are still run and recorded (``counted: false``).

    python benchmarks/fig2/b_capabilities.py      # seconds, < 1 GB

Writes ``paper/fig2/results/b_capabilities.json`` and Supplementary Table S1
(``paper/fig2/tableS_capabilities.md``).
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
    ("coords", "3-D coordinates"),
    ("hierarchy", "cell › trace › spot hierarchy"),
    ("spot_signals", "per-spot signals"),
    ("bin_signals", "per-locus (bin) signals"),
    ("cells", "cell table & embeddings"),
    ("contacts", "contact maps"),
    ("intervals", "genomic intervals (TADs / loops)"),
    ("points", "non-genomic points (RNA spots)"),
    ("provenance", "analysis results with provenance"),
    ("partial", "partial reads by cell / chromosome"),
]

RNG = np.random.default_rng(0)
N_CELL, N_TRACE_PER_CELL, N_BIN = 3, 2, 8
N_SPOT = N_CELL * N_TRACE_PER_CELL * N_BIN


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
    contacts = pd.DataFrame({"bin1_id": [0, 0, 1, 5], "bin2_id": [0, 1, 3, 7], "count": [5, 3, 2, 1]})
    tads = pd.DataFrame({"chrom": ["chr1", "chr1"], "start": [0, 200], "end": [200, 500]})
    rna = pd.DataFrame({"x": RNG.normal(size=20), "y": RNG.normal(size=20), "z": RNG.normal(size=20),
                        "gene": RNG.choice(["Actb", "Gapdh"], 20), "cell_id": RNG.choice(["c0", "c1", "c2"], 20)})
    return dict(bins=bins, spots=spots, xyz=xyz, spot_sig=spot_sig, bin_sig=bin_sig, cells=cells, emb=emb,
                contacts=contacts, tads=tads, rna=rna)


def dense(contacts, n=N_BIN):
    m = np.zeros((n, n))
    m[contacts.bin1_id, contacts.bin2_id] = contacts["count"]
    return m


def run(fn, tmp):
    """Run one test; ``fn`` returns {column: ok or {"ok", "detail"}}."""
    try:
        return {"ok": True, "detail": fn(tmp)}
    except Exception as exc:  # a failure is a result too
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=3)}


# --------------------------------------------------------------------------- chromdata.zarr

def t_chromdata(tmp):
    from uchrom.core import ChromData

    d = toy()
    spots = d["spots"][["bin_id", "trace_id", "cell_id"]]
    cd = ChromData(d["xyz"], spots, bins=d["bins"],
                   cells=d["cells"], cellm={"X_umap": d["emb"]},
                   spot_tracks=pd.DataFrame({"intensity": d["spot_sig"]}),
                   tracks=pd.DataFrame({"atac": d["bin_sig"]}),
                   points={"rna": d["rna"]})
    cd.intervals.add("tads", d["tads"], kind="domain")
    cd.results.set("tads.di", d["tads"], function="uchrom.strc.tad.di", params={"window": 5})
    cd.link_scool(tmp / "cells.scool", bin_size=100)
    path = tmp / "x.chromdata.zarr"
    cd.write(path)
    r = ChromData.read(path, original_order=True)
    b = ChromData.read(path, backed=True)
    one = b.get_cell("c1")
    ch = b.get_chrom("chr2")
    out = {
        "coords": np.allclose(r.coords, cd.coords),
        "hierarchy": (r.spots["trace_id"].astype(str).tolist() == spots["trace_id"].tolist()
                      and r.spots["cell_id"].astype(str).tolist() == spots["cell_id"].tolist()),
        "spot_signals": np.allclose(r.spot_tracks["intensity"], d["spot_sig"]),
        "bin_signals": np.allclose(r.bin_tracks["atac"], d["bin_sig"]),
        "cells": (np.allclose(r.cellm["X_umap"], d["emb"])
                  and r.cells["cell_type"].astype(str).tolist() == ["a", "b", "a"]),
        "contacts": r.uns["linked_scool"]["default"]["bin_size"] == 100,
        "intervals": (r.intervals["tads"].kind == "domain"
                      and r.intervals["tads"][["start", "end"]].to_numpy().tolist() == [[0, 200], [200, 500]]),
        "points": np.allclose(r.points["rna"][["x", "y", "z"]], d["rna"][["x", "y", "z"]]),
        "provenance": (r.results.record("tads.di").function == "uchrom.strc.tad.di"
                       and r.results.record("tads.di").params == {"window": 5}),
        "partial": one.n_spots == N_TRACE_PER_CELL * N_BIN and ch.n_spots == N_CELL * N_TRACE_PER_CELL * 3,
    }
    return out


# --------------------------------------------------------------------------- AnnData

def t_anndata(tmp):
    import anndata as ad
    import scipy.sparse as sp

    d = toy()
    out = {}
    # spots as obs: coords in obsm, ids in obs, per-spot signal in X
    obs = d["spots"].astype({"cell_id": str, "trace_id": str}).set_index(pd.Index(d["spots"]["spot_id"].astype(str).to_numpy()))
    a = ad.AnnData(X=d["spot_sig"][:, None], obs=obs, obsm={"spatial": d["xyz"]},
                   var=pd.DataFrame(index=["intensity"]))
    a.uns["tads"] = d["tads"]
    a.uns["rna_spots"] = d["rna"]
    a.uns["tads_params"] = {"function": "di", "window": 5}
    a.write_h5ad(tmp / "spots.h5ad")
    r = ad.read_h5ad(tmp / "spots.h5ad")
    out["coords"] = np.allclose(r.obsm["spatial"], d["xyz"])
    out["hierarchy"] = r.obs["trace_id"].tolist() == obs["trace_id"].tolist()
    out["spot_signals"] = np.allclose(np.asarray(r.X).ravel(), d["spot_sig"])
    out["intervals"] = np.array_equal(r.uns["tads"][["start", "end"]].to_numpy(), d["tads"][["start", "end"]].to_numpy())
    out["points"] = np.allclose(r.uns["rna_spots"][["x", "y", "z"]], d["rna"][["x", "y", "z"]])
    out["provenance"] = r.uns["tads_params"]["window"] == 5
    # cells as obs × loci as var: cell table + embedding, per-locus var table, varp contact map
    var = d["bins"].copy()
    var["atac"] = d["bin_sig"]
    var.index = [f"b{i}" for i in range(N_BIN)]
    c = ad.AnnData(X=RNG.random((N_CELL, N_BIN)), obs=d["cells"], var=var,
                   obsm={"X_umap": d["emb"]}, varp={"contacts": sp.csr_matrix(dense(d["contacts"]))})
    c.write_h5ad(tmp / "cells.h5ad")
    rc = ad.read_h5ad(tmp / "cells.h5ad")
    out["bin_signals"] = np.allclose(rc.var["atac"], d["bin_sig"])
    out["cells"] = np.allclose(rc.obsm["X_umap"], d["emb"]) and rc.obs["cell_type"].tolist() == ["a", "b", "a"]
    out["contacts"] = np.allclose(rc.varp["contacts"].toarray(), dense(d["contacts"]))
    # partial read: anndata.experimental.read_lazy, select one cell, load only that
    from anndata.experimental import read_lazy
    a.write_zarr(tmp / "spots.zarr")
    lz = read_lazy(tmp / "spots.zarr")
    sub = lz[(lz.obs["cell_id"] == "c1").to_numpy()].to_memory()
    out["partial"] = sub.n_obs == N_TRACE_PER_CELL * N_BIN and np.allclose(
        sub.obsm["spatial"], d["xyz"][d["spots"]["cell_id"].to_numpy() == "c1"])
    return out


# --------------------------------------------------------------------------- SpatialData

def t_spatialdata(tmp):
    import anndata as ad
    import geopandas as gpd
    import scipy.sparse as sp
    import spatialdata as sd
    from shapely.geometry import Point
    from spatialdata.models import PointsModel, ShapesModel, TableModel

    d = toy()
    df = d["spots"].astype({"cell_id": str, "trace_id": str}).copy()
    df[["x", "y", "z"]] = d["xyz"]
    df["intensity"] = d["spot_sig"]
    spots = PointsModel.parse(df, coordinates={"x": "x", "y": "y", "z": "z"})
    rna = PointsModel.parse(d["rna"], coordinates={"x": "x", "y": "y", "z": "z"}, feature_key="gene")
    circles = gpd.GeoDataFrame({"geometry": [Point(i, i) for i in range(N_CELL)], "radius": [1.0] * N_CELL},
                               index=list(d["cells"].index))
    cells_shape = ShapesModel.parse(circles)
    # cell table annotating the cell shapes, with an embedding
    ct = ad.AnnData(obs=d["cells"].reset_index(names="cell").assign(region="cells"),
                    obsm={"X_umap": d["emb"]})
    ct.obs["region"] = pd.Categorical(ct.obs["region"])
    ct.obs.index = ct.obs.index.astype(str)
    ct = TableModel.parse(ct, region="cells", region_key="region", instance_key="cell")
    # per-locus table (not annotating any element) with a varp contact map
    var = d["bins"].copy()
    var["atac"] = d["bin_sig"]
    var.index = [f"b{i}" for i in range(N_BIN)]
    lt = ad.AnnData(X=np.zeros((1, N_BIN)), var=var, varp={"contacts": sp.csr_matrix(dense(d["contacts"]))})
    lt = TableModel.parse(lt)
    tads = ad.AnnData(obs=d["tads"].astype({"start": int, "end": int}).set_index(pd.Index(["t0", "t1"])))
    sdata = sd.SpatialData(points={"spots": spots, "rna": rna}, shapes={"cells": cells_shape},
                           tables={"cell_table": ct, "loci": lt, "tads": TableModel.parse(tads)})
    sdata.attrs["tads_params"] = {"function": "di", "window": 5}
    sdata.write(tmp / "x.sdata.zarr")
    r = sd.read_zarr(tmp / "x.sdata.zarr")
    p = r.points["spots"].compute().sort_values("spot_id")
    out = {
        "coords": np.allclose(p[["x", "y", "z"]].to_numpy(), d["xyz"]),
        "hierarchy": p["trace_id"].tolist() == df["trace_id"].tolist(),
        "spot_signals": np.allclose(p["intensity"], d["spot_sig"]),
        "bin_signals": np.allclose(r.tables["loci"].var["atac"], d["bin_sig"]),
        "cells": np.allclose(r.tables["cell_table"].obsm["X_umap"], d["emb"]),
        "contacts": np.allclose(r.tables["loci"].varp["contacts"].toarray(), dense(d["contacts"])),
        "intervals": r.tables["tads"].obs["end"].astype(int).tolist() == [200, 500],
        "points": len(r.points["rna"].compute()) == len(d["rna"]),
        "provenance": r.attrs.get("tads_params", {}).get("window") == 5,
    }
    lazy = r.points["spots"]
    one = lazy[lazy["cell_id"] == "c1"].compute()
    out["partial"] = len(one) == N_TRACE_PER_CELL * N_BIN
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
    cells = ad.AnnData(X=RNG.random((N_CELL, N_BIN)), obs=d["cells"], var=var, obsm={"X_umap": d["emb"]},
                       varp={"contacts": sp.csr_matrix(dense(d["contacts"]))})
    rna = ad.AnnData(obs=d["rna"][["gene", "cell_id"]].set_index(pd.Index([f"r{i}" for i in range(len(d["rna"]))])),
                     obsm={"spatial": d["rna"][["x", "y", "z"]].to_numpy()})
    m = md.MuData({"spots": spots, "cells": cells, "rna": rna})
    m.uns["tads"] = d["tads"]
    m.uns["tads_params"] = {"function": "di", "window": 5}
    m.write_h5mu(tmp / "x.h5mu")
    r = md.read_h5mu(tmp / "x.h5mu")
    out = {
        "coords": np.allclose(r["spots"].obsm["spatial"], d["xyz"]),
        "hierarchy": r["spots"].obs["trace_id"].tolist() == obs["trace_id"].tolist(),
        "spot_signals": np.allclose(np.asarray(r["spots"].X).ravel(), d["spot_sig"]),
        "bin_signals": np.allclose(r["cells"].var["atac"], d["bin_sig"]),
        "cells": np.allclose(r["cells"].obsm["X_umap"], d["emb"]),
        "contacts": np.allclose(r["cells"].varp["contacts"].toarray(), dense(d["contacts"])),
        "intervals": np.array_equal(r.uns["tads"]["end"].to_numpy(), d["tads"]["end"].to_numpy()),
        "points": np.allclose(r["rna"].obsm["spatial"], d["rna"][["x", "y", "z"]].to_numpy()),
        "provenance": r.uns["tads_params"]["window"] == 5,
    }
    b = md.read_h5mu(tmp / "x.h5mu", backed=True)
    mask = (b["spots"].obs["cell_id"] == "c1").to_numpy()
    xs = np.asarray(b["spots"].X[np.flatnonzero(mask)]).ravel()
    out["partial"] = b["spots"].isbacked and np.allclose(xs, d["spot_sig"][mask])
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
    meta = {"tads_params": {"function": "di", "window": 5}}
    cooler.create_cooler(str(tmp / "x.cool"), bins, d["contacts"], metadata=meta)
    c = cooler.Cooler(str(tmp / "x.cool"))
    rb = c.bins()[:]
    m = dense(d["contacts"])
    out = {
        "coords": np.allclose(rb[["x", "y", "z"]].to_numpy(), xyz0),
        "bin_signals": np.allclose(rb["atac"], d["bin_sig"]),
        "contacts": np.allclose(c.matrix(balance=False)[:], np.triu(m) + np.triu(m, 1).T),
        "intervals": rb["tad"].tolist() == [0, 0, 1, 1, 1, -1, -1, -1],
        "provenance": c.info["metadata"]["tads_params"]["window"] == 5 and "generated-by" in c.info,
    }
    # .scool: per-cell maps under named cell groups
    cooler.create_scool(str(tmp / "x.scool"), d["bins"], {f"c{i}": d["contacts"] for i in range(N_CELL)})
    cells = cooler.fileops.list_scool_cells(str(tmp / "x.scool"))
    one = cooler.Cooler(f"{tmp / 'x.scool'}::{cells[1]}")
    out["partial"] = (c.matrix(balance=False).fetch("chr2").shape == (3, 3)
                      and one.matrix(balance=False).fetch("chr1").shape == (5, 5))
    # Data tables serialised to JSON text in the metadata attribute are recorded but NOT counted
    # (rule 3): a cell table with embeddings and 2e5 RNA spots.
    big = pd.DataFrame({"x": RNG.normal(size=200_000), "y": RNG.normal(size=200_000),
                        "z": RNG.normal(size=200_000)})
    for col, payload, what in (
            ("cells", {"cells": {"c0": {"cell_type": "a", "X_umap": d["emb"][0].tolist()}}},
             "a cell table with an embedding as JSON text in the metadata attribute"),
            ("points", {"rna_spots": big.to_dict("list")}, "2e5 RNA spots as JSON text in the metadata attribute")):
        try:
            cooler.create_cooler(str(tmp / f"{col}.cool"), d["bins"], d["contacts"], metadata=payload)
            back = cooler.Cooler(str(tmp / f"{col}.cool")).info["metadata"]
            ok = back == json.loads(json.dumps(payload))
            out[col] = {"ok": ok, "counted": False, "detail": what + " (stored; not counted, rule 3)"}
        except Exception as exc:
            out[col] = {"ok": False, "counted": False, "detail": f"{what}: {type(exc).__name__}: {exc}"}
    return out


# --------------------------------------------------------------------------- marks + evidence

AD_DOC = "https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.html"
SD_DOC = "https://spatialdata.scverse.org/en/stable/design_doc.html"
MU_DOC = "https://mudata.readthedocs.io/stable/io/mudata.html"
CO_DOC = "https://cooler.readthedocs.io/en/latest/schema.html"
FOF = "https://fish-omics-format.readthedocs.io/en/latest/"
CD_SPEC = "uchrom/core/spec.md"
FAVOURABLE = ("Rated in the most favourable orientation; one AnnData has a single obs axis, so spots, cells "
              "and loci cannot all be first-class in the same object (see the hierarchy column).")

MARKS = {
    "chromdata.zarr": {
        "coords": ("native", "coords (n_spots, 3) + layers; unit in uns", [CD_SPEC]),
        "hierarchy": ("native", "spots → traces → cells via trace_id / cell_id; traces and cells tables", [CD_SPEC]),
        "spot_signals": ("native", "spot_tracks, row-aligned with spots", [CD_SPEC]),
        "bin_signals": ("native", "bins (locus axis, bin_id) + bin_tracks / binm", [CD_SPEC]),
        "cells": ("native", "cells table + cellm (embeddings, UMAP)", [CD_SPEC]),
        "contacts": ("linked", "linked, not copied: uns['linked_scool' / 'linked_cool'] records path, bin size "
                               "and cell map; load_linked_scool / Dataset.contacts(group=) read them. Our own "
                               "call: the pixels stay in the external .scool / .cool by design.", [CD_SPEC]),
        "intervals": ("native", "intervals: typed IntervalTable (domain / pair / peak / segment)", [CD_SPEC]),
        "points": ("native", "points: non-genomic 3-D points in the coords frame", [CD_SPEC]),
        "provenance": ("native", "results: ResultsStore of ResultRecord(kind, params, function, version, inputs, "
                                 "created_utc)", [CD_SPEC]),
        "partial": ("native", "read(backed=True): get_cell / get_trace / get_chrom read only the needed row "
                              "ranges (index/ runs; Fig. 2d)", [CD_SPEC, "uchrom/core/backed.py"]),
    },
    "FOF-CT (4DN)": {
        "coords": ("native", "core table X, Y, Z (required)", [FOF + "core.html"]),
        "hierarchy": ("native", "Spot_ID → Trace_ID → Cell_ID in the core table; Trace Data and Cell Data "
                                "tables indexed by Trace_ID / Cell_ID", [FOF + "core.html", FOF + "trace.html",
                                                                         FOF + "cell.html"]),
        "spot_signals": ("native", "Spot Biological Data / Spot Quality tables indexed by Spot_ID; optional core "
                                   "columns (##columns, #^ descriptions)", [FOF + "bio.html", FOF + "core.html"]),
        "bin_signals": ("convention", "no table indexed by genomic locus; a per-locus value can only be repeated "
                                      "on every spot as an optional column", [FOF + "format_overview.html"]),
        "cells": ("native", "Cell Data table indexed by Cell_ID (cell properties, cell type); an embedding only "
                            "as optional columns (given the better mark)", [FOF + "cell.html"]),
        "contacts": ("none", "no contact-matrix table in the 12 FOF-CT tables", [FOF + "format_overview.html"]),
        "intervals": ("convention", "no interval table; domain labels only as an optional per-spot column (loops, "
                                    "i.e. pairs, not representable); given the better mark",
                      [FOF + "format_overview.html"]),
        "points": ("native", "RNA Spot Data table (RNA_Spot_ID, X, Y, Z, Gene_ID, RNA_name, link ids)",
                   [FOF + "rna.html"]),
        "provenance": ("convention", "header Software_* fields describe the tools that produced a table; no "
                                     "place for analysis results beyond optional columns",
                       [FOF + "format_overview.html"]),
        "partial": ("convention", "plain CSV, no index: a cell or chromosome is read by scanning the file "
                                  "(e.g. pandas chunksize); given the better mark", [FOF + "format_overview.html"]),
    },
    "AnnData": {
        "coords": ("convention", "obsm['spatial'] (n_obs, 3), a community convention; no trace / unit structure",
                   [AD_DOC]),
        "hierarchy": ("convention", "one obs axis: cell_id / trace_id only as obs columns; spots and cells cannot "
                                    "both be observations", [AD_DOC]),
        "spot_signals": ("native", "spots as obs: X / layers / obs columns", [AD_DOC]),
        "bin_signals": ("native", "loci as var (cells × loci, as for scATAC peaks): var table. " + FAVOURABLE,
                        [AD_DOC]),
        "cells": ("native", "cells as obs: obs + obsm (X_umap, X_pca). " + FAVOURABLE, [AD_DOC]),
        "contacts": ("convention", "no contact-map type: one dense or sparse locus × locus matrix can be put in varp "
                                  "(loci as var), without pixel/balancing schema, resolutions or per-cell maps. "
                               + FAVOURABLE, [AD_DOC]),
        "intervals": ("convention", "a DataFrame in uns", [AD_DOC]),
        "points": ("convention", "a DataFrame in uns (or a second AnnData)", [AD_DOC]),
        "provenance": ("convention", "free-form dicts in uns (scanpy writes uns['<tool>']['params'])", [AD_DOC]),
        "partial": ("native", "anndata.experimental.read_lazy (0.12; experimental) selects rows before loading; "
                              "no per-cell index, the selection scans obs. Given the better mark.",
                    ["https://anndata.readthedocs.io/en/stable/generated/anndata.experimental.read_lazy.html"]),
    },
    "SpatialData": {
        "coords": ("native", "points element with x, y, z and coordinate-system transformations", [SD_DOC]),
        "hierarchy": ("convention", "cell_id / trace_id as columns of the points; a table annotates one element "
                                    "level (region + instance_key), no nested cell › trace › spot", [SD_DOC]),
        "spot_signals": ("native", "extra columns of the points element, or a table annotating the points",
                         [SD_DOC]),
        "bin_signals": ("native", "no genomic locus axis among the spatial elements, but a table is an AnnData: "
                                  "loci as var of a table that annotates no element, as for AnnData (given the "
                                  "better mark)", [SD_DOC]),
        "cells": ("native", "shapes (or labels) for cells + a table annotating them, obsm embeddings", [SD_DOC]),
        "contacts": ("convention", "no contact-map element: a table is an AnnData, so one locus × locus matrix in varp, "
                                  "as for AnnData", [SD_DOC]),
        "intervals": ("convention", "a table with interval rows annotating no element", [SD_DOC]),
        "points": ("native", "a second points element (feature_key = gene)", [SD_DOC]),
        "provenance": ("convention", "SpatialData.attrs / table uns (free-form)", [SD_DOC]),
        "partial": ("native", "points are lazy dask DataFrames: filter on cell_id, then compute (streams every "
                              "partition, no index; Fig. 2d). Spatial bounding-box queries are native. "
                              "Given the better mark.", [SD_DOC]),
    },
    "MuData": {
        "coords": ("convention", "obsm['spatial'] of a spots modality", [MU_DOC]),
        "hierarchy": ("convention", "spots and cells as separate modalities; the link is an obs column, "
                                    "no parent / child relation", [MU_DOC]),
        "spot_signals": ("native", "a spots modality: X / obs", [MU_DOC]),
        "bin_signals": ("native", "var of a cells × loci modality", [MU_DOC]),
        "cells": ("native", "global obs / obsm or a cells modality", [MU_DOC]),
        "contacts": ("convention", "no contact-map type: varp of a cells × loci modality (one matrix, as for AnnData)",
                     [MU_DOC]),
        "intervals": ("convention", "a DataFrame in uns", [MU_DOC]),
        "points": ("convention", "an RNA-spot modality with obsm['spatial']", [MU_DOC]),
        "provenance": ("convention", "free-form uns", [MU_DOC]),
        "partial": ("native", "read_h5mu(backed=True): X of each modality stays on disk and is sliced by row "
                              "(obs / obsm are loaded). Given the better mark.", [MU_DOC]),
    },
    "cooler (.cool / .scool)": {
        "coords": ("convention", "extra bin columns x, y, z: one structure per file, no spots or traces",
                   [CO_DOC]),
        "hierarchy": ("none", ".scool has cells, but no traces or spots", [CO_DOC]),
        "spot_signals": ("none", "no spot level", [CO_DOC]),
        "bin_signals": ("native", "bins table with extra columns (e.g. weight, signals)", [CO_DOC]),
        "cells": ("none", ".scool names its cells (one map per cell) but has no cell attribute table or "
                          "embeddings; JSON text in the metadata attribute works (test) but is not counted",
                  [CO_DOC]),
        "contacts": ("native", "pixels (bulk .cool; per cell .scool; multi-resolution .mcool)", [CO_DOC]),
        "intervals": ("convention", "domain membership as a per-bin label column of the bins table; loops "
                                    "(pairs) have no place", [CO_DOC]),
        "points": ("none", "no place for non-genomic points; JSON text in the metadata attribute works for 2e5 "
                           "spots (test) but is not counted", [CO_DOC]),
        "provenance": ("convention", "generated-by / creation-date attributes + free-form JSON metadata",
                       [CO_DOC]),
        "partial": ("native", "indexed fetch by genomic region; one cell of a .scool", [CO_DOC]),
    },
}

TESTS = {"chromdata.zarr": t_chromdata, "AnnData": t_anndata, "SpatialData": t_spatialdata,
         "MuData": t_mudata, "cooler (.cool / .scool)": t_cooler}
LIB = {"chromdata.zarr": "uchrom", "AnnData": "anndata", "SpatialData": "spatialdata", "MuData": "mudata",
       "cooler (.cool / .scool)": "cooler"}


def main() -> None:
    import importlib

    versions = {}
    for mod in ("uchrom", "anndata", "spatialdata", "mudata", "cooler", "zarr", "h5py"):
        try:
            versions[mod] = importlib.import_module(mod).__version__
        except Exception:  # pragma: no cover
            versions[mod] = None
    versions["FOF-CT"] = "v1.0 (specification pages checked 2026-09-26)"
    cells, failures = {}, []
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
                    test = {c: {"ok": False, "detail": res["detail"]} for c, _ in COLS}
            cells[row] = {}
            for col, _ in COLS:
                mark, note, urls = MARKS[row][col]
                entry = {"value": mark, "note": note, "evidence": urls,
                         "version": versions["FOF-CT"] if row.startswith("FOF") else versions[LIB[row]]}
                t = test.get(col)
                if t is not None:
                    t = t if isinstance(t, dict) else {"ok": bool(t)}
                    entry["test"] = {"script": "benchmarks/fig2/b_capabilities.py", **t}
                    # a stored-and-read-back element cannot be "none"; a native / convention mark needs a pass
                    if t.get("counted", True) and (mark == "none") == t["ok"]:
                        failures.append((row, col, mark, t))
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
        "rules": ["if in doubt the other tool gets the better mark (noted)",
                  "AnnData elements rated in their most favourable orientation",
                  "a data table serialised to JSON text in a descriptive metadata attribute does not count "
                  "(recorded with counted: false); provenance-like metadata there does"],
        "rows": ROWS, "cols": [c for c, _ in COLS], "col_labels": dict(COLS),
        "cells": cells, "versions": versions, "mismatches": [list(map(str, f)) for f in failures],
    }
    print(C.write_json("b_capabilities", payload))
    print(write_table(payload))


SYMBOL = {"native": "● native", "linked": "◎ linked (external file, queried through the index)",
          "convention": "○ by convention", "none": "– not supported"}


def write_table(payload) -> Path:
    """Supplementary Table S1 (``paper/fig2/tableS_capabilities.md``) from the JSON."""
    rows, cols, lab = payload["rows"], payload["cols"], payload["col_labels"]
    v = payload["versions"]
    out = [
        "# Supplementary Table S1 — What each format can represent (evidence for Fig. 2b)",
        "",
        "Generated by `benchmarks/fig2/b_capabilities.py` from `paper/fig2/results/b_capabilities.json`; "
        "do not edit by hand.",
        "",
        "**Marks.** ● *native*: first-class, with its own structure. ◎ *linked*: kept in an external community-standard "
        "file (not copied) and queried through the shared index. ○ *by convention*: stored and read back "
        "through the library's public API, but only in a general-purpose slot (`uns`, `obsm`, extra columns, "
        "attributes), so the structure is lost or ad hoc. – *not supported*: no place for it in the format or "
        "its API.",
        "",
        "**Rules (fair and conservative toward the other tools).** (1) If in doubt, the other tool gets the "
        "better mark, and the note says so. (2) AnnData has a single observation axis: each element is rated "
        "in its most favourable orientation (spots, cells or loci as `obs` / `var`), although these "
        "orientations exclude each other in one object; the hierarchy column is where that shows. (3) A data "
        "table serialised to JSON text inside a descriptive metadata attribute (cooler's `metadata`) does not "
        "count; such tests are still run and reported as *not counted*. Provenance-like metadata there does "
        "count.",
        "",
        "**Tests.** ✓ = a tiny test in `benchmarks/fig2/b_capabilities.py` stored the element with that "
        "library's own API, wrote it to disk, read it back and compared the values; FOF-CT is a CSV "
        "specification, not a library, so its row rests on the specification pages alone.",
        "",
        "**Versions checked.** " + "; ".join(f"{k} {val}" for k, val in v.items() if val) + ".",
        "",
        "| Container | " + " | ".join(lab[c] for c in cols) + " |",
        "|---|" + "---|" * len(cols),
    ]
    short = {"native": "●", "linked": "◎", "convention": "○", "none": "–"}
    for r in rows:
        out.append(f"| {r} | " + " | ".join(short[payload["cells"][r][c]["value"]] for c in cols) + " |")
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
                ts = "✓" if t["ok"] else "✗ " + t.get("detail", "")
            links = ", ".join(f"[{u.rsplit('/', 1)[-1] or u}]({u})" if u.startswith("http") else f"`{u}`"
                              for u in e["evidence"])
            note = e["note"].replace("|", "\\|")
            out.append(f"| {lab[c]} | {SYMBOL[e['value']]} | {note} ({links}) | {ts} |")
        out.append("")
    path = C.ROOT / "paper" / "fig2" / "tableS_capabilities.md"
    path.write_text("\n".join(out))
    return path


if __name__ == "__main__":
    main()
