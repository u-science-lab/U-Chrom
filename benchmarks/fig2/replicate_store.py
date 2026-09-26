"""Build a larger ``.chromdata.zarr`` store by replicating the cells of a real one, streaming.

For the 1e8-spot points of Figure 2 (panels b, c): the in-memory route
(``_common.subset_by_cells`` + ``cd.write``) needs the whole table in RAM
(~50 GB at 1e8 spots with Takei's 62 spot tracks), so this script copies the
source store's Parquet row groups ``k`` times instead, one row group at a
time.  Copy ``r > 0`` renames every cell and trace to ``<id>_r<r>`` (codes
shifted), exactly like ``_common._relabel``; ``cells`` / ``traces`` /
``cellm`` are replicated to match; bins, bin tracks and ``uns`` are shared.
The last copy takes whole cells until the target is reached.  The result is
flagged ``replicated`` in the root attrs (``uchrom.replicated``).

    python benchmarks/fig2/replicate_store.py SRC.chromdata.zarr DST.chromdata.zarr --n 1e8
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--n", type=float, required=True, help="target number of spots")
    args = ap.parse_args()

    import pyarrow as pa
    import pyarrow.parquet as pq
    import zarr

    from uchrom.core.zarrcd import Container, _compressor, _write_frame, read_small_parts

    t0 = time.perf_counter()
    c = Container(args.src)
    parts = read_small_parts(c)
    meta = dict(c.meta)
    tmeta = parts["tables_meta"]
    idx = parts["index"]
    n_src = int(meta["n_spots"])
    target = int(args.n)
    rg = np.asarray(idx["row_groups"], dtype=np.int64)
    cell_off = np.asarray(idx["cell_offsets"], dtype=np.int64)
    if not meta.get("has_cell_id"):
        raise SystemExit("the source store needs cell_id")
    k_full, rest = divmod(target, n_src)
    copies = [(r, len(rg) - 1) for r in range(k_full)]
    if rest:
        # whole row groups (which hold whole cells) until the target is reached
        g_last = int(np.searchsorted(rg, rest, side="left"))
        copies.append((k_full, max(1, g_last)))
    cats = parts["categories"]["spots"]
    trace_cats, trace_ord = cats["trace_id"]
    cell_cats, cell_ord = cats["cell_id"]
    n_tc, n_cc = len(trace_cats), len(cell_cats)

    dst = args.dst
    if dst.exists():
        shutil.rmtree(dst)
    root = zarr.open_group(str(dst), mode="w", zarr_format=3)
    tables = root.create_group("tables")
    tdir = dst / "tables"
    comp = _compressor(3)

    files = {"spots": "spots.parquet"}
    if "spot_tracks" in tmeta:
        files["spot_tracks"] = "spot_tracks.parquet"
    for key, f in tmeta.get("layers", {}).items():
        files[f"layers/{key}"] = f
    writers = {}
    new_rg = [0]
    n_out = 0
    for r, n_groups in copies:
        for g in range(n_groups):
            for name, f in files.items():
                t = c.parquet(f"tables/{f}").read_row_group(g)
                if name == "spots":
                    cols = []
                    for fld in t.schema:
                        col = t.column(fld.name)
                        if fld.name == "trace_id":
                            col = pa.array(col.to_numpy().astype(np.int32) + np.int32(r * n_tc))
                        elif fld.name == "cell_id":
                            col = pa.array(col.to_numpy().astype(np.int32) + np.int32(r * n_cc))
                        cols.append(col)
                    t = pa.Table.from_arrays(cols, names=t.column_names)
                if name not in writers:
                    (tdir / f).parent.mkdir(parents=True, exist_ok=True)
                    dict_cols = [fl.name for fl in t.schema if pa.types.is_integer(fl.type)
                                 or pa.types.is_string(fl.type)]
                    writers[name] = pq.ParquetWriter(tdir / f, t.schema, compression="zstd",
                                                     compression_level=3, use_dictionary=dict_cols or False)
                writers[name].write_table(t, row_group_size=max(1, t.num_rows))
            n_out += int(rg[g + 1] - rg[g])
            new_rg.append(n_out)
        print(f"copy {r}: {n_out:,} spots written ({time.perf_counter() - t0:.0f} s)", flush=True)
    for w in writers.values():
        w.close()

    # categories of the copies
    def suffixed(values, r):
        return values if r == 0 else pd.Index([f"{v}_r{r}" for v in values])

    n_copies = len(copies)
    cat_dir = tdir / "categories"
    t_all = pd.Index(np.concatenate([np.asarray(suffixed(trace_cats, r), dtype=object) for r in range(n_copies)]))
    c_all = pd.Index(np.concatenate([np.asarray(suffixed(cell_cats, r), dtype=object) for r in range(n_copies)]))
    spot_meta = dict(tmeta["spots"])
    cat_meta = dict(spot_meta["categorical"])
    for col, values, ordered in (("trace_id", t_all, trace_ord), ("cell_id", c_all, cell_ord)):
        _write_frame(pd.DataFrame({"value": values.astype(str)}), dst / "tables" / cat_meta[col]["file"], 3)
    for col, info in cat_meta.items():
        if col not in ("trace_id", "cell_id"):
            shutil.copy(args.src / "tables" / info["file"], dst / "tables" / info["file"])
    spot_meta["n_rows"] = n_out
    for f in ("spot_tracks",):
        if f in tmeta:
            tmeta[f] = {**tmeta[f], "n_rows": n_out}
    tmeta["spots"] = spot_meta
    for name in ("bins.parquet", "bin_tracks.parquet"):
        if (args.src / "tables" / name).exists():
            shutil.copy(args.src / "tables" / name, dst / "tables" / name)
    for name in ("cells", "traces"):
        if name in tmeta:
            df = parts[name]
            reps = []
            for r in range(n_copies):
                d = df.copy()
                d.index = pd.Index([f"{v}_r{r}" if r else v for v in d.index], name=d.index.name)
                reps.append(d)
            _write_frame(pd.concat(reps), dst / "tables" / tmeta[name]["file"], 3)
            tmeta[name] = {**tmeta[name], "n_rows": int(len(df) * n_copies)}
    for sub in ("intervals", "points"):
        if (args.src / "tables" / sub).exists():
            shutil.copytree(args.src / "tables" / sub, dst / "tables" / sub)
    tables.attrs.update({"tables": tmeta})

    # index
    seg = np.asarray(idx["trace_offsets"], dtype=np.int64)
    parts_idx = {k: [] for k in ("trace_offsets", "trace_codes", "trace_cells", "chrom_trace",
                                 "cell_offsets", "cell_codes")}
    for r, n_groups in copies:
        stop = int(rg[n_groups])
        base = sum(int(rg[ng]) for _, ng in copies[:r])
        s_sel = seg[:-1] < stop
        c_sel = cell_off[:-1] < stop
        parts_idx["trace_offsets"].append(seg[:-1][s_sel] + base)
        parts_idx["trace_codes"].append(np.asarray(idx["trace_codes"])[s_sel] + r * n_tc)
        tc = np.asarray(idx["trace_cells"])[s_sel]
        parts_idx["trace_cells"].append(np.where(tc >= 0, tc + r * n_cc, tc))
        parts_idx["chrom_trace"].append(np.asarray(idx["chrom_trace"])[s_sel])
        parts_idx["cell_offsets"].append(cell_off[:-1][c_sel] + base)
        parts_idx["cell_codes"].append(np.asarray(idx["cell_codes"])[c_sel] + r * n_cc)
    index = root.create_group("index")

    def arr(group, name, data):
        data = np.ascontiguousarray(data)
        group.create_array(name, data=data, chunks=(max(1, min(len(data), 1 << 20)),) + data.shape[1:],
                           compressors=comp)

    for key in ("trace_offsets", "cell_offsets"):
        arr(index, key, np.r_[np.concatenate(parts_idx[key]), n_out].astype(np.int64))
    for key in ("trace_codes", "trace_cells", "chrom_trace", "cell_codes"):
        arr(index, key, np.concatenate(parts_idx[key]).astype(np.int32))
    arr(index, "row_groups", np.asarray(new_rg, dtype=np.int64))

    # arrays, results, uns, links: cellm replicated, the rest copied
    g = root.create_group("cellm")
    names = c.group_attrs("cellm").get("keys", {})
    for key, node in names.items():
        a = np.asarray(c.array(f"cellm/{node}"))
        arr(g, node, np.concatenate([a] * n_copies))
    g.attrs.update({"keys": names})
    for sub in ("binm", "results", "uns", "contacts", "links"):
        if (args.src / sub).exists():
            shutil.copytree(args.src / sub, dst / sub)
    n_traces = int(len(np.unique(np.concatenate(parts_idx["trace_codes"]))))
    n_cells = int(len(np.concatenate(parts_idx["cell_codes"])))
    meta.update({"n_spots": n_out, "n_traces": n_traces, "n_cells": n_cells,
                 "n_row_groups": len(new_rg) - 1, "has_source_row": False,
                 "replicated": {"source": str(args.src), "source_n_spots": n_src, "n_copies": n_copies}})
    root.attrs.update({"uchrom": meta, "uchrom_format_version": meta["format_version"],
                       "uchrom_version": meta.get("uchrom_version", "unknown")})
    size = sum(f.stat().st_size for f in dst.rglob("*") if f.is_file())
    print(json.dumps({"n_spots": n_out, "n_cells": n_cells, "n_traces": n_traces, "n_copies": n_copies,
                      "bytes": size, "seconds": time.perf_counter() - t0}))


if __name__ == "__main__":
    main()
