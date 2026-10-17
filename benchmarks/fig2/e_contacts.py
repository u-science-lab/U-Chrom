"""Figure 2e — contacts linked, not copied (scHiCAR MOp, 5,313 cells, 1 Mb ``.scool``).

**Size.**  The HDF5 ``.h5cd`` baseline of the scHiCAR store records the
per-cell map ``contacts_cells_1Mb.scool`` in ``uns['linked_scool']`` (a path +
metadata).  ``.h5cd`` is no longer a ChromData format: the file is written
once from ``schicar_mop.chromdata.zarr`` with the legacy writer
(``uchrom.io._h5cd_legacy.write_h5cd``, no compression, as 1.x wrote) into the
work directory.

* *linked* = the h5cd as built (the scool stays where it is; the link adds
  only a small uns record — its cost is measured by writing the same object
  without the link records);
* *copied* = the same h5cd plus every cell's pixels materialised inside it:
  one ``contacts/`` group with the pixels of all cells concatenated
  (``bin1_id``, ``bin2_id`` int64 and ``count`` int32, exactly cooler's
  dtypes) and a ``cell_offset`` (n_cells + 1) index, i.e. the most compact
  CSR-style copy.  Written twice: with h5cd 1.x's settings (no compression —
  1.x ``cd.write`` used none) and with cooler's own settings (gzip 6 + shuffle),
  so the comparison is not only about compression.

**Pseudo-bulk.**  The web browser's group pseudo-bulk
(``uchrom_browser.data.Dataset.contacts(key, chrom, group=…)`` →
``_pseudobulk``: per-cell bin1-offset slices read straight from the ``.scool``
(HDF5) and summed with ``np.bincount``, LRU-cached) on the ``.chromdata.zarr``
store with its maps linked only, opened backed as the browser opens it
(``_common.schicar_linked``).  Region: all of chr1.  For each group size
(random cells, seed 0) a fresh interpreter opens the dataset, lists the map
(``contact_maps()``, timed separately as setup), then times the first query
and the same query again (served from the LRU cache).  3 repeats → median,
min/max.  The OS page cache is warm (not flushed).

    python benchmarks/fig2/e_contacts.py [--cells 50,100,500,1000,all] [--repeats 3]

Writes ``u-chrom-paper/manuscripts/full/figures/fig2/results/e_contacts.json``.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

SCRIPT = Path(__file__).resolve()
STORE = C.DATA / "schicar_mop" / "schicar_mop.chromdata.zarr"
SCHICAR = C.WORK / "e_contacts" / "schicar_mop.h5cd"   # the HDF5 baseline, written from STORE


def ensure_h5cd() -> None:
    """Write the ``.h5cd`` baseline of ``STORE`` (legacy writer, uncompressed) once."""
    if SCHICAR.exists():
        return
    from uchrom import ChromData
    from uchrom.io._h5cd_legacy import write_h5cd

    cd = ChromData.read(STORE)
    for rec in (cd.uns.get("linked_scool") or {}).values():   # links relative to the data folder
        if isinstance(rec, dict) and "path" in rec:
            rec["path"] = str(cd.resolve_link_path(rec["path"]))
    SCHICAR.parent.mkdir(parents=True, exist_ok=True)
    write_h5cd(cd, SCHICAR, compression=None)
CHROM = "chr1"


def scool_key(cd):
    recs = cd.uns.get("linked_scool") or {}
    if "path" in recs:
        return "default", recs
    key = next(iter(recs))
    return key, recs[key]


def child_query(n_cells):
    from uchrom_browser.data import Dataset, load_chromdata

    store = C.schicar_linked()
    t0 = time.perf_counter()
    cd = load_chromdata(store)                     # backed, as the web browser opens it
    ds = Dataset(id="schicar", name="schicar", path=str(store), cd=cd)
    maps = ds.contact_maps()
    setup_s = time.perf_counter() - t0
    key = next(m["key"] for m in maps if m["kind"] == "scool")
    cells = sorted(str(c) for c in cd.cells.index)
    n = len(cells) if n_cells == "all" else int(n_cells)
    pick = sorted(np.random.default_rng(0).choice(len(cells), n, replace=False).tolist())
    gid = ds.register_group([cells[i] for i in pick])["id"]
    t0 = time.perf_counter()
    buf = ds.contacts(key, CHROM, group=gid)
    cold = time.perf_counter() - t0
    t0 = time.perf_counter()
    buf2 = ds.contacts(key, CHROM, group=gid)
    cached = time.perf_counter() - t0
    assert buf == buf2
    from uchrom_browser.data import decode_matrix
    hdr = decode_matrix(buf)
    hdr = hdr.get("header", hdr)
    C.emit({"n_cells": n, "setup_s": setup_s, "cold_s": cold, "cached_s": cached,
            "n_contacts": float(hdr.get("n_contacts", float("nan"))) if isinstance(hdr, dict) else None,
            "peak_rss_mb": C.peak_rss_mb()})


def copied_sizes(work: Path):
    import cooler
    import h5py

    from uchrom.io._h5cd_legacy import read_h5cd, write_h5cd

    cd = read_h5cd(SCHICAR)
    key, rec = scool_key(cd)
    scool = cd.resolve_link_path(rec["path"])
    out = {"h5cd_linked_bytes": SCHICAR.stat().st_size, "scool_bytes": scool.stat().st_size,
           "scool_key": key, "scool_path": str(rec["path"])}

    nolink = work / "schicar_nolinks.h5cd"
    cd2 = read_h5cd(SCHICAR)
    for fam in ("linked_scool", "linked_cool"):
        cd2.uns.pop(fam, None)
    write_h5cd(cd2, nolink, compression=None)
    out["h5cd_without_link_records_bytes"] = nolink.stat().st_size
    nolink.unlink()

    names = cooler.fileops.list_scool_cells(str(scool))
    b1, b2, cnt, offs = [], [], [], [0]
    t0 = time.perf_counter()
    with h5py.File(scool, "r") as f:
        for uri in names:
            g = f["cells"][uri.rsplit("/", 1)[-1]]["pixels"]
            b1.append(g["bin1_id"][:]); b2.append(g["bin2_id"][:]); cnt.append(g["count"][:])
            offs.append(offs[-1] + len(cnt[-1]))
    out["materialise_s"] = time.perf_counter() - t0
    b1, b2, cnt = np.concatenate(b1), np.concatenate(b2), np.concatenate(cnt)
    out["n_cells"] = len(names)
    out["n_pixels"] = int(len(cnt))
    out["n_contacts"] = int(cnt.sum())
    out["pixel_bytes_in_memory"] = int(b1.nbytes + b2.nbytes + cnt.nbytes)
    for tag, opts in (("h5cd_1x_settings", {}), ("cooler_settings_gzip6_shuffle",
                                                 {"compression": "gzip", "compression_opts": 6, "shuffle": True})):
        dst = work / f"schicar_copied_{tag}.h5cd"
        dst.write_bytes(SCHICAR.read_bytes())
        t0 = time.perf_counter()
        with h5py.File(dst, "a") as f:
            g = f.create_group("contacts")
            g.attrs["source"] = str(rec["path"])
            g.create_dataset("cell_names", data=np.array([n.rsplit("/", 1)[-1] for n in names], dtype="S"))
            g.create_dataset("cell_offset", data=np.asarray(offs, dtype=np.int64), **opts)
            for name, arr in (("bin1_id", b1), ("bin2_id", b2), ("count", cnt)):
                g.create_dataset(name, data=arr, chunks=True if opts else None, **opts)
        out[f"copied_{tag}_bytes"] = dst.stat().st_size
        out[f"copied_{tag}_write_s"] = time.perf_counter() - t0
        dst.unlink()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cells", default="50,100,500,1000,all")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--child", nargs="+", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        return child_query(args.child[0])
    if not STORE.exists():
        raise SystemExit(f"{STORE} missing — run apps/atlas/recipes/build_schicar_mop.py")
    ensure_h5cd()
    C.schicar_linked()                             # once, before the children

    work = C.WORK / "e_contacts"
    work.mkdir(parents=True, exist_ok=True)
    sizes = copied_sizes(work)
    print({k: (round(v / 2**20, 1) if k.endswith("bytes") else v) for k, v in sizes.items()})
    agg = []
    for n in args.cells.split(","):
        trials = [C.run_child(SCRIPT, ["--child", n]) for _ in range(args.repeats)]
        agg.append({"n_cells": trials[0]["n_cells"], "cold_s": C.summarize([t["cold_s"] for t in trials]),
                    "cached_s": C.summarize([t["cached_s"] for t in trials]),
                    "setup_s": C.summarize([t["setup_s"] for t in trials]),
                    "n_contacts": trials[0]["n_contacts"], "trials": trials})
        print(f"{trials[0]['n_cells']:5d} cells: first {agg[-1]['cold_s']['median'] * 1e3:8.1f} ms   "
              f"cached {agg[-1]['cached_s']['median'] * 1e6:8.1f} µs   setup {agg[-1]['setup_s']['median']:.2f} s",
              flush=True)
    C.write_json("e_contacts", {
        "panel": "e", "machine": C.machine_info(),
        "dataset": {"name": "scHiCAR mouse brain (GSE305439), per-cell 1 Mb .scool",
                    "h5cd": "schicar_mop/schicar_mop.chromdata.zarr written as .h5cd (legacy writer, uncompressed)", "scool": "schicar_mop/contacts_cells_1Mb.scool"},
        "size": sizes,
        "size_method": ("copied = h5cd + all per-cell pixels materialised in one contacts/ group "
                        "(concatenated bin1_id/bin2_id int64, count int32, cell_offset CSR index); "
                        "written uncompressed (as h5cd 1.x's cd.write did) and with gzip-6+shuffle "
                        "(cooler's defaults)"),
        "aggregation": {"implementation": "uchrom_browser.data.Dataset._pseudobulk (via Dataset.contacts, group=)",
                        "store": "schicar_mop.chromdata.zarr, maps linked only (no embedded copies), opened backed "
                                 "as the web browser opens it",
                        "region": f"{CHROM} (whole chromosome)", "repeats": args.repeats,
                        "cold": "first query in a fresh process (map listing done beforehand, reported as setup_s); "
                                "OS page cache warm",
                        "cached": "same query again (Dataset LRU cache)", "points": agg},
    })
    print(C.RESULTS / "e_contacts.json")


if __name__ == "__main__":
    main()
