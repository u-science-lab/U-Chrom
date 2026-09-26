"""Build a larger ``.chromdata.zarr`` store by replicating the cells of a real one, streaming.

For the 1e8-spot points of Figure 2 (panels b, c, d): the in-memory route
(``_common.subset_by_cells`` + ``cd.write``) needs the whole table in RAM
(~50 GB at 1e8 spots with Takei's 62 spot tracks), so this script copies the
source store's Parquet row groups ``k`` times instead, one row group at a
time.  Copy ``r > 0`` renames every cell and trace to ``<id>_r<r>`` (codes
shifted by ``r`` × the number of categories), exactly like
``_common._relabel``; ``cells`` / ``traces`` / ``cellm`` are replicated to
match; bins, bin tracks and ``uns`` are shared.  The last copy takes the
cells with the lowest codes until the target is reached.  The result is
flagged ``replicated`` in the root attrs (``uchrom.replicated``).

The source must be a format 2.1 (chromosome-partitioned) store — convert a
2.0 store first with ``python -m uchrom.io.upgrade old.chromdata.zarr
new.chromdata.zarr``.  Each chromosome partition of the output holds the
copies one after the other, which keeps it sorted by (cell, trace, bin).

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

    from uchrom.core.zarrcd import (Container, _compressor, _write_frame, _write_root_meta,
                                    read_small_parts)

    t0 = time.perf_counter()
    c = Container(args.src)
    parts = read_small_parts(c)
    if not parts.get("partitioned"):
        raise SystemExit(f"{args.src} is a format {c.meta.get('format_version')} store; "
                         f"convert it to 2.1 first (python -m uchrom.io.upgrade)")
    meta = dict(c.meta)
    tmeta = parts["tables_meta"]
    idx = {k: np.asarray(v) for k, v in parts["index"].items()}
    n_src = int(meta["n_spots"])
    target = int(args.n)
    if not meta.get("has_cell_id"):
        raise SystemExit("the source store needs cell_id")
    cats = parts["categories"]["spots"]
    trace_cats, trace_ord = cats["trace_id"]
    cell_cats, cell_ord = cats["cell_id"]
    n_tc, n_cc = len(trace_cats), len(cell_cats)

    # copies: k_full whole copies, then the cells with the lowest codes
    k_full, rest = divmod(target, n_src)
    cell_len = np.bincount(idx["cell_codes"], weights=np.diff(idx["cell_offsets"]), minlength=n_cc)
    k_cells = int(np.searchsorted(np.cumsum(cell_len), rest, side="left") + 1) if rest else 0
    n_copies = k_full + (1 if rest else 0)

    poff, pgrp, pch = idx["partition_offsets"], idx["partition_groups"], idx["partition_chrom"]
    rg = idx["row_groups"]
    seg, cel = idx["trace_offsets"], idx["cell_offsets"]

    dst = args.dst
    if dst.exists():
        shutil.rmtree(dst)
    root = zarr.open_group(str(dst), mode="w", zarr_format=3)
    tdir = dst / "tables"
    comp = _compressor(3)
    names = list(tmeta["partitions"][0]["files"])
    new_idx = {k: [] for k in ("trace_offsets", "trace_codes", "trace_cells", "chrom_trace",
                               "cell_offsets", "cell_codes", "cell_partition")}
    new_rg, new_poff, new_pgrp = [0], [0], [0]
    n_out = 0
    for p, part in enumerate(tmeta["partitions"]):
        a, b = int(poff[p]), int(poff[p + 1])
        n_p = b - a
        groups = rg[pgrp[p]:pgrp[p + 1] + 1] - a          # local group offsets
        # prefix of the partition holding the cells with code < k_cells
        c_sel = (cel[:-1] >= a) & (cel[:-1] < b)
        c_codes, c_off = idx["cell_codes"][c_sel], cel[:-1][c_sel] - a
        prefix = int(c_off[np.searchsorted(c_codes, k_cells)]) if (rest and np.any(c_codes >= k_cells)) \
            else (n_p if rest else 0)
        copies = [(r, n_p) for r in range(k_full)] + ([(k_full, prefix)] if rest else [])
        writers = {}
        base = n_out
        for r, stop in copies:
            for g in range(len(groups) - 1):
                g0, g1 = int(groups[g]), int(groups[g + 1])
                if g0 >= stop:
                    break
                for name in names:
                    t = c.parquet(f"tables/{part['files'][name]}").read_row_group(g)
                    if g1 > stop:
                        t = t.slice(0, stop - g0)
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
                        f = tdir / part["files"][name]
                        f.parent.mkdir(parents=True, exist_ok=True)
                        dict_cols = [fl.name for fl in t.schema if pa.types.is_integer(fl.type)
                                     or pa.types.is_string(fl.type)]
                        writers[name] = pq.ParquetWriter(f, t.schema, compression="zstd",
                                                         compression_level=3, use_dictionary=dict_cols or False)
                    writers[name].write_table(t, row_group_size=max(1, t.num_rows))
                new_rg.append(new_rg[-1] + (min(g1, stop) - g0))
            # index entries of this copy
            s_sel = (seg[:-1] >= a) & (seg[:-1] < a + stop)
            new_idx["trace_offsets"].append(seg[:-1][s_sel] - a + n_out)
            new_idx["trace_codes"].append(idx["trace_codes"][s_sel] + r * n_tc)
            tc = idx["trace_cells"][s_sel]
            new_idx["trace_cells"].append(np.where(tc >= 0, tc + r * n_cc, tc))
            new_idx["chrom_trace"].append(np.full(int(s_sel.sum()), int(pch[p]), dtype=np.int32))
            k_sel = (cel[:-1] >= a) & (cel[:-1] < a + stop)
            new_idx["cell_offsets"].append(cel[:-1][k_sel] - a + n_out)
            new_idx["cell_codes"].append(idx["cell_codes"][k_sel] + r * n_cc)
            new_idx["cell_partition"].append(np.full(int(k_sel.sum()), p, dtype=np.int32))
            n_out += stop
        for w in writers.values():
            w.close()
        new_poff.append(n_out)
        new_pgrp.append(len(new_rg) - 1)
        part["n_rows"] = n_out - base
        print(f"{part['chrom']}: {n_out - base:,} spots ({time.perf_counter() - t0:.0f} s)", flush=True)
    tables = root.create_group("tables")

    # categories of the copies
    def suffixed(values, r):
        return values if r == 0 else pd.Index([f"{v}_r{r}" for v in values])

    t_all = pd.Index(np.concatenate([np.asarray(suffixed(trace_cats, r), dtype=object) for r in range(n_copies)]))
    c_all = pd.Index(np.concatenate([np.asarray(suffixed(cell_cats, r), dtype=object) for r in range(n_copies)]))
    spot_meta = dict(tmeta["spots"])
    cat_meta = dict(spot_meta["categorical"])
    for col, values in (("trace_id", t_all), ("cell_id", c_all)):
        _write_frame(pd.DataFrame({"value": values.astype(str)}), tdir / cat_meta[col]["file"], 3)
    for col, info in cat_meta.items():
        if col not in ("trace_id", "cell_id"):
            shutil.copy(args.src / "tables" / info["file"], tdir / info["file"])
    for tname in ("spot_tracks",):
        if tname in tmeta:
            for col, info in tmeta[tname].get("categorical", {}).items():
                shutil.copy(args.src / "tables" / info["file"], tdir / info["file"])
            tmeta[tname] = {**tmeta[tname], "n_rows": n_out}
    spot_meta["n_rows"] = n_out
    tmeta["spots"] = spot_meta
    for name in ("bins.parquet", "bin_tracks.parquet"):
        if (args.src / "tables" / name).exists():
            shutil.copy(args.src / "tables" / name, tdir / name)
    for name in ("cells", "traces"):
        if name in tmeta:
            df = parts[name]
            reps = []
            for r in range(n_copies):
                d = df.copy()
                d.index = pd.Index([f"{v}_r{r}" if r else v for v in d.index], name=d.index.name)
                reps.append(d)
            _write_frame(pd.concat(reps), tdir / tmeta[name]["file"], 3)
            tmeta[name] = {**tmeta[name], "n_rows": int(len(df) * n_copies)}
    for sub in ("intervals", "points"):
        if (args.src / "tables" / sub).exists():
            shutil.copytree(args.src / "tables" / sub, tdir / sub)
    tables.attrs.update({"tables": tmeta})

    index = root.create_group("index")

    def arr(group, name, data):
        data = np.ascontiguousarray(data)
        group.create_array(name, data=data, chunks=(max(1, min(len(data), 1 << 20)),) + data.shape[1:],
                           compressors=comp)

    for key in ("trace_offsets", "cell_offsets"):
        arr(index, key, np.r_[np.concatenate(new_idx[key]), n_out].astype(np.int64))
    for key in ("trace_codes", "trace_cells", "chrom_trace", "cell_codes", "cell_partition"):
        arr(index, key, np.concatenate(new_idx[key]).astype(np.int32))
    arr(index, "row_groups", np.asarray(new_rg, dtype=np.int64))
    arr(index, "partition_offsets", np.asarray(new_poff, dtype=np.int64))
    arr(index, "partition_groups", np.asarray(new_pgrp, dtype=np.int64))
    arr(index, "partition_chrom", np.asarray(pch, dtype=np.int32))

    # arrays, results, uns, links: cellm replicated, the rest copied
    g = root.create_group("cellm")
    cnames = c.group_attrs("cellm").get("keys", {})
    for key, node in cnames.items():
        a = np.asarray(c.array(f"cellm/{node}"))
        arr(g, node, np.concatenate([a] * n_copies))
    g.attrs.update({"keys": cnames})
    for sub in ("binm", "results", "uns", "contacts", "links"):
        if (args.src / sub).exists():
            shutil.copytree(args.src / sub, dst / sub)
    trace_codes = np.concatenate(new_idx["trace_codes"])
    n_traces = int(len(np.unique(trace_codes)))
    n_cells = int(len(np.unique(np.concatenate(new_idx["cell_codes"]))))
    out_meta = {k: v for k, v in meta.items() if k not in ("format", "format_version", "uchrom_version",
                                                           "spot_order", "layout")}
    out_meta.update({"n_spots": n_out, "n_traces": n_traces, "n_cells": n_cells,
                     "n_row_groups": len(new_rg) - 1, "has_source_row": False,
                     "replicated": {"source": str(args.src), "source_n_spots": n_src, "n_copies": n_copies,
                                    "last_copy_cells": k_cells if rest else None}})
    _write_root_meta(root, out_meta, layout="2.1")
    size = sum(f.stat().st_size for f in dst.rglob("*") if f.is_file())
    print(json.dumps({"n_spots": n_out, "n_cells": n_cells, "n_traces": n_traces, "n_copies": n_copies,
                      "bytes": size, "seconds": time.perf_counter() - t0}))


if __name__ == "__main__":
    main()
