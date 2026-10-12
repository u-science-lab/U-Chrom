"""Single cells across assays: does a locus signature learned in one kind of data tell excitatory neurons (ExN) from
mature oligodendrocytes (Oligo) in single cells of another?

Every cell -- imaged (Liu 2025 DNA-MERFISH) or reconstructed (EMber, ``recon.py``) -- is put on the Liu 2025 locus
panel (a reconstruction's 1-Mb particle covering each locus's midpoint; pairs of loci in one particle dropped).  A
**signature** is the ExN - Oligo difference of the median distance of every cis pair of panel loci, detrended by
separation (``recon.py`` stage loci, column ``resid``).  A cell's **score** is the Pearson correlation, over the pairs
it has, between its own log distances -- less its median at each separation band, so the overall decay is removed --
and the signature: high when its pairs are far where neurons' are.  AUROC of ExN against Oligo (bootstrap CI over
cells), against the scalar of ``separation_profile`` (``log2_short_long``) as the baseline.

Directions: imaging signature -> each reconstruction's cells; each reconstruction's signature (and their mean) ->
imaging cells; within a dataset, 2-fold (signature from half of the cells, scored on the other half).

    python benchmarks/cross_assay/transfer.py --liu STORE --recon-root $SCRATCH/uchrom-nd/runs/xassay \
        --xa-work $SCRATCH/uchrom-nd/runs/xassay/full/work --out DIR
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "screcon"))

AUTOS = [f"chr{k}" for k in range(1, 20)]
SEP_BANDS = np.geomspace(1e6, 2e8, 25)
#: (dataset folder under --recon-root, variant, label); the first variant of each folder is its reference
RECON = [("recon_tan", "dip", "Dip-C (Tan), diploid"), ("recon_tan", "hap", "Dip-C (Tan), haploid"),
         ("recon_tan", "hap_c150k", "Dip-C (Tan), haploid 150k"), ("recon_tan", "hap_c45k", "Dip-C (Tan), haploid 45k"),
         ("recon_tan", "hap_c20k", "Dip-C (Tan), haploid 20k"), ("recon_tan", "dipc", "Dip-C (Tan), published"),
         ("recon_hires_brain", "dip", "HiRES, diploid"), ("recon_hires_brain", "dipc", "HiRES, published"),
         ("recon_gageseq_mouse_cortex", "hap", "GAGE-seq, haploid"),
         ("recon_dschic_aging_cortex", "hap", "dscHi-C, haploid"),
         ("recon_droplet_hic_mouse_cortex", "hap", "Droplet Hi-C, haploid"),
         ("recon_schicar_mouse_cortex", "hap", "scHiCAR, haploid")]


class Panel:
    """The locus panel (Liu 2025 bins on the autosomes): pair ids ``offset[chrom] + i * n + j`` of local indices."""

    def __init__(self, bins: pd.DataFrame):
        b = bins[bins["chrom"].astype(str).isin(AUTOS)].copy()
        b["chrom"] = b["chrom"].astype(str)
        b = b.sort_values(["chrom", "start"], key=lambda s: s.map(AUTOS.index) if s.name == "chrom" else s)
        self.bins = b
        self.mid = ((b["start"].to_numpy() + b["end"].to_numpy()) // 2).astype(np.int64)
        self.chrom_code = b["chrom"].map(AUTOS.index).to_numpy()
        self.local = b.groupby("chrom", sort=False).cumcount().to_numpy()
        n = b.groupby("chrom", sort=False).size().reindex(AUTOS).fillna(0).astype(int).to_numpy()
        self.n = n
        self.offset = np.r_[0, np.cumsum(n * n)[:-1]]
        self.n_pairs = int((n * n).sum())
        self.row = pd.Series(np.arange(len(b)), index=b.index)        # panel bin id -> panel row

    def pair_id(self, ra: np.ndarray, rb: np.ndarray) -> np.ndarray:
        c = self.chrom_code[ra]
        return self.offset[c] + self.local[ra] * self.n[c] + self.local[rb]

    def signature(self, table: pd.DataFrame, col: str = "resid") -> np.ndarray:
        """A loci table of recon.py (index chrom, i, j = panel bin ids) -> dense vector over pair ids (both orders)."""
        t = table.reset_index()
        ok = t["i"].isin(self.row.index) & t["j"].isin(self.row.index)
        t = t[ok]
        ra, rb = self.row.reindex(t["i"]).to_numpy(), self.row.reindex(t["j"]).to_numpy()
        w = np.full(self.n_pairs, np.nan)
        v = t[col].to_numpy(np.float64)
        w[self.pair_id(ra, rb)] = v
        w[self.pair_id(rb, ra)] = v
        return w


def panel_cells_from_recon(cd, panel: Panel):
    """A reconstruction (1-Mb particles, (k - 1, k] Mb) on the panel: per spot of the panel, the particle covering its
    midpoint -> (cell, trace, panel row, source particle, xyz) arrays."""
    sp = cd.spots_with_loci()
    s = pd.DataFrame({"chrom": sp["chrom"].astype(str).to_numpy(), "end": sp["end"].to_numpy(np.int64),
                      "trace": sp["trace_id"].astype(str).to_numpy(), "cell": sp["cell_id"].astype(str).to_numpy(),
                      "src": np.arange(len(sp))})
    pend = (-(-panel.mid // 1_000_000)) * 1_000_000                # end of the particle holding the midpoint
    loci = pd.DataFrame({"chrom": panel.bins["chrom"].to_numpy(), "end": pend, "prow": np.arange(len(panel.mid))})
    m = s.merge(loci, on=["chrom", "end"], how="inner")
    xyz = np.asarray(cd.coords, np.float64)[m["src"].to_numpy()]
    return m["cell"].to_numpy(), m["trace"].to_numpy(), m["prow"].to_numpy(), m["src"].to_numpy(), xyz


def panel_cells_from_imaging(cd, panel: Panel):
    sp = cd.spots_with_loci()
    keep = sp["bin_id"].isin(panel.row.index).to_numpy() if "bin_id" in sp else None
    if keep is None:
        raise KeyError("spots without bin_id")
    sp = sp[keep]
    xyz = np.asarray(cd.coords, np.float64)[keep]
    ok = np.isfinite(xyz).all(1)
    prow = panel.row.reindex(sp["bin_id"].to_numpy()).to_numpy()
    src = np.arange(len(sp))
    return (sp["cell_id"].astype(str).to_numpy()[ok], sp["trace_id"].astype(str).to_numpy()[ok], prow[ok], src[ok],
            xyz[ok])


def score_cells(cells, traces, prow, src, xyz, panel: Panel, sigs: dict, max_pairs: int = 20_000_000) -> pd.DataFrame:
    """Per cell and signature: Pearson r between the cell's band-detrended log distances and the signature."""
    order = np.lexsort((prow, traces, cells))
    cells, traces, prow, src, xyz = cells[order], traces[order], prow[order], src[order], xyz[order]
    ucell, cstart = np.unique(cells, return_index=True)
    cend = np.r_[cstart[1:], len(cells)]
    out = {k: np.full(len(ucell), np.nan) for k in sigs}
    npairs = np.zeros(len(ucell), np.int64)
    # blocks of whole cells
    k0 = 0
    while k0 < len(ucell):
        k1, est = k0, 0
        while k1 < len(ucell) and (k1 == k0 or est < max_pairs):
            m = cend[k1] - cstart[k1]
            est += m * m // 2
            k1 += 1
        lo, hi = cstart[k0], cend[k1 - 1]
        tr, pr, sr, X = traces[lo:hi], prow[lo:hi], src[lo:hi], xyz[lo:hi]
        cc = np.repeat(np.arange(k0, k1), cend[k0:k1] - cstart[k0:k1])
        run = np.r_[True, (tr[1:] != tr[:-1]) | (cc[1:] != cc[:-1]) | (panel.chrom_code[pr[1:]] != panel.chrom_code[pr[:-1]])]
        rid = np.cumsum(run) - 1
        starts = np.flatnonzero(run)
        lens = np.diff(np.r_[starts, len(tr)])
        A, B = [], []
        for s0, L in zip(starts, lens):
            if L < 2:
                continue
            i, j = np.triu_indices(L, 1)
            A.append(s0 + i); B.append(s0 + j)
        if A:
            a, b = np.concatenate(A), np.concatenate(B)
            keep = (sr[a] != sr[b]) & (pr[a] != pr[b])
            a, b = a[keep], b[keep]
            d = np.linalg.norm(X[a] - X[b], axis=1)
            ok = d > 0
            a, b, d = a[ok], b[ok], d[ok]
            ra, rb = np.minimum(pr[a], pr[b]), np.maximum(pr[a], pr[b])
            pid = panel.pair_id(ra, rb)
            sep = np.abs(panel.mid[rb] - panel.mid[ra])
            band = np.searchsorted(SEP_BANDS, sep)
            cell = cc[a]
            y = np.log(d)
            key = (cell - k0) * (len(SEP_BANDS) + 1) + band
            med = pd.Series(y).groupby(key).transform("median").to_numpy()
            r = y - med
            npairs[k0:k1] += np.bincount(cell - k0, minlength=k1 - k0)
            for name, w in sigs.items():
                x = w[pid]
                f = np.isfinite(x)
                c, rr, xx = cell[f] - k0, r[f], x[f]
                n = np.bincount(c, minlength=k1 - k0).astype(float)
                sx, sy = np.bincount(c, xx, k1 - k0), np.bincount(c, rr, k1 - k0)
                sxx, syy, sxy = np.bincount(c, xx * xx, k1 - k0), np.bincount(c, rr * rr, k1 - k0), np.bincount(c, xx * rr, k1 - k0)
                with np.errstate(invalid="ignore", divide="ignore"):
                    cov = sxy - sx * sy / n
                    out[name][k0:k1] = cov / np.sqrt((sxx - sx * sx / n) * (syy - sy * sy / n))
        k0 = k1
    t = pd.DataFrame(out, index=pd.Index(ucell, name="cell_id"))
    t["n_pairs"] = npairs
    return t


