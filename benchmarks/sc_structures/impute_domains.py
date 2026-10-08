"""Single-cell domain boundaries of the mES cells (imputed maps, insulation) against the bulk mESC map.

    python benchmarks/sc_structures/impute_domains.py --out DIR --mesc DIR [--n 742 100 ...]

Cells: the 742 deepest Nagano 2017 diploid serum cells (``snaphic_data.py``); subsets as in ``snaphic_mesc.py``
(first N of a seeded permutation).  ``uchrom.strc.tad.single_cell_boundaries`` (RWR as SnapHiC, window
``auto``; insulation diamond 100 kb at 10 kb; Li's threshold per cell) on chr1-19, against the insulation of the
Bonev et al. 2017 bulk map with the same diamond (``snaphic_mesc.py bonev`` -> ``bonev_insulation_10kb.tsv`` in
``--mesc``):

* consensus single-cell boundaries within 2 bins of a bulk boundary (precision), bulk boundaries with a
  consensus boundary within 2 bins (recall), the chance of the former (every scored bin) — for the default
  consensus (minima of the cells' mean insulation) and for the peaks of the boundary frequency (Li's threshold
  of their prominences, computed here from the same table);
* the boundary frequency at bulk boundaries (+-1 bin) and elsewhere;
* Spearman of the mean single-cell log2 insulation with the bulk log2 insulation, per bin.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snaphic_common as C  # noqa: E402
from snaphic_mesc import load_cells, subset  # noqa: E402


def near(mask: np.ndarray, idx: np.ndarray, k: int) -> np.ndarray:
    out = np.zeros(len(mask), bool)
    for d in range(-k, k + 1):
        j = idx + d
        j = j[(j >= 0) & (j < len(mask))]
        out[j] = True
    return out


def cpu_name() -> str:
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def main() -> None:
    from scipy.stats import spearmanr

    from uchrom.strc.tad.single_cell import SingleCellBoundaryParams, single_cell_boundaries

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--mesc", type=Path, required=True)
    ap.add_argument("--n", type=int, nargs="+", default=[742, 200, 50])
    ap.add_argument("--chrom", nargs="*", default=C.MM10_AUTOSOMES)
    ap.add_argument("--threads", type=int, default=0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    bulk = pd.read_csv(args.mesc / "bonev_insulation_10kb.tsv", sep="\t")
    bulk = bulk[bulk["chrom"].isin(args.chrom)].reset_index(drop=True)
    cd, top = load_cells()
    rows = []
    for n in args.n:
        cells = subset(top, n, 0)
        tm = {}
        t0 = time.time()
        sc = single_cell_boundaries(cd, cells=cells, chrom=args.chrom,
                                    params=SingleCellBoundaryParams(insulation_window=100_000), key_added=None,
                                    n_threads=args.threads, timing=tm)
        dt = time.time() - t0
        sc.to_csv(args.out / f"single_cell_boundaries_N{len(cells)}.tsv", sep="\t", index=False)
        m = sc.merge(bulk[["chrom", "start", "log2_insulation_score_100000", "is_boundary_100000"]],
                     on=["chrom", "start"], how="inner")
        r = {"n_cells": len(cells), "seconds": dt, "timing": tm, "peak_rss_gb": C.peak_rss_gb(), "cpu": cpu_name()}
        from scipy.signal import find_peaks

        from uchrom.strc.tad.insulation import threshold_li

        prom = np.full(len(m), np.nan)
        for _, idx in m.groupby("chrom", sort=False).indices.items():
            pk, pr = find_peaks(np.nan_to_num(m["frequency"].to_numpy()[idx]), prominence=0)
            prom[idx[pk]] = pr["prominences"]
        with np.errstate(invalid="ignore"):
            freq_cons = prom >= threshold_li(prom)
        for label, cons_all in (("", m["consensus"].to_numpy(bool)), ("freqpeaks_", freq_cons)):
            prec, rec, chance = [], [], []
            for _, idx in m.groupby("chrom", sort=False).indices.items():
                g = m.iloc[idx].reset_index(drop=True)
                bb = np.flatnonzero(g["is_boundary_100000"].to_numpy(bool))
                cons = np.flatnonzero(cons_all[idx])
                scored = (g["n_cells"] > 0).to_numpy() & np.isfinite(g["log2_insulation_score_100000"].to_numpy())
                nb2 = near(np.zeros(len(g), bool), bb, 2)
                prec += list(nb2[cons])
                rec += list(near(np.zeros(len(g), bool), cons, 2)[bb])
                chance += list(nb2[scored])
            r.update({f"{label}n_consensus": int(cons_all.sum()), f"{label}precision_2bins": float(np.mean(prec)),
                      f"{label}recall_2bins": float(np.mean(rec))})
            r["chance_2bins"] = float(np.mean(chance))
        fb, fo = [], []
        for _, idx in m.groupby("chrom", sort=False).indices.items():
            g = m.iloc[idx].reset_index(drop=True)
            bb = np.flatnonzero(g["is_boundary_100000"].to_numpy(bool))
            scored = (g["n_cells"] > 0).to_numpy()
            nb1 = near(np.zeros(len(g), bool), bb, 1)
            f = g["frequency"].to_numpy()
            fb += list(f[nb1 & scored])
            fo += list(f[~nb1 & scored])
        ok = np.isfinite(m["insulation"]) & np.isfinite(m["log2_insulation_score_100000"])
        rho = spearmanr(m.loc[ok, "insulation"], m.loc[ok, "log2_insulation_score_100000"])[0]
        r.update({"n_bulk_boundaries": int(m["is_boundary_100000"].sum()),
                  "frequency_at_bulk_boundaries": float(np.nanmean(fb)), "frequency_elsewhere": float(np.nanmean(fo)),
                  "spearman_insulation": float(rho)})
        print({k: v for k, v in r.items() if k != "timing"}, flush=True)
        rows.append(r)
    C.write_json({"rows": rows, "load": C.load_avg()}, args.out / "impute_domains.json")


if __name__ == "__main__":
    main()
