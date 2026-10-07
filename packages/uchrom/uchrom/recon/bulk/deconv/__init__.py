"""Deconvolution of population (bulk) Hi-C into a population of structures.

``deconvolve(...)`` dispatches to a method subpackage:

* ``method="igm"`` — :mod:`uchrom.recon.bulk.deconv.igm`, the A/M
  population modelling of IGM (Boninsegna et al. 2022, *Nat Methods*
  19:938; predecessor PGS, Tjong et al. 2016 *PNAS* 113:E1663, Hua et al.
  2018 *Nat Protoc* 13:915) on the native engine (``uchrom_recon``,
  protocol ``igm``; multi-core CPU or GPU).

A later ``method="pgs"`` will live next to it.  The shared Hi-C →
contact-probability preprocessing is :mod:`uchrom.recon.bulk.deconv.preprocess`.

::

    from uchrom.recon.bulk.deconv import deconvolve, preprocess_hic
    prob = preprocess_hic(cd, contacts="bulk", chroms=["chr21"])     # a ChromData with a linked Hi-C map
    pop = deconvolve(prob, method="igm", n_structures=1000, out="pop.chromdata.zarr")
    pop.get_cell("s00000")          # one structure: one trace per chromosome copy
"""

from __future__ import annotations

from typing import Any

try:  # the shared preprocessing (Hi-C -> probabilities), written separately
    from .preprocess import *  # noqa: F401,F403
except ImportError:  # pragma: no cover - module not merged yet
    pass

from .igm import IgmParams, deconvolve_igm  # noqa: F401

__all__ = ["deconvolve", "deconvolve_igm", "IgmParams", "METHODS"]

#: Available methods.
METHODS = ("igm",)


def deconvolve(data: Any = None, *, method: str = "igm", **kwargs: Any):
    """Fit a population of structures to a contact-probability matrix.

    Parameters
    ----------
    data
        The :class:`~uchrom.recon.bulk.deconv.preprocess.ProbabilityMatrix`
        of :func:`preprocess_hic` (matrix and bins), a haploid
        contact-probability matrix (``scipy.sparse`` or dense, bins × bins;
        pass ``bins=``), or a :class:`~chromdata.ChromData` whose ``bins``
        define the loci (pass the matrix as ``probabilities=``).
    method
        ``"igm"`` (default).  The remaining keywords go to the method
        (:func:`uchrom.recon.bulk.deconv.igm.deconvolve_igm`).

    Returns
    -------
    ChromData (in memory, or backed on ``out=``): one cell per structure,
    one trace per chromosome copy.
    """
    if method == "igm":
        return deconvolve_igm(data, **kwargs)
    raise ValueError(f"unknown deconvolution method {method!r}; available: {', '.join(METHODS)}")
