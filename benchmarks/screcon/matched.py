"""Matched-modality comparison: single-cell Hi-C structures vs chromatin-tracing structures of the
same cell type, compared as distributions over cells (no cell is measured by both methods).

Both sides are *structure sets* on one locus axis (``matched_data.py``: the 2,460 Takei 2021
~1 Mb loci; ``X`` (cells, H copies, L, 3)).  Every feature is computed identically on both
sides from the coordinates of the loci only.

Scale
-----
Lengths are in arbitrary model units on one side and nm on the other, and nuclear size varies
between cells, so every length is divided by the cell's own **1 Mb unit** u = median distance of
the cis locus pairs 0.75-1.25 Mb apart (all copies of the cell pooled).  It is defined on the
same locus pairs in both modalities and keeps the shape of the distance-separation curve
(a rank transform would remove the curve; dividing by the nuclear radius would tie every cis
feature to the trans geometry, the least constrained part of a scHi-C model).  Imaging
localisation error (~50-100 nm vs u ~ 500-700 nm) inflates short distances slightly; models
have none.  Distances 0.75-1.25 Mb apart are then ~1 by construction - scaling metrics use
2-50 Mb.

Units
-----
* cis features use every chromosome copy (imaging: both homologs; haploid models: one);
* nucleus features (radial position, trans proximity, intermingling) use one copy per
  chromosome: diploid sets are reduced to a **pseudo-haploid nucleus** (one accepted homolog
  per chromosome drawn at random, seeded), so haploid models meet haploid-like imaging nuclei
  (``--nucleus diploid`` keeps both copies, for diploid-vs-diploid comparisons);
* ``--mask-like-imaging`` (default on): every model / baseline cell gets the detection mask
  of a randomly drawn imaging cell, so missing loci (imaging detects ~40-60 % of loci per
  copy, and nuclei cut by the z range lose whole regions) bias both sides alike.

Features and comparison metrics (A = models, B = imaging)
---------------------------------------------------------
``pair``      per cis locus pair (fixed seeded sample of ``--n-pairs`` pairs, separation
              >= 1.5 Mb): distribution of normalised distances over copies.
              ``median_spearman`` (per-pair medians), ``median_resid_spearman`` (log median
              minus the set's own median-vs-separation trend: what is left after P(s)),
              ``w1_median`` (median over pairs of the Wasserstein-1 distance between the two
              per-pair distributions, from 19 quantiles), ``ks_median`` (median two-sample KS
              statistic over 2,000 of the pairs).
``scaling``   median normalised distance vs separation (log bins 1.5-150 Mb):
              ``alpha_a`` / ``alpha_b`` (log-log slope 2-50 Mb), ``curve_rmsd_log10``.
``variab``    per-pair cell-to-cell variability: ``cv_spearman`` (std / mean),
              ``cv_ratio`` (median CV of A / of B), ``iqr_ratio`` (median IQR / median).
``radial``    r / R per locus, R = sqrt(5/3) Rg of the nucleus' detected loci:
              ``locus_spearman`` (per-locus medians), ``chrom_spearman`` (per-chromosome
              medians), ``level_ratio`` (median r/R of A / of B).
``trans``     chromosome pairs: fraction of nuclei with min distance < ``--trans-thr`` u:
              ``spearman`` (190 pairs), ``resid_spearman`` (after removing additive
              per-chromosome effects on logit(F): what is left after chromosome size /
              radial position), ``level_ratio``.
``mingle``    intermingling: per locus, fraction of loci within ``--mingle-thr`` u that sit on
              other chromosomes, averaged (mean: mostly zeros in sparse imaging nuclei) per
              chromosome: ``chrom_spearman``, ``level_ratio``.

Reference ceiling and floors
----------------------------
* ``ceiling``: n_A imaging cells drawn at random vs the remaining imaging cells, same metrics,
  ``--n-rep`` repeats (mean, sd) - the best a perfect method can reach with n_A cells;
* ``random_polymer``: Gaussian random walks per chromosome on the loci (step variance ∝
  genomic gap), chromosome centres uniform in a sphere; knows nothing but the genome;
* ``ps_only``: fractional-Brownian chains whose exponent is the imaging scaling exponent
  (distance ∝ s^alpha), same placement - the right P(s), no locus-specific structure.
Baselines have n_A cells (H = 1) and get the imaging masks too.

    python benchmarks/screcon/matched.py compare --a nagano_nucdyn.npz --b takei_mesc.npz \\
        --label mesc/nagano/nucdyn --out rows.csv
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matched_data import load_set, subset_set  # noqa: E402

QS = np.linspace(0.05, 0.95, 19)
warnings.filterwarnings("ignore", message="All-NaN slice")
warnings.filterwarnings("ignore", message="Mean of empty slice")
warnings.filterwarnings("ignore", category=stats.ConstantInputWarning)


# --------------------------------------------------------------------------- geometry helpers

class Axis:
    """Locus axis: chromosome blocks, cis pairs, 1 Mb unit pairs."""

    def __init__(self, chrom, start, end, n_pairs=20000, seed=0, min_sep=1.5e6):
        self.chrom = np.asarray(chrom).astype(str)
        self.mid = (np.asarray(start) + np.asarray(end)) / 2
        self.L = len(self.chrom)
        self.chroms = list(dict.fromkeys(self.chrom))
        self.cidx = np.array([self.chroms.index(c) for c in self.chrom])
        ii, jj = np.triu_indices(self.L, 1)
        cis = self.chrom[ii] == self.chrom[jj]
        ii, jj = ii[cis], jj[cis]
        sep = np.abs(self.mid[jj] - self.mid[ii])
        u = (sep >= 0.75e6) & (sep <= 1.25e6)
        self.unit_pairs = (ii[u], jj[u])
        far = np.flatnonzero(sep >= min_sep)
        rng = np.random.default_rng(seed)
        pick = np.sort(rng.choice(far, size=min(n_pairs, len(far)), replace=False))
        self.pi, self.pj, self.sep = ii[pick], jj[pick], sep[pick]
        self.pchrom = self.chrom[self.pi]


def pair_dists(X, i, j):
    """X (..., L, 3) -> distances (..., P)."""
    return np.linalg.norm(X[..., i, :] - X[..., j, :], axis=-1)


def cell_units(S, ax: Axis):
    """Per cell 1 Mb unit u (median over copies of the 0.75-1.25 Mb pair distances)."""
    d = pair_dists(S, *ax.unit_pairs)                       # (n, H, U)
    d = d.reshape(len(S), -1)
    with np.errstate(all="ignore"):
        return np.nanmedian(d, axis=1)


def nuclei(S, ax: Axis, rng, mode="pseudo_haploid"):
    """-> (n, L', 3) nucleus coordinates and the locus index of each column (copy-aware)."""
    n, H, L, _ = S.shape
    if H == 1:
        return S[:, 0], np.arange(L), np.zeros(L, int)
    if mode == "diploid":
        return S.reshape(n, H * L, 3), np.tile(np.arange(L), H), np.repeat(np.arange(H), L)
    out = np.full((n, L, 3), np.nan, np.float32)
    present = np.isfinite(S[..., 0])                        # (n, H, L)
    for k, c in enumerate(ax.chroms):
        cols = np.flatnonzero(ax.cidx == k)
        has = present[:, :, cols].any(2)                     # (n, H)
        r = rng.random((n, H)) * has
        pick = np.argmax(r, axis=1)
        out[:, cols] = S[np.arange(n), pick][:, cols]
    return out, np.arange(L), np.zeros(L, int)


def detection_masks(B, ax, rng, H_out, mode="pseudo_haploid"):
    """Detection masks of imaging cells shaped like a set with ``H_out`` copies."""
    if H_out == B.shape[1]:
        return np.isfinite(B[..., 0])
    nb, _, _ = nuclei(B, ax, rng, "pseudo_haploid")      # a haploid set gets one copy per chromosome
    return np.isfinite(nb[..., 0])[:, None]


def apply_masks(S, masks, rng):
    pick = rng.integers(0, len(masks), len(S))
    out = S.copy()
    out[~masks[pick]] = np.nan
    return out


# --------------------------------------------------------------------------- features

def features(S, ax: Axis, rng, nucleus="pseudo_haploid", trans_thr=1.0, mingle_thr=1.0, ks_pairs=2000):
    """All per-set summaries used by :func:`compare` (S: (n, H, L, 3), any unit)."""
    n, H, L, _ = S.shape
    u = cell_units(S, ax)
    ok = np.isfinite(u) & (u > 0)
    S = S[ok] / u[ok, None, None, None]
    n = len(S)
    out = {"n_cells": int(n), "n_units": None}
    # ---- cis pairs over copies
    D = pair_dists(S, ax.pi, ax.pj).reshape(n * H, -1)       # (units, P)
    keep = np.isfinite(D).any(1)
    D = D[keep]
    out["n_units"] = int(len(D))
    cnt = np.isfinite(D).sum(0)
    with np.errstate(all="ignore"):
        q = np.nanquantile(D, QS, axis=0)                        # (19, P)
        med = np.nanmedian(D, 0)
        mean = np.nanmean(D, 0)
        sd = np.nanstd(D, 0)
        q25, q75 = np.nanquantile(D, [0.25, 0.75], axis=0)
    out.update(pair_n=cnt, pair_q=q, pair_med=med, pair_cv=sd / mean, pair_iqr=(q75 - q25) / med)
    sub = np.linspace(0, D.shape[1] - 1, min(ks_pairs, D.shape[1])).astype(int)
    out["ks_idx"] = sub
    out["ks_samples"] = [D[np.isfinite(D[:, p]), p] for p in sub]
    # scaling curve
    edges = np.logspace(np.log10(1.5e6), np.log10(1.5e8), 21)
    b = np.digitize(ax.sep, edges) - 1
    curve = np.full(len(edges) - 1, np.nan)
    for k in range(len(edges) - 1):
        v = D[:, b == k]
        v = v[np.isfinite(v)]
        if v.size >= 20:
            curve[k] = np.median(v)
    out["curve_x"] = np.sqrt(edges[1:] * edges[:-1])
    out["curve"] = curve
    sel = (out["curve_x"] >= 2e6) & (out["curve_x"] <= 5e7) & np.isfinite(curve)
    out["alpha"] = float(np.polyfit(np.log10(out["curve_x"][sel]), np.log10(curve[sel]), 1)[0]) if sel.sum() >= 3 else np.nan
    # P(s) trend for residuals: per-separation-bin median of per-pair log medians
    lm = np.log10(med)
    trend = np.full_like(lm, np.nan)
    for k in range(len(edges) - 1):
        m = (b == k) & np.isfinite(lm)
        if m.sum():
            trend[b == k] = np.median(lm[m])
    out["pair_resid"] = lm - trend
    # ---- nuclei
    N, li, cp = nuclei(S, ax, rng, nucleus)
    radial = np.full((n, N.shape[1]), np.nan)
    nucR = np.full(n, np.nan)
    C = len(ax.chroms)
    near = np.zeros((n, C, C), bool)
    both = np.zeros((n, C, C), bool)
    mingle = np.full((n, N.shape[1]), np.nan)
    ch = ax.cidx[li]
    for k in range(n):
        x = N[k]
        f = np.isfinite(x[:, 0])
        if f.sum() < 50:
            continue
        xf = x[f]
        c0 = xf.mean(0)
        rg = np.sqrt(((xf - c0) ** 2).sum(1).mean())
        nucR[k] = np.sqrt(5 / 3) * rg
        radial[k, f] = np.linalg.norm(xf - c0, axis=1) / nucR[k]
        dd = np.sqrt(((xf[:, None] - xf[None]) ** 2).sum(-1))
        cf = ch[f]
        idf = cf * 2 + cp[f]                                  # chromosome copy id
        # trans proximity: min distance per chromosome pair (both copies of a chromosome count as one)
        o = np.argsort(cf, kind="stable")
        cs = cf[o]
        starts = np.flatnonzero(np.r_[True, cs[1:] != cs[:-1]])
        present = cs[starts]
        m1 = np.minimum.reduceat(dd[o][:, o], starts, axis=0)
        m2 = np.minimum.reduceat(m1, starts, axis=1)
        both[k][np.ix_(present, present)] = True
        near[k][np.ix_(present, present)] = m2 < trans_thr
        within = dd < mingle_thr
        np.fill_diagonal(within, False)
        other = (within & (idf[:, None] != idf[None])).sum(1)
        tot = within.sum(1)
        v = np.where(tot > 0, other / np.maximum(tot, 1), np.nan)
        mingle[k, np.flatnonzero(f)] = v
    out["radial_locus"] = np.array([np.nanmedian(radial[:, li == i]) if np.isfinite(radial[:, li == i]).sum() >= 5
                                    else np.nan for i in range(L)])
    out["radial_chrom"] = np.array([np.nanmedian(radial[:, ch == c]) for c in range(C)])
    out["radial_level"] = float(np.nanmedian(radial))
    iu = np.triu_indices(C, 1)
    with np.errstate(all="ignore"):
        F = near.sum(0) / both.sum(0)
    out["trans_F"] = F[iu]
    out["trans_n"] = both.sum(0)[iu]
    out["mingle_chrom"] = np.array([np.nanmean(mingle[:, ch == c]) for c in range(C)])   # mean: zero-inflated
    out["mingle_level"] = float(np.nanmean(mingle))
    out["u_raw_median"] = float(np.median(u[ok]))
    out["nuc_radius_u"] = float(np.nanmedian(nucR))
    return out


def _spearman(a, b, mask=None):
    m = np.isfinite(a) & np.isfinite(b)
    if mask is not None:
        m &= mask
    if m.sum() < 5:
        return np.nan
    return float(stats.spearmanr(a[m], b[m])[0])


def _ratio(a, b) -> float:
    a, b = float(a), float(b)
    return a / b if np.isfinite(a) and np.isfinite(b) and b != 0 else float("nan")


def _additive_resid(F, C):
    """logit(F_ab) minus the least-squares fit of r_a + r_b (per-chromosome effects)."""
    iu = np.triu_indices(C, 1)
    y = np.log(np.clip(F, 1e-3, 1 - 1e-3) / (1 - np.clip(F, 1e-3, 1 - 1e-3)))
    ok = np.isfinite(F)
    A = np.zeros((len(F), C))
    A[np.arange(len(F)), iu[0]] = 1
    A[np.arange(len(F)), iu[1]] = 1
    coef = np.linalg.lstsq(A[ok], y[ok], rcond=None)[0]
    r = np.full(len(F), np.nan)
    r[ok] = y[ok] - A[ok] @ coef
    return r


def compare(fa: dict, fb: dict, ax: Axis, min_n=5) -> dict:
    """Metrics between two feature dicts (see module docstring)."""
    ok = (fa["pair_n"] >= min_n) & (fb["pair_n"] >= min_n)
    w1 = np.nanmean(np.abs(fa["pair_q"] - fb["pair_q"]), axis=0)
    ks = []
    for p, sa, sb in zip(fa["ks_idx"], fa["ks_samples"], fb["ks_samples"]):
        if len(sa) >= min_n and len(sb) >= min_n:
            ks.append(stats.ks_2samp(sa, sb).statistic)
    C = len(ax.chroms)
    sel = np.isfinite(fa["curve"]) & np.isfinite(fb["curve"])
    with np.errstate(all="ignore"):
        r = {
            ("pair", "median_spearman"): _spearman(fa["pair_med"], fb["pair_med"], ok),
            ("pair", "median_resid_spearman"): _spearman(fa["pair_resid"], fb["pair_resid"], ok),
            ("pair", "w1_median"): float(np.nanmedian(w1[ok])) if ok.any() else np.nan,
            ("pair", "ks_median"): float(np.median(ks)) if ks else np.nan,
            ("pair", "n_pairs"): int(ok.sum()),
            ("scaling", "alpha_a"): fa["alpha"],
            ("scaling", "alpha_b"): fb["alpha"],
            ("scaling", "alpha_diff"): fa["alpha"] - fb["alpha"],
            ("scaling", "curve_rmsd_log10"): float(np.sqrt(np.mean((np.log10(fa["curve"][sel]) - np.log10(fb["curve"][sel])) ** 2))) if sel.any() else np.nan,
            ("variab", "cv_spearman"): _spearman(fa["pair_cv"], fb["pair_cv"], ok),
            ("variab", "cv_ratio"): _ratio(np.nanmedian(fa["pair_cv"][ok]), np.nanmedian(fb["pair_cv"][ok])),
            ("variab", "iqr_ratio"): _ratio(np.nanmedian(fa["pair_iqr"][ok]), np.nanmedian(fb["pair_iqr"][ok])),
            ("radial", "locus_spearman"): _spearman(fa["radial_locus"], fb["radial_locus"]),
            ("radial", "chrom_spearman"): _spearman(fa["radial_chrom"], fb["radial_chrom"]),
            ("radial", "level_ratio"): _ratio(fa["radial_level"], fb["radial_level"]),
            ("trans", "spearman"): _spearman(fa["trans_F"], fb["trans_F"]),
            ("trans", "resid_spearman"): _spearman(_additive_resid(fa["trans_F"], C), _additive_resid(fb["trans_F"], C)),
            ("trans", "level_ratio"): _ratio(np.nanmean(fa["trans_F"]), np.nanmean(fb["trans_F"])),
            ("mingle", "chrom_spearman"): _spearman(fa["mingle_chrom"], fb["mingle_chrom"]),
            ("mingle", "level_ratio"): _ratio(fa["mingle_level"], fb["mingle_level"]),
        }
    return r


# --------------------------------------------------------------------------- baselines

def _place(n, ax: Axis, chains, rng, radius):
    X = np.full((n, 1, ax.L, 3), np.nan, np.float32)
    for k in range(n):
        for c, ch in enumerate(ax.chroms):
            cols = np.flatnonzero(ax.cidx == c)
            v = rng.normal(size=3)
            ctr = v / np.linalg.norm(v) * radius * rng.random() ** (1 / 3)
            y = chains(cols, rng)
            X[k, 0, cols] = y - y.mean(0) + ctr
    return X


def random_polymer(n, ax: Axis, rng, radius=6.0):
    """Gaussian random walks on the loci (step variance ∝ genomic gap in Mb), centres uniform in a sphere."""
    def chain(cols, rng):
        g = np.diff(ax.mid[cols], prepend=ax.mid[cols][0]) / 1e6
        return np.cumsum(rng.normal(size=(len(cols), 3)) * np.sqrt(np.maximum(g, 0))[:, None] / np.sqrt(3), 0)
    return _place(n, ax, chain, rng, radius)


def ps_only(n, ax: Axis, rng, alpha, radius=6.0):
    """Fractional-Brownian chains, <|x_i - x_j|^2> ∝ |s_i - s_j|^(2 alpha) (s in Mb), alpha <= 1."""
    a = float(np.clip(alpha, 0.05, 0.95))
    chol = {}

    def chain(cols, rng):
        key = cols[0]
        if key not in chol:
            s = (ax.mid[cols] - ax.mid[cols][0]) / 1e6 + 1.0
            K = 0.5 * (s[:, None] ** (2 * a) + s[None] ** (2 * a) - np.abs(s[:, None] - s[None]) ** (2 * a))
            chol[key] = np.linalg.cholesky(K + 1e-9 * np.eye(len(s)))
        return chol[key] @ rng.normal(size=(len(cols), 3)) / np.sqrt(3)
    return _place(n, ax, chain, rng, radius)


# --------------------------------------------------------------------------- driver

def run(A: dict, B: dict, *, label="", n_rep=5, seed=0, n_pairs=20000, mask=True, nucleus="pseudo_haploid",
        trans_thr=1.0, mingle_thr=1.0, baselines=True) -> pd.DataFrame:
    if not (np.array_equal(A["chrom"], B["chrom"]) and np.array_equal(A["start"], B["start"])):
        raise ValueError("structure sets are on different locus axes")
    ax = Axis(B["chrom"], B["start"], B["end"], n_pairs=n_pairs, seed=seed)
    kw = dict(nucleus=nucleus, trans_thr=trans_thr, mingle_thr=mingle_thr)
    rows = []
    XA, XB = A["X"], B["X"]
    nA = len(XA)

    def emit(kind, rep, m, fa, fb):
        for (feat, met), v in m.items():
            rows.append({"comparison": label, "kind": kind, "rep": rep, "feature": feat, "metric": met,
                         "value": v, "n_a": fa["n_cells"], "n_b": fb["n_cells"], "units_a": fa["n_units"],
                         "units_b": fb["n_units"]})

    rng = np.random.default_rng(seed)
    fB = features(XB, ax, np.random.default_rng(seed + 1), **kw)
    XAm = apply_masks(XA, detection_masks(XB, ax, rng, XA.shape[1], nucleus), rng) if mask else XA
    fA = features(XAm, ax, np.random.default_rng(seed + 2), **kw)
    emit("model", 0, compare(fA, fB, ax), fA, fB)
    for r in range(n_rep):
        rr = np.random.default_rng(seed + 100 + r)
        perm = rr.permutation(len(XB))
        k = min(nA, len(XB) // 2)
        f1 = features(XB[perm[:k]], ax, rr, **kw)
        f2 = features(XB[perm[k:]], ax, rr, **kw)
        emit("ceiling", r, compare(f1, f2, ax), f1, f2)
        if baselines:
            rad = 0.75 * fB["nuc_radius_u"]          # centres inside the imaging nucleus (radius in 1 Mb units)
            for name, gen in (("random_polymer", lambda: random_polymer(nA, ax, rr, rad)),
                              ("ps_only", lambda: ps_only(nA, ax, rr, fB["alpha"], rad))):
                Z = gen()
                if mask:
                    Z = apply_masks(Z, detection_masks(XB, ax, rr, 1, nucleus), rr)
                fz = features(Z, ax, rr, **kw)
                emit(name, r, compare(fz, fB, ax), fz, fB)
    return pd.DataFrame(rows)


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["comparison", "feature", "metric", "kind"]).value
    s = g.agg(["mean", "std"]).reset_index()
    w = s.pivot_table(index=["comparison", "feature", "metric"], columns="kind", values=["mean", "std"])
    w.columns = [f"{k}" if a == "mean" else f"{k}_sd" for a, k in w.columns]
    keep = [c for c in ("model", "ceiling", "ceiling_sd", "random_polymer", "ps_only") if c in w.columns]
    return w[keep].reset_index()


KEY_METRICS = [("pair", "median_resid_spearman"), ("pair", "ks_median"), ("scaling", "alpha_diff"),
               ("variab", "cv_spearman"), ("variab", "cv_ratio"), ("radial", "locus_spearman"),
               ("radial", "chrom_spearman"), ("trans", "spearman"), ("mingle", "chrom_spearman"),
               ("mingle", "level_ratio")]


def markdown_table(summ: pd.DataFrame, metrics=KEY_METRICS) -> str:
    """One row per comparison: ``model [ceiling ± sd; best structure-free baseline]`` per key metric
    (best baseline = the one closer to the ceiling)."""
    cols = [f"{f}.{m}" for f, m in metrics]
    lines = ["| comparison | n_a | " + " | ".join(cols) + " |", "| --- | --- |" + " --- |" * len(cols)]
    for comp, g in summ.groupby("comparison", sort=False):
        cells = []
        for f, m in metrics:
            r = g[(g.feature == f) & (g.metric == m)]
            if r.empty:
                cells.append("")
                continue
            r = r.iloc[0]
            base = [r.get(k) for k in ("random_polymer", "ps_only") if pd.notna(r.get(k))]
            best = min(base, key=lambda v: abs(v - r["ceiling"])) if base else float("nan")
            cells.append(f"{r['model']:.2f} [{r['ceiling']:.2f}±{r.get('ceiling_sd', float('nan')):.2f}; {best:.2f}]")
        n = summ.attrs.get("n_a", {}).get(comp, "")
        n = int(n) if n != "" else ""
        lines.append(f"| {comp} | {n} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _parse_where(items):
    out = {}
    for it in items or []:
        k, v = it.split("=", 1)
        out[k] = v.split(",")
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("compare")
    p.add_argument("--a", required=True); p.add_argument("--b", required=True)
    p.add_argument("--a-where", nargs="*"); p.add_argument("--b-where", nargs="*")
    p.add_argument("--label", required=True)
    p.add_argument("--n-rep", type=int, default=5); p.add_argument("--seed", type=int, default=0)
    p.add_argument("--n-pairs", type=int, default=20000)
    p.add_argument("--no-mask", action="store_true")
    p.add_argument("--nucleus", default="pseudo_haploid", choices=["pseudo_haploid", "diploid"])
    p.add_argument("--trans-thr", type=float, default=1.0); p.add_argument("--mingle-thr", type=float, default=1.0)
    p.add_argument("--no-baselines", action="store_true")
    p.add_argument("--out", required=True)
    s = sub.add_parser("summary")
    s.add_argument("--rows", nargs="+", required=True); s.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "compare":
        A = subset_set(load_set(args.a), _parse_where(args.a_where))
        B = subset_set(load_set(args.b), _parse_where(args.b_where))
        df = run(A, B, label=args.label, n_rep=args.n_rep, seed=args.seed, n_pairs=args.n_pairs,
                 mask=not args.no_mask, nucleus=args.nucleus, trans_thr=args.trans_thr,
                 mingle_thr=args.mingle_thr, baselines=not args.no_baselines)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.out, index=False)
        print(summarise(df).to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    else:
        df = pd.concat([pd.read_csv(r) for r in args.rows], ignore_index=True)
        summ = summarise(df)
        summ.attrs["n_a"] = df[df.kind == "model"].groupby("comparison").n_a.first().to_dict()
        summ.to_csv(args.out, index=False)
        print(summ.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        md = markdown_table(summ)
        Path(args.out).with_suffix(".md").write_text(md + "\n")
        print(md)


if __name__ == "__main__":
    main()
