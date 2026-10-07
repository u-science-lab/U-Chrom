"""Plotting helpers for population-level trace statistics."""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import matplotlib.pyplot as plt


def plot_distance_matrix(
    matrix: np.ndarray,
    bin_ids: Optional[Sequence] = None,
    title: Optional[str] = None,
    cmap: str = "viridis_r",
    ax=None,
):
    """Heatmap of a (n_bins, n_bins) population-mean distance matrix."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 5))
    else:
        fig = ax.figure
    im = ax.imshow(matrix, cmap=cmap, aspect="equal", origin="lower")
    ax.set_xlabel("Bin index")
    ax.set_ylabel("Bin index")
    if title:
        ax.set_title(title)
    fig.colorbar(im, ax=ax, label="Distance")
    fig.tight_layout()
    return fig


def plot_contact_map(
    matrix: np.ndarray,
    bin_ids: Optional[Sequence] = None,
    title: Optional[str] = None,
    cmap: str = "magma",
    ax=None,
):
    """Heatmap of a (n_bins, n_bins) contact frequency matrix (values in [0, 1])."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 5))
    else:
        fig = ax.figure
    im = ax.imshow(matrix, cmap=cmap, aspect="equal", origin="lower", vmin=0, vmax=1)
    ax.set_xlabel("Bin index")
    ax.set_ylabel("Bin index")
    if title:
        ax.set_title(title)
    fig.colorbar(im, ax=ax, label="Contact frequency")
    fig.tight_layout()
    return fig


def plot_rg_histogram(
    rg_series,
    bins: int = 30,
    title: Optional[str] = None,
    ax=None,
):
    """Histogram of per-trace radii of gyration."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(5.5, 3.5))
    else:
        fig = ax.figure
    values = np.asarray(rg_series).astype(float)
    values = values[~np.isnan(values)]
    ax.hist(values, bins=bins, edgecolor="black", alpha=0.8)
    ax.set_xlabel("Radius of gyration")
    ax.set_ylabel("Number of traces")
    if title:
        ax.set_title(title)
    med = float(np.median(values)) if values.size else float("nan")
    ax.axvline(med, color="red", linestyle="--", label=f"median = {med:.1f}")
    ax.legend()
    fig.tight_layout()
    return fig


__all__ = [
    "plot_distance_matrix",
    "plot_contact_map",
    "plot_rg_histogram",
]
