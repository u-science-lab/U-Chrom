"""scA/B (cis, raw) of ``single_cell_compartments`` against the original scHiCluster compartment score.

    python benchmarks/sc_structures/scab_schicluster_reference.py --schicluster DIR --scool X.scool
        --genome mm10 [--cells 20] [--out DIR]

The original: ``single_chrom_compartment`` of scHiCluster (github.com/zhoujt1994/scHiCluster,
``schicluster/compartment/call_compartment.py``; ``--schicluster`` a checkout outside the repository), the
compartment score of ``hicluster compartment`` (cool mode): per chromosome, the cell's raw map without its
diagonal, bins without contacts given a 1 on the diagonal, rows normalised to 1, times the CpG ratio of the bins.
The function's source is taken from the file and executed as it is (its module imports xarray, which is not
needed by this function; nothing of scHiCluster is installed or imported by U-Chrom).

Inputs: per-cell maps of a ``.scool`` (``scool::/cells/<name>``, read with ``cooler.matrix(balance=False,
sparse=True).fetch(chrom)`` as scHiCluster reads them) and one CpG track for both (the CpG frequency of
``<genome>_genome``, cached by ``scab_common.cpg_track``).  scHiCluster's own CpG ratio comes from ``bedtools
nuc`` with missing values set to 0, so its partners without sequence count with CpG 0: U-Chrom is run once with
that track (NaN -> 0: must agree exactly where a bin has cis contacts) and once with NaN left as NaN (its default:
such partners are skipped).  Bins without cis contacts get their own CpG in scHiCluster and NaN in U-Chrom;
they are counted, not compared.

Results: a table on stdout and ``scab_schicluster_reference.json`` in ``--out``.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scab_common import cpg_track  # noqa: E402


def original(schicluster: Path):
    """``single_chrom_compartment`` (and ``compartment_strength``, which it calls) from the scHiCluster source."""
    import scipy.sparse as sp

    src = (schicluster / "schicluster/compartment/call_compartment.py").read_text()
    tree = ast.parse(src)
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef)
            and n.name in ("single_chrom_compartment", "compartment_strength")]
    ns = {"np": np, "pd": pd, "diags": sp.diags, "csr_matrix": sp.csr_matrix}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "call_compartment.py", "exec"), ns)
    return ns["single_chrom_compartment"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--schicluster", type=Path, required=True)
    ap.add_argument("--scool", type=Path, required=True)
    ap.add_argument("--genome", required=True)
    ap.add_argument("--cells", type=int, default=20)
    ap.add_argument("--label", default=None)
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "uchrom_scab_schicluster")
    a = ap.parse_args()
    import cooler
    from chromdata import ChromData

    from uchrom.strc.comp.single_cell import ScABParams, single_cell_compartments

    a.out.mkdir(parents=True, exist_ok=True)
    func = original(a.schicluster)
    names = [p.rsplit("/", 1)[-1] for p in cooler.fileops.list_scool_cells(str(a.scool))][: a.cells]
    clr0 = cooler.Cooler(f"{a.scool}::/cells/{names[0]}")
    res = int(clr0.binsize)
    sizes = {c: int(n) for c, n in clr0.chromsizes.items()}
    track = cpg_track(a.genome, sizes, res, a.out / "cache")
    bins = clr0.bins()[["chrom", "start", "end"]][:].astype({"chrom": str})
    tv = bins.merge(track, on=["chrom", "start", "end"], how="left")["value"].to_numpy()
    chroms = [c for c in clr0.chromnames if not np.isnan(tv[(bins["chrom"] == c).to_numpy()]).all()]

    no_spots = pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                             "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str),
                             "cell_id": pd.Series(dtype=str)})
    cd = ChromData(np.zeros((0, 3)), no_spots, cells=pd.DataFrame(index=pd.Index(names, name="cell_id")))
    cd.link_scool(str(a.scool), key="per_cell", cell_name="cell_id", bin_size=res)
    zero = bins.assign(value=np.nan_to_num(tv, nan=0.0))
    nan = bins.assign(value=tv)
    p = ScABParams(contacts="cis", normalize="none")
    t0 = time.perf_counter()
    ours0 = single_cell_compartments(cd, track=zero, params=p, chrom=chroms, key_added=None)
    t_ours = time.perf_counter() - t0
    ours_nan = single_cell_compartments(cd, track=nan, params=p, chrom=chroms, key_added=None)
    labels = list(ours0.columns)

    rows, t_orig = [], 0.0
    for n in names:
        clr = cooler.Cooler(f"{a.scool}::/cells/{n}")
        theirs = []
        t0 = time.perf_counter()
        for c in chroms:
            m = clr.matrix(balance=False, sparse=True).fetch(c).tocsr()
            cpg = zero.loc[zero["chrom"] == c, "value"].reset_index(drop=True)
            comp, _ = func(m, cpg)
            theirs.append(np.asarray(comp, float))
        t_orig += time.perf_counter() - t0
        theirs = pd.Series(np.concatenate(theirs), index=labels)
        o0, on = ours0.loc[n].astype(float), ours_nan.loc[n].astype(float)
        has = o0.notna()
        d0 = (o0[has] - theirs[has]).abs()
        dn = (on[has] - theirs[has]).abs()
        own = theirs[~has]
        own_ok = np.allclose(own.to_numpy(), zero.set_index(pd.Index(
            [f"{c}:{s}-{e}" for c, s, e in zip(zero["chrom"], zero["start"], zero["end"])]))["value"].reindex(
            own.index).to_numpy())
        rows.append({"cell": n, "bins_with_cis_contacts": int(has.sum()), "bins_without": int((~has).sum()),
                     "max_abs_diff_zero_track": float(d0.max()),
                     "max_rel_diff_zero_track": float((d0 / theirs[has].abs().clip(lower=1e-12)).max()),
                     "max_abs_diff_nan_track": float(dn.max()), "median_abs_diff_nan_track": float(dn.median()),
                     "r_nan_track": float(np.corrcoef(on[has], theirs[has])[0, 1]),
                     "without_contacts_get_own_cpg": bool(own_ok)})
    tab = pd.DataFrame(rows)
    print(tab.to_string(index=False))
    summary = {"label": a.label or a.scool.name, "cells": len(names), "resolution": res, "chroms": chroms,
               "max_abs_diff_zero_track": float(tab["max_abs_diff_zero_track"].max()),
               "max_rel_diff_zero_track": float(tab["max_rel_diff_zero_track"].max()),
               "max_abs_diff_nan_track": float(tab["max_abs_diff_nan_track"].max()),
               "min_r_nan_track": float(tab["r_nan_track"].min()),
               "uchrom_seconds_all_cells": t_ours, "schicluster_seconds_all_cells": t_orig,
               "load": os.getloadavg()}
    print(json.dumps(summary, indent=1))
    out = a.out / f"scab_schicluster_reference_{summary['label']}.json"
    out.write_text(json.dumps({"summary": summary, "cells": rows}, indent=1))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
