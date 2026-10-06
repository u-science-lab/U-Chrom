"""Joint Hi-C + FISH 3D chromosome reconstruction.

First backend: :mod:`uchrom.recon.fish.gem_fish` — independent PyTorch
reimplementation of Abbas et al. 2019 (*Nature Communications*,
doi:10.1038/s41467-019-10005-6), GEM-FISH.

Unlike the Hi-C-only reconstructors in :mod:`uchrom.recon.sc` and
:mod:`uchrom.recon.bulk`, this module consumes both a Hi-C matrix and
a FISH-derived pairwise-distance / Rg measurement (e.g. from a
:class:`~chromdata.ChromData` loaded via
:func:`~chromdata.ChromData.from_fofct`) and solves a joint
optimisation over the 3-D coordinates.
"""

from .gem_fish import reconstruct_gem_fish, GEMFISHParams

__all__ = ["reconstruct_gem_fish", "GEMFISHParams"]
