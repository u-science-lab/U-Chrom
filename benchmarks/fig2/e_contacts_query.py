"""Figure 2e — linked contacts, queried through the shared index (scHiCAR MOp).

**Correctness.**  ``schicar_mop.chromdata.zarr`` links the per-cell 1 Mb map
``contacts_cells_1Mb.scool`` (5,313 cells) and holds the cell table with
``cell_type`` (22 types).  For every cell type the group pseudo-bulk is
computed through the library path the web browser uses —
``uchrom_browser.data.Dataset.register_group`` (the cells of the type)
then ``Dataset.contacts(key, chrom, group=...)`` → ``Dataset._pseudobulk``
(per-cell pixels summed straight from the ``.scool``) — for the cis map of
every chromosome, and compared with the published per-type map
``contacts_<type>.cool`` (500 kb) coarsened to the same 1 Mb bins (the
stored upper-triangle pixels summed): max |Δ| and the number of pixels
compared.

**Thumbnail.**  The Oligodendrocyte pseudo-bulk of one chromosome window
(``--window chr2:40-90Mb``) at 1 Mb, stored in the JSON for the figure.

**Speed.**  Per type, the time of the first query and of the same query
again (LRU cache), in the same process.  (The scaling curve, time vs cells
aggregated, is ``e_contacts.py`` → ``e_contacts.json``.)

**Import (supplementary figure).**  Linking vs copying on the
``.chromdata.zarr`` container, measured in fresh processes (3 repeats):

* *link*: ``cd.link_scool(path, ...)`` + ``cd.write(store)`` — records the
  path, bin size and cell naming; the ``.scool`` stays where it is;
* *copy*: read every cell's pixels from the ``.scool`` (h5py, as
  ``_pseudobulk`` does) and write them into the store as one Parquet table
  ``tables/contacts/pixels.parquet`` (``cell`` int16 code, ``bin1_id`` /
  ``bin2_id`` int32, ``count`` int32; zstd-3, the store's own table
  compression), plus the store itself;

with the resulting sizes: the store alone, and the user's total footprint
where the ``.scool`` is always kept (linked = ``.scool`` + store, copied =
``.scool`` + store with the copy).

    python benchmarks/fig2/e_contacts_query.py [--repeats 3]

Writes ``u-chrom-paper/manuscripts/full/figures/fig2/results/e_query.json``.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

SCRIPT = Path(__file__).resolve()
SCHICAR = C.DATA / "schicar_mop" / "schicar_mop.chromdata.zarr"
FUNCTION = "uchrom_browser.data.Dataset.contacts(key, chrom, group=...) -> Dataset._pseudobulk"


def _coarsen(mat: np.ndarray, starts: np.ndarray, target_starts: np.ndarray) -> np.ndarray:
    """Sum an upper-triangular (n, n) map at a finer resolution onto the
    target bins (by bin start); the result's upper triangle is the coarse map."""
    idx = np.searchsorted(target_starts, starts, side="right") - 1
    n = len(target_starts)
    out = np.zeros((n, n))
    np.add.at(out, (idx[:, None], idx[None, :]), mat)
    return out


