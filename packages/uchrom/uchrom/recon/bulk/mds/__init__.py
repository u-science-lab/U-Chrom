"""MDS-based 3-D structure of a bulk Hi-C map (GPU-accelerated with PyTorch).

:func:`reconstruct_mds` runs on a ``ChromData`` with a linked map (or a path) and returns the structure as a
``ChromData``; :func:`run_mds`, :func:`partitioned_mds` and :func:`inter_mds` are the matrix-level kernels.
"""

from .core import (
    contact_to_distance,
    fill_missing_distances,
    normalize_distances,
    apply_distance_decay_prior,
)
from .torch_mds import torch_mds, compute_stress, run_mds
from .partitioned import partitioned_mds
from .inter import inter_mds
from .reconstruct import reconstruct_mds
from .transforms import (
    procrustes_alignment,
    apply_transform,
    compute_radius_of_gyration,
)

__all__ = [
    'reconstruct_mds',
    'contact_to_distance',
    'fill_missing_distances',
    'normalize_distances',
    'apply_distance_decay_prior',
    'torch_mds',
    'compute_stress',
    'run_mds',
    'partitioned_mds',
    'inter_mds',
    'procrustes_alignment',
    'apply_transform',
    'compute_radius_of_gyration',
]