def auroc(score: pd.Series, cls: pd.Series, rng, a="ExN", b="Oligo", n_boot: int = 500) -> dict:
    x = score[cls == a].dropna().to_numpy()
    y = score[cls == b].dropna().to_numpy()
    if len(x) < 3 or len(y) < 3:
        return {"n_a": len(x), "n_b": len(y)}
    from scipy.stats import mannwhitneyu

    f = lambda u, v: float(mannwhitneyu(u, v).statistic / (len(u) * len(v)))  # noqa: E731
    bs = [f(rng.choice(x, len(x)), rng.choice(y, len(y))) for _ in range(n_boot)]
    return {"auroc": f(x, y), "ci95": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))],
            "n_a": int(len(x)), "n_b": int(len(y))}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--liu", type=Path, required=True)
    ap.add_argument("--recon-root", type=Path, required=True)
    ap.add_argument("--xa-work", type=Path, required=True, help="cross_assay.py work folder (imaging per-cell tables)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--results", type=Path, default=HERE / "results")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--limit-cells", type=int, help="smoke test: at most N cells per class and dataset")
    a = ap.parse_args()
    import cross_assay as X
    import recon as R
    from _record import save
    from chromdata import ChromData

    rng = np.random.default_rng(a.seed)
    a.out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    liu = ChromData.read(str(a.liu), columns="coords")
    panel = Panel(liu.bins)
    lc = liu.cells.copy()
    lc.index = lc.index.astype(str)
    lcls = X.liu_classes(lc)
    img_sig = panel.signature(pd.read_parquet(a.recon_root / "recon_tan" / "loci_liu2025_imaging.parquet"))
    log = {"panel_loci": int(len(panel.bins)), "panel_pairs": int(np.isfinite(img_sig).sum() // 2)}

    def limited(ids, cls):
        if not a.limit_cells:
            return ids
        keep = []
        for c in ("ExN", "Oligo"):
            m = [i for i in ids if cls.get(i) == c]
            keep += m[: a.limit_cells]
        return keep

    # --- the recon signatures and the per-dataset 2-fold signatures
    recon_sigs, results, per_cell = {}, {"recon_cells": {}, "imaging_cells": {}, "within": {}}, []
    for folder, v, label in RECON:
        p = a.recon_root / folder / f"loci_liu2025_{v}.parquet"
        if p.exists():
            recon_sigs[label] = panel.signature(pd.read_parquet(p))
    if recon_sigs:
        Z = np.vstack([(w - np.nanmean(w)) / np.nanstd(w) for k, w in recon_sigs.items()
                       if not k.endswith(("150k", "45k", "20k", "published", "Tan), haploid"))])
        with np.errstate(invalid="ignore"):
            recon_sigs["all reconstructions (mean)"] = np.nanmean(Z, axis=0)

    # --- imaging cells: scored by every reconstruction signature; imaging 2-fold as the within-imaging reference
    ids = [i for i in lcls.index[lcls.isin(["ExN", "Oligo"])]]
    ids = limited(ids, lcls)
    sub = liu.get_cells(ids, columns="coords")
    c, tr, pr, sr, xyz = panel_cells_from_imaging(sub, panel)
    hs = {k: R._halves([i for i in ids if lcls[i] == k], rng) for k in ("ExN", "Oligo")}
    half_of = {i: h for k in hs for h in (0, 1) for i in hs[k][h]}
    half_sigs = {h: panel.signature(R._panel_values(R._class_maps(sub, {k: list(hs[k][h]) for k in hs}, AUTOS),
                                                    panel.bins, "ExN", "Oligo")) for h in (0, 1)}
    sigs = {**recon_sigs, "imaging (other half)": None}
    S = score_cells(c, tr, pr, sr, xyz, panel, {**recon_sigs, "_h0": half_sigs[0], "_h1": half_sigs[1]})
    S["imaging (other half)"] = np.where(pd.Series(half_of).reindex(S.index).to_numpy() == 0, S["_h1"], S["_h0"])
    S["cls"] = lcls.reindex(S.index).to_numpy()
    sc = a.xa_work / "imaging_liu2025_mop.parquet"
    if sc.exists():
        S["scalar"] = pd.read_parquet(sc)["log2_short_long"].reindex(S.index).to_numpy()
    for k in [*sigs, "scalar"]:
        if k in S:
            results["imaging_cells"][k] = auroc(S[k], S["cls"], rng)
    S.drop(columns=["_h0", "_h1"]).assign(dataset="liu2025").to_parquet(a.out / "scores_liu2025.parquet")
    print(f"[imaging cells] {json.dumps({k: round(v.get('auroc', float('nan')), 3) for k, v in results['imaging_cells'].items()})}", flush=True)

    # --- reconstruction cells: scored by the imaging signature, the other reconstructions' mean, own 2-fold
    for folder, v, label in RECON:
        p = a.recon_root / folder / f"{v}.chromdata.zarr"
        if not p.exists():
            continue
        cd = ChromData.read(p)
        cls = cd.cells["cls"].copy()
        cls.index = cls.index.astype(str)
        ids = limited([i for i in cls.index[cls.isin(["ExN", "Oligo"])]], cls)
        sub = cd.get_cells(ids, columns="coords")
        c, tr, pr, sr, xyz = panel_cells_from_recon(sub, panel)
        hs = {k: R._halves([i for i in ids if cls[i] == k], rng) for k in ("ExN", "Oligo")}
        half_of = {i: h for k in hs for h in (0, 1) for i in hs[k][h]}
        hsig = {}
        for h in (0, 1):
            cells_h = {k: list(hs[k][h]) for k in hs}
            hsig[h] = panel.signature(R._panel_values(R._class_maps(sub, cells_h, AUTOS), panel.bins, "ExN", "Oligo"))
        others = [w for k, w in recon_sigs.items() if not k.startswith(label.split(",")[0]) and k != "all reconstructions (mean)"
                  and not k.endswith(("150k", "45k", "20k"))]
        osig = np.nanmean(np.vstack([(w - np.nanmean(w)) / np.nanstd(w) for w in others]), axis=0) if others else None
        sg = {"imaging": img_sig, "_h0": hsig[0], "_h1": hsig[1]}
        if osig is not None:
            sg["other datasets' reconstructions"] = osig
        T = score_cells(c, tr, pr, sr, xyz, panel, sg)
        T["own data (other half)"] = np.where(pd.Series(half_of).reindex(T.index).to_numpy() == 0, T["_h1"], T["_h0"])
        T["cls"] = cls.reindex(T.index).to_numpy()
        cp = a.recon_root / folder / f"cells_{v}.parquet"
        if cp.exists():
            T["scalar"] = pd.read_parquet(cp)["log2_short_long"].reindex(T.index).to_numpy()
        r = {k: auroc(T[k], T["cls"], rng) for k in ("imaging", "other datasets' reconstructions", "own data (other half)",
                                                      "scalar") if k in T}
        r["median_pairs_per_cell"] = float(T["n_pairs"].median())
        results["recon_cells"][label] = r
        T.drop(columns=["_h0", "_h1"]).assign(dataset=label).to_parquet(a.out / f"scores_{folder}_{v}.parquet")
        print(f"[recon cells] {label}: " + json.dumps({k: round(x.get("auroc", float("nan")), 3) for k, x in r.items()
                                                       if isinstance(x, dict)}), flush=True)
    log["seconds"] = round(time.perf_counter() - t0, 1)
    results["log"] = log
    path = save(a.results / "transfer.json", results, script="benchmarks/cross_assay/transfer.py",
                datasets=["liu2025_mop", "tan2021_cortex", "hires2023_brain", "gageseq_mouse_cortex",
                          "dschic_aging_cortex", "droplet_hic_mouse_cortex", "schicar_mouse_cortex"],
                params={"seed": a.seed, "signature": "recon.py loci resid (ExN - Oligo, detrended by separation)",
                        "score": "Pearson r of the cell's band-detrended log distances with the signature",
                        "limit_cells": a.limit_cells})
    print(f"results: {path}", flush=True)


if __name__ == "__main__":
    main()
