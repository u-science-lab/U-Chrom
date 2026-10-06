"""Shared statistical / device primitives used by multiple analysis modules.

The Cauchy combination test (ACAT) and the LOWESS-on-log-log helper are the
two fundamental building blocks of the ArcFISH-style pipeline
(:mod:`uchrom.fea.arc`, :mod:`uchrom.strc.loop`, ``.tad``, ``.comp``).

Tensor-heavy code is written against PyTorch so it runs on CUDA / MPS / CPU
interchangeably; LOWESS stays on CPU via ``statsmodels`` because it is a
non-parallel kernel smoother on ~n_bins² points (small).
"""

from __future__ import annotations

import math

import numpy as np


# ----------------------------------------------------------------------
# Device
# ----------------------------------------------------------------------

def get_device(device: str = "auto"):
    """Resolve ``'auto' | 'cpu' | 'cuda' | 'mps'`` into a ``torch.device``.

    Priority for ``auto``: CUDA > MPS > CPU.  Mirrors the convention used by
    ``uchrom.recon.bulk.mds.torch_mds`` so the whole project shares one
    device-selection rule.
    """
    import torch

    if device == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(device)


def default_float_dtype(device):
    """Pick a floating dtype that the given device supports well.

    MPS only supports float32; elsewhere we default to float64 for the
    better numeric behaviour during LOWESS-normalised F-tests.
    """
    import torch

    if isinstance(device, str):
        device = torch.device(device)
    if device.type == "mps":
        return torch.float32
    return torch.float64


# ----------------------------------------------------------------------
# Cauchy combination test (ACAT, Liu & Xie 2020)
# ----------------------------------------------------------------------

def cauchy_combination(
    pvals,
    weights=None,
    axis: int = -1,
):
    """Aggregate p-values along ``axis`` using the Cauchy combination test.

    ``T = Σ_k w_k · tan((0.5 − p_k) · π)`` — ``T`` is asymptotically standard
    Cauchy under the null, so the combined p-value is ``1 − Cauchy.cdf(T)``.

    Accepts numpy arrays or torch tensors; the output matches the input
    backend.  Numerically safe clamping keeps ``p`` away from {0, 1}.

    Parameters
    ----------
    pvals : ndarray | Tensor
        Per-test p-values.  The reduction is over ``axis``.
    weights : ndarray | Tensor | None
        Non-negative weights.  If given, broadcast along ``pvals``; if None,
        uniform weights.
    axis : int
        Axis to combine along.
    """
    try:
        import torch
        if isinstance(pvals, torch.Tensor):
            return _cauchy_torch(pvals, weights, axis)
    except ImportError:
        pass
    return _cauchy_numpy(pvals, weights, axis)


def _cauchy_numpy(pvals: np.ndarray, weights, axis: int) -> np.ndarray:
    p = np.clip(np.asarray(pvals, dtype=np.float64), 1e-15, 1 - 1e-15)
    if weights is None:
        weights = np.ones(p.shape[axis], dtype=np.float64) / p.shape[axis]
    else:
        weights = np.asarray(weights, dtype=np.float64)
        wsum = np.sum(weights)
        weights = weights / max(wsum, 1e-15)
    # Broadcast weights onto the chosen axis
    shape = [1] * p.ndim
    shape[axis] = p.shape[axis]
    w = weights.reshape(shape)
    stat = np.sum(w * np.tan((0.5 - p) * np.pi), axis=axis)
    # 1 - Cauchy.cdf(stat) = 0.5 - arctan(stat)/pi
    return 0.5 - np.arctan(stat) / np.pi


def _cauchy_torch(pvals, weights, axis: int):
    import torch
    dtype = default_float_dtype(pvals.device)
    p = pvals.to(dtype).clamp(1e-7 if dtype == torch.float32 else 1e-15,
                              1 - (1e-7 if dtype == torch.float32 else 1e-15))
    n_axis = p.shape[axis]
    if weights is None:
        w = torch.full((n_axis,), 1.0 / n_axis, dtype=dtype, device=p.device)
    else:
        if not isinstance(weights, torch.Tensor):
            w = torch.as_tensor(weights, dtype=dtype, device=p.device)
        else:
            w = weights.to(dtype).to(p.device)
        wsum = w.sum().clamp(min=1e-15)
        w = w / wsum
    shape = [1] * p.ndim
    shape[axis] = n_axis
    w = w.reshape(shape)
    stat = (w * torch.tan((0.5 - p) * math.pi)).sum(dim=axis)
    return 0.5 - torch.atan(stat) / math.pi


# ----------------------------------------------------------------------
# LOWESS helpers
# ----------------------------------------------------------------------

def lowess_log_log(
    x: np.ndarray,
    y: np.ndarray,
    frac: float = 0.1,
    eps: float = 1e-12,
) -> np.ndarray:
    """LOWESS regression of ``log(y) ~ log(x)`` evaluated at the input ``x``.

    Used throughout the ArcFISH pipeline to get a "distance-stratified"
    expected value — e.g. expected per-pair variance as a smooth function of
    1D genomic separation.

    NaNs / non-positive values are ignored during fitting and yield NaN in
    the output for those entries.  Returns predictions on the *linear*
    scale (``exp`` applied).

    Parameters
    ----------
    x, y : 1D arrays
        Same length.
    frac : float
        LOWESS span (0–1).  Default 0.1 matches ArcFISH.
    eps : float
        Numerical floor to keep ``log`` defined.
    """
    import statsmodels.nonparametric.smoothers_lowess as _sm_lowess

    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.shape != y.shape:
        raise ValueError("x and y must have the same shape")
    out = np.full_like(x, np.nan, dtype=np.float64)

    mask = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
    if mask.sum() < 3:
        return out

    lx = np.log(x[mask])
    ly = np.log(y[mask])
    # Return x/y pairs sorted by x; return_sorted=False keeps input order
    smoothed = _sm_lowess.lowess(
        ly, lx, frac=frac, return_sorted=False
    )
    out[mask] = np.exp(smoothed)
    return out
