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

:func:`embed_contacts` does all of it on a ``ChromData``: it reads the
per-cell maps linked to it (or embedded in its atlas store), computes the
features and stores the embeddings.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

__all__ = ["schicluster_impute", "schicluster_features", "scool_cell_features", "embed_contacts"]


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

    Returns ``(features, column_names, n_contacts_per_cell)`` (all the
    contacts of each cell in the file).
    """
    feats, cols, depth, _ = _scool_cell_features(scool, cell_names, chroms=chroms, pad=pad, rp=rp, top_pct=top_pct,
                                                 n_per_chrom=n_per_chrom, random_state=random_state)
    return feats, cols, depth


def _scool_cell_features(scool, cell_names, *, chroms, pad, rp, top_pct, n_per_chrom, random_state):
    """:func:`scool_cell_features`, also returning each cell's intra-chromosomal contacts of ``chroms``."""
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
    cis = np.zeros(len(cell_names), dtype=np.int64)
    for i, name in enumerate(cell_names):
        path = f"/cells/{name}"
        if path not in names_in_file:
            for c in offs:
                pix[c].append(empty)
            continue
        px = cooler.Cooler(f"{scool}::{path}").pixels()[:]
        b1 = px["bin1_id"].to_numpy()
        b2 = px["bin2_id"].to_numpy()
        raw = px["count"].to_numpy()
        cnt = raw.astype(np.float32)
        depth[i] = int(cnt.sum())
        c1, c2 = chrom_of_bin[b1], chrom_of_bin[b2]
        for c, o in offs.items():
            sel = (c1 == c) & (c2 == c)
            pix[c].append((b1[sel] - o, b2[sel] - o, cnt[sel]))
            cis[i] += int(raw[sel].sum())

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
    return feats, cols, depth, cis


_CONTACT_METHODS = ("schicluster",)