def child_identity(window):
    import cooler

    from uchrom import ChromData
    from uchrom_browser.data import Dataset, decode_matrix

    cd = ChromData.read(SCHICAR)
    ds = Dataset(id="schicar", name="schicar", path=str(SCHICAR), cd=cd)
    maps = ds.contact_maps()
    key = next(m["key"] for m in maps if m["kind"] == "scool")
    base = SCHICAR.parent
    cells = cd.cells
    types = sorted(cells["cell_type"].astype(str).unique())
    scool = cd.resolve_link_path(cd.uns["linked_scool"]["per_cell"]["path"])
    first = cooler.Cooler(f"{scool}::{cooler.fileops.list_scool_cells(str(scool))[0]}")
    chroms = list(first.chromnames)
    wchrom, wrange = window.split(":")
    w0, w1 = (int(float(x.rstrip("Mb")) * 1e6) for x in wrange.split("-"))
    per_type = []
    thumb = None
    for t in types:
        gid = ds.register_group([str(c) for c in cells.index[cells["cell_type"].astype(str) == t]])["id"]
        clr = cooler.Cooler(str(base / f"contacts_{t.replace('.', '_')}.cool"))
        max_abs, n_pix, n_nonzero, total, first_s, cached_s = 0.0, 0, 0, 0.0, [], []
        for ch in chroms:
            t0 = time.perf_counter()
            buf = ds.contacts(key, ch, group=gid)
            first_s.append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            ds.contacts(key, ch, group=gid)
            cached_s.append(time.perf_counter() - t0)
            got = decode_matrix(buf)
            mat = np.asarray(got["matrix"], dtype=np.float64)
            tstarts = np.asarray(got["header"]["bin_starts"], dtype=np.int64)
            if got["header"].get("note"):
                raise RuntimeError(f"{t} {ch}: pooled map ({got['header']['note']})")
            ref_fine = clr.matrix(balance=False).fetch(ch).astype(np.float64)
            fstarts = clr.bins().fetch(ch)["start"].to_numpy(np.int64)
            # cool stores the upper triangle: coarsen that (a symmetric fine map
            # would count a contact inside a coarse diagonal block twice)
            ref = _coarsen(np.triu(ref_fine), fstarts, tstarts)
            if ref.shape != mat.shape:
                raise RuntimeError(f"{t} {ch}: shapes {mat.shape} vs {ref.shape}")
            iu = np.triu_indices(len(mat))
            d = np.abs(mat[iu] - ref[iu])
            max_abs = max(max_abs, float(d.max()) if len(d) else 0.0)
            n_pix += len(d)
            n_nonzero += int((ref[iu] > 0).sum())
            total += float(ref[iu].sum())
            if t == "Oligo" and ch == wchrom:
                sel = (tstarts >= w0) & (tstarts < w1)
                thumb = {"cell_type": t, "chrom": ch, "start": int(tstarts[sel][0]),
                         "end": int(tstarts[sel][-1] + 1_000_000), "resolution": 1_000_000,
                         "n_cells": int(got["header"]["n_cells"]),
                         "matrix": mat[np.ix_(sel, sel)].astype(int).tolist()}
        per_type.append({"cell_type": t, "n_cells": int((cells["cell_type"].astype(str) == t).sum()),
                         "published": f"contacts_{t.replace('.', '_')}.cool (500 kb, coarsened to 1 Mb)",
                         "max_abs_diff": max_abs, "n_pixels": n_pix, "n_nonzero_pixels": n_nonzero,
                         "n_contacts": total, "identical": bool(max_abs == 0.0),
                         "first_query_s_median": statistics.median(first_s),
                         "first_query_s_total": float(sum(first_s)),
                         "cached_query_s_median": statistics.median(cached_s)})
        print(f"{t:8s} {per_type[-1]['n_cells']:5d} cells  max|Δ| {max_abs:g} over {n_pix:,} pixels  "
              f"first {per_type[-1]['first_query_s_total']:.2f} s", flush=True)
    C.emit({"per_type": per_type, "chroms": chroms, "thumbnail": thumb, "key": key})


def _pixels(scool: Path):
    import cooler
    import h5py

    names = [n.rsplit("/", 1)[-1] for n in cooler.fileops.list_scool_cells(str(scool))]
    cols = {"cell": [], "bin1_id": [], "bin2_id": [], "count": []}
    with h5py.File(scool, "r") as f:
        for k, name in enumerate(names):
            g = f["cells"][name]["pixels"]
            b1 = g["bin1_id"][:]
            cols["cell"].append(np.full(len(b1), k, dtype=np.int16))
            cols["bin1_id"].append(b1.astype(np.int32))
            cols["bin2_id"].append(g["bin2_id"][:].astype(np.int32))
            cols["count"].append(g["count"][:].astype(np.int32))
    return names, {k: np.concatenate(v) for k, v in cols.items()}


