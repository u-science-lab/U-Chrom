"""Pairwise contact maps derived from multi-way contacts (``cd.clusters``: SPRITE, SpaceA, Pore-C, ChIA-Drop).

A cluster of ``n`` fragments holds ``n (n − 1) / 2`` fragment pairs; binned at a resolution, the pairs of every
cluster summed give a contact map.  The maps here count those pairs (integers: the embedded atlas copies store
counts as unsigned integers), from the clusters of ``min_size`` to ``max_size`` fragments (SPRITE's usual 2–1,000;
the size counts every fragment of the cluster, also those on chromosomes left out).  For one set of clusters the
binned map is ``Aᵀ A`` of the cluster × bin fragment counts ``A``: off the diagonal the pairs between two bins,
on it ``(Σ a² − Σ a) / 2``, the pairs within a bin::

    from uchrom.fea import clusters_to_scool, clusters_to_mcool
    clusters_to_scool(cd, "spacea", "spacea_1mb.scool", chromsizes=MM10, resolution=1_000_000)   # per cell
    clusters_to_mcool(cd, "spacea", "spacea.mcool", chromsizes=MM10, resolutions=[100_000, ...])  # pooled

:func:`filter_clusters` applies the SpaceA authors' cluster filter first (a new table next to the original).

Both link the file to ``cd`` (``link_scool`` / ``link_cool``) so the analyses and the web browser read them like
any linked map (``uchrom.emb.embed_contacts`` on the per-cell maps, ``python -m chromdata.embedded`` for an
atlas copy).  The clusters themselves stay in ``cd.clusters``: the maps are derived from them, not stored there.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

__all__ = ["filter_clusters", "cluster_pixels", "clusters_to_scool", "clusters_to_mcool"]


def _bin_codes(t, chromsizes: Mapping, resolution: int) -> Tuple[pd.DataFrame, np.ndarray]:
    """Genome bins of ``chromsizes`` and the bin of every fragment of ``t`` (−1: chromosome left out)."""
    from ..io.pairs_maps import genome_bins

    bins = genome_bins(chromsizes, resolution)
    first = np.concatenate([[0], np.cumsum([-(-int(s) // resolution) for s in chromsizes.values()])])
    offset = np.full(len(t.chroms), -1, np.int64)
    n_bins = np.zeros(len(t.chroms), np.int64)
    names = list(chromsizes)
    for k, c in enumerate(t.chroms):
        if c in chromsizes:
            i = names.index(c)
            offset[k], n_bins[k] = first[i], first[i + 1] - first[i]
    m = t.members_array
    code = m[0].astype(np.int64)
    local = m[1].astype(np.int64) // resolution
    ok = (offset[code] >= 0) & (local < n_bins[code])
    return bins, np.where(ok, offset[code] + local, -1)


def _pixels(member_offsets: np.ndarray, bin_of: np.ndarray, clusters: np.ndarray, n_bins: int) -> pd.DataFrame:
    """Upper-triangle pixels ``bin1_id, bin2_id, count`` of the fragment pairs of ``clusters``."""
    import scipy.sparse as sp

    if not len(clusters):
        return pd.DataFrame({"bin1_id": np.zeros(0, np.int64), "bin2_id": np.zeros(0, np.int64),
                             "count": np.zeros(0, np.int64)})
    a = member_offsets[clusters]
    n = member_offsets[clusters + 1] - a
    rows = np.repeat(np.arange(len(clusters)), n)
    cols = bin_of[np.arange(len(rows)) - np.repeat(np.cumsum(n) - n, n) + np.repeat(a, n)]   # the fragments, in order
    keep = cols >= 0
    A = sp.csr_matrix((np.ones(int(keep.sum()), np.int64), (rows[keep], cols[keep])), shape=(len(clusters), n_bins))
    A.sum_duplicates()
    C = sp.triu(A.T @ A, format="coo")
    count = C.data.astype(np.int64)
    diag = C.row == C.col
    if diag.any():
        within = np.asarray(A.sum(axis=0)).ravel()
        count[diag] = (count[diag] - within[C.row[diag]]) // 2
    order = np.lexsort((C.col, C.row))
    px = pd.DataFrame({"bin1_id": C.row[order].astype(np.int64), "bin2_id": C.col[order].astype(np.int64),
                       "count": count[order]})
    return px[px["count"] > 0].reset_index(drop=True)


def _filter_mask(t, min_size, max_size, min_chrom_share, min_cis_share) -> Tuple[np.ndarray, np.ndarray]:
    """The fragments :func:`filter_clusters` keeps (a mask over the stored fragments) and every fragment's cluster."""
    m = t.members_array
    cid = np.repeat(np.arange(t.n_clusters), t.sizes())
    # the authors' reads are chrom:start: fragments of a cluster with the same start count once
    order = np.lexsort((m[1], m[0], cid))
    first = np.ones(len(cid), bool)
    first[order[1:]] = (np.diff(cid[order]) != 0) | (np.diff(m[0][order].astype(np.int64)) != 0) | \
        (np.diff(m[1][order].astype(np.int64)) != 0)
    sizes = np.bincount(cid[first], minlength=t.n_clusters)
    ok = sizes >= int(min_size)
    if max_size is not None:
        ok &= sizes <= int(max_size)
    n_chrom = len(t.chroms)
    group, inv, per = np.unique(cid[first] * n_chrom + m[0][first].astype(np.int64), return_inverse=True,
                                return_counts=True)
    g_cluster = group // n_chrom
    g_keep = per / sizes[g_cluster] > float(min_chrom_share)                # step 2, per (cluster, chromosome)
    kept_n = np.bincount(g_cluster, weights=np.where(g_keep, per, 0), minlength=t.n_clusters)
    cis = np.bincount(g_cluster, weights=np.where(g_keep, per * (per - 1) / 2, 0), minlength=t.n_clusters)
    pairs = kept_n * (kept_n - 1) / 2
    ok &= (kept_n >= 2) & (cis >= float(min_cis_share) * pairs)              # step 3
    keep = np.zeros(len(cid), bool)
    keep[first] = ok[cid[first]] & g_keep[inv]
    return keep, cid


