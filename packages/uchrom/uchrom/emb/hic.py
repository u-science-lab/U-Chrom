"""scHiCluster-style cell features from single-cell contact maps (``.scool``).

Zhou et al. 2019 (*PNAS* 116:14011, "Robust single-cell Hi-C clustering by
convolution- and random-walk-based imputation"): for each cell and
chromosome, the intra-chromosomal contact matrix is

1. smoothed by a ``(2·pad+1)²`` mean filter (linear convolution),
2. imputed by random walk with restart (``Q ← (1-rp)·Q·P + rp·I`` until
   convergence, P the row-normalised smoothed matrix),
3. binarised: the top ``top_pct`` % of the upper-triangle entries → 1.

Per chromosome the binarised vectors of all cells go through PCA; the
concatenated per-chromosome PCs are the cell features (feed them to
:func:`uchrom.emb.embed_cells` with ``source="hic", normalization="none"``,
which runs the final PCA → t-SNE / UMAP).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

__all__ = ["schicluster_impute", "schicluster_features", "scool_cell_features"]


def schicluster_impute(mats: np.ndarray, *, pad: int = 1, rp: float = 0.5,
                       tol: float = 1e-6, max_iter: int = 100) -> np.ndarray:
    """Convolution + random-walk-with-restart imputation of a batch of
    symmetric contact matrices, shape ``(n_cells, n, n)`` (or ``(n, n)``)."""
    a = np.asarray(mats, dtype=np.float64)
    single = a.ndim == 2
    if single:
        a = a[None]
    n = a.shape[-1]
    if pad > 0:
        p = np.pad(a, ((0, 0), (pad, pad), (pad, pad)))
        c = np.zeros_like(a)
        for di in range(2 * pad + 1):
            for dj in range(2 * pad + 1):
                c += p[:, di:di + n, dj:dj + n]
        a = c / (2 * pad + 1) ** 2
    # self-loops keep rows of empty bins stochastic (as in scHiCluster)
    a = a + np.eye(n)[None]
    P = a / a.sum(axis=2, keepdims=True)
    eye = np.broadcast_to(np.eye(n), a.shape)
    Q = eye.copy()
    for _ in range(max_iter):
        Q_new = (1 - rp) * (Q @ P) + rp * eye
        delta = np.abs(Q_new - Q).max()
        Q = Q_new
        if delta < tol:
            break
    Q = (Q + np.swapaxes(Q, 1, 2)) / 2
    return Q[0] if single else Q


def schicluster_features(per_chrom, *, pad: int = 1, rp: float = 0.5,
                         top_pct: float = 20.0, n_per_chrom: int = 20, batch: int = 256,
                         random_state: int = 0) -> Tuple[np.ndarray, List[str]]:
    """scHiCluster features, per chromosome.

    ``per_chrom`` maps chrom → either an ``(n_cells, n, n)`` array of raw
    counts or a callable ``f(lo, hi) -> (hi - lo, n, n)`` array for a batch
    of cells (so all maps never need to be dense at once) together with
    ``n_cells`` — pass ``(callable, n_cells, n)`` tuples for that.

    Returns ``(features, column_names)`` — per-chromosome PCs of the
    imputed, binarised maps, concatenated (``chr1_PC1``, …).
    """
    from sklearn.decomposition import PCA

    blocks, names = [], []
    for chrom, spec in per_chrom.items():
        if isinstance(spec, tuple):
            get, n_cells, n = spec
        else:
            arr = np.asarray(spec)
            n_cells, n = arr.shape[0], arr.shape[1]
            get = (lambda a: (lambda lo, hi: a[lo:hi]))(arr)
        if n < 3:
            continue
        iu = np.triu_indices(n, 1)
        vec = np.zeros((n_cells, len(iu[0])), dtype=np.float32)
        for s in range(0, n_cells, batch):
            q = schicluster_impute(get(s, min(s + batch, n_cells)), pad=pad, rp=rp)
            v = q[:, iu[0], iu[1]]
            cut = np.percentile(v, 100 - top_pct, axis=1, keepdims=True)
            vec[s:s + batch] = (v > cut).astype(np.float32)
        if not vec.std(axis=0).any():
            continue  # identical in every cell (e.g. no contacts): no information
        k = int(min(n_per_chrom, n_cells - 1, vec.shape[1]))
        pcs = PCA(n_components=k, random_state=random_state).fit_transform(vec)
        blocks.append(pcs)
        names += [f"{chrom}_PC{i + 1}" for i in range(k)]
    return np.hstack(blocks), names


def scool_cell_features(scool: str, cell_names: Sequence[str], *, chroms: Optional[Sequence[str]] = None,
                        pad: int = 1, rp: float = 0.5, top_pct: float = 20.0, n_per_chrom: int = 20,
                        random_state: int = 0) -> Tuple[np.ndarray, List[str], np.ndarray]:
    """Read one contact map per cell from a ``.scool`` and compute
    :func:`schicluster_features`.

    ``cell_names`` are the scool cell names, in the order wanted for the
    output rows; cells missing from the file get all-zero maps.

    Returns ``(features, column_names, n_contacts_per_cell)``.
    """
    import cooler

    names_in_file = set(cooler.fileops.list_scool_cells(scool))
    first = next(iter(sorted(names_in_file)))
    clr0 = cooler.Cooler(f"{scool}::{first}")
    bins = clr0.bins()[["chrom", "start", "end"]][:]
    chroms = list(chroms) if chroms is not None else [str(c) for c in clr0.chromnames]
    chrom_of_bin = bins["chrom"].astype(str).to_numpy()
    offs = {c: int(np.flatnonzero(chrom_of_bin == c)[0]) for c in chroms if (chrom_of_bin == c).any()}
    sizes = {c: int((chrom_of_bin == c).sum()) for c in offs}
    # keep each cell's intra-chromosomal pixels sparse; densify per batch
    pix: Dict[str, List[Tuple[np.ndarray, np.ndarray, np.ndarray]]] = {c: [] for c in offs}
    empty = (np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.float32))
    depth = np.zeros(len(cell_names), dtype=np.int64)
    for i, name in enumerate(cell_names):
        path = f"/cells/{name}"
        if path not in names_in_file:
            for c in offs:
                pix[c].append(empty)
            continue
        px = cooler.Cooler(f"{scool}::{path}").pixels()[:]
        b1 = px["bin1_id"].to_numpy()
        b2 = px["bin2_id"].to_numpy()
        cnt = px["count"].to_numpy(dtype=np.float32)
        depth[i] = int(cnt.sum())
        c1, c2 = chrom_of_bin[b1], chrom_of_bin[b2]
        for c, o in offs.items():
            sel = (c1 == c) & (c2 == c)
            pix[c].append((b1[sel] - o, b2[sel] - o, cnt[sel]))

    def getter(c: str):
        n = sizes[c]

        def get(lo: int, hi: int) -> np.ndarray:
            m = np.zeros((hi - lo, n, n), dtype=np.float64)
            for j in range(lo, hi):
                r, q, v = pix[c][j]
                np.add.at(m[j - lo], (r, q), v)
                off = r != q
                np.add.at(m[j - lo], (q[off], r[off]), v[off])
            return m
        return get

    spec = {c: (getter(c), len(cell_names), sizes[c]) for c in offs}
    feats, cols = schicluster_features(spec, pad=pad, rp=rp, top_pct=top_pct,
                                       n_per_chrom=n_per_chrom, random_state=random_state)
    return feats, cols, depth
