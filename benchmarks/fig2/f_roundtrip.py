"""Figure 2f — round trips: which fields survive, checked value by value.

Rows (each through the uchrom API that exists today on main):

* **h5cd 1.x** — ``cd.write`` → ``ChromData.read`` (baseline).
* **FOF-CT** — ``_common.write_fofct`` (+ a FOF-CT *cell* table) →
  ``ChromData.from_fofct(core, cell_table=…)``.  uchrom has no FOF-CT writer,
  so the benchmark ships a minimal one.
* **AnnData** — ``cd.to_anndata()`` → ``.h5ad`` → recorded in
  ``uns['linked_anndata']`` → h5cd → ``ChromData.read`` →
  ``load_linked_anndata()`` / ``link_anndata()`` into a fresh ChromData.
* **.cool / .scool** — contacts are *linked*: ``link_cool`` (sim_cell1 .mcool)
  and ``link_scool`` (scHiCAR 1 Mb .scool) → h5cd → read → the linked map's
  pixels are compared with the source file's.
* **PDB** — ``uchrom.io.export_pdb_coords`` of a genome structure (sim_cell1,
  NucDynamics) → parsed back (fixed PDB columns; no uchrom PDB reader).
* **.3dg** — uchrom reads ``.3dg`` (``uchrom.io.read_3dg``) but has no writer:
  only the import direction is tested (a .3dg written by this script →
  ``read_3dg`` → ``ChromData.from_dataframe``).

Columns: coords, cell › trace hierarchy, tracks, cell table, contacts.
Status per cell: ``preserved`` (tested, exact or within the stated tolerance),
``partial`` (tested; some of the field survives — see the note), ``lost``
(representable but dropped), ``na`` (the format has no place for the field, or
the API does not export it by design), ``untested``.

Data: Takei 2025 FOV0 (``takei2025_fov0/takei2025_fov0.h5cd``: 383,674 spots,
1,500 traces, 47 cells, 62 tracks, cell table + cellm) for the h5cd, FOF-CT
and AnnData rows; ``sim_cell1`` (in repo) for PDB / .3dg / .cool;
``schicar_mop`` for .scool.

    python benchmarks/fig2/f_roundtrip.py

Writes ``paper/fig2/results/f_roundtrip.json``.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

TAKEI_FOV0 = C.DATA / "takei2025_fov0" / "takei2025_fov0.h5cd"
SIM = C.ROOT / "example-data" / "sim_cell1" / "sim_cell1.h5cd"
SCHICAR = C.DATA / "schicar_mop" / "schicar_mop.h5cd"
COLS = ["coords", "cell › trace", "tracks", "cell table", "contacts"]


def cell(status, note, **ev):
    return {"status": status, "note": note, **ev}


# ----------------------------------------------------------------------------- comparisons

def same_coords(a, b, tol=0.0):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape:
        return False, f"shape {a.shape} vs {b.shape}"
    nan_ok = np.array_equal(np.isnan(a), np.isnan(b))
    err = float(np.nanmax(np.abs(a - b))) if a.size else 0.0
    return nan_ok and err <= tol, f"max |Δ| = {err:.3g}" + ("" if nan_ok else "; NaN pattern differs")


def same_hierarchy(sa, sb):
    """Row-wise equality of trace_id and cell_id (as strings) + identical trace→cell map."""
    t = np.array_equal(sa["trace_id"].astype(str).to_numpy(), sb["trace_id"].astype(str).to_numpy())
    c = ("cell_id" in sa and "cell_id" in sb
         and np.array_equal(sa["cell_id"].astype(str).to_numpy(), sb["cell_id"].astype(str).to_numpy()))
    return t and c, f"trace_id equal: {t}; cell_id equal: {c}"


def same_frame(a: pd.DataFrame, b: pd.DataFrame, rtol=0.0):
    """Column-by-column (NaN-aware) equality; strings compared as str; index as str.
    Numeric columns pass if |a-b| <= rtol*|a|; the note reports the worst relative error."""
    if list(map(str, a.index)) != list(map(str, b.index)):
        return False, "index differs"
    bad, worst = [], 0.0
    for c in a.columns:
        if c not in b.columns:
            bad.append(f"{c}: missing")
            continue
        x, y = a[c], b[c]
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            xa, ya = x.to_numpy(float), y.to_numpy(float)
            fin = np.isfinite(xa) & np.isfinite(ya)
            rel = np.abs(xa - ya)[fin] / np.maximum(np.abs(xa[fin]), np.finfo(float).tiny)
            worst = max(worst, float(rel.max()) if rel.size else 0.0)
            ok = np.array_equal(np.isnan(xa), np.isnan(ya)) and (not rel.size or rel.max() <= rtol)
        else:
            ok = np.array_equal(x.astype(str).to_numpy(), y.astype(str).to_numpy())
        if not ok:
            bad.append(c)
    extra = [c for c in b.columns if c not in a.columns]
    exact = "exact" if worst == 0 else f"max rel. error {worst:.2g}"
    return not bad, (f"{len(a.columns) - len(bad)}/{len(a.columns)} columns equal ({exact})"
                     + (f"; differ: {bad[:5]}" if bad else "") + (f"; extra: {extra[:5]}" if extra else ""))


TEXT_RTOL = 1e-12  # pandas' default (fast, not correctly rounded) float parser: a few ulp off the written repr


def pixels_digest(clr) -> str:
    px = clr.pixels()[:]
    h = hashlib.sha256()
    for c in ("bin1_id", "bin2_id", "count"):
        h.update(np.ascontiguousarray(px[c].to_numpy()).tobytes())
    return h.hexdigest()[:16]


# ----------------------------------------------------------------------------- rows

def row_h5cd(cd, tmp):
    from uchrom import ChromData
    p = tmp / "rt.h5cd"
    cd.write(p)
    back = ChromData.read(p)
    out = {}
    ok, n = same_coords(cd.coords, back.coords)
    out["coords"] = cell("preserved" if ok else "lost", n)
    ok, n = same_hierarchy(cd.spots, back.spots)
    out["cell › trace"] = cell("preserved" if ok else "lost", n)
    ok, n = same_frame(cd.tracks, back.tracks)
    out["tracks"] = cell("preserved" if ok else "partial", n)
    ok, n = same_frame(cd.cells, back.cells)
    cm = all(np.array_equal(cd.cellm[k], back.cellm[k]) for k in cd.cellm)
    out["cell table"] = cell("preserved" if ok and cm else "partial", f"{n}; cellm equal: {cm}")
    out["contacts"] = _linked_contacts_note()
    return out


def write_fofct_cells(cells: pd.DataFrame, path: Path):
    df = cells.copy()
    df.insert(0, "Cell_ID", [str(i) for i in df.index])
    with open(path, "w") as fh:
        fh.write("##FOF-CT_version=v0.1\n##Table_namespace=4dn_FOF-CT_cell\n")
        fh.write("##columns=(" + ",".join(df.columns) + ")\n")
        df.to_csv(fh, header=False, index=False)


def row_fofct(cd, tmp):
    from uchrom import ChromData
    core, cells = tmp / "core.csv", tmp / "cells.csv"
    C.write_fofct(cd, core)
    write_fofct_cells(cd.cells, cells)
    back = ChromData.from_fofct(core, cell_table=cells, cell_value_prefix=None)
    out = {}
    ok, n = same_coords(cd.coords, back.coords)
    out["coords"] = cell("preserved" if ok else "partial", n + " (floats written with full repr)")
    ok, n = same_hierarchy(cd.spots, back.spots)
    tr_lost = len(back.traces) == 0 and len(cd.traces) > 0
    out["cell › trace"] = cell("preserved" if ok else "lost",
                               n + ("; trace-level table (traces) not carried: FOF-CT core has no trace table"
                                    if tr_lost else ""), traces_table_lost=tr_lost)
    tcols = list(cd.tracks.columns)
    in_spots = [c for c in tcols if c in back.spots.columns]
    missing = [c for c in tcols if c not in back.spots.columns]
    renamed = [c for c in back.spots.columns if c not in cd.spots.columns and c not in tcols]
    vals_ok, n = same_frame(cd.tracks[in_spots], back.spots[in_spots].set_axis(cd.tracks.index), rtol=TEXT_RTOL)
    out["tracks"] = cell("partial" if vals_ok else "lost",
                         f"{len(in_spots)}/{len(tcols)} track columns back, values: {n}; read back as extra *spot* "
                         f"columns (FOF-CT has no spot-vs-track distinction; back.tracks is "
                         f"{'None' if back.tracks is None else 'set'})"
                         + (f"; missing {missing} — reader bug: from_fofct strips '()' from the whole "
                            f"##columns list, so a last name ending in ')' comes back as {renamed}"
                            if missing else ""), missing_columns=missing)
    ok, n = same_frame(cd.cells, back.cells.loc[[str(i) for i in cd.cells.index]], rtol=TEXT_RTOL)
    out["cell table"] = cell("partial" if ok else "lost",
                             f"cells: {n}; cellm ({', '.join(cd.cellm)}) has no FOF-CT table → dropped")
    out["contacts"] = cell("na", "FOF-CT core/cell tables carry no contact maps")
    return out


def row_anndata(cd, tmp):
    import anndata as ad

    from uchrom import ChromData
    h5ad = tmp / "cells.h5ad"
    cd.to_anndata().write_h5ad(h5ad)
    host = ChromData(cd.coords, cd.spots.copy(), tracks=cd.tracks, uns={"linked_anndata": {"path": str(h5ad)}})
    host.write(tmp / "host.h5cd")
    back = ChromData.read(tmp / "host.h5cd")
    adata = back.load_linked_anndata()
    fresh = ChromData(cd.coords, cd.spots.copy())
    n_matched = fresh.link_anndata(ad.read_h5ad(h5ad))
    out = {"coords": cell("na", "to_anndata exports the cell axis (obs = cells, obsm = cellm); "
                                "spot coordinates stay in the h5cd by design")}
    ids_ok = list(adata.obs_names) == [str(i) for i in cd.cells.index]
    out["cell › trace"] = cell("partial", f"cell ids preserved: {ids_ok}; the trace level has no place in a "
                                          f"cells-as-obs AnnData", cell_ids_equal=ids_ok)
    out["tracks"] = cell("na", "spot-level tracks are not flattened into AnnData by design (to_anndata docstring)")
    ok1, n1 = same_frame(cd.cells, adata.obs)
    cm1 = all(np.array_equal(cd.cellm[k], adata.obsm[k]) for k in cd.cellm)
    pos = {str(c): i for i, c in enumerate(fresh.cells.index)}
    order = [pos[str(i)] for i in cd.cells.index]
    ok2, n2 = same_frame(cd.cells, fresh.cells.iloc[order])
    cm2 = all(np.array_equal(cd.cellm[k], np.asarray(fresh.cellm[k])[order]) for k in cd.cellm)
    good = ok1 and cm1 and ok2 and cm2
    out["cell table"] = cell("preserved" if good else "partial",
                             f"load_linked_anndata obs: {n1}, obsm equal: {cm1}; link_anndata ({n_matched} "
                             f"cells matched) cells: {n2}, cellm equal: {cm2}")
    out["contacts"] = cell("na", "AnnData carries no contact maps (link them as .cool/.scool)")
    return out


def row_cool(tmp):
    import cooler

    from uchrom import ChromData
    out = {"coords": cell("na", ".cool/.scool hold contacts, not coordinates"),
           "tracks": cell("na", "no spot tracks in a contact map"),
           "cell table": cell("na", "an .scool stores per-cell maps, not a cell table")}
    notes, ok_all = [], True
    # .mcool linked to a single-cell structure (sim_cell1, in repo)
    sim = ChromData.read(SIM)
    key, rec = next(iter(sim.uns["linked_cool"].items()))
    src = sim.resolve_link_path(rec["path"])
    p = tmp / "sim.h5cd"
    sim.uns["linked_cool"][key]["path"] = str(src)
    sim.write(p)
    back = ChromData.read(p)
    res = cooler.fileops.list_coolers(str(src))
    same = all(pixels_digest(cooler.Cooler(f"{back.resolve_link_path(back.uns['linked_cool'][key]['path'])}::{u}"))
               == pixels_digest(cooler.Cooler(f"{src}::{u}")) for u in res)
    ok_all &= same
    notes.append(f"sim_cell1 .mcool ({len(res)} resolutions) pixels identical after h5cd round trip: {same}")
    # .scool linked to scHiCAR cells
    hier = None
    if SCHICAR.exists():
        sc = ChromData.read(SCHICAR)
        k2, rec2 = next(iter(sc.uns["linked_scool"].items()))
        src2 = sc.resolve_link_path(rec2["path"])
        sc.uns["linked_scool"][k2]["path"] = str(src2)
        p2 = tmp / "schicar.h5cd"
        sc.write(p2)
        back2 = ChromData.read(p2)
        listing = back2.load_linked_scool(key=k2)
        names = {c.rsplit("/", 1)[-1] for c in listing["cells"]}
        cells = [str(c) for c in back2.cells.index]
        pick = [cells[i] for i in np.random.default_rng(0).choice(len(cells), 25, replace=False)]
        same2 = all(pixels_digest(back2.load_linked_scool(key=k2, cell=c))
                    == pixels_digest(cooler.Cooler(f"{src2}::/cells/{c}")) for c in pick)
        covered = sum(c in names for c in cells)
        ok_all &= same2
        hier = (covered, len(cells))
        notes.append(f"scHiCAR .scool: {covered}/{len(cells)} h5cd cells have a map; pixels of 25 random cells "
                     f"identical via load_linked_scool: {same2}")
    out["contacts"] = cell("preserved" if ok_all else "lost", "linked, not copied — " + "; ".join(notes))
    out["cell › trace"] = cell("partial", (f"cell ↔ per-cell map: {hier[0]}/{hier[1]} cells matched by id; " if hier else "")
                                          + "no trace level in a contact map")
    return out


def _parse_pdb(path):
    rows = []
    for line in open(path):
        if line.startswith(("ATOM", "HETATM")):
            rows.append((line[21], float(line[30:38]), float(line[38:46]), float(line[46:54]),
                         int(line[80:].strip() or -1)))
    return pd.DataFrame(rows, columns=["chain", "x", "y", "z", "pos"])


def row_pdb(tmp):
    from uchrom import ChromData
    from uchrom.io import export_pdb_coords
    sim = ChromData.read(SIM)
    df = sim.to_dataframe()
    df["chrom"] = df["chrom"].astype(str)
    p = tmp / "sim.pdb"
    export_pdb_coords(str(p), df)
    back = _parse_pdb(p)
    # the exporter writes chromosomes in natural order: align by (chrom order, start)
    order = sorted(df["chrom"].unique(), key=lambda c: (c[3:].zfill(3) if c[3:].isdigit() else c[3:]))
    ref = pd.concat([df[df["chrom"] == c] for c in order])
    ok, n = same_coords(ref[["x", "y", "z"]].to_numpy(), back[["x", "y", "z"]].to_numpy(), tol=5e-4)
    pos_ok = np.array_equal(ref["start"].to_numpy(), back["pos"].to_numpy())
    rng = float(np.abs(df[["x", "y", "z"]].to_numpy()).max())
    return {
        "coords": cell("partial" if ok else "lost",
                       f"{n} (PDB %8.3f: 3 decimals; values must stay within ±9999.999 — max |coord| here "
                       f"{rng:.1f})", tol=5e-4),
        "cell › trace": cell("partial", f"chromosome → chain; bin start in the extended column preserved: {pos_ok}; "
                                        f"one MODEL, so trace / cell ids are lost"),
        "tracks": cell("na", "exporter writes occupancy/B-factor as 0.0; no per-bin values"),
        "cell table": cell("na", "PDB has no cell table"),
        "contacts": cell("na", "PDB has no contacts"),
    }


def row_3dg(tmp):
    from uchrom import ChromData
    from uchrom.io import read_3dg
    sim = ChromData.read(SIM)
    df = sim.to_dataframe()
    p = tmp / "sim.3dg"
    pd.DataFrame({"chrom": df["chrom"].astype(str), "start": df["start"], "x": df["x"], "y": df["y"],
                  "z": df["z"]}).to_csv(p, sep="\t", header=False, index=False)
    raw = read_3dg(str(p))
    raw["end"] = raw["start"] + int((df["end"] - df["start"]).iloc[0])
    back = ChromData.from_dataframe(raw)
    ok, n = same_coords(df[["x", "y", "z"]].to_numpy(), back.coords, tol=1e-12)
    return {
        "coords": cell("partial" if ok else "lost",
                       f"import only: .3dg → read_3dg → from_dataframe {n}; uchrom has no .3dg writer, "
                       f"so h5cd → .3dg is not possible"),
        "cell › trace": cell("partial", "import only: one trace per chromosome; haplotype / cell ids absent in .3dg"),
        "tracks": cell("na", ".3dg has no per-bin values"),
        "cell table": cell("na", ".3dg has no cell table"),
        "contacts": cell("na", ".3dg has no contacts"),
    }


def _linked_contacts_note():
    return cell("preserved", "link records (uns['linked_cool'/'linked_scool']) round-trip; see the .cool/.scool row")


def main():
    from uchrom import ChromData

    rows = {}
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cd = ChromData.read(TAKEI_FOV0)
        for name, fn in (("h5cd 1.x", lambda: row_h5cd(cd, tmp)), ("FOF-CT", lambda: row_fofct(cd, tmp)),
                         ("AnnData", lambda: row_anndata(cd, tmp)), (".cool / .scool", lambda: row_cool(tmp)),
                         ("PDB", lambda: row_pdb(tmp)), (".3dg", lambda: row_3dg(tmp))):
            rows[name] = fn()
            print(f"{name:14s} " + "  ".join(f"{c}={rows[name][c]['status']}" for c in COLS), flush=True)
    C.write_json("f_roundtrip", {
        "panel": "f", "machine": C.machine_info(), "cols": COLS, "rows": list(rows), "cells": rows,
        "status_values": {"preserved": 1.0, "partial": 0.5, "lost": 0.0, "na": 0.0, "untested": None},
        "datasets": {"h5cd / FOF-CT / AnnData": "Takei 2025 FOV0 (takei2025_fov0.h5cd)",
                     "PDB / .3dg / .cool": "sim_cell1 (NucDynamics on Stevens 2017 cell 1, in repo)",
                     ".scool": "scHiCAR MOp (schicar_mop.h5cd + contacts_cells_1Mb.scool)"},
    })
    print(C.RESULTS / "f_roundtrip.json")


if __name__ == "__main__":
    main()