def filter_clusters(cd, key: str, *, min_size: int = 2, max_size: Optional[int] = 1000,
                    min_chrom_share: float = 0.15, min_cis_share: float = 0.2,
                    key_added: Optional[str] = None):
    """The clusters of ``cd.clusters[key]`` filtered as the SpaceA authors filter them (Ma et al. 2026; their
    ``2_Filter_SpotsClustersReads/filter_sprite.py``, ``spot_qc``, at commit ``c1e1753`` of
    github.com/YuetongXU/SpaceA-Paper), stored as ``cd.clusters[key_added]`` (default ``f"{key}_filtered"``).

    1. clusters of ``min_size``–``max_size`` fragments are kept;
    2. in each, the fragments of a chromosome holding no more than ``min_chrom_share`` of the cluster are dropped;
    3. a cluster whose remaining fragment pairs are less than ``min_cis_share`` within a chromosome (or that keeps
       fewer than two fragments) is dropped.

    Clusters mixing the fragments of several complexes (two barcodes alike) are mostly trans; the filter keeps the
    part of a cluster that is on its main chromosomes.  As the authors count reads by chromosome and start, fragments
    of a cluster with the same start count once (the first is kept).  Returns the new table.
    """
    from chromdata import ClusterTable

    t = cd.clusters[key]
    frag, cid = _filter_mask(t, min_size, max_size, min_chrom_share, min_cis_share)
    df = t.to_frame()                                                       # one row per fragment, stored order
    if len(df) != len(frag) or not np.array_equal(df["cluster"].to_numpy(), cid):
        raise RuntimeError("to_frame is not in the stored fragment order")
    df = df[frag]
    attrs = dict(t.attrs or {})
    attrs["filters"] = (f"the SpaceA authors' cluster filter (uchrom.fea.filter_clusters): size {min_size}-"
                        f"{max_size}, chromosomes > {min_chrom_share} of the cluster, cis share >= {min_cis_share}")
    attrs["filtered_from"] = key
    cell = "cell_id" if t.cells is not None else None
    member_columns = [c for c in df.columns if c not in ("cluster", "cell_id", "chrom", "start", "end")]
    new = ClusterTable.from_frame(df, cluster="cluster", cell=cell, chroms=list(t.chroms),
                                  cells=None if t.cells is None else list(t.cells), member_columns=member_columns,
                                  keep_names=False, attrs=attrs)
    cd.set_clusters(key_added or f"{key}_filtered", new)
    return new


def _selected(t, min_size: int, max_size: Optional[int], ids: Optional[np.ndarray] = None) -> np.ndarray:
    sizes = t.sizes()
    ok = sizes >= int(min_size)
    if max_size is not None:
        ok &= sizes <= int(max_size)
    sel = np.flatnonzero(ok)
    return sel if ids is None else np.intersect1d(sel, ids)


