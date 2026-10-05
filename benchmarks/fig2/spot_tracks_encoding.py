"""Why the format 2.1 store is larger on Takei 2025, and what Parquet options recover it.

The 2.1 layout partitions the spot-aligned tables by chromosome.  On the
Takei 2025 cerebellum data (62 per-spot z-score tracks) the store grew by
~35 %, almost all in ``spot_tracks``.  This script measures, on the same
rows (every ``spot_tracks`` value of the 1e7-spot subset):

* the size per table (spots / spot_tracks / layers) of a 2.0 and a 2.1 store;
* ``spot_tracks`` written in the **2.0 order** (cell › trace › bin across
  all chromosomes) vs the **2.1 order** (chromosome › cell › trace › bin),
  each with the same Parquet options — isolating the effect of the order;
* Parquet options on the 2.1 order: row-group size (16k / 65k / 262k rows),
  zstd level (3 / 6 / 9 / 15), dictionary encoding of the float columns,
  ``BYTE_STREAM_SPLIT`` for the float columns (alone and with a higher
  level): file size, write time and full-read (decode) time.

    python benchmarks/fig2/spot_tracks_encoding.py OLD_2_0.chromdata.zarr NEW_2_1.chromdata.zarr

Writes ``u-chrom-paper/manuscripts/full/figures/fig2/results/spot_tracks_encoding.json``.
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402


def table_sizes(store: Path):
    out = {}
    t = store / "tables"
    for name in ("spots", "spot_tracks", "layers"):
        for cand in (t / name, t / f"{name}.parquet"):
            if cand.exists():
                out[name] = C.size_bytes(cand)
    out["total"] = C.size_bytes(store)
    return out


def encode(table, **kw):
    import pyarrow as pa
    import pyarrow.parquet as pq

    buf = io.BytesIO()
    t0 = time.perf_counter()
    rg = kw.pop("row_group_size", 16384)
    pq.write_table(table, buf, compression="zstd", row_group_size=rg, **kw)
    w = time.perf_counter() - t0
    data = buf.getvalue()
    times = []
    for _ in range(3):
        t0 = time.perf_counter()
        pq.read_table(pa.BufferReader(data), use_threads=True)
        times.append(time.perf_counter() - t0)
    return {"bytes": len(data), "write_s": w, "read_s": float(np.median(times))}


def main():
    import pyarrow as pa
    import pyarrow.types as pat

    from uchrom import ChromData

    old, new = Path(sys.argv[1]), Path(sys.argv[2])
    res = {"table_bytes": {"2.0": table_sizes(old), "2.1": table_sizes(new)}}
    # the same rows in both orders
    b20 = ChromData.read(old, backed=True)
    t20 = b20._rows.read_all("spot_tracks")                     # 2.0 order
    chrom = b20.bins["chrom"].cat.codes.to_numpy()[b20.spots["bin_id"].to_numpy()]
    order21 = np.argsort(chrom, kind="stable")                  # chromosome first, else 2.0 order
    t21 = t20.take(pa.array(order21))
    floats = [f.name for f in t21.schema if pat.is_floating(f.type)]
    n = t21.num_rows
    res["n_rows"], res["n_columns"], res["n_float_columns"] = n, t21.num_columns, len(floats)
    base = dict(compression_level=3, use_dictionary=False)
    res["order"] = {"2.0 order (cell>trace>bin)": encode(t20, **base),
                    "2.1 order (chrom>cell>trace>bin)": encode(t21, **base)}
    print("order", {k: round(v["bytes"] / 2**20) for k, v in res["order"].items()}, flush=True)
    opts = {
        "zstd-3, 16k rows (2.1 default)": dict(base),
        "zstd-3, 65k rows": dict(base, row_group_size=65536),
        "zstd-3, 262k rows": dict(base, row_group_size=262144),
        "zstd-6": dict(base, compression_level=6),
        "zstd-9": dict(base, compression_level=9),
        "zstd-15": dict(base, compression_level=15),
        "dictionary (floats)": dict(compression_level=3, use_dictionary=True),
        "byte_stream_split (floats), zstd-3": dict(base, use_byte_stream_split=floats),
        "byte_stream_split (floats), zstd-9": dict(base, compression_level=9, use_byte_stream_split=floats),
    }
    res["options_2_1_order"] = {}
    for name, kw in opts.items():
        r = encode(t21, **kw)
        res["options_2_1_order"][name] = r
        print(f"{name:40s} {r['bytes'] / 2**20:8.0f} MB  write {r['write_s']:6.1f} s  read {r['read_s']:5.2f} s",
              flush=True)
    res["what"] = __doc__.split("\n\n")[0]
    C.write_json("spot_tracks_encoding", {"machine": C.machine_info(), **res})
    print(C.RESULTS / "spot_tracks_encoding.json")


if __name__ == "__main__":
    main()
