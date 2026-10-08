"""The path from a scHi-C dataset to the tracing callers, one call each: ``ds.load`` then the caller.

    python benchmarks/sc_structures/structures_onecall.py [--out DIR] [--chrom chr21]

On the backed Tan 2018 store (``ds.load("tan2018_gm12878", backed=True)``: structures + per-cell maps):
``call_compartments_axes_pc``, ``call_tads_by_pval`` (streaming on a backed object), ``call_loops_axiswise_f``
and ``call_domains_fishnet_trace`` (one homolog, a 100-locus stretch) on one chromosome, results stored on
the object (``cd.results`` / ``cd.intervals`` / ``cd.bin_tracks``); run time and peak memory of each; the
streaming ArcFISH result against the in-memory one (same boundaries).  JSON to ``--out``.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import structures_common as sc  # noqa: E402

warnings.filterwarnings("ignore")


def particle_convention(cell: str = "gm12878_01") -> dict:
    """What a particle's position means, from the cell's own contacts: the median 3-D distance (structure
    units) between the particles holding the two legs of every cis contact on one homolog (> 100 kb apart),
    when a leg at ``x`` is given the particle at ``floor(x / 20 kb)`` or at ``ceil(x / 20 kb)`` x 20 kb.  Dip-C:
    its ``impute3.round4.con`` contacts (phase 0 / 1 tried as pat / mat) and clean structure; hickit: the
    hickit pairs (``phase_prob00`` / ``11`` > 0.9) and 20 kb structure in the cell's GEO tarball."""
    import gzip
    import io
    import re
    import tarfile

    import pandas as pd

    import uchrom.datasets as ds
    from uchrom.io.dipc_3dg import read_3dg_structure

    folder = Path(ds.fetch("tan2018_gm12878"))
    size = 20_000
    conv = {"floor": lambda p: p // size * size, "ceil": lambda p: -(-p // size) * size}

    def med(g, chrom, hap, a, b):
        sub = g[(g["chrom"] == chrom) & (g["homolog"] == hap)].set_index("position")[["x", "y", "z"]]
        out = {}
        for name, f in conv.items():
            i, j = f(a), f(b)
            ok = np.isin(i, sub.index) & np.isin(j, sub.index)
            out[name] = float(np.median(np.linalg.norm(sub.loc[i[ok]].to_numpy() - sub.loc[j[ok]].to_numpy(), axis=1)))
        return out

    res = {}
    dipc = next(folder.glob(f"GSM*_{cell}.impute3.round4.clean.3dg.txt.gz"))
    g = read_3dg_structure(dipc)
    con = pd.read_csv(next(folder.glob(f"GSM*_{cell}.impute3.round4.con.txt.gz")), sep="\t", header=None)
    a, b = con[0].str.split(",", expand=True), con[1].str.split(",", expand=True)
    for phase0 in ("pat", "mat"):
        names = {"0": phase0, "1": "mat" if phase0 == "pat" else "pat"}
        for ch in ("21", "7"):
            m = (a[0] == ch) & (b[0] == ch) & (a[2] == b[2]) & ((a[1].astype(int) - b[1].astype(int)).abs() > 100_000)
            for h in ("0", "1"):
                mm = m & (a[2] == h)
                res[f"dipc chr{ch} phase{h}={names[h]}"] = med(
                    g, f"chr{ch}", names[h], a.loc[mm, 1].astype(int).to_numpy(), b.loc[mm, 1].astype(int).to_numpy())
    tar = next(p for p in folder.glob("GSM*_gm12878_*.tar.gz") if re.search(cell, p.name))
    with tarfile.open(tar) as tf:
        h3 = tf.extractfile(f"{cell}.3dg.gz").read()
        pr = pd.read_csv(io.BytesIO(gzip.decompress(tf.extractfile(f"{cell}.pairs.gz").read())), sep="\t",
                         header=None, comment="#", dtype={1: str, 3: str})
    tmp = sc.default_out("sc_structures_onecall") / f"{cell}.hickit.3dg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(gzip.decompress(h3))
    gh = read_3dg_structure(tmp)
    for ch in ("21", "7"):
        for col, hap in ((9, "pat"), (12, "mat")):
            m = (pr[1] == ch) & (pr[3] == ch) & (pr[col] > 0.9) & ((pr[4] - pr[2]).abs() > 100_000)
            res[f"hickit chr{ch} {hap}"] = med(gh, f"chr{ch}", hap, pr.loc[m, 2].to_numpy(), pr.loc[m, 4].to_numpy())
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=sc.default_out("sc_structures_onecall"))
    ap.add_argument("--chrom", default="chr21")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    import uchrom.datasets as ds
    from uchrom.strc.comp import call_compartments_axes_pc
    from uchrom.strc.loop import call_loops_axiswise_f
    from uchrom.strc.tad import call_domains_fishnet_trace, call_tads_by_pval

    conv = particle_convention()
    for k, v in conv.items():
        print("particle convention", k, v, flush=True)
    cd, rt_load = sc.timed(ds.load, "tan2018_gm12878", backed=True)
    res = {"particle_convention": conv, "load": rt_load,
           "store": {"n_spots": int(cd.n_spots), "n_traces": int(cd.n_traces), "n_cells": int(len(cd.cells)),
                     "layers": list(cd.layers), "structures": cd.uns["structures"]}}
    print(res, flush=True)
    c = a.chrom
    for name, fn in (("axes_pc", lambda: call_compartments_axes_pc(cd, chrom=c, device="cpu")),
                     ("arcfish_tads", lambda: call_tads_by_pval(cd, chrom=c, device="cpu")),
                     ("axiswise_f_loops", lambda: call_loops_axiswise_f(cd, chrom=c, device="cpu"))):
        out, rt = sc.timed(fn)
        res[name] = {"rows": int(len(out)), **rt}
        print(name, res[name], flush=True)
    sub = sc.in_memory_chrom(cd, c)
    tid = sc.trace_ids(sub)[0]
    from uchrom.fea import trace_distance_matrix

    dist, _ = trace_distance_matrix(sub, tid, chrom=c)          # every locus of the chromosome (NaN: absent)
    ok = np.flatnonzero(np.isfinite(dist).any(1))[600:700]       # a stretch of 100 particles of this homolog
    fn_out, rt = sc.timed(call_domains_fishnet_trace, dist[np.ix_(ok, ok)])
    res["fishnet_trace_100_loci"] = {"boundaries": [int(x) for x in fn_out["boundaries"]], **rt}
    res["stored"] = {"results": list(cd.results.keys()), "intervals": list(cd.intervals.keys()),
                     "bin_tracks": [str(x) for x in cd.bin_tracks.columns]}
    mem = call_tads_by_pval(sub, chrom=c, device="cpu", key_added=None)
    stream = cd.results["tads.arcfish"]
    s1, m1 = stream[stream["level"] == 1], mem[mem["level"] == 1]
    res["arcfish_streaming_equals_in_memory"] = bool(np.array_equal(s1["start"].to_numpy(), m1["start"].to_numpy()))
    print(res["fishnet_trace_100_loci"], res["stored"], res["arcfish_streaming_equals_in_memory"], flush=True)
    sc.dump(res, a.out / "structures_onecall.json")


if __name__ == "__main__":
    main()
