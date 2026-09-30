"""Consensus 3-D structure of bulk Hi-C by hierarchical restraint annealing.

``reconstruct_consensus(data, *, method="anneal", resolution=..., params=ConsensusParams(...))``
turns one bulk contact map (``.cool`` / ``.mcool`` path or URL, a ChromData with a
linked cool, or a count matrix + bins) into **one** representative structure —
the whole genome by default, all chromosomes in one structure with
inter-chromosomal restraints — plus the per-bin spread over independent runs.

The dynamics run in the native engine (``uchrom_nucdyn``, protocol
``consensus``: NucDynamics integrator, repulsion, annealing schedule and
restraint forms of Stevens et al. 2017, *Nature* 544:59; a Lorentzian
option after Trieu & Cheng 2017, *NAR* 45:1049); the contact → restraint
conversion (power law, alpha = 4 after Wang et al. 2016, *Science* 353:598)
is done here.  No TAD partitioning: the hierarchy is a resolution ladder,
every stage interpolated from the previous one.  Design and validation:
``benchmarks/bulk/consensus/``.  The PyTorch MDS of :mod:`uchrom.recon.bulk.mds`
stays as the non-dynamics baseline.

::

    from uchrom.recon.bulk.consensus import reconstruct_consensus
    cd = reconstruct_consensus("imr90.mcool", resolution=250_000, n_runs=8)
    cd.coords                               # consensus structure
    cd.bin_tracks["consensus_spread"]       # per-bin uncertainty
"""

from ._contacts import CoolerSource, MatrixSource, fit_decay, fit_power_law
from ._params import ConsensusParams
from ._restraints import stage_ladder
from ._run import CITATIONS, METHODS, native_available, reconstruct_consensus
from ._superpose import kabsch

__all__ = ["reconstruct_consensus", "ConsensusParams", "native_available", "stage_ladder", "fit_decay",
           "fit_power_law", "kabsch", "CoolerSource", "MatrixSource", "CITATIONS", "METHODS"]