def child_import(mode, store):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from uchrom import ChromData

    cd = ChromData.read(SCHICAR)
    rec = cd.uns["linked_scool"]["per_cell"]
    scool = cd.resolve_link_path(rec["path"])
    cd.uns.pop("linked_scool")
    store = Path(store)
    C.remove(store)
    t0 = time.perf_counter()
    if mode == "link":
        cd.link_scool(scool, key="per_cell", cell_name=rec.get("cell_name"),
                      barcode_source=rec.get("barcode_source"), genome_assembly=rec.get("genome_assembly"),
                      bin_size=int(rec.get("bin_size")))
        cd.write(store)
        n_pixels = None
    else:
        names, px = _pixels(scool)
        cd.uns["copied_contacts"] = {"table": "tables/contacts/pixels.parquet", "cell_names": "cell index of "
                                     "the scool listing", "bin_size": int(rec.get("bin_size"))}
        cd.write(store)
        (store / "tables" / "contacts").mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table(px), store / "tables" / "contacts" / "pixels.parquet",
                       compression="zstd", compression_level=3, row_group_size=1 << 20)
        n_pixels = int(len(px["count"]))
    dt = time.perf_counter() - t0
    C.emit({"mode": mode, "seconds": dt, "store_bytes": C.size_bytes(store), "scool_bytes": scool.stat().st_size,
            "n_pixels": n_pixels, "peak_rss_mb": C.peak_rss_mb()})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--window", default="chr2:40-90Mb")
    ap.add_argument("--child", nargs="+", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        kind, *rest = args.child
        return {"identity": child_identity, "import": child_import}[kind](*rest)
    if not SCHICAR.exists():
        raise SystemExit(f"{SCHICAR} missing — run apps/atlas/recipes/build_schicar_mop.py")
    ident = C.run_child(SCRIPT, ["--child", "identity", args.window])
    work = C.WORK / "e_query"
    work.mkdir(parents=True, exist_ok=True)
    imports = {}
    for mode in ("link", "copy"):
        trials = [C.run_child(SCRIPT, ["--child", "import", mode, str(work / f"{mode}.chromdata.zarr")])
                  for _ in range(args.repeats)]
        imports[mode] = {"seconds": C.summarize([t["seconds"] for t in trials]),
                         "store_bytes": trials[0]["store_bytes"], "scool_bytes": trials[0]["scool_bytes"],
                         "user_total_bytes": trials[0]["store_bytes"] + trials[0]["scool_bytes"],
                         "n_pixels": trials[0]["n_pixels"], "trials": trials}
        print(mode, imports[mode]["seconds"], imports[mode]["store_bytes"] / 2**20, flush=True)
    n_ok = sum(p["identical"] for p in ident["per_type"])
    C.write_json("e_query", {
        "panel": "e", "machine": C.machine_info(),
        "dataset": {"name": "scHiCAR mouse brain (GSE305439)", "store": "schicar_mop/schicar_mop.chromdata.zarr",
                    "scool": "schicar_mop/contacts_cells_1Mb.scool (5,313 cells, 1 Mb)",
                    "published_per_type": "schicar_mop/contacts_<type>.cool (500 kb)"},
        "function": FUNCTION,
        "identity": {"n_types": len(ident["per_type"]), "n_identical": int(n_ok),
                     "n_pixels": int(sum(p["n_pixels"] for p in ident["per_type"])),
                     "max_abs_diff": float(max(p["max_abs_diff"] for p in ident["per_type"])),
                     "scope": "cis map of every chromosome (" + ", ".join(ident["chroms"]) + "), upper "
                              "triangle incl. diagonal, raw counts; published map coarsened 500 kb → 1 Mb by summing",
                     "per_type": ident["per_type"]},
        "thumbnail": ident["thumbnail"],
        "import": {"repeats": args.repeats, "protocol": "fresh process per trial; warm OS cache",
                   "link": imports["link"], "copy": imports["copy"],
                   "copy_method": "every cell's pixels read from the .scool with h5py and written into the store "
                                  "as tables/contacts/pixels.parquet (cell int16, bin1_id/bin2_id/count int32, "
                                  "zstd-3)"},
    })
    print(f"{n_ok}/{len(ident['per_type'])} cell types identical")
    print(C.RESULTS / "e_query.json")


if __name__ == "__main__":
    main()
