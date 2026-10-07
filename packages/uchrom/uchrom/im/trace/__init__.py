"""Spot → fiber tracing algorithms for multiplexed DNA-FISH data.

Takes detected-and-decoded spots with ambiguous trace assignments
(multiple candidate spots per genomic locus per cell) and decides which
spots belong to the same chromatin fiber.  Output is a
:class:`chromdata.ChromData` with a populated ``trace_id`` column.

The first backend, :mod:`uchrom.im.trace.jie`, is an independent
reimplementation of Jia & Ren 2022 (*Nature Biotechnology*,
doi:10.1038/s41587-022-01568-9) — a spatial genome aligner that uses
a Gaussian-chain polymer model to score candidate spot-to-fiber
assignments, then picks fibers via iterative shortest-path.
"""

from .jie import align_spots, SpotAlignerParams

__all__ = ["align_spots", "SpotAlignerParams"]
