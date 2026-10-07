"""Pseudo-bulk maps of the dscHi-C aging cortex atlas store (32,777 cells, 1 Mb per-cell maps embedded, read
over HTTP): runtime / memory of ``uchrom.fea.pseudobulk`` and its exactness.

    .venv/bin/python benchmarks/hic_structures/pseudobulk_dschic.py [--out DIR] [--groupby cell_type] [--cis]

1. ``pseudobulk(cd, groupby)`` over every cell (all cell types): wall time per stage (HTTP read + decode,
   accumulation, cooler write, ICE), peak resident memory (sampled every 0.2 s), bytes received.
2. Exactness: the group maps added up are the store's all-cells sums (``EmbeddedContacts.sum_pixels``, every
   partition, cis + trans) pixel for pixel, and are compared with the store's bulk map at 1 Mb (``bulk``,
   built from the merged published contacts).
3. Per group: cells, contacts per cell, cis fraction, ICE convergence.

Results: a table on stdout and ``pseudobulk_dschic.json`` in ``--out`` (default: a folder in the system temp
directory — not the repository).
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd


class PeakRSS:
    """Peak resident memory of this process, sampled in a thread."""

    def __init__(self, every: float = 0.2):
        import psutil

        self.proc, self.every, self.peak, self._stop = psutil.Process(), every, 0, threading.Event()

    def __enter__(self):
        self.peak = self.proc.memory_info().rss
        self.base = self.peak
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()
        return self

    def _run(self):
        while not self._stop.wait(self.every):
            self.peak = max(self.peak, self.proc.memory_info().rss)

    def __exit__(self, *exc):
        self._stop.set()
        self.t.join()


def stored_bytes(e, store: str, trans: bool) -> dict:
    """Compressed bytes of the per-cell pixel arrays to transfer, per partition (HEAD of every shard)."""
    from concurrent.futures import ThreadPoolExecutor

    import fsspec

    fs = fsspec.filesystem("https")
    r = e.resolutions[0]
    shard = e.g[f"r{r}/cis/{e.chroms[0]}/pix"].shards[1]
    urls = []
    for part, n in e.meta["n_pixels"].items():
        if part == "trans" and not trans:
            continue
        name = "trans" if part == "trans" else f"cis/{part}"
        urls += [(part, f"{store}/embedded/contacts/{e.name}/r{r}/{name}/pix/c/0/{k}") for k in range(-(-n // shard))]
    with ThreadPoolExecutor(16) as ex:
        sizes = list(ex.map(lambda u: fs.info(u[1])["size"], urls))
    out: dict = {}
    for (part, _), size in zip(urls, sizes):
        out[part] = out.get(part, 0) + int(size)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "uchrom_pseudobulk_dschic")
    ap.add_argument("--groupby", default="cell_type")
    ap.add_argument("--cis", action="store_true", help="cis contacts only (trans=False)")
    ap.add_argument("--max-pixels", type=int, default=None)
    ap.add_argument("--workers", type=int, default=None, help="reads in flight (default: pseudobulk's)")
    a = ap.parse_args()

    import uchrom.datasets as ds
    from chromdata.embedded import open_all

    from uchrom.fea.pseudobulk_maps import BLOCK_PIXELS, READ_WORKERS, pseudobulk

    a.out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    cd = ds.load("dschic_aging_cortex")
    t_open = time.perf_counter() - t0
    print(f"opened {cd._links_from()} in {t_open:.1f} s: {len(cd.cells):,} cells")

    t0 = time.perf_counter()
    with PeakRSS() as mem:
        summary = pseudobulk(cd, a.groupby, out_dir=a.out / "maps", overwrite=True, trans=not a.cis,
                             max_pixels=a.max_pixels or BLOCK_PIXELS, workers=a.workers or READ_WORKERS,
                             verbose=True)
    wall = time.perf_counter() - t0
    stages = cd.results.record("pseudobulk").inputs["seconds"]
    per_part = stored_bytes(open_all(cd._links_from())["per_cell"], str(cd._links_from()), not a.cis)
    rx = sum(per_part.values())
    print(f"\npseudobulk: {wall:.1f} s wall, stages {stages}; peak RSS {mem.peak / 1e9:.2f} GB "
          f"(+{(mem.peak - mem.base) / 1e9:.2f} GB over the open object); {rx / 1e9:.2f} GB of per-cell pixels "
          f"transferred ({rx / 1e6 / wall:.1f} MB/s over the wall time)")

    # --- exactness: sum of the group maps vs the store's all-cells sums and its bulk map ---------------------
    import cooler

    emb = open_all(cd._links_from())
    e, bulk = emb["per_cell"], emb["bulk"]
    r = e.resolutions[0]
    nb = len(e.bins(r))
    acc = {}
    for p in summary["path"]:
        px = cooler.Cooler(p).pixels()[:]
        k = px["bin1_id"].to_numpy(np.int64) * nb + px["bin2_id"].to_numpy(np.int64)
        acc[p] = (k, px["count"].to_numpy(np.int64))
    keys = np.concatenate([v[0] for v in acc.values()])
    vals = np.concatenate([v[1] for v in acc.values()])
    uk, inv = np.unique(keys, return_inverse=True)
    groups_sum = pd.Series(np.bincount(inv, weights=vals).astype(np.int64), index=uk)

    ref = []
    chrom_cells = np.asarray(e.bins(r)["chrom"])
    for b1, b2, c in e.iter_sum_pixels(r):
        if a.cis:
            keep = chrom_cells[b1] == chrom_cells[b2]
            b1, b2, c = b1[keep], b2[keep], c[keep]
        ref.append(pd.Series(c.astype(np.int64), index=b1.astype(np.int64) * nb + b2.astype(np.int64)))
    ref = pd.concat(ref).groupby(level=0).sum()
    both = pd.concat({"groups": groups_sum, "store_sum": ref}, axis=1).fillna(0).astype(np.int64)
    exact = bool((both["groups"] == both["store_sum"]).all())
    print(f"sum of the {len(summary)} group maps == store all-cells sums: {exact} "
          f"({len(both):,} pixels, {int(both['groups'].sum()):,} contacts; max |diff| "
          f"{int((both['groups'] - both['store_sum']).abs().max())})")

    rb = int(r)
    bpx = []
    chrom_of = np.asarray(bulk.bins(rb)["chrom"])
    for b1, b2, c in bulk.iter_pixels(rb):
        bpx.append(pd.Series(c.astype(np.int64), index=b1.astype(np.int64) * nb + b2.astype(np.int64)))
    bulk_s = pd.concat(bpx).groupby(level=0).sum()
    cmp = pd.concat({"groups": groups_sum, "bulk": bulk_s}, axis=1).fillna(0).astype(np.int64)
    b1 = (cmp.index.to_numpy() // nb)
    b2 = (cmp.index.to_numpy() % nb)
    cis = chrom_of[b1] == chrom_of[b2]
    if a.cis:
        cmp, cis = cmp[cis], cis[cis]
    ok = (cmp["groups"] > 0) & (cmp["bulk"] > 0)
    lg, lb = np.log(cmp["groups"][ok]), np.log(cmp["bulk"][ok])
    vs_bulk = {
        "pixels_groups": int((cmp["groups"] > 0).sum()), "pixels_bulk": int((cmp["bulk"] > 0).sum()),
        "contacts_groups": int(cmp["groups"].sum()), "contacts_bulk": int(cmp["bulk"].sum()),
        "contacts_groups_cis": int(cmp["groups"][cis].sum()), "contacts_bulk_cis": int(cmp["bulk"][cis].sum()),
        "pixels_identical": float((cmp["groups"] == cmp["bulk"]).mean()),
        "pearson_log_counts": float(np.corrcoef(lg, lb)[0, 1]),
        "ratio_median": float(np.median(cmp["groups"][ok] / cmp["bulk"][ok])),
    }
    print("vs the store's bulk map (1 Mb):", json.dumps(vs_bulk))

    summary = summary.assign(contacts_per_cell=summary["n_contacts"] / summary["n_cells"],
                             frac_cis=summary["n_cis"] / summary["n_contacts"])
    print()
    print(summary[["group", "n_cells", "n_contacts", "contacts_per_cell", "frac_cis", "n_pixels", "balanced"]]
          .to_string(index=False))
    res = {"store": str(cd._links_from()), "n_cells": int(len(cd.cells)), "groupby": a.groupby,
           "trans": not a.cis, "resolution": int(r), "open_s": t_open, "wall_s": wall, "stages_s": stages,
           "peak_rss_gb": mem.peak / 1e9, "rss_increase_gb": (mem.peak - mem.base) / 1e9,
           "transferred_gb": rx / 1e9, "transferred_mb_per_partition": {k: v / 1e6 for k, v in per_part.items()},
           "workers": a.workers or READ_WORKERS, "max_pixels": a.max_pixels or BLOCK_PIXELS,
           "n_partition_pixels": e.meta.get("n_pixels"),
           "sum_equals_store_sums": exact, "vs_bulk": vs_bulk,
           "groups": json.loads(summary.drop(columns=["path"]).to_json(orient="records"))}
    out = a.out / "pseudobulk_dschic.json"
    out.write_text(json.dumps(res, indent=1))
    print(f"\n-> {out}")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    main()