def embed_contacts(
    cd,
    *,
    contacts: str = "per_cell",
    method: str = "schicluster",
    cells=None,
    chroms: Optional[Sequence[str]] = None,
    pad: int = 1,
    rp: float = 0.5,
    top_pct: float = 20.0,
    n_per_chrom: int = 20,
    methods: Sequence[str] = ("pca", "tsne", "umap"),
    n_pcs: int = 20,
    random_state: int = 0,
    key_added: str = "hic",
    copy: bool = False,
):
    """Embed cells by their single-cell contact maps — from the per-cell maps linked to ``cd``
    (``cd.link_scool``, key ``contacts``; or embedded in an atlas store).

    ``method="schicluster"`` (Zhou et al. 2019, *PNAS* 116:14011): each cell's intra-chromosomal maps are
    smoothed by a ``(2·pad+1)²`` convolution, imputed by a random walk with restart (``rp``) and binarised
    (top ``top_pct`` %); each chromosome is reduced to ``n_per_chrom`` PCs across the cells and the PCs of
    all chromosomes are concatenated (:func:`scool_cell_features`).  :func:`uchrom.emb.embed_cells` then
    runs PCA (``n_pcs``) → t-SNE / UMAP on these features.  The maps are read with
    ``cd.linked_scool_path(contacts, cells=..., trans=False)``: the linked ``.scool`` itself, or — on an
    atlas store — the cells' maps exported once from the embedded copy (one read per chromosome, the
    contacts between chromosomes left out).  For FastHigashi use :func:`uchrom.emb.embed_higashi`.

    Parameters
    ----------
    cd : ChromData
        With ``cells`` and linked per-cell contact maps (``cd.uns["linked_scool"][contacts]``).
    contacts : str
        Key of the linked per-cell maps.
    method : ``"schicluster"``
        The contact-map features.
    cells : sequence of cell ids, optional
        Cells to embed (default: every cell of ``cd``); the other rows of the embeddings are NaN.
    chroms : sequence of str, optional
        Chromosomes to use, in this order (default: those of the maps without Y and M).
    pad, rp, top_pct, n_per_chrom
        scHiCluster's convolution half-width, restart probability, share of entries kept, PCs per
        chromosome (see :func:`schicluster_features`).
    methods, n_pcs, random_state
        Passed to :func:`uchrom.emb.embed_cells` (``random_state`` also seeds the per-chromosome PCAs).
    key_added : str
        Names the outputs: ``cd.cellm[f"{key_added}_pca"]`` (``_tsne``, ``_umap``), registered in
        ``cd.uns["embeddings"]`` as the Hi-C modality; the number of contacts used per cell (intra-
        chromosomal, of ``chroms``) in ``cd.cells[f"{key_added}_n_cis_contacts"]``; the settings in
        ``cd.uns[key_added]``; the scHiCluster features (cells × ``n_per_chrom`` per chromosome, float32,
        on the cells axis) in ``cd.results[key_added]`` with the call's provenance.
    copy : bool
        Return a new ``ChromData`` holding the results instead of modifying ``cd``.

    Returns
    -------
    dict mapping cellm key → embedding (``copy=False``), or the new ``ChromData`` (``copy=True``).
    """
    import cooler

    from .cells import embed_cells
    from .higashi import _SKIP_CHROMS               # autosomes + X by default, as for FastHigashi

    if method not in _CONTACT_METHODS:
        raise ValueError(f"unknown contact-map method {method!r}; choose from {_CONTACT_METHODS} "
                         "(FastHigashi: uchrom.emb.embed_higashi)")
    if copy:
        cd = cd.copy()
    all_ids = [str(c) for c in cd.cells.index]
    if not all_ids:
        raise ValueError("cd.cells is empty — nothing to embed")
    ids = all_ids if cells is None else [str(c) for c in cells]
    unknown = sorted(set(ids) - set(all_ids))
    if unknown:
        raise KeyError(f"cells not in cd.cells: {unknown[:5]}")
    record = (cd.uns.get("linked_scool") or {}).get(contacts) or {}
    scool = cd.linked_scool_path(contacts, cells=ids, trans=False)
    in_file = cooler.fileops.list_scool_cells(scool)
    first = cooler.Cooler(f"{scool}::{in_file[0]}")
    if chroms is None:
        chroms = [c for c in first.chromnames if c not in _SKIP_CHROMS]
    chroms = [str(c) for c in chroms]
    resolution = int(first.binsize)
    feats, cols, _, depth = _scool_cell_features(scool, ids, chroms=chroms, pad=pad, rp=rp, top_pct=top_pct,
                                                 n_per_chrom=n_per_chrom, random_state=random_state)
    used = sorted({c.rsplit("_PC", 1)[0] for c in cols}, key=chroms.index)
    text = (f"scHiCluster: {_size(resolution)} maps of {len(used)} chromosomes ({used[0]}–{used[-1]}); "
            f"{2 * pad + 1}x{2 * pad + 1} convolution, random walk (rp={rp}), top {top_pct:g}% binarised, "
            f"{n_per_chrom} PCs per chromosome")
    subset = None if ids == all_ids else ids
    out = embed_cells(cd, source=key_added, matrix=feats, cells=subset, normalization="none", methods=methods,
                      n_pcs=n_pcs, random_state=random_state, modality="Hi-C", features=text)

    pos = pd.Index(all_ids).get_indexer(ids)
    if subset is None:
        n_cis = np.asarray(depth, dtype=np.int64)
    else:
        n_cis = np.full(len(all_ids), np.nan)
        n_cis[pos] = depth
    cd.cells[f"{key_added}_n_cis_contacts"] = n_cis
    on_cells = np.full((len(all_ids), feats.shape[1]), np.nan, dtype=np.float32)
    on_cells[pos] = feats
    settings = {"method": method, "contacts": contacts, "chroms": used, "resolution": resolution, "pad": int(pad),
                "rp": float(rp), "top_pct": float(top_pct), "n_per_chrom": int(n_per_chrom),
                "n_features": int(feats.shape[1]), "n_pcs": int(n_pcs), "random_state": int(random_state),
                "n_cells": len(ids), "embeddings": sorted(out)}
    cd.uns[key_added] = settings
    cd.results.set(key_added, on_cells, kind="array", function="uchrom.emb.embed_contacts",
                   params={k: v for k, v in settings.items() if k not in ("embeddings",)},
                   inputs={"contacts": contacts, "n_cells": len(ids),
                           "genome_assembly": record.get("genome_assembly") or cd.uns.get("genome_assembly")})
    return cd if copy else out


def _size(bp: int) -> str:
    return f"{bp / 1e6:g} Mb" if bp >= 1_000_000 else f"{bp / 1e3:g} kb"
