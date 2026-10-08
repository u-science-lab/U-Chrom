"""U-Chrom's SnapHiC against the authors' implementation on the same cells and the same contacts.

    python benchmarks/sc_structures/snaphic_reference.py prepare --out DIR --n 100 --rep 0
    <ref python> SnapHiC/snap.py ...                         # the authors' pipeline (snaphic_reference.sbatch)
    python benchmarks/sc_structures/snaphic_reference.py compare --out DIR --n 100 --rep 0 --chrom chr17 chr18 chr19

The reference is SnapHiC v0.2.x (github.com/HuMingLab/SnapHiC, commit 782dc2b; GPL-3.0, run in its own
environment, never imported by U-Chrom), sliding-window RWR (SnapHiC2), loops of 100 kb - 1 Mb, its mm10 filter
regions.  ``prepare`` writes the cells' contacts as the authors' input — one line per non-empty 10-kb pixel of the
per-cell maps (``cell chr pos chr pos``, positions at bin centres, so the authors' binning gives back the same
binary maps) for every autosome (the window size rule pools all of them).  The authors' run computes the RWR,
the tests and the loops on the chromosomes given (small ones: the code holds a dense chromosome x chromosome
matrix per process).  ``compare`` runs ``call_loops_snaphic`` on the same cells and chromosomes with the
window the authors' log reports and compares:

* U-Chrom twice: by default (every pixel imputed) and with ``sliding_window_holes=True`` (the pixels the
  authors' sliding windows leave at 0 reproduced);
* the imputation: per cell and chromosome, the authors' normalised RWR z-scores vs U-Chrom's (Pearson, largest
  difference; by default the pixels the authors' windows leave at 0 are left out);
* the per-pixel statistics of the test (``outlier_count``, ``case_avg``, ``control_avg``, ``tstat``,
  ``fdr_dist``);
* the loop summits: identical, within 20 kb (both directions).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snaphic_common as C  # noqa: E402
from snaphic_mesc import MAX_DIST, RES, filter_regions, load_cells, subset  # noqa: E402


def stage_prepare(args):
    from uchrom.fea.impute_rwr import _cells_and_source, _ScoolCells

    cd, top = load_cells()
    cells = subset(top, args.n, args.rep)
    ids, scool = _cells_and_source(cd, "per_cell", cells)
    d = args.out / "input"
    d.mkdir(parents=True, exist_ok=True)
    src = _ScoolCells(scool)
    n_lines = 0
    for c in ids:
        rows = []
        for chrom in C.MM10_AUTOSOMES:
            i, j, _ = src.cis(c, chrom)
            if len(i):
                rows.append(pd.DataFrame({"id": c, "c1": chrom, "p1": i * RES + RES // 2, "c2": chrom,
                                          "p2": j * RES + RES // 2}))
        t = pd.concat(rows, ignore_index=True)
        t.to_csv(d / f"{c}.contacts.txt", sep="\t", header=False, index=False)
        n_lines += len(t)
    src.close()
    (args.out / "cells.json").write_text(json.dumps(cells))
    print(f"{len(ids)} cells, {n_lines:,} pixels -> {d}")


def _their_window(out: Path) -> int:
    log = (out / "snaphic_out" / "snapHiC.log").read_text()
    m = re.findall(r"sliding window size is set to (\d+)", log)
    if not m:
        raise SystemExit("no window size in the authors' log")
    return int(m[-1])


def _read_bedpe(p: Path, names) -> pd.DataFrame:
    return pd.read_csv(p, sep="\t", header=None, names=names)


def _loops_vs(ours: pd.DataFrame, theirs: pd.DataFrame) -> dict:
    o = ours[["chrom1", "start1", "chrom2", "start2"]]
    key = lambda t: set(zip(t["chrom1"], t["start1"], t["start2"]))  # noqa: E731
    return {"n_ours": int(len(o)), "n_theirs": int(len(theirs)), "identical": len(key(o) & key(theirs)),
            "ours_within_20kb_of_theirs": float(C.overlap(o, theirs).mean()) if len(o) else None,
            "theirs_within_20kb_of_ours": float(C.overlap(theirs, o).mean()) if len(theirs) else None}


def stage_compare(args):
    """Both U-Chrom modes against the authors' run: the default (every pixel imputed) and
    ``sliding_window_holes=True`` (the pixels SnapHiC's windows leave at 0 reproduced)."""
    from uchrom.fea.impute_rwr import _cells_and_source, _snaphic_holes, read_cell_pixels, rwr_band, zscore_band
    from uchrom.strc.loop import snaphic as S

    out = args.out
    ref = out / "snaphic_out"
    cells = json.loads((out / "cells.json").read_text())
    cd, _ = load_cells()
    w = _their_window(out)
    step = w // 2
    D = (MAX_DIST + 50_000) // RES
    res = {"n_cells": len(cells), "window_bins": w, "chrom": args.chrom}
    ids, scool = _cells_and_source(cd, "per_cell", cells)
    summits = ref / "postprocessed" / "ref.postprocessed.summits.bedpe"
    t = pd.read_csv(summits, sep="\t") if summits.exists() and summits.stat().st_size else pd.DataFrame(
        columns=["chr1", "x1", "y1"])
    theirs_loops = pd.DataFrame({"chrom1": t["chr1"].astype(str), "start1": t["x1"].astype(np.int64),
                                 "chrom2": t["chr1"].astype(str), "start2": t["y1"].astype(np.int64)})
    for mode, holes in (("default", False), ("holes", True)):
        r = {}
        # 1. imputation of a few cells
        imp = []
        for chrom in args.chrom:
            n, pix = read_cell_pixels(scool, ids, chrom)
            for k in range(min(3, len(ids))):
                f = ref / "rwr" / f"{ids[k]}.{chrom}.normalized.rwr.bedpe"   # setname = file name - suffix
                if not f.exists():
                    continue
                tb = _read_bedpe(f, ["c1", "x1", "x2", "c2", "y1", "y2", "v"])
                i = (tb["x1"] // RES).to_numpy()
                dd = ((tb["y1"] - tb["x1"]) // RES).to_numpy()
                i0, j0 = pix[k]
                z = zscore_band(rwr_band(i0, j0, n, window=w, step=step, max_diag=D, holes=holes), edge=5)
                ours, theirs = z[i, dd], tb["v"].to_numpy()
                hole = _snaphic_holes(n, D + 1, step)[i, dd]
                ok = np.isfinite(ours) & (holes | ~hole)
                imp.append({"cell": ids[k], "chrom": chrom, "n_pixels": int(len(tb)), "n_hole": int(hole.sum()),
                            "pearson": float(np.corrcoef(ours[ok], theirs[ok])[0, 1]),
                            "max_abs_diff": float(np.max(np.abs(ours[ok] - theirs[ok]))),
                            "median_abs_diff": float(np.median(np.abs(ours[ok] - theirs[ok]))),
                            "theirs_at_holes_mean": float(theirs[hole].mean()) if hole.any() else None})
        r["imputation"] = imp
        # 2. per-pixel statistics
        stats = []
        for chrom in args.chrom:
            f = ref / "interactions" / f"significances.{chrom}.bedpe"
            if not f.exists():
                continue
            theirs = pd.read_csv(f, sep="\t")
            n, pix = read_cell_pixels(scool, ids, chrom)
            acc = S.snaphic_sums(n, pix, window=w, step=step, max_diag=D, out_diag=MAX_DIST // RES, holes=holes)
            px = S._pixel_table(acc, n, 5, 5)
            px["x1"], px["y1"] = px["i"] * RES, px["j"] * RES
            m = theirs.merge(px, on=["x1", "y1"], suffixes=("_ref", ""))
            c = 2 * m["i"].to_numpy() + (m["j"] - m["i"]).to_numpy()
            near_hole = np.zeros(len(m), bool)
            for di in range(-5, 6):                      # pixels whose background square touches a hole
                for dj in range(-5, 6):
                    cc = c + di + dj
                    near_hole |= ((cc - step) % (2 * step) == 0) | (cc <= step)
            if holes:
                near_hole[:] = False
            row = {"chrom": chrom, "n_ref": int(len(theirs)), "n_matched": int(len(m)),
                   "n_compared": int((~near_hole).sum())}
            for col in ("outlier_count", "case_avg", "control_avg", "tstat", "fdr_dist"):
                a, b = m[f"{col}_ref"].to_numpy(float), m[col].to_numpy(float)
                okk = np.isfinite(a) & np.isfinite(b) & (np.abs(a) < 900) & (np.abs(b) < 900) & ~near_hole
                row[f"{col}_pearson"] = float(np.corrcoef(a[okk], b[okk])[0, 1]) if okk.sum() > 2 else None
                row[f"{col}_max_abs"] = float(np.max(np.abs(a[okk] - b[okk]))) if okk.any() else None
                row[f"{col}_q999_abs"] = float(np.quantile(np.abs(a[okk] - b[okk]), 0.999)) if okk.any() else None
            row["outlier_count_equal"] = float((m["outlier_count_ref"] == m["outlier_count"])[~near_hole].mean())
            stats.append(row)
        r["statistics"] = stats
        # 3. calls
        tm = {}
        params = S.SnapHiCParams(max_dist=MAX_DIST, window=w * RES, sliding_window_holes=holes)
        loops = S.call_loops_snaphic(cd, cells=cells, chrom=args.chrom, params=params, exclude=filter_regions(),
                                     key_added=None, timing=tm)
        loops.to_csv(out / f"uchrom_loops_{mode}.tsv", sep="\t", index=False)
        r["loops"] = {**_loops_vs(loops, theirs_loops), "uchrom_timing": tm}
        res[mode] = r
    print(json.dumps(res, indent=1, default=str))
    C.write_json(res, out / "snaphic_reference.json")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["prepare", "compare"])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--chrom", nargs="+", default=["chr17", "chr18", "chr19"])
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    {"prepare": stage_prepare, "compare": stage_compare}[args.stage](args)


if __name__ == "__main__":
    main()
