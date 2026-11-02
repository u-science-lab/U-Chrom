"""scHiCluster cell features from single-cell contact maps (``.scool``).

Zhou et al. 2019 (*PNAS* 116:14011, "Robust single-cell Hi-C clustering by convolution- and random-walk-based
imputation"), as the authors' code computes them (``schicluster.schicluster``: ``impute_cpu`` →
``neighbor_ave_cpu`` / ``random_walk_cpu``, then ``hicluster_cpu``; github.com/zhoujt1994/scHiCluster, PyPI 1.3.2,
MIT licence).  For each cell and chromosome, from the cell's contact counts ``S`` (symmetric, the diagonal once):

1. ``A = log2(S + diag(S) + 1)`` — the authors build ``A + Aᵀ`` from the upper triangle, which counts the
   diagonal twice;
2. the ``(2·pad+1)²`` mean filter, zeros outside the map (by cumulative sums, rounded to 8 decimals, as the code);
3. the random walk with restart: the diagonal set to 0, then to 1 in the columns without contacts, ``P`` the
   column-normalised map, ``Q ← (1 − rp)·I + rp·Q·P`` from ``Q = I`` until the Frobenius norm of the change is
   below ``tol`` (1e-6), at most ``max_iter`` (30) steps, each cell on its own;
4. the features: ``Q`` of every cell flattened (all ``n²`` entries), set to 1 above the cell's ``100 − top_pct``
   percentile and 0 elsewhere; per chromosome a PCA across the cells with ``int(0.2 · min(cells, n²)) − 1``
   components (the authors' rule; ``n_per_chrom`` sets a number instead); the chromosomes' PCs concatenated.  With
   the authors' rule this PCA (scikit-learn's, as theirs) is the slowest step (2,000 cells, 8 CPUs: about 400 of
   506 s); a fixed ``n_per_chrom`` such as 20 makes it much shorter.

:func:`embed_contacts` does all of it on a ``ChromData`` (it reads the per-cell maps linked to it, or embedded in
its atlas store) and then embeds the cells with :func:`uchrom.emb.embed_cells` (PCA → t-SNE / UMAP; the authors
cluster their concatenated PCs with k-means instead).
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

__all__ = ["schicluster_impute", "schicluster_features", "scool_cell_features", "embed_contacts"]


def _neighbor_average(a: np.ndarray, pad: int) -> np.ndarray:
    """The authors' ``neighbor_ave_cpu`` on a batch ``(k, n, n)``: the ``(2 pad + 1)²`` mean with zeros outside,
    by two cumulative sums, rounded to 8 decimals before the division (as their code)."""
    if pad <= 0:
        return a
    k, n, _ = a.shape
    ll = 2 * pad + 1
    B = np.zeros((k, n + ll, n + ll))
    B[:, pad + 1:pad + n + 1, pad + 1:pad + n + 1] = a
    F = B.cumsum(axis=1).cumsum(axis=2)
    C = np.zeros_like(F)
    D = np.zeros_like(F)
    E = np.zeros_like(F)
    C[:, ll:, ll:] = F[:, :-ll, :-ll]
    D[:, ll:, :] = F[:, :-ll, :]
    E[:, :, ll:] = F[:, :, :-ll]
    return np.around(F + C - D - E, decimals=8)[:, ll:, ll:] / float(ll * ll)


def _random_walk(a: np.ndarray, rp: float, tol: float, max_iter: int) -> np.ndarray:
    """The authors' ``random_walk_cpu`` on one map ``(n, n)`` (module docstring, step 3), with their operations
    (``np.dot``, the Frobenius norm of the change)."""
    n = len(a)
    a = a.copy()
    d = np.arange(n)
    a[d, d] = 0.0
    a[d, d] = (a.sum(axis=0) == 0).astype(np.float64)          # columns without contacts
    P = a / a.sum(axis=0)                                       # each column divided by its sum
    eye = np.eye(n)
    Q = eye
    for _ in range(int(max_iter)):
        Qn = (1 - rp) * eye + rp * np.dot(Q, P)
        delta = np.linalg.norm(Q - Qn)
        Q = Qn
        if delta < tol:
            break
    return Q


def _impute_one(m: np.ndarray, pad: int, rp: float, log: bool, tol: float, max_iter: int) -> np.ndarray:
    """Steps 1-3 of the module docstring for one map of raw counts (symmetric, the diagonal once)."""
    a = np.array(m, dtype=np.float64)
    d = np.arange(len(a))
    a[d, d] *= 2                                                 # A + Aᵀ of the upper triangle
    if log:
        a = np.log2(a + 1)
    a = _neighbor_average(a[None], pad)[0]
    return a if rp == -1 else _random_walk(a, rp, tol, max_iter)


def _n_threads(n_threads: int) -> int:
    if n_threads and n_threads > 0:
        return int(n_threads)
    try:
        return len(os.sched_getaffinity(0))                      # the CPUs this process may use (Slurm, cgroups)
    except AttributeError:
        return os.cpu_count() or 1


def _map_cells(fn, mats, n_threads: int) -> List[np.ndarray]:
    """``fn`` on every map, one map per thread with single-threaded BLAS (as the authors' process pool runs their
    code: many small matrices are faster side by side than each spread over all cores)."""
    w = min(_n_threads(n_threads), len(mats))
    if w <= 1:
        return [fn(m) for m in mats]
    from concurrent.futures import ThreadPoolExecutor

    from threadpoolctl import threadpool_limits

    with threadpool_limits(limits=1, user_api="blas"), ThreadPoolExecutor(w) as ex:
        return list(ex.map(fn, mats))


def schicluster_impute(mats: np.ndarray, *, pad: int = 1, rp: float = 0.5, log: bool = True,
                       tol: float = 1e-6, max_iter: int = 30, n_threads: int = 0) -> np.ndarray:
    """scHiCluster's imputation (module docstring, steps 1-3) of a batch of contact maps ``(n_cells, n, n)``
    (or one ``(n, n)``): symmetric raw counts with the diagonal once, as a ``.scool`` stores them.

    ``log``: the authors' ``log2(S + diag(S) + 1)`` (False: the counts as given, ``S + diag(S)``).  ``rp``: the
    weight of the walk as the authors' code uses it, ``Q ← (1 − rp) I + rp Q P`` (their default 0.5; ``rp=-1``
    returns the smoothed map without the walk, as their code).  Each map stops at its own step.  ``n_threads``: maps
    imputed side by side (0: every CPU this process may use).  Returns ``Q`` as the authors' code (not symmetric:
    ``(Q + Qᵀ) / 2`` symmetrises it).
    """
    a = np.asarray(mats, dtype=np.float64)
    single = a.ndim == 2
    if single:
        a = a[None]
    q = np.stack(_map_cells(lambda m: _impute_one(m, pad, rp, log, tol, max_iter), a, n_threads))
    return q[0] if single else q


def schicluster_features(per_chrom, *, pad: int = 1, rp: float = 0.5, log: bool = True,
                         top_pct: float = 20.0, n_per_chrom: Optional[int] = None, batch: int = 256,
                         random_state: int = 0, n_threads: int = 0,
                         pca: str = "full") -> Tuple[np.ndarray, List[str]]:
    """scHiCluster features, per chromosome (module docstring, step 4).

    ``per_chrom`` maps chrom → either an ``(n_cells, n, n)`` array of raw counts or a callable
    ``f(lo, hi) -> (hi - lo, n, n)`` array for a batch of cells (so all maps never need to be dense at once)
    together with ``n_cells`` — pass ``(callable, n_cells, n)`` tuples for that.  ``n_per_chrom``: PCs per
    chromosome (None: the authors' ``int(0.2 · min(cells, n²)) − 1``); ``top_pct`` the share set to 1
    (``top_pct < 0``: the imputed values, not binarised, as the authors' ``prct=-1``); ``n_threads`` as
    :func:`schicluster_impute`.  ``pca="incremental"`` (needs ``n_per_chrom``) fits each chromosome's PCA in
    batches of cells (scikit-learn's ``IncrementalPCA``, float32) instead of on a float64 copy of all cells' features:
    for 10⁵ cells; the components agree with the full PCA up to sign and rounding.

    Returns ``(features, column_names)`` — the PCs of all chromosomes, concatenated (``chr1_PC1``, …).
    """
    from sklearn.decomposition import PCA, IncrementalPCA

    if pca not in ("full", "incremental"):
        raise ValueError(f"pca must be 'full' or 'incremental', not {pca!r}")
    if pca == "incremental" and n_per_chrom is None:
        raise ValueError("pca='incremental' needs n_per_chrom (the authors' rule gives thousands of components)")
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
        binar = top_pct >= 0
        vec = np.zeros((n_cells, n * n), dtype=np.uint8 if binar else np.float32)
        for s in range(0, n_cells, batch):
            q = schicluster_impute(get(s, min(s + batch, n_cells)), pad=pad, rp=rp, log=log, n_threads=n_threads)
            v = q.reshape(len(q), n * n)
            if binar:
                cut = np.percentile(v, 100 - top_pct, axis=1)
                vec[s:s + len(q)] = v > cut[:, None]
            else:
                vec[s:s + len(q)] = v
        if not vec.std(axis=0).any():
            continue  # identical in every cell (e.g. no contacts): no information
        k = int(min(vec.shape) * 0.2) - 1 if n_per_chrom is None else int(min(n_per_chrom, min(vec.shape) - 1))
        if k < 1:
            continue
        if pca == "full":
            pcs = PCA(n_components=k, random_state=random_state).fit_transform(vec.astype(np.float64))
        else:
            step = max(10 * k, 4096)
            ipca = IncrementalPCA(n_components=k)
            for s in range(0, n_cells, step):
                part = vec[s:s + step]
                if len(part) >= k:                     # partial_fit needs at least k rows
                    ipca.partial_fit(part.astype(np.float32))
            pcs = np.vstack([ipca.transform(vec[s:s + step].astype(np.float32)) for s in range(0, n_cells, step)])
        blocks.append(pcs.astype(np.float32))
        names += [f"{chrom}_PC{i + 1}" for i in range(k)]
    return np.hstack(blocks), names


def scool_cell_features(scool: str, cell_names: Sequence[str], *, chroms: Optional[Sequence[str]] = None,
                        pad: int = 1, rp: float = 0.5, top_pct: float = 20.0, n_per_chrom: Optional[int] = None,
                        random_state: int = 0, n_threads: int = 0,
                        pca: str = "full") -> Tuple[np.ndarray, List[str], np.ndarray]:
    """Read one contact map per cell from a ``.scool`` and compute
    :func:`schicluster_features`.

    ``cell_names`` are the scool cell names, in the order wanted for the
    output rows; cells missing from the file get all-zero maps.

    Returns ``(features, column_names, n_contacts_per_cell)`` (all the
    contacts of each cell in the file).
    """
    feats, cols, depth, _ = _scool_cell_features(scool, cell_names, chroms=chroms, pad=pad, rp=rp, top_pct=top_pct,
                                                 n_per_chrom=n_per_chrom, random_state=random_state,
                                                 n_threads=n_threads, pca=pca)
    return feats, cols, depth


def _scool_cell_features(scool, cell_names, *, chroms, pad, rp, top_pct, n_per_chrom, random_state, n_threads=0,
                         pca="full"):
    """:func:`scool_cell_features`, also returning each cell's intra-chromosomal contacts of ``chroms``."""
    import cooler
    import h5py

    names_in_file = set(cooler.fileops.list_scool_cells(scool))
    first = next(iter(sorted(names_in_file)))
    clr0 = cooler.Cooler(f"{scool}::{first}")
    bins = clr0.bins()[["chrom", "start", "end"]][:]
    chroms = list(chroms) if chroms is not None else [str(c) for c in clr0.chromnames]
    chrom_of_bin = bins["chrom"].astype(str).to_numpy()
    offs = {c: int(np.flatnonzero(chrom_of_bin == c)[0]) for c in chroms if (chrom_of_bin == c).any()}
    sizes = {c: int((chrom_of_bin == c).sum()) for c in offs}
    # each chromosome's pixels are read per batch of cells, straight from the file (bounded memory)
    f = h5py.File(scool, "r")
    starts = np.array([offs[c] for c in offs] + [0], dtype=np.int64)
    ends = np.array([offs[c] + sizes[c] for c in offs] + [0], dtype=np.int64)
    depth = np.zeros(len(cell_names), dtype=np.int64)
    cis = np.zeros(len(cell_names), dtype=np.int64)
    # per cell: the pixel range of each chromosome's rows ((-1, -1): not in the file)
    lo_px = np.full((len(cell_names), len(offs)), -1, dtype=np.int64)
    hi_px = np.full((len(cell_names), len(offs)), -1, dtype=np.int64)
    for i, name in enumerate(cell_names):
        if f"/cells/{name}" not in names_in_file:
            continue
        g = f["cells"][name]
        raw = g["pixels/count"][:]
        depth[i] = int(raw.sum())
        c1, c2 = chrom_of_bin[g["pixels/bin1_id"][:]], chrom_of_bin[g["pixels/bin2_id"][:]]
        cis[i] = int(raw[(c1 == c2) & np.isin(c1, list(offs))].sum())
        b1_off = g["indexes/bin1_offset"][:]
        lo_px[i], hi_px[i] = b1_off[starts[:-1]], b1_off[ends[:-1]]

    def getter(k: int, c: str):
        n, o = sizes[c], offs[c]

        def get(lo: int, hi: int) -> np.ndarray:
            m = np.zeros((hi - lo, n * n), dtype=np.float64)
            for j in range(lo, hi):
                a, b = lo_px[j, k], hi_px[j, k]
                if a < 0 or a == b:
                    continue
                g = f["cells"][cell_names[j]]["pixels"]
                b2 = g["bin2_id"][a:b]
                sel = b2 < o + n                      # rows of this chromosome, columns too
                r = g["bin1_id"][a:b][sel] - o
                q = b2[sel] - o
                v = g["count"][a:b][sel].astype(np.float32)
                off = r != q
                idx = np.concatenate([r * n + q, (q * n + r)[off]])
                m[j - lo] = np.bincount(idx, weights=np.concatenate([v, v[off]]), minlength=n * n)
            return m.reshape(hi - lo, n, n)
        return get

    spec = {c: (getter(k, c), len(cell_names), sizes[c]) for k, c in enumerate(offs)}
    try:
        feats, cols = schicluster_features(spec, pad=pad, rp=rp, top_pct=top_pct, n_per_chrom=n_per_chrom,
                                           random_state=random_state, n_threads=n_threads, pca=pca)
    finally:
        f.close()
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
    n_per_chrom: Optional[int] = None,
    pca: str = "full",
    methods: Sequence[str] = ("pca", "tsne", "umap"),
    n_pcs: int = 20,
    random_state: int = 0,
    key_added: str = "hic",
    copy: bool = False,
    n_threads: int = 0,
):
    """Embed cells by their single-cell contact maps — from the per-cell maps linked to ``cd``
    (``cd.link_scool``, key ``contacts``; or embedded in an atlas store).

    ``method="schicluster"`` (Zhou et al. 2019, *PNAS* 116:14011; the authors' computation, module docstring):
    each cell's intra-chromosomal maps are log-transformed, smoothed by a ``(2·pad+1)²`` mean filter, imputed by
    a random walk (``rp``) and binarised (top ``top_pct`` %); each chromosome is reduced to PCs across the cells
    (``n_per_chrom``; default the authors' ``int(0.2 · min(cells, n²)) − 1``) and the PCs of all chromosomes are
    concatenated (:func:`scool_cell_features`).  :func:`uchrom.emb.embed_cells` then
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
        scHiCluster's filter half-width, walk weight (``Q ← (1 − rp) I + rp Q P``; 0.5), share of entries kept,
        PCs per chromosome (None: the authors' rule; see :func:`schicluster_features`).
    pca : ``"full"`` or ``"incremental"``
        How each chromosome's PCA is fitted (:func:`schicluster_features`); ``"incremental"`` (with ``n_per_chrom``)
        for 10⁵ cells.
    methods, n_pcs, random_state
        Passed to :func:`uchrom.emb.embed_cells` (``random_state`` also seeds the per-chromosome PCAs).
    key_added : str
        Names the outputs: ``cd.cellm[f"{key_added}_pca"]`` (``_tsne``, ``_umap``), registered in
        ``cd.uns["embeddings"]`` as the Hi-C modality; the number of contacts used per cell (intra-
        chromosomal, of ``chroms``) in ``cd.cells[f"{key_added}_n_cis_contacts"]``; the settings in
        ``cd.uns[key_added]``; the scHiCluster features (cells × the PCs of every chromosome, float32,
        on the cells axis) in ``cd.results[key_added]`` with the call's provenance.
    copy : bool
        Return a new ``ChromData`` holding the results instead of modifying ``cd``.
    n_threads : int
        Maps imputed side by side (0: every CPU this process may use); the results do not depend on it.

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
                                                 n_per_chrom=n_per_chrom, random_state=random_state,
                                                 n_threads=n_threads, pca=pca)
    used = sorted({c.rsplit("_PC", 1)[0] for c in cols}, key=chroms.index)
    text = (f"scHiCluster: {_size(resolution)} maps of {len(used)} chromosomes ({used[0]}–{used[-1]}); "
            f"log2, {2 * pad + 1}x{2 * pad + 1} mean filter, random walk (rp={rp}), top {top_pct:g}% binarised, "
            f"{'int(0.2 min(cells, bins^2)) - 1' if n_per_chrom is None else n_per_chrom} PCs per chromosome"
            f"{' (incremental PCA)' if pca == 'incremental' else ''}")
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
                "rp": float(rp), "top_pct": float(top_pct), "n_per_chrom": None if n_per_chrom is None else int(n_per_chrom),
                "pca": pca,
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
