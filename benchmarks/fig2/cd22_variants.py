"""Format 2.2 experiment: store layouts vs a flat Parquet table, every metric.

Variants (``VARIANTS``):

* ``parquet``        — the flat spot table (spots + x/y/z + tracks) with
  pyarrow **defaults** (``df.to_parquet``: snappy, dictionary), read with
  ``pd.read_parquet`` defaults: the headline baseline (what users do);
* ``parquet_tuned``  — the same table, zstd-3 and the same lossless decimal
  float encoding as 2.2 (``uchrom.core.floatcodec``), read with
  ``pq.read_table`` + decode + ``to_pandas(split_blocks, self_destruct)``
  (transparency row);
* ``zarr20`` / ``zarr21`` — ``.chromdata.zarr`` 2.0 (one cell-sorted file per
  table) and 2.1 (every spot table partitioned by chromosome);
* ``A``   — 2.2 layout: the 2.0 primary + a coordinate projection partitioned
  by chromosome (``tables/coords_by_chrom/``), floats stored as float64;
* ``AB``  — ``A`` + lossless decimal float encoding (the 2.2 default).
  The read-speed work (C) changes the reader, not the store: measured as
  ``AB`` on the checkout before / after it (``--tag``).

Metrics: size, write time and peak RSS (one fresh process); full read time
and peak RSS (``--repeats`` fresh processes; ``ChromData.read`` — Parquet:
the DataFrame); for the stores also ``c_access.py``'s backed child (open,
get_trace / get_cell / get_chrom with and without ``columns="coords"``,
RSS after the trace + cell queries) and ``d_streaming.py``'s streaming
child (exact median distance map of chr11 under a 2 GB budget: time, peak
RSS).  Warm OS cache (reads follow the write; not flushed).

    python benchmarks/fig2/cd22_variants.py --data takei --sizes 1e5,1e6,1e7 --variants parquet,zarr21,A,AB
    python benchmarks/fig2/cd22_variants.py --data liu --variants parquet,parquet_tuned,zarr20,zarr21,A,AB

Writes ``u-chrom-paper/manuscripts/full/figures/fig2/results/cd22_variants.json`` (merged by (data, size, variant, tag)).
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

SCRIPT = Path(__file__).resolve()
ACCESS = SCRIPT.parent / "c_access.py"
STREAM = SCRIPT.parent / "d_streaming.py"
LIU_STORE = C.DATA / "liu2025_mop" / "liu2025_mop.chromdata.zarr"


# ----------------------------------------------------------------------------- variants

def _flat(cd):
    import pandas as pd
    df = cd.to_dataframe()
    st = cd.tracks_spot_view()
    if len(st.columns):
        df = pd.concat([df, st.reset_index(drop=True)], axis=1)
    return df


def write_parquet_tuned(cd, path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    import pyarrow.types as pat

    from uchrom.core.zarrcd import encode_float_columns

    t = pa.Table.from_pandas(_flat(cd), preserve_index=False)
    enc = {}
    cols = encode_float_columns([(f.name, t.column(f.name).combine_chunks()) for f in t.schema], enc)
    out = pa.Table.from_arrays([a for _, a in cols], names=[n for n, _ in cols])
    meta = dict(t.schema.metadata or {})
    meta[b"uchrom_float_encoding"] = json.dumps(enc).encode()
    out = out.replace_schema_metadata(meta)
    dict_cols = [f.name for f in out.schema if pat.is_integer(f.type) or pat.is_string(f.type)
                 or pat.is_dictionary(f.type)]
    pq.write_table(out, path, compression="zstd", compression_level=3, use_dictionary=dict_cols)


def read_parquet_tuned(path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from concurrent.futures import ThreadPoolExecutor

    import numpy as np
    from uchrom.core import floatcodec

    t = pq.read_table(path)
    enc = json.loads(t.schema.metadata[b"uchrom_float_encoding"])
    n = t.num_rows

    def one(c):
        buf = pa.allocate_buffer(max(1, 8 * n))
        out = np.frombuffer(buf, dtype=np.float64, count=n)
        floatcodec.decode_arrow(t.column(c), t.column(c + "#exc"), enc[c], out=out)
        return pa.Array.from_buffers(pa.float64(), n, [None, buf])

    with ThreadPoolExecutor(8) as ex:
        dec = dict(zip(enc, ex.map(one, list(enc))))
    cols, names = [], []
    for c in t.column_names:
        if c.endswith("#exc"):
            continue
        cols.append(dec.get(c, t.column(c)))
        names.append(c)
    meta = {k: v for k, v in (t.schema.metadata or {}).items() if k != b"uchrom_float_encoding"}
    t2 = pa.Table.from_arrays(cols, names=names).replace_schema_metadata(meta)
    del t
    return t2.to_pandas(split_blocks=True, self_destruct=True)


def _zarr_writer(**kw):
    def write(cd, path):
        from uchrom.core.zarrcd import write_zarr
        write_zarr(cd, path, **kw)
    return write


def _zarr_read(path):
    from uchrom import ChromData
    return ChromData.read(path)


_V22 = dict(_layout="2.2")


VARIANTS = {
    "parquet": {"label": "Parquet (pyarrow defaults)", "ext": ".parquet",
                "write": lambda cd, p: C.FORMATS["parquet"].write(cd, p),
                "read": lambda p: C.FORMATS["parquet"].read(p), "store": False},
    "parquet_tuned": {"label": "Parquet (zstd-3 + decimal floats)", "ext": ".parquet",
                      "write": write_parquet_tuned, "read": read_parquet_tuned, "store": False},
    "zarr20": {"label": "chromdata.zarr 2.0", "ext": ".chromdata.zarr",
               "write": _zarr_writer(_layout="2.0"), "read": _zarr_read, "store": True},
    "zarr21": {"label": "chromdata.zarr 2.1", "ext": ".chromdata.zarr",
               "write": _zarr_writer(_layout="2.1"), "read": _zarr_read, "store": True},
    "A": {"label": "2.2 layout (primary + coord projection), float64", "ext": ".chromdata.zarr",
          "write": _zarr_writer(_layout="2.2", float_encoding=False), "read": _zarr_read, "store": True},
    "AB": {"label": "2.2 layout + decimal floats", "ext": ".chromdata.zarr",
           "write": _zarr_writer(_layout="2.2", float_encoding=True), "read": _zarr_read, "store": True},
    "AB_zstd1": {"label": "2.2 layout + decimal floats, zstd level 1", "ext": ".chromdata.zarr",
                 "write": _zarr_writer(_layout="2.2", compression_level=1), "read": _zarr_read, "store": True},
    # -- second attempt (coordinates stored once + derived spot columns) -----
    "zarr21_serial": {"label": "chromdata.zarr 2.1, serial reader (as on main)", "ext": ".chromdata.zarr",
                      "write": _zarr_writer(_layout="2.1"), "read": _zarr_read, "store": True,
                      "env": {"UCHROM_ZARR_SERIAL_READ": "1"}},
    "D": {"label": "2.2: coords once + derived spot columns, float64", "ext": ".chromdata.zarr",
          "write": _zarr_writer(**_V22, float_encoding=False), "read": _zarr_read, "store": True},
    "D_serial": {"label": "D, serial reader (no C)", "ext": ".chromdata.zarr",
                 "write": _zarr_writer(**_V22, float_encoding=False), "read": _zarr_read, "store": True,
                 "env": {"UCHROM_ZARR_SERIAL_READ": "1"}},
    "D_nonorm": {"label": "D without derived spot columns", "ext": ".chromdata.zarr",
                 "write": _zarr_writer(**_V22, float_encoding=False, normalize_spot_columns=False),
                 "read": _zarr_read, "store": True},
    "D_rg32k": {"label": "D, 32,768-row primary row groups", "ext": ".chromdata.zarr",
                "write": _zarr_writer(**_V22, float_encoding=False, row_group_rows=32768),
                "read": _zarr_read, "store": True},
    "D_rg16k": {"label": "D, 16,384-row primary row groups", "ext": ".chromdata.zarr",
                "write": _zarr_writer(**_V22, float_encoding=False, row_group_rows=16384),
                "read": _zarr_read, "store": True},
    "D_fdict": {"label": "D + Parquet dictionary pages for float columns", "ext": ".chromdata.zarr",
                "write": _zarr_writer(**_V22, float_encoding=False, float_dictionary=True),
                "read": _zarr_read, "store": True},
    "D_lz4dict": {"label": "D, primary lz4 + float dictionaries (coords zstd)", "ext": ".chromdata.zarr",
                  "write": _zarr_writer(**_V22, float_encoding=False, float_dictionary=True,
                                        compression={"primary": "lz4", "coords": "zstd"}),
                  "read": _zarr_read, "store": True},
    "D_snappydict": {"label": "D, primary snappy + float dictionaries (coords zstd)", "ext": ".chromdata.zarr",
                     "write": _zarr_writer(**_V22, float_encoding=False, float_dictionary=True,
                                           compression={"primary": "snappy", "coords": "zstd"}),
                     "read": _zarr_read, "store": True},
    "D_lz4": {"label": "D, primary lz4 (coords zstd)", "ext": ".chromdata.zarr",
              "write": _zarr_writer(**_V22, float_encoding=False, compression={"primary": "lz4", "coords": "zstd"}),
              "read": _zarr_read, "store": True},
    "zarr22": {"label": "chromdata.zarr 2.2 (the default: coordinates once, derived spot columns, "
                        "float dictionary pages)", "ext": ".chromdata.zarr",
               "write": _zarr_writer(_layout="2.2"), "read": _zarr_read, "store": True},
    "DF": {"label": "2.2: coords once + derived columns + float dictionary pages (primary)",
           "ext": ".chromdata.zarr",
           "write": _zarr_writer(**_V22, float_encoding=False, float_dictionary=True),
           "read": _zarr_read, "store": True},
    "DF_serial": {"label": "DF, serial reader (no C)", "ext": ".chromdata.zarr",
                  "write": _zarr_writer(**_V22, float_encoding=False, float_dictionary=True),
                  "read": _zarr_read, "store": True, "env": {"UCHROM_ZARR_SERIAL_READ": "1"}},
    "DF_nonorm": {"label": "DF without derived spot columns", "ext": ".chromdata.zarr",
                  "write": _zarr_writer(**_V22, float_encoding=False, float_dictionary=True,
                                        normalize_spot_columns=False),
                  "read": _zarr_read, "store": True},
    "DFBc": {"label": "DF + decimal floats (coordinates)", "ext": ".chromdata.zarr",
             "write": _zarr_writer(**_V22, float_encoding=("coords",), float_dictionary=True),
             "read": _zarr_read, "store": True},
    "DFB": {"label": "DF + decimal floats (all tables)", "ext": ".chromdata.zarr",
            "write": _zarr_writer(**_V22, float_encoding=True, float_dictionary=True),
            "read": _zarr_read, "store": True},
    "DB": {"label": "D + decimal floats (all tables)", "ext": ".chromdata.zarr",
           "write": _zarr_writer(**_V22, float_encoding=True), "read": _zarr_read, "store": True},
    "DBc": {"label": "D + decimal floats (coordinates only)", "ext": ".chromdata.zarr",
            "write": _zarr_writer(**_V22, float_encoding=("coords",)), "read": _zarr_read, "store": True},
    "DBt": {"label": "D + decimal floats (spot tracks only)", "ext": ".chromdata.zarr",
            "write": _zarr_writer(**_V22, float_encoding=("spot_tracks",)), "read": _zarr_read, "store": True},
}


def _apply_env(key):
    for k, v in VARIANTS[key].get("env", {}).items():
        os.environ[k] = v


# ----------------------------------------------------------------------------- children

def load(stage):
    stage = Path(stage)
    if stage.suffix == ".pkl":
        return C.load_stage(stage)
    from uchrom import ChromData
    return ChromData.read(stage)


def child_write(key, stage, out):
    cd = load(stage)
    v = VARIANTS[key]
    t0 = time.perf_counter()
    v["write"](cd, Path(out))
    dt = time.perf_counter() - t0
    tables = {}
    tdir = Path(out) / "tables"
    if tdir.is_dir():
        for sub in sorted(tdir.iterdir()):
            tables[sub.name] = C.size_bytes(sub)
        idx = Path(out) / "index"
        tables["index"] = C.size_bytes(idx)
    C.emit({"write_s": dt, "bytes": C.size_bytes(Path(out)), "table_bytes": tables,
            "write_peak_rss_mb": C.peak_rss_mb()})


def child_read(key, path):
    _apply_env(key)
    import pyarrow.parquet  # noqa: F401  (import cost out of the timing)
    import zarr  # noqa: F401
    import h5py  # noqa: F401
    from uchrom import ChromData  # noqa: F401
    import uchrom.core.backed  # noqa: F401
    from uchrom.core import floatcodec  # noqa: F401
    base = C.current_rss_mb()
    t0 = time.perf_counter()
    obj = VARIANTS[key]["read"](Path(path))
    dt = time.perf_counter() - t0
    n = obj.n_spots if hasattr(obj, "n_spots") else len(obj)
    C.emit({"read_s": dt, "read_peak_rss_mb": C.peak_rss_mb(), "baseline_rss_mb": base, "n_rows": int(n)})


def child_stage_liu(out):
    from uchrom import ChromData
    cd = ChromData.read(LIU_STORE)
    with open(out, "wb") as fh:
        pickle.dump(cd, fh, protocol=5)
    C.emit({"n_spots": int(cd.n_spots), "n_cells": int(cd.n_cells)})


# ----------------------------------------------------------------------------- driver

def _summ(trials, key):
    return C.summarize([t[key] for t in trials])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="takei", choices=["takei", "liu"])
    ap.add_argument("--sizes", default="1e5,1e6,1e7")
    ap.add_argument("--variants", default="parquet,parquet_tuned,zarr20,zarr21,A,AB")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--queries", type=int, default=20)
    ap.add_argument("--no-access", action="store_true")
    ap.add_argument("--no-stream", action="store_true")
    ap.add_argument("--chrom", default="chr11")
    ap.add_argument("--budget", default="2GB")
    ap.add_argument("--tag", default="", help="suffix of the variant key (e.g. 'C' after the read-path work)")
    ap.add_argument("--keep", action="store_true", help="keep the written stores")
    ap.add_argument("--out", default="cd22_variants.json", help="results file under u-chrom-paper/manuscripts/full/figures/fig2/results")
    ap.add_argument("--child", nargs="+", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        kind, *rest = args.child
        return {"write": child_write, "read": child_read, "stage_liu": child_stage_liu}[kind](*rest)

    work = C.WORK / "cd22"
    work.mkdir(parents=True, exist_ok=True)
    if args.data == "liu":
        stage = work / "liu_stage.pkl"
        if not stage.exists():
            C.run_child(SCRIPT, ["--child", "stage_liu", str(stage)])
        stages = {"all": (stage, {"n_spots": 9582069, "dataset": "Liu 2025 MOp (4DN), all spots"})}
    else:
        stages = {}
        for s in args.sizes.split(","):
            n = int(float(s))
            st = C.stage_subset(n)
            stages[str(n)] = (st, C.stage_info(st))
    out_json = C.RESULTS / args.out
    res = json.loads(out_json.read_text()) if out_json.exists() else {"points": {}}
    res["machine"] = C.machine_info()
    res["protocol"] = {
        "repeats": args.repeats, "stat": "median (min / max) over fresh processes",
        "page_cache": "warm (reads follow the write; OS cache not flushed)",
        "queries_per_level": args.queries, "streaming": f"distance_map({args.chrom}, 'median'), budget {args.budget}",
        "variants": {k: v["label"] for k, v in VARIANTS.items()}}
    for size, (stage, info) in stages.items():
        for key in args.variants.split(","):
            v = VARIANTS[key]
            vkey = key + (f"+{args.tag}" if args.tag and v["store"] else "")
            path = work / f"{args.data}_{size}_{key}{v['ext']}"
            C.remove(path)
            w = C.run_child(SCRIPT, ["--child", "write", key, str(stage), str(path)])
            reads = [C.run_child(SCRIPT, ["--child", "read", key, str(path)]) for _ in range(args.repeats)]
            rec = {"data": args.data, "size": size, "variant": vkey, "label": v["label"],
                   "n_spots": info.get("n_spots"), "git": C.machine_info()["versions"].get("uchrom_git"),
                   "size_mb": w["bytes"] / 2**20, "table_mb": {k: b / 2**20 for k, b in w["table_bytes"].items()},
                   "write_s": w["write_s"], "write_peak_rss_mb": w["write_peak_rss_mb"],
                   "read_s": _summ(reads, "read_s"), "read_peak_rss_mb": _summ(reads, "read_peak_rss_mb"),
                   "read_baseline_rss_mb": _summ(reads, "baseline_rss_mb")}
            line = (f"{args.data} {size:>9} {vkey:14s} {rec['size_mb']:8.1f} MB  write {w['write_s']:6.1f} s  "
                    f"read {rec['read_s']['median']:6.2f} s  peak {rec['read_peak_rss_mb']['median'] / 1024:6.2f} GB")
            if v["store"] and not args.no_access and not v.get("env"):
                sys.path.insert(0, str(ACCESS.parent))
                import c_access
                runs = [C.run_child(ACCESS, ["--child", "zarr-backed", str(path), str(args.queries)])
                        for _ in range(args.repeats)]
                acc = c_access._pool_repeats(runs)
                rec["access"] = {k: acc[k] for k in ("open_s", "rss_after_open_mb", "rss_after_trace_cell_mb",
                                                     "peak_rss_trace_cell_mb", "peak_rss_mb", "baseline_rss_mb")}
                for lv in ("trace", "cell", "chrom", "trace_coords", "cell_coords", "chrom_coords"):
                    rec["access"][lv] = acc[lv]["latency_s"]
                line += (f"  open {acc['open_s'] * 1e3:6.1f} ms  trace {acc['trace']['latency_s']['median'] * 1e3:6.1f}"
                         f"  cell {acc['cell']['latency_s']['median'] * 1e3:6.1f}  chrom "
                         f"{acc['chrom']['latency_s']['median'] * 1e3:7.1f}  chrom(coords) "
                         f"{acc['chrom_coords']['latency_s']['median'] * 1e3:6.1f} ms  rss(q) "
                         f"{(acc['rss_after_trace_cell_mb'] - acc['baseline_rss_mb']) / 1024:5.2f} GB")
            if v["store"] and not args.no_stream and args.data == "takei" and not v.get("env"):
                runs = [C.run_child(STREAM, ["--child", "streaming", str(path), args.chrom, args.budget, "-"])
                        for _ in range(args.repeats)]
                rec["streaming"] = {"seconds": _summ(runs, "seconds"), "peak_rss_mb": _summ(runs, "peak_rss_mb"),
                                    "baseline_rss_mb": _summ(runs, "baseline_rss_mb")}
                line += (f"  stream {rec['streaming']['seconds']['median']:5.1f} s "
                         f"{rec['streaming']['peak_rss_mb']['median'] / 1024:5.2f} GB")
            print(line, flush=True)
            res["points"][f"{args.data}|{size}|{vkey}"] = rec
            out_json.write_text(json.dumps(res, indent=1, default=C._jsonable))
            if not args.keep:
                C.remove(path)
    print(out_json)


if __name__ == "__main__":
    main()
