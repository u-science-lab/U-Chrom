"""scA/B of ``uchrom.strc.comp.single_cell_compartments`` against the original Dip-C implementation, cell by cell.

    .venv/bin/python benchmarks/sc_structures/scab_dipc_reference.py --dipc DIR --python2 PY27 [--cells 20] [--out DIR]

The original: Dip-C (github.com/tanlongzhi/dip-c, Python 2; ``--dipc`` a checkout, ``--python2`` a Python 2.7 with
numpy + scipy, both outside the repository — e.g. ``CONDA_SUBDIR=osx-64 micromamba create -p py27 -c conda-forge
python=2.7 numpy scipy``), run as Tan et al. 2021 (Cell 184:741) ran it on each cell::

    scripts/hickit_pairs_to_con.sh contacts.pairs.gz                     # -> contacts.con.gz
    dip-c color2 -b1000000 -H -c color/mm10.cpg.1m.txt -s contacts.con.gz > cpg_b1m.color2
    python scripts/color_to_rank.py cpg_b1m.color2 > cpg_b1m.rank         # "rank-normalized", 0-1

on Tan 2021 adult cortex cells (``tan2021_cortex``: the per-cell ``contacts.pairs`` of the registered entry,
fetched file by file).  U-Chrom reads the *same* contacts and the *same* CpG file: the legs of
``contacts.con.gz`` binned as Dip-C bins them (``round(locus / 1 Mb)``: bins centred on multiples of 1 Mb), one
``.scool`` of those maps linked to a ``ChromData``, ``track`` = Dip-C's ``mm10.cpg.1m.txt`` on those bins.
Compared per cell: the bins with a value, max |difference| of the raw values (``normalize="none"``) and of the
ranks (``normalize="rank"``, the default; a mismatch: > 1e-6, a rank step being ~4e-4 — U-Chrom returns
float32, hence differences of ~1e-9 / 3e-8), and wall time (Dip-C per cell vs U-Chrom for all the cells).

Results: a table on stdout and ``scab_dipc_reference.json`` in ``--out``.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

BIN = 1_000_000
HERE = Path(__file__).resolve().parent
CELLS_TSV = HERE.parents[1] / "packages/uchrom/uchrom/datasets/tan2021_adult_cortex_cells.tsv"


def fetch_cells(names):
    """The registered ``contacts.pairs`` files of these Tan 2021 cells (a subset of ``tan2021_cortex``)."""
    from uchrom.datasets import _entry, _files, data_dir
    from uchrom.datasets._fetch import download

    want = {f"{n}.contacts.pairs.txt.gz" for n in names}
    out = {}
    for rel, url in _files(_entry("tan2021_cortex")):
        name = rel.rsplit("/", 1)[-1]
        if name in want:
            out[name.split(".")[0]] = download(url, data_dir() / rel, verbose=False)
    return out


def read_con(path):
    """Legs of a Dip-C ``.con.gz``: chrom1, locus1, chrom2, locus2."""
    df = pd.read_csv(path, sep=r"[,\t]", header=None, engine="python",
                     names=["c1", "p1", "h1", "c2", "p2", "h2"], usecols=[0, 1, 3, 4])
    return df


def dipc_bin(locus: np.ndarray) -> np.ndarray:
    """Dip-C ``leg_to_bin_ref_locus``: ``int(round(locus / bin)) * bin`` (Python 2 rounds halves away from 0)."""
    return np.floor(locus / BIN + 0.5).astype(np.int64)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dipc", type=Path, required=True, help="Dip-C checkout (github.com/tanlongzhi/dip-c)")
    ap.add_argument("--python2", type=Path, required=True, help="Python 2.7 with numpy and scipy")
    ap.add_argument("--cells", type=int, default=20)
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "uchrom_scab_dipc")
    a = ap.parse_args()
    import cooler
    from chromdata import ChromData

    from uchrom.strc.comp.single_cell import ScABParams, single_cell_compartments

    a.out.mkdir(parents=True, exist_ok=True)
    work = a.out / "dipc_runs"
    work.mkdir(exist_ok=True)
    table = pd.read_csv(CELLS_TSV, sep="\t")
    names = list(table["name"].iloc[: a.cells])
    pairs = fetch_cells(names)

    # --- the original, cell by cell -------------------------------------------------------------------------
    t_dipc = {}
    for n in names:
        d = work / n
        d.mkdir(exist_ok=True)
        link = d / "contacts.pairs.gz"
        if not link.exists():
            shutil.copyfile(pairs[n], link)
        con = d / "contacts.con.gz"
        if not con.exists():
            subprocess.run(["bash", str(a.dipc / "scripts/hickit_pairs_to_con.sh"), str(link)], check=True)
        if not (d / "cpg_b1m.rank").exists():
            t0 = time.perf_counter()
            with open(d / "cpg_b1m.color2", "w") as fh:
                subprocess.run([str(a.python2), str(a.dipc / "dip-c"), "color2", "-b1000000", "-H", "-c",
                                str(a.dipc / "color/mm10.cpg.1m.txt"), "-s", str(con)], check=True, stdout=fh,
                               stderr=subprocess.DEVNULL)
            with open(d / "cpg_b1m.rank", "w") as fh:
                subprocess.run([str(a.python2), str(a.dipc / "scripts/color_to_rank.py"), str(d / "cpg_b1m.color2")],
                               check=True, stdout=fh, stderr=subprocess.DEVNULL)
            (d / "seconds.txt").write_text(f"{time.perf_counter() - t0:.3f}\n")
        if (d / "seconds.txt").exists():
            t_dipc[n] = float((d / "seconds.txt").read_text())
    print(f"Dip-C color2 + color_to_rank on {len(names)} cells: "
          f"{np.mean(list(t_dipc.values())) if t_dipc else float('nan'):.1f} s per cell (Python 2 start included)")

    # --- the same contacts, binned as Dip-C bins them, into one .scool ---------------------------------------
    header = [line.split()[1:] for line in gzip.open(pairs[names[0]], "rt") if line.startswith("#chromosome")]
    sizes = {c: int(n) for c, n in header}
    nk = {c: int(np.floor(s / BIN + 0.5)) + 1 for c, s in sizes.items()}      # bin k = centre k * 1 Mb
    fake = {c: nk[c] * BIN for c in sizes}                                      # uniform bins [k Mb, k+1 Mb)
    first = dict(zip(fake, np.r_[0, np.cumsum([nk[c] for c in fake])[:-1]]))
    from uchrom.io.pairs_maps import genome_bins

    bins = genome_bins(fake, BIN)
    maps = {}
    for n in names:
        legs = read_con(work / n / "contacts.con.gz")
        g1 = legs["c1"].map(first).to_numpy(np.int64) + dipc_bin(legs["p1"].to_numpy(np.int64))
        g2 = legs["c2"].map(first).to_numpy(np.int64) + dipc_bin(legs["p2"].to_numpy(np.int64))
        lo, hi = np.minimum(g1, g2), np.maximum(g1, g2)
        px = pd.DataFrame({"bin1_id": lo, "bin2_id": hi}).value_counts().rename("count").reset_index()
        maps[n] = px.sort_values(["bin1_id", "bin2_id"]).reset_index(drop=True)
    scool = a.out / "dipc_binned_1Mb.scool"
    if scool.exists():
        scool.unlink()
    cooler.create_scool(str(scool), bins, maps, ordered=True)
    cpg = pd.read_csv(a.dipc / "color/mm10.cpg.1m.txt", sep="\t", header=None, names=["chrom", "start", "value"])
    track = cpg.assign(end=cpg["start"] + BIN)[["chrom", "start", "end", "value"]]
    no_spots = pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                             "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str),
                             "cell_id": pd.Series(dtype=str)})
    cd = ChromData(np.zeros((0, 3)), no_spots, cells=pd.DataFrame(index=pd.Index(names, name="cell_id")))
    cd.link_scool(str(scool), key="per_cell", cell_name="cell_id", bin_size=BIN)

    t0 = time.perf_counter()
    raw = single_cell_compartments(cd, track=track, params=ScABParams(normalize="none"), key_added=None)
    t_raw = time.perf_counter() - t0
    t0 = time.perf_counter()
    rank = single_cell_compartments(cd, track=track, key_added=None)
    t_rank = time.perf_counter() - t0

    rows = []
    for n in names:
        ref = pd.read_csv(work / n / "cpg_b1m.color2", sep="\t", header=None, names=["chrom", "locus", "v"])
        refr = pd.read_csv(work / n / "cpg_b1m.rank", sep="\t", header=None, names=["chrom", "locus", "v"])
        keys = ref["chrom"] + ":" + ref["locus"].astype(str) + "-" + (ref["locus"] + BIN).astype(str)
        ours = raw.loc[n]
        ours_set = set(ours.index[ours.notna()])
        both = keys[keys.isin(ours_set)]
        d_raw = np.abs(ours[both].to_numpy(np.float64) - ref["v"][keys.isin(ours_set)].to_numpy())
        keysr = refr["chrom"] + ":" + refr["locus"].astype(str) + "-" + (refr["locus"] + BIN).astype(str)
        d_rank = np.abs(rank.loc[n].reindex(keysr).to_numpy(np.float64) - refr["v"].to_numpy())
        rows.append({"cell": n, "contacts": int(len(read_con(work / n / "contacts.con.gz"))),
                     "bins_dipc": int(len(ref)), "bins_uchrom": int(len(ours_set)),
                     "same_bins": bool(set(keys) == ours_set),
                     "max_abs_diff_raw": float(d_raw.max()), "max_rel_diff_raw": float((d_raw / ref["v"].abs().max()).max()),
                     "max_abs_diff_rank": float(np.nanmax(d_rank)),
                     "rank_mismatches": int((d_rank > 1e-6).sum()),   # rank steps are 1 / (n - 1) ~ 4e-4; float32 output
                     "dipc_seconds": t_dipc.get(n)})
    res = pd.DataFrame(rows)
    print(res.to_string(index=False))
    summary = {"cells": len(names), "all_same_bins": bool(res["same_bins"].all()),
               "max_abs_diff_raw": float(res["max_abs_diff_raw"].max()),
               "max_abs_diff_rank": float(res["max_abs_diff_rank"].max()),
               "rank_mismatches_total": int(res["rank_mismatches"].sum()),
               "uchrom_seconds_all_cells_raw": t_raw, "uchrom_seconds_all_cells_rank": t_rank,
               "dipc_seconds_per_cell_mean": float(np.nanmean([v for v in t_dipc.values()])) if t_dipc else None,
               "load": os.getloadavg()}
    print(json.dumps(summary, indent=1))
    out = a.out / "scab_dipc_reference.json"
    out.write_text(json.dumps({"summary": summary, "cells": rows}, indent=1))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
