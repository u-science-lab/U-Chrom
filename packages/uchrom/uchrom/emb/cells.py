"""Cell embeddings from per-cell features of any modality.

:func:`embed_cells` turns a group of numeric ``cd.cells`` columns — the
``rna.<gene>`` counts written by :meth:`~chromdata.ChromData.from_fofct`,
``if.<mark>`` immunofluorescence summaries from :func:`aggregate_tracks`,
``atac.<gene>`` accessibility, … — or an explicit cells × features matrix
into PCA (or LSI) / t-SNE / UMAP coordinates stored in ``cd.cellm`` (rows
aligned with ``cd.cells``).  Parameters, including the normalisation, are
recorded in ``cd.uns["embeddings"]`` so they round-trip through ChromData files
and the web browser can group the embeddings by modality.

Normalisations (``normalization=``; ``"auto"`` picks one from ``source``):

``"counts"``  (``rna`` and unknown prefixes)
    ``log1p`` then z-score per feature (optionally library-size first).
``"zscore"``  (``if``, ``protein``, ``ab``)
    continuous intensities: z-score per feature, ``log=True`` adds ``log1p``.
``"tfidf"``  (``atac``)
    sparse accessibility: TF-IDF → truncated SVD (latent semantic indexing);
    component 1 is dropped when it tracks sequencing depth.
``"none"``
    features used as given (already normalised, e.g. Hi-C vectors).
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd

__all__ = ["embed_cells", "cluster_cells", "marker_features", "normalize_counts", "tfidf_lsi",
           "aggregate_tracks",
           "MODALITY_LABELS"]

_METHODS = ("pca", "tsne", "umap")
_NORMS = ("auto", "counts", "zscore", "tfidf", "none")

#: display name of each feature prefix (the browser groups embeddings by it): chromdata's naming convention
from chromdata.conventions import MODALITY_LABELS  # noqa: E402


def _auto_norm(source: str) -> str:
    if source == "atac":
        return "tfidf"
    if source in ("if", "protein", "ab"):
        return "zscore"
    if source == "hic":
        return "none"
    return "counts"


def _zscore(x: np.ndarray) -> np.ndarray:
    sd = x.std(axis=0)
    return (x - x.mean(axis=0)) / np.where(sd > 0, sd, 1.0)


def normalize_counts(counts: np.ndarray, *, library_size: bool = False) -> np.ndarray:
    """``log1p`` and z-score each feature (optionally library-size first).

    ``library_size=False`` (default) suits small targeted panels (seqFISH,
    MERFISH): there one or two housekeeping genes dominate the total, so
    dividing by it turns PC1 into "that gene vs the rest" (on Takei 2021,
    Eef2 ≈ 16 % of all counts).  Use ``True`` for transcriptome-wide data.
    Constant features become zero.
    """
    x = np.asarray(counts, dtype=np.float64)
    x = np.where(np.isfinite(x), x, 0.0)
    if library_size:
        totals = x.sum(axis=1, keepdims=True)
        scale = float(np.median(totals[totals > 0])) if (totals > 0).any() else 1.0
        with np.errstate(invalid="ignore", divide="ignore"):
            x = np.where(totals > 0, x / totals * scale, 0.0)
    return _zscore(np.log1p(x))


def tfidf_lsi(x, n_components: int = 30, *, depth: Optional[np.ndarray] = None,
              drop_depth_r: float = 0.5, random_state: int = 0):
    """TF-IDF + truncated SVD (LSI) of a cells × features count matrix.

    Follows Signac's ``RunTFIDF`` (method 1: ``log1p(tf · idf · 1e4)``, tf =
    count / cell total, idf = n_cells / feature total) and ``RunSVD`` (each
    component scaled to mean 0, sd 1).  Dense or ``scipy.sparse`` input;
    sparse stays sparse.

    Component 1 of scATAC LSI usually tracks sequencing depth.  It is
    dropped when ``|Pearson r(component, log depth)| > drop_depth_r`` (only
    component 1 is tested; pass ``drop_depth_r=None`` to keep all).

    Returns
    -------
    (lsi, info) — lsi: (n_cells, n_kept) array; info: dict with
    ``depth_r`` (per component), ``dropped`` (1-based component numbers),
    ``explained_variance_ratio``.
    """
    import scipy.sparse as sp
    from sklearn.decomposition import TruncatedSVD

    x = sp.csr_matrix(x, dtype=np.float64) if not sp.issparse(x) else x.tocsr().astype(np.float64)
    n_cells, n_feat = x.shape
    totals = np.asarray(x.sum(axis=1)).ravel()
    col = np.asarray(x.sum(axis=0)).ravel()
    keep = col > 0
    x = x[:, keep]
    col = col[keep]
    idf = n_cells / col
    tf = sp.diags(1.0 / np.maximum(totals, 1e-12)) @ x
    y = (tf @ sp.diags(idf)).tocsr()
    y.data = np.log1p(y.data * 1e4)
    k = int(max(2, min(n_components + 1, n_cells - 1, y.shape[1] - 1)))
    svd = TruncatedSVD(n_components=k, algorithm="randomized", random_state=random_state)
    comps = svd.fit_transform(y)
    comps = _zscore(comps)
    d = np.log1p(totals if depth is None else np.asarray(depth, dtype=np.float64))
    depth_r = [float(np.corrcoef(comps[:, j], d)[0, 1]) if np.std(d) > 0 else 0.0
               for j in range(comps.shape[1])]
    dropped: List[int] = []
    if drop_depth_r is not None and abs(depth_r[0]) > drop_depth_r:
        dropped = [1]
    kept = [j for j in range(comps.shape[1]) if (j + 1) not in dropped][:n_components]
    info = {"depth_r": depth_r, "dropped": dropped,
            "explained_variance_ratio": [float(v) for v in svd.explained_variance_ratio_],
            "n_features_used": int(keep.sum())}
    return comps[:, kept], info


def aggregate_tracks(cd, fields: Optional[Sequence[str]] = None, *, prefix: str = "if",
                     stat: str = "mean", by: Union[None, str, int] = None,
                     min_spots: int = 1, write: bool = True) -> pd.DataFrame:
    """Summarise tracks (``cd.spot_tracks`` + ``cd.bin_tracks`` seen per
    spot) into per-cell features.

    Parameters
    ----------
    cd : ChromData
        With tracks and a ``cell_id`` column in ``cd.spots``.
    fields : sequence of str, optional
        Track columns to use (default: every numeric track).
    prefix : str
        Output columns are named ``f"{prefix}.{field}"``.
    stat : ``"mean"``, ``"median"``, ``"std"`` or ``"corr"``
        Per-cell statistic.  ``"corr"`` gives the within-cell Pearson
        correlation of every pair of fields (``f"{prefix}.{a}~{b}"``) — how
        marks co-occur on the same loci, which is insensitive to per-cell
        intensity scaling.
    by : None, ``"chrom"`` or int
        Also split by chromosome (``…@chr1``) or by genomic bins of this
        many bp (``…@chr1:10`` = 10th bin); not with ``stat="corr"``.
    min_spots : int
        Groups with fewer spots become NaN.
    write : bool
        Add the columns to ``cd.cells`` (replacing ones of the same name).

    Returns
    -------
    DataFrame indexed like ``cd.cells`` (cells without spots are NaN).
    """
    if stat not in ("mean", "median", "std", "corr"):
        raise ValueError("stat must be 'mean', 'median', 'std' or 'corr'")
    if "cell_id" not in cd.spots.columns:
        raise ValueError("cd.spots has no cell_id column")
    tracks = cd.tracks_spot_view()
    if fields is None:
        fields = [c for c in tracks.columns if pd.api.types.is_numeric_dtype(tracks[c])]
    fields = [str(f) for f in fields]
    missing = [f for f in fields if f not in tracks.columns]
    if missing:
        raise KeyError(f"unknown track(s): {missing[:5]}")
    cells_index = cd.cells.index.astype(str) if len(cd.cells) else None
    cell = cd.spots["cell_id"].astype(str).to_numpy()
    vals = tracks[fields].to_numpy(dtype=np.float64)

    if stat == "corr":
        if by is not None:
            raise ValueError("by= is not supported with stat='corr'")
        iu = np.triu_indices(len(fields), 1)
        names = [f"{prefix}.{fields[a]}~{fields[b]}" for a, b in zip(*iu)]
        order = np.argsort(cell, kind="stable")
        uniq, starts = np.unique(cell[order], return_index=True)
        bounds = np.r_[starts, len(order)]
        rows = np.full((len(uniq), len(names)), np.nan)
        for i in range(len(uniq)):
            block = vals[order[bounds[i]:bounds[i + 1]]]
            block = block[np.isfinite(block).all(axis=1)]
            if len(block) >= max(3, min_spots):
                with np.errstate(invalid="ignore", divide="ignore"):
                    rows[i] = np.corrcoef(block.T)[iu]
        out = pd.DataFrame(rows, index=pd.Index(uniq, name="cell_id"), columns=names)
    else:
        df = pd.DataFrame(vals, columns=fields)
        keys = [pd.Series(cell, name="cell_id")]
        if by == "chrom":
            keys.append(pd.Series("@" + cd.spots["chrom"].astype(str).to_numpy(), name="grp"))
        elif isinstance(by, (int, np.integer)) and not isinstance(by, bool):
            b = cd.spots["start"].to_numpy() // int(by)
            keys.append(pd.Series("@" + cd.spots["chrom"].astype(str).to_numpy() + ":" + b.astype(str),
                                  name="grp"))
        elif by is not None:
            raise ValueError("by must be None, 'chrom' or a bin size in bp")
        grouped = df.groupby(keys, observed=True, sort=False)
        out = getattr(grouped, stat)()
        n = grouped.size()
        out[n.to_numpy() < min_spots] = np.nan
        if by is None:
            out.columns = [f"{prefix}.{f}" for f in fields]
        else:
            out = out.unstack("grp")
            out.columns = [f"{prefix}.{f}{g}" for f, g in out.columns]
            out = out[sorted(out.columns, key=_natural)]
        out.index.name = "cell_id"
    if cells_index is not None:
        out = out.reindex(cells_index)
        out.index = cd.cells.index
    if write:
        if len(cd.cells) == 0:
            raise ValueError("cd.cells is empty — create it before writing features")
        keep = [c for c in cd.cells.columns if c not in out.columns]
        cd.cells = pd.concat([cd.cells[keep], out], axis=1)
    return out


def _natural(s: str):
    import re

    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def embed_cells(
    cd,
    *,
    source: str = "rna",
    fields: Optional[Sequence[str]] = None,
    matrix=None,
    normalization: str = "auto",
    log: bool = False,
    methods: Sequence[str] = _METHODS,
    n_pcs: int = 10,
    n_lsi: int = 30,
    drop_depth_r: Optional[float] = 0.5,
    random_state: int = 0,
    tsne_perplexity: Optional[float] = None,
    umap_neighbors: int = 15,
    umap_min_dist: float = 0.3,
    library_size: bool = False,
    modality: Optional[str] = None,
    features: Optional[str] = None,
) -> Dict[str, np.ndarray]:
    """Compute cell embeddings and store them in ``cd.cellm``.

    Parameters
    ----------
    cd : ChromData
        Needs a non-empty ``cd.cells``; rows of the embeddings follow it.
    source : str
        Feature group; selects the numeric columns ``f"{source}.*"`` and
        names the outputs ``f"{source}_{method}"`` (``rna_pca``, ``if_umap``,
        ``atac_lsi``, …).
    fields : sequence of str, optional
        Explicit ``cd.cells`` columns to use instead of the prefix.
    matrix : array or scipy.sparse matrix, optional
        cells × features input instead of ``cd.cells`` columns (rows in
        ``cd.cells`` order) — e.g. a genome-wide ATAC bin matrix too large
        to keep as cell columns.  Describe it with ``features=``.
    normalization : ``"auto"``, ``"counts"``, ``"zscore"``, ``"tfidf"``, ``"none"``
        See the module docstring.  ``"auto"``: ``atac`` → tfidf, ``if`` /
        ``protein`` → zscore, ``hic`` → none, anything else → counts.
    log : bool
        ``"zscore"`` only: ``log1p`` first (needs non-negative intensities).
    methods : subset of ``("pca", "tsne", "umap")``
        With ``"tfidf"`` the linear step is LSI and is stored as
        ``f"{source}_lsi"``.  UMAP needs ``umap-learn``
        (``pip install "u-chrom[umap]"``); it is skipped with a warning when
        missing.  t-SNE and UMAP run on the PCs / LSI components.
    n_pcs : int
        Principal components kept (and fed to t-SNE / UMAP).
    n_lsi : int
        LSI components kept (``"tfidf"``).
    drop_depth_r : float or None
        ``"tfidf"``: drop LSI component 1 if ``|r(component, log depth)|``
        exceeds this.
    library_size : bool
        ``"counts"``: divide by each cell's total before ``log1p`` (see
        :func:`normalize_counts`; off by default for targeted panels).
    modality : str, optional
        Display name (default from :data:`MODALITY_LABELS`, e.g. ``atac`` →
        ``"ATAC"``); the browser groups embeddings by it.
    features : str, optional
        Free-text description of the features, recorded in the metadata.

    Returns
    -------
    dict mapping cellm key → array (also written to ``cd.cellm``).
    """
    unknown = set(methods) - set(_METHODS)
    if unknown:
        raise ValueError(f"unknown methods {sorted(unknown)}; choose from {_METHODS}")
    if normalization not in _NORMS:
        raise ValueError(f"unknown normalization {normalization!r}; choose from {_NORMS}")
    norm_kind = _auto_norm(source) if normalization == "auto" else normalization
    cells: pd.DataFrame = cd.cells
    if len(cells) == 0:
        raise ValueError("cd.cells is empty — nothing to embed")

    import scipy.sparse as sp

    if matrix is not None:
        if fields is not None:
            raise ValueError("pass either fields= or matrix=, not both")
        x = matrix if sp.issparse(matrix) else np.asarray(matrix, dtype=np.float64)
        if x.ndim != 2 or x.shape[0] != len(cells):
            raise ValueError(f"matrix must be (n_cells={len(cells)}, n_features), got {x.shape}")
        field_list: Optional[List[str]] = None
        n_features = int(x.shape[1])
    else:
        if fields is None:
            fields = [c for c in cells.columns
                      if str(c).startswith(f"{source}.") and pd.api.types.is_numeric_dtype(cells[c])]
        field_list = [str(f) for f in fields]
        if len(field_list) < 2:
            raise ValueError(f"need at least 2 numeric '{source}.*' columns in cd.cells, "
                             f"found {len(field_list)}")
        x = cells[field_list].to_numpy(dtype=np.float64)
        n_features = len(field_list)
    if n_features < 2:
        raise ValueError("need at least 2 features")
    n_cells = x.shape[0]

    extra_linear: Dict = {}
    if norm_kind == "tfidf":
        lin, info = tfidf_lsi(x, n_components=n_lsi, drop_depth_r=drop_depth_r,
                              random_state=random_state)
        norm = ("TF-IDF (log1p(tf·idf·1e4)) + truncated SVD (LSI), components scaled; "
                + (f"component 1 dropped (r with log depth = {info['depth_r'][0]:.2f})"
                   if info["dropped"] else "all components kept"))
        extra_linear = {"n_components": int(lin.shape[1]), "dropped_components": info["dropped"],
                        "depth_r": info["depth_r"],
                        "explained_variance_ratio": info["explained_variance_ratio"]}
        lin_method, lin_axis, lin_name = "lsi", "LSI", "LSI"
    else:
        x = x.toarray() if sp.issparse(x) else x
        x = np.where(np.isfinite(x), x, np.nan)
        # missing values (e.g. a chromosome without spots) → feature mean
        if np.isnan(x).any():
            mu = np.nanmean(x, axis=0)
            x = np.where(np.isnan(x), np.where(np.isfinite(mu), mu, 0.0)[None, :], x)
        if norm_kind == "counts":
            x = normalize_counts(x, library_size=library_size)
            norm = ("library-size (median total), " if library_size else "") + "log1p, z-score per feature"
        elif norm_kind == "zscore":
            if log:
                if (x < 0).any():
                    raise ValueError("log=True needs non-negative intensities")
                x = np.log1p(x)
            x = _zscore(x)
            norm = ("log1p, " if log else "") + "z-score per feature"
        else:
            norm = "none (features used as given)"
        from sklearn.decomposition import PCA

        k = int(max(2, min(n_pcs, n_cells - 1, n_features)))
        pca = PCA(n_components=k, random_state=random_state)
        lin = pca.fit_transform(x)
        extra_linear = {"n_components": k,
                        "explained_variance_ratio": [float(v) for v in pca.explained_variance_ratio_]}
        lin_method, lin_axis, lin_name = "pca", "PC", "PCA"

    mod = modality or MODALITY_LABELS.get(source, source.upper())
    meta_base = {"source": source, "modality": mod, "normalization": norm,
                 "normalization_kind": norm_kind, "n_features": n_features,
                 "random_state": int(random_state)}
    if field_list is not None:
        meta_base["fields"] = field_list
    if features:
        meta_base["features"] = str(features)

    out: Dict[str, np.ndarray] = {}
    registry = dict(cd.uns.get("embeddings") or {})

    def store(method: str, arr: np.ndarray, pretty: str, axis: str, **extra) -> None:
        key = f"{source}_{method}"
        cd.cellm[key] = np.asarray(arr, dtype=np.float64)
        registry[key] = {**meta_base, "method": method, "label": f"{mod} {pretty}",
                         "axis_prefix": axis, **extra}
        out[key] = cd.cellm[key]

    if "pca" in methods:
        store(lin_method, lin, lin_name, lin_axis, **extra_linear)
    if "tsne" in methods:
        from sklearn.manifold import TSNE

        perplexity = tsne_perplexity or float(min(30.0, max(2.0, (n_cells - 1) / 3)))
        emb = TSNE(n_components=2, perplexity=perplexity, init="pca",
                   random_state=random_state).fit_transform(lin)
        store("tsne", emb, "t-SNE", "tSNE", perplexity=perplexity, input=lin_method)
    if "umap" in methods:
        try:
            import umap  # noqa: F401
        except ImportError:
            warnings.warn("umap-learn is not installed; skipping UMAP "
                          "(pip install 'u-chrom[umap]')", stacklevel=2)
        else:
            reducer = umap.UMAP(n_neighbors=min(umap_neighbors, n_cells - 1),
                                min_dist=umap_min_dist, random_state=random_state)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # umap's n_jobs / numba chatter
                emb = reducer.fit_transform(lin)
            store("umap", emb, "UMAP", "UMAP", n_neighbors=int(reducer.n_neighbors),
                  min_dist=float(umap_min_dist), input=lin_method)

    cd.uns["embeddings"] = registry
    return out


def cluster_cells(cd, *, use: str = "rna_pca", n_neighbors: int = 15, resolution: float = 1.0,
                  n_components: Optional[int] = None, random_state: int = 0,
                  key_added: Optional[str] = None) -> pd.Series:
    """Leiden clusters of the cells from an embedding in ``cd.cellm``.

    A k-nearest-neighbour graph (``n_neighbors``, Euclidean, symmetrised) of
    ``cd.cellm[use]`` (first ``n_components`` columns) is partitioned with
    the Leiden algorithm (``leidenalg``, RB configuration model at
    ``resolution``, seeded).  Clusters are numbered ``"0", "1", …`` by
    decreasing size and stored as a categorical column
    ``cd.cells[key_added]`` (default ``f"leiden_{use}"``); the parameters go
    to ``cd.uns["clusters"][key_added]``.  Needs ``leidenalg`` and
    ``python-igraph`` (``pip install leidenalg``).

    Returns the cluster labels (a Series indexed like ``cd.cells``).
    """
    try:
        import igraph as ig
        import leidenalg
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("cluster_cells needs leidenalg and python-igraph "
                          "(pip install leidenalg)") from exc
    from sklearn.neighbors import NearestNeighbors

    if use not in cd.cellm:
        raise KeyError(f"cd.cellm has no {use!r}; available: {sorted(cd.cellm)}")
    x = np.asarray(cd.cellm[use], dtype=np.float64)
    if n_components is not None:
        x = x[:, :int(n_components)]
    n = len(x)
    if n != len(cd.cells):
        raise ValueError(f"cellm[{use!r}] has {n} rows, cells {len(cd.cells)}")
    k = int(min(n_neighbors, n - 1))
    nn = NearestNeighbors(n_neighbors=k + 1).fit(x)
    idx = nn.kneighbors(x, return_distance=False)[:, 1:]
    src = np.repeat(np.arange(n), k)
    dst = idx.ravel()
    pairs = np.unique(np.sort(np.stack([src, dst], axis=1), axis=1), axis=0)
    g = ig.Graph(n=n, edges=pairs.tolist(), directed=False)
    part = leidenalg.find_partition(g, leidenalg.RBConfigurationVertexPartition,
                                    resolution_parameter=float(resolution), seed=int(random_state),
                                    n_iterations=-1)
    memb = np.asarray(part.membership)
    sizes = np.bincount(memb)
    rank = np.empty_like(sizes)
    rank[np.argsort(-sizes, kind="stable")] = np.arange(len(sizes))
    labels = rank[memb].astype(str)
    key = key_added or f"leiden_{use}"
    cats = [str(i) for i in range(len(sizes))]
    s = pd.Series(pd.Categorical(labels, categories=cats), index=cd.cells.index, name=key)
    cd.cells[key] = s
    reg = dict(cd.uns.get("clusters") or {})
    reg[key] = {"method": "leiden", "use": use, "n_neighbors": k, "resolution": float(resolution),
                "n_components": None if n_components is None else int(n_components),
                "random_state": int(random_state), "n_clusters": int(len(sizes)),
                "function": "uchrom.emb.cluster_cells"}
    cd.uns["clusters"] = reg
    return s


def marker_features(cd, groups: Union[str, pd.Series], *, prefix: str = "rna.", n_top: int = 5,
                    log: bool = True) -> Dict[str, List[str]]:
    """Top features of each group of cells: the ``prefix`` columns of
    ``cd.cells`` ranked by the difference of the mean (``log1p`` when
    ``log``) between the group and the other cells."""
    lab = cd.cells[groups] if isinstance(groups, str) else pd.Series(groups, index=cd.cells.index)
    lab = lab.astype(str)
    cols = [c for c in cd.cells.columns if str(c).startswith(prefix)]
    x = cd.cells[cols].to_numpy(dtype=np.float64)
    if log:
        x = np.log1p(np.clip(x, 0, None))
    out: Dict[str, List[str]] = {}
    for g in pd.unique(lab):
        m = (lab == g).to_numpy()
        diff = x[m].mean(axis=0) - x[~m].mean(axis=0)
        out[str(g)] = [str(cols[i])[len(prefix):] for i in np.argsort(-diff)[:n_top]]
    return out
