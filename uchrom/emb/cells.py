"""Cell embeddings from per-cell features (e.g. RNA copy numbers).

:func:`embed_cells` turns a group of numeric ``cd.cells`` columns — by
default the ``rna.<gene>`` counts written by
:meth:`~uchrom.core.ChromData.from_fofct` — into PCA / t-SNE / UMAP
coordinates stored in ``cd.cellm`` (rows aligned with ``cd.cells``), with
parameters recorded in ``cd.uns["embeddings"]`` so they round-trip through
``.h5cd`` and the web browser can show them.
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

__all__ = ["embed_cells", "normalize_counts"]

_METHODS = ("pca", "tsne", "umap")


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
    x = np.log1p(x)
    sd = x.std(axis=0)
    x = (x - x.mean(axis=0)) / np.where(sd > 0, sd, 1.0)
    return x


def embed_cells(
    cd,
    *,
    source: str = "rna",
    fields: Optional[Sequence[str]] = None,
    methods: Sequence[str] = _METHODS,
    n_pcs: int = 10,
    random_state: int = 0,
    tsne_perplexity: Optional[float] = None,
    umap_neighbors: int = 15,
    umap_min_dist: float = 0.3,
    library_size: bool = False,
) -> Dict[str, np.ndarray]:
    """Compute cell embeddings and store them in ``cd.cellm``.

    Parameters
    ----------
    cd : ChromData
        Needs a non-empty ``cd.cells``; rows of the embeddings follow it.
    source : str
        Feature group; selects the numeric columns ``f"{source}.*"`` and
        names the outputs ``f"{source}_{method}"`` (``rna_pca``, …).
    fields : sequence of str, optional
        Explicit ``cd.cells`` columns to use instead of the prefix.
    methods : subset of ``("pca", "tsne", "umap")``
        UMAP needs ``umap-learn`` (``pip install "u-chrom[umap]"``); it is
        skipped with a warning when missing.
    n_pcs : int
        Principal components kept (and fed to t-SNE / UMAP).
    library_size : bool
        Divide by each cell's total before ``log1p`` (see
        :func:`normalize_counts`; off by default for targeted panels).

    Returns
    -------
    dict mapping cellm key → array (also written to ``cd.cellm``).
    """
    unknown = set(methods) - set(_METHODS)
    if unknown:
        raise ValueError(f"unknown methods {sorted(unknown)}; choose from {_METHODS}")
    cells: pd.DataFrame = cd.cells
    if len(cells) == 0:
        raise ValueError("cd.cells is empty — nothing to embed")
    if fields is None:
        fields = [c for c in cells.columns
                  if str(c).startswith(f"{source}.") and pd.api.types.is_numeric_dtype(cells[c])]
    fields = list(fields)
    if len(fields) < 2:
        raise ValueError(f"need at least 2 numeric '{source}.*' columns in cd.cells, found {len(fields)}")

    x = normalize_counts(cells[fields].to_numpy(dtype=np.float64), library_size=library_size)
    n_cells = x.shape[0]
    n_pcs = int(max(2, min(n_pcs, n_cells - 1, len(fields))))
    norm = ("library-size (median total), " if library_size else "") + "log1p, z-score per feature"
    meta_base = {"source": source, "fields": fields, "normalization": norm,
                 "random_state": int(random_state)}

    from sklearn.decomposition import PCA

    pca = PCA(n_components=n_pcs, random_state=random_state)
    pcs = pca.fit_transform(x)
    out: Dict[str, np.ndarray] = {}
    registry = dict(cd.uns.get("embeddings") or {})

    def store(method: str, arr: np.ndarray, label: str, axis: str, **extra) -> None:
        key = f"{source}_{method}"
        cd.cellm[key] = np.asarray(arr, dtype=np.float64)
        registry[key] = {**meta_base, "method": method, "label": label,
                         "axis_prefix": axis, **extra}
        out[key] = cd.cellm[key]

    if "pca" in methods:
        store("pca", pcs, f"{source.upper()} PCA", "PC", n_components=n_pcs,
              explained_variance_ratio=[float(v) for v in pca.explained_variance_ratio_])
    if "tsne" in methods:
        from sklearn.manifold import TSNE

        perplexity = tsne_perplexity or float(min(30.0, max(2.0, (n_cells - 1) / 3)))
        emb = TSNE(n_components=2, perplexity=perplexity, init="pca",
                   random_state=random_state).fit_transform(pcs)
        store("tsne", emb, f"{source.upper()} t-SNE", "tSNE", perplexity=perplexity, input="pca")
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
                emb = reducer.fit_transform(pcs)
            store("umap", emb, f"{source.upper()} UMAP", "UMAP", n_neighbors=int(reducer.n_neighbors),
                  min_dist=float(umap_min_dist), input="pca")

    cd.uns["embeddings"] = registry
    return out


def embedding_keys(cd) -> List[str]:
    """cellm keys usable as 2-D embeddings (≥ 2 columns, one row per cell)."""
    n = len(cd.cells)
    return [k for k, v in cd.cellm.items()
            if np.ndim(v) == 2 and np.shape(v)[1] >= 2 and (n == 0 or np.shape(v)[0] == n)]
