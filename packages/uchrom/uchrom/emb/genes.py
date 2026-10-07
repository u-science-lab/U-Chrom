"""Genes for a cell embedding: highly variable genes of a count matrix, added to ``cd.cells``.

:func:`highly_variable_genes` ranks the genes of a cells × genes count matrix (Seurat v1 "mean.var.plot":
log-normalise, then z-score the dispersion within bins of mean expression).  :func:`add_gene_counts` reads
the count matrix linked to a ``ChromData`` (``cd.linked_adata``: a linked ``.h5ad`` or the copy embedded
in an atlas store), picks genes and writes their counts as ``rna.<gene>`` columns of ``cd.cells`` — what
:func:`uchrom.emb.embed_cells` (``source="rna"``) and :func:`uchrom.emb.marker_features` read.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import numpy as np
import pandas as pd

__all__ = ["highly_variable_genes", "add_gene_counts"]


def _as_csr(counts):
    import scipy.sparse as sp

    return counts.tocsr().astype(np.float64) if sp.issparse(counts) else sp.csr_matrix(np.asarray(counts, dtype=np.float64))


def _hvg_stats(x, n_bins: int, min_frac: float) -> pd.DataFrame:
    """Per gene: mean and log dispersion of the log-normalised counts, the dispersion z-scored within
    ``n_bins`` equal-width bins of the mean (genes detected in fewer than ``min_frac`` of the cells get
    ``-inf``)."""
    import scipy.sparse as sp

    totals = np.asarray(x.sum(1)).ravel()
    norm = sp.diags(1e4 / np.maximum(totals, 1e-12)) @ x
    norm.data = np.log1p(norm.data)
    mean = np.asarray(norm.mean(0)).ravel()
    var = np.asarray(norm.multiply(norm).mean(0)).ravel() - mean ** 2
    disp = np.log(np.maximum(var, 1e-12) / np.maximum(mean, 1e-12))
    frac = np.asarray((x > 0).mean(0)).ravel()
    ok = frac >= min_frac
    frame = pd.DataFrame({"disp": disp, "bin": pd.cut(mean, n_bins)})
    stats = frame[ok].groupby("bin", observed=True)["disp"].agg(["mean", "std"])
    z = (disp - frame["bin"].map(stats["mean"]).astype(float)) / frame["bin"].map(stats["std"]).astype(float)
    z = np.where(ok & np.isfinite(z), z, -np.inf)
    return pd.DataFrame({"mean": mean, "dispersion": disp, "dispersion_z": z, "frac_cells": frac})


def highly_variable_genes(counts, *, n_top: int = 2000, n_bins: int = 20, min_frac: float = 0.01) -> np.ndarray:
    """Rank genes by their normalised dispersion (Seurat v1, "mean.var.plot").

    Each cell's counts are scaled to 10,000 and ``log1p``-transformed; per gene, the dispersion
    ``log(variance / mean)`` is z-scored within ``n_bins`` equal-width bins of the mean.  Genes detected
    (count > 0) in fewer than ``min_frac`` of the cells are left out.

    Parameters
    ----------
    counts : array or scipy.sparse matrix
        Cells × genes raw counts.
    n_top : int
        Number of genes returned.
    n_bins : int
        Bins of mean expression the dispersion is standardised in.
    min_frac : float
        Minimum fraction of cells in which a gene is detected.

    Returns
    -------
    numpy.ndarray
        Column indices of the ``n_top`` most variable genes, most variable first (fewer when fewer genes
        pass ``min_frac``).
    """
    return _top(_hvg_stats(_as_csr(counts), n_bins, min_frac), n_top)


def _top(stats: pd.DataFrame, n_top: int) -> np.ndarray:
    z = stats["dispersion_z"].to_numpy()
    top = np.argsort(-z)[:int(n_top)]
    return top[np.isfinite(z[top])]


def add_gene_counts(
    cd,
    genes: Optional[Sequence[str]] = None,
    *,
    n_top: int = 2000,
    n_bins: int = 20,
    min_frac: float = 0.01,
    prefix: str = "rna",
    replace: bool = True,
    adata=None,
) -> List[str]:
    """Write per-cell counts of genes from the linked count matrix as ``cd.cells`` columns ``rna.<gene>``.

    The counts come from ``cd.linked_adata`` (an ``.h5ad`` linked with the store, or the copy embedded in
    an atlas store, read on first access); its rows are matched to ``cd.cells`` by cell id.  Without
    ``genes`` the :func:`highly_variable_genes` of ``cd``'s cells are taken.

    Parameters
    ----------
    cd : ChromData
        With a ``cells`` table and a linked AnnData (cells × genes counts in ``X``).
    genes : sequence of str, optional
        Genes to add (``var_names``); default: the ``n_top`` highly variable genes of the cells of ``cd``.
    n_top, n_bins, min_frac
        See :func:`highly_variable_genes`.
    prefix : str
        Column names are ``f"{prefix}.{gene}"``.
    replace : bool
        Drop the ``cd.cells`` columns that already start with ``f"{prefix}."`` (e.g. a smaller gene panel
        stored with the data), so that ``embed_cells(cd, source=prefix)`` uses only the new genes.
    adata : AnnData, optional
        A count matrix to use instead of ``cd.linked_adata``.

    Returns
    -------
    list of str
        The genes added, in the order of their columns (most variable first).  The selection is recorded
        in ``cd.results[f"{prefix}.genes"]`` (per gene: mean, dispersion and its z-score, fraction of cells).
    """
    linked = adata is None
    adata = cd.linked_adata if linked else adata
    if adata is None:
        raise ValueError("cd has no linked AnnData (cd.uns['linked_anndata']); pass adata=")
    ids = pd.Index([str(c) for c in cd.cells.index])
    obs = pd.Index([str(c) for c in adata.obs_names])
    pos = obs.get_indexer(ids)
    found = pos >= 0
    if not found.any():
        raise KeyError("no cell of cd.cells is in the linked AnnData (obs_names)")
    if not found.all():
        import warnings

        warnings.warn(f"{int((~found).sum())} cells have no row in the linked AnnData: their counts are NaN",
                      stacklevel=2)
    x = _as_csr(adata.X[pos[found]])
    var = pd.Index([str(g) for g in adata.var_names])
    if genes is None:
        stats = _hvg_stats(x, n_bins, min_frac)
        idx = _top(stats, n_top)
        table = stats.iloc[idx].reset_index(drop=True)
        params = {"selection": "highly variable (Seurat v1 dispersion)", "n_top": int(n_top),
                  "n_bins": int(n_bins), "min_frac": float(min_frac)}
    else:
        idx = var.get_indexer([str(g) for g in genes])
        if (idx < 0).any():
            missing = [g for g, i in zip(genes, idx) if i < 0]
            raise KeyError(f"genes not in the linked AnnData: {missing[:5]}")
        table = pd.DataFrame(index=pd.RangeIndex(len(idx)))
        params = {"selection": "given"}
    names = _unique([var[i] for i in idx])
    values = np.full((len(ids), len(idx)), np.nan)
    values[found] = x[:, idx].toarray()
    cols = [f"{prefix}.{g}" for g in names]
    frame = pd.DataFrame(values, index=cd.cells.index, columns=cols)
    keep = [c for c in cd.cells.columns
            if c not in frame.columns and not (replace and str(c).startswith(f"{prefix}."))]
    cd.cells = pd.concat([cd.cells[keep], frame], axis=1)
    table.insert(0, "gene", names)
    cd.results.set(f"{prefix}.genes", table, kind="table", function="uchrom.emb.add_gene_counts",
                   params={**params, "prefix": prefix, "replace": bool(replace)},
                   inputs={"counts": "linked_anndata" if linked else "adata",
                           "n_cells": int(found.sum()), "n_genes_in_matrix": int(len(var))})
    return names


def _unique(names: List[str]) -> List[str]:
    """Gene names made unique (a repeated name gets ``-1``, ``-2``, ... as AnnData's ``var_names_make_unique``)."""
    seen: dict = {}
    out = []
    for g in names:
        if g in seen:
            seen[g] += 1
            out.append(f"{g}-{seen[g]}")
        else:
            seen[g] = 0
            out.append(g)
    return out
