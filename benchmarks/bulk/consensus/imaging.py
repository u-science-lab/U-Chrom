"""Imaging reference of the consensus benchmark: per locus pair the MEDIAN (and mean, count)
of the imaged 3-D distances over cells.

* cis pairs: distances within one chromosome copy (homolog) — pooled over cells and copies;
* trans pairs (different chromosomes): all copy combinations pooled (a haploid consensus model
  has one copy per chromosome, so it is compared with the distance distribution of any
  copy pair — IGM's pooling of inter-chromosomal copy combinations);
* single-copy datasets (Su chr21 traces) have cis pairs only.

Loaders: ``benchmarks/bulk/truths.py`` (Su 2020 genome-scale: homologs resolved by the
experiment; Su 2020 chr21: one trace per copy; Takei 2021 1 Mb: homologs split by the
screcon heuristic, flagged).  Also writes the "mean-distance embedding": classical MDS +
SMACOF of the median-distance matrix (the scale-free RMSD reference of ``score.py``).

    python benchmarks/bulk/consensus/imaging.py --dataset su2020_genome --out IMG/su2020_genome.npz
"""

from __future__ import annotations

import argparse
import time

import numpy as np

import _bc  # noqa: F401  (paths)
from _bc import jdump
from truths import load_dataset


def pair_medians(X: np.ndarray, chrom: np.ndarray, block: int = 16):
    """X (S, P, L, 3) -> median, mean, count (L, L) float32; cis within copies, trans all combos."""
    S, P, L, _ = X.shape
    med = np.full((L, L), np.nan, np.float32)
    mean = np.full((L, L), np.nan, np.float32)
    cnt = np.zeros((L, L), np.int32)
    Xt = np.ascontiguousarray(np.transpose(X, (2, 0, 1, 3)))      # (L, S, P, 3)
    same_chrom = chrom[:, None] == chrom[None]
    for a in range(0, L, block):
        b = min(a + block, L)
        xa = Xt[a:b]                                              # (B, S, P, 3)
        # same copy: (B, L, S, P)
        d_same = np.linalg.norm(xa[:, None] - Xt[None], axis=-1)
        if P > 1:
            # other copies: (B, L, S, P, P) -> the P*(P-1) cross combinations
            d_all = np.linalg.norm(xa[:, None, :, :, None, :] - Xt[None, :, :, None, :, :], axis=-1)
            d_all = d_all.reshape(b - a, L, S, P * P)
        for k in range(b - a):
            i = a + k
            cis = same_chrom[i]
            samp = np.full((L, S * P * P), np.nan, np.float32)
            samp[cis, : S * P] = d_same[k][cis].reshape(int(cis.sum()), S * P)
            if P > 1:
                samp[~cis] = d_all[k][~cis].reshape(int((~cis).sum()), S * P * P)
            c = np.isfinite(samp).sum(1)
            cnt[i] = c
            with np.errstate(all="ignore"):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    med[i] = np.nanmedian(samp, axis=1)
                    mean[i] = np.nanmean(samp, axis=1)
    np.fill_diagonal(med, 0)
    np.fill_diagonal(mean, 0)
    return med, mean, cnt


def classical_mds(D: np.ndarray, dim: int = 3) -> np.ndarray:
    n = len(D)
    J = np.eye(n) - 1.0 / n
    B = -0.5 * J @ (D ** 2) @ J
    w, v = np.linalg.eigh(B)
    k = np.argsort(w)[::-1][:dim]
    return v[:, k] * np.sqrt(np.maximum(w[k], 1e-12))


def smacof(D: np.ndarray, X0: np.ndarray, n_iter: int = 300, W=None) -> np.ndarray:
    """Weighted SMACOF (Guttman transform); W = 0 for missing pairs."""
    n = len(D)
    W = np.ones_like(D) if W is None else W
    np.fill_diagonal(W, 0)
    V = -W.copy()
    np.fill_diagonal(V, W.sum(1))
    Vp = np.linalg.pinv(V)
    X = X0.copy()
    for _ in range(n_iter):
        E = np.linalg.norm(X[:, None] - X[None], axis=2)
        with np.errstate(divide="ignore", invalid="ignore"):
            Bm = -np.where(E > 0, W * D / E, 0.0)
        np.fill_diagonal(Bm, 0)
        np.fill_diagonal(Bm, -Bm.sum(1))
        X = Vp @ Bm @ X
    return X


def embed(D: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Mean-distance embedding of a (possibly incomplete) distance matrix: rows with too many
    NaN dropped, remaining NaN filled from the chromosome-free median for classical MDS, then
    weighted SMACOF on the observed pairs.  Returns (coords (L, 3) NaN for dropped rows,
    kept mask, info)."""
    ok = np.isfinite(D).mean(1) >= 0.5
    Dk = D[np.ix_(ok, ok)].astype(float)
    W = np.isfinite(Dk).astype(float)
    Df = np.where(np.isfinite(Dk), Dk, np.nanmedian(Dk))
    X0 = classical_mds(Df)
    X = smacof(Df, X0, W=W)
    E = np.linalg.norm(X[:, None] - X[None], axis=2)
    iu = np.triu_indices(len(Dk), 1)
    m = np.isfinite(Dk[iu])
    r = float(np.corrcoef(Dk[iu][m], E[iu][m])[0, 1])
    out = np.full((len(D), 3), np.nan)
    out[ok] = X
    return out, ok, {"n_embedded": int(ok.sum()), "distance_r_embedding_vs_input": r}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, choices=["su2020_genome", "su2020_chr21", "takei2021_1mb"])
    ap.add_argument("--path", default=None, help="raw imaging file (default: example-data)")
    ap.add_argument("--min-detect", type=float, default=0.0, help="su2020_chr21: keep traces with >= this detection")
    ap.add_argument("--max-cells", type=int, default=0, help="subsample structures (0 = all; smoke tests)")
    ap.add_argument("--block", type=int, default=16)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    t0 = time.time()
    kw = {"min_detect": a.min_detect} if a.dataset == "su2020_chr21" else {}
    pop = load_dataset(a.dataset, a.path, **kw)
    X = pop.coords
    if a.max_cells and len(X) > a.max_cells:
        X = X[np.random.default_rng(0).choice(len(X), a.max_cells, replace=False)]
    med, mean, cnt = pair_medians(X, pop.chrom, a.block)
    emb, ok, info = embed(med.astype(float))
    meta = {**pop.meta, "n_structures_used": int(len(X)), "n_copies": int(X.shape[1]), **info,
            "pooling": "cis: same copy; trans: all copy combinations", "seconds": time.time() - t0}
    meta.pop("cell_ids", None)
    np.savez_compressed(a.out, chrom=pop.chrom, start=pop.start, end=pop.end, median=med, mean=mean, count=cnt,
                        embedding=emb.astype(np.float32), meta=jdump(meta))
    print(f"{a.dataset}: {len(pop.chrom)} loci, {len(X)} structures, embedding r {info['distance_r_embedding_vs_input']:.3f}, "
          f"{time.time() - t0:.0f} s -> {a.out}")


if __name__ == "__main__":
    main()