def cluster_pixels(cd, key: str, *, chromsizes: Mapping, resolution: int, cells=None, min_size: int = 2,
                   max_size: Optional[int] = 1000) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Binned fragment pairs of the clusters ``cd.clusters[key]`` (of ``cells``, default all).

    Returns ``(bins, pixels)``: the genome bins of ``chromsizes`` (``chrom, start, end``) and the upper-triangle
    pixels ``bin1_id, bin2_id, count`` (count = fragment pairs; a fragment is binned by its start).
    """
    t = cd.clusters[key]
    bins, bin_of = _bin_codes(t, chromsizes, int(resolution))
    off = np.asarray(t.member_offsets, np.int64)
    ids = None
    if cells is not None:
        ids = np.concatenate([np.arange(r.start, r.stop) for r in (t.cell_clusters(c) for c in cells)] or
                             [np.zeros(0, np.int64)])
    return bins, _pixels(off, bin_of, _selected(t, min_size, max_size, ids), len(bins))


def _meta(t, key: str, min_size: int, max_size: Optional[int]) -> dict:
    return {"source": f"cd.clusters[{key!r}]", "count": "fragment pairs of the clusters",
            "cluster_size": [int(min_size), None if max_size is None else int(max_size)],
            "assay": t.attrs.get("assay")}


def clusters_to_scool(cd, key: str, out: Union[str, os.PathLike], *, chromsizes: Mapping, resolution: int,
                      min_size: int = 2, max_size: Optional[int] = 1000, link_key: Optional[str] = None,
                      label: Optional[str] = None) -> pd.DataFrame:
    """One map per cell of ``cd.clusters[key]`` in a ``.scool`` (cell names = cell ids), linked as ``link_key``
    (default ``key``) with ``cd.link_scool``.

    Returns per cell: ``n_clusters`` (of ``min_size``–``max_size`` fragments), ``n_pairs`` (fragment pairs in
    the kept chromosomes), ``n_cis`` and ``n_pixels``.
    """
    import cooler

    t = cd.clusters[key]
    if t.cells is None:
        raise ValueError(f"cd.clusters[{key!r}] has no cells (a bulk table): use clusters_to_mcool")
    res = int(resolution)
    bins, bin_of = _bin_codes(t, chromsizes, res)
    off = np.asarray(t.member_offsets, np.int64)
    keep = _selected(t, min_size, max_size)
    cell_off = np.asarray(t.cell_offsets, np.int64)
    chrom_of_bin = bins["chrom"].to_numpy()
    stats = {}

    class _Cells(Mapping):
        def __getitem__(self, cell):
            i = code[cell]
            ids = keep[(keep >= cell_off[i]) & (keep < cell_off[i + 1])]
            px = _pixels(off, bin_of, ids, len(bins))
            cis = chrom_of_bin[px["bin1_id"].to_numpy()] == chrom_of_bin[px["bin2_id"].to_numpy()]
            stats[cell] = {"n_clusters": len(ids), "n_pairs": int(px["count"].sum()),
                           "n_cis": int(px["count"].to_numpy()[cis].sum()), "n_pixels": len(px)}
            return px

        def __iter__(self):
            return iter(names)

        def __len__(self):
            return len(names)

    names = [str(c) for c in t.cells]
    code = {c: i for i, c in enumerate(names)}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.{os.getpid()}.part")
    try:
        cooler.create_scool(str(tmp), bins, _Cells(), ordered=True, assembly=cd.uns.get("genome_assembly"),
                            metadata=_meta(t, key, min_size, max_size), dtypes={"count": np.int32})
        os.replace(tmp, out)
    finally:
        if tmp.exists():
            tmp.unlink()
    cd.link_scool(out, key=link_key or key, cell_name="cell_id", genome_assembly=cd.uns.get("genome_assembly"),
                  bin_size=res, label=label or f"Per cell, fragment pairs of the clusters ({res // 1000} kb)",
                  cluster_size=[int(min_size), None if max_size is None else int(max_size)])
    st = pd.DataFrame.from_dict(stats, orient="index")
    st.index.name = "cell_id"
    return st.reindex(names)


def clusters_to_mcool(cd, key: str, out: Union[str, os.PathLike], *, chromsizes: Mapping,
                      resolutions: Sequence[int], cells=None, min_size: int = 2, max_size: Optional[int] = 1000,
                      balance: bool = True, link_key: Optional[str] = None, label: Optional[str] = None,
                      n_threads: int = 1) -> Path:
    """The fragment pairs of the clusters ``cd.clusters[key]`` (of ``cells``, default all) pooled into one
    ``.mcool``: binned at the finest of ``resolutions``, coarsened to the others (``cooler.zoomify_cooler``),
    ICE-balanced when ``balance``; linked as ``link_key`` (default ``f"{key}_pooled"``) with ``cd.link_cool``.
    """
    import cooler

    t = cd.clusters[key]
    res = sorted(int(r) for r in resolutions)
    bins, px = cluster_pixels(cd, key, chromsizes=chromsizes, resolution=res[0], cells=cells,
                              min_size=min_size, max_size=max_size)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    base = out.with_name(f".{out.name}.{os.getpid()}.base.cool")
    tmp = out.with_name(f".{out.name}.{os.getpid()}.part")
    try:
        cooler.create_cooler(str(base), bins, px, assembly=cd.uns.get("genome_assembly"),
                             metadata=_meta(t, key, min_size, max_size), dtypes={"count": np.int64})
        cooler.zoomify_cooler(str(base), str(tmp), res, chunksize=10_000_000, nproc=max(1, int(n_threads)))
        if balance:
            for r in res:
                clr = cooler.Cooler(f"{tmp}::/resolutions/{r}")
                cooler.balance_cooler(clr, store=True)
        os.replace(tmp, out)
    finally:
        for p in (base, tmp):
            if p.exists():
                p.unlink()
    cd.link_cool(out, key=link_key or f"{key}_pooled",
                 label=label or "Pooled, fragment pairs of the clusters",
                 cluster_size=[int(min_size), None if max_size is None else int(max_size)])
    return out
