"""Native kernels of U-Chrom's Hi-C map callers (Rust, multi-core CPU).

``uchrom.strc.loop.hiccups`` (HiCCUPS) and ``uchrom.strc.loop.mustache`` (Mustache) call these kernels
when this package is installed (``pip install ./packages/uchrom-maps``, extra ``u-chrom[maps]``) and fall
back to their numpy reference otherwise.  The kernels reproduce the reference bit for bit: the same
tiles and the same order of floating-point operations (summed-area tables built as ``np.cumsum`` builds
them, Gaussians in the arithmetic of ``scipy.ndimage.correlate1d``, sums in numpy's pairwise order).

- :func:`hiccups_score` — one chromosome of HiCCUPS (``hiccups._score_chrom``): the locally adjusted
  expecteds of the four kernels, the λ-chunk histograms and the candidates;
- :func:`mustache_scan` — the Mustache scale-space scan (``mustache._scan``): best difference-of-Gaussians
  response and layer per pixel, per-layer ``|L|`` statistics;
- :func:`rwr_band` — the random walk with restart of one cell's chromosome (``uchrom.fea.impute_rwr``;
  SnapHiC / scHiCluster imputation): profile Cholesky + selected inversion per sliding window, the band of
  the imputed map; :func:`zscore_band`, :func:`local_background` — SnapHiC's per-diagonal z-scores and local
  backgrounds; :func:`snaphic_chrom` — SnapHiC's sums over the cells of one chromosome
  (``uchrom.strc.loop.snaphic``).  These solve the reference's linear systems by another factorisation:
  equal to rounding, not bit for bit;
- :func:`gaussian_filter`, :func:`pairwise_sum` — ``scipy.ndimage.gaussian_filter(mode="reflect")`` and
  ``np.sum`` in their exact arithmetic (used by the kernels; exposed for tests);
- :func:`scipy_arithmetic` — how the installed scipy accumulates its correlations (fused multiply-adds or
  not, and where a vectorised loop multiplies and adds separately: platform- and build-dependent), which
  :func:`mustache_scan` must copy to give scipy's numbers.

Tiles run in parallel with rayon: ``n_threads=0`` uses rayon's global pool (``RAYON_NUM_THREADS`` or all
cores), ``n_threads=k`` a pool of ``k`` threads.  The GIL is released while a kernel runs.
"""

from __future__ import annotations

from functools import lru_cache

from ._kernels import (  # noqa: F401
    __version__,
    default_threads,
    gaussian_filter,
    hiccups_score,
    local_background,
    mustache_scan,
    pairwise_sum,
    rwr_band,
    snaphic_chrom,
    zscore_band,
)

__all__ = ["hiccups_score", "mustache_scan", "gaussian_filter", "pairwise_sum", "scipy_arithmetic",
           "scipy_uses_fma", "default_threads", "rwr_band", "zscore_band", "local_background", "snaphic_chrom",
           "__version__"]


#: accumulation schemes tried by :func:`scipy_arithmetic`, most likely first: rounded products (expected for
#: builds without FMA instructions, e.g. the x86-64 baseline), fused multiply-adds with the first ``8 * floor(s / 8)`` of ``s >= 10`` terms unfused (clang's
#: vectorised loop in the macOS arm64 wheels), all fused, then other vector widths / thresholds
_SCHEMES = ([(False, 0, 0), (True, 8, 10), (True, 0, 0)]
            + [(True, b, m) for b in (2, 4, 8, 16) for m in range(b, 4 * b + 1) if (b, m) != (8, 10)])


@lru_cache(maxsize=None)
def scipy_arithmetic() -> dict:
    """How the installed ``scipy.ndimage.correlate1d`` accumulates a symmetric kernel of ``s`` terms:
    ``{"fma": bool, "block": int, "min_terms": int}`` — fused multiply-adds (``fma``) except for the first
    ``block * floor(s / block)`` terms when ``s >= min_terms`` (a vectorised loop that multiplies and adds
    separately); ``fma=False``: every product and sum rounded.

    Decided once per process by filtering a small random image with radii 1-40 under each candidate
    scheme and comparing with scipy (the macOS arm64 wheels of scipy 1.18: ``fma=True, block=8,
    min_terms=10``); raises ``RuntimeError`` when no scheme reproduces scipy exactly (the native Mustache
    scan would then differ from the numpy one in the last bits).
    """
    import numpy as np
    from scipy.ndimage import gaussian_filter as sp_gaussian

    rng = np.random.default_rng(12345)
    img = rng.normal(size=(43, 97)) * 10.0 ** rng.uniform(-3, 3, size=(43, 97))
    cases = []
    for radius in range(1, 41):
        sigma = radius / 2.7
        truncate = (radius + 0.25) / sigma
        w = _scipy_weights(sigma, truncate)
        cases.append((w.tolist(), sp_gaussian(img, sigma, mode="reflect", truncate=truncate)))
    for fma, block, min_terms in _SCHEMES:
        if all(np.array_equal(gaussian_filter(img, w, fma, block, min_terms), want) for w, want in cases):
            return {"fma": fma, "block": block, "min_terms": min_terms}
    raise RuntimeError("scipy.ndimage.gaussian_filter is not reproduced by any known accumulation scheme")


def scipy_uses_fma() -> bool:
    """True when the installed scipy accumulates its correlations with fused multiply-adds
    (:func:`scipy_arithmetic`)."""
    return bool(scipy_arithmetic()["fma"])


def _scipy_weights(sigma: float, truncate: float):
    """The correlation weights of ``scipy.ndimage.gaussian_filter1d(sigma, truncate=truncate)``."""
    import numpy as np

    radius = int(truncate * float(sigma) + 0.5)
    try:
        from scipy.ndimage._filters import _gaussian_kernel1d
    except ImportError:                                 # pragma: no cover - other scipy layouts
        x = np.arange(-radius, radius + 1)
        phi = np.exp(-0.5 / (sigma * sigma) * x ** 2)
        return np.ascontiguousarray((phi / phi.sum())[::-1])
    return np.ascontiguousarray(_gaussian_kernel1d(sigma, 0, radius)[::-1])
