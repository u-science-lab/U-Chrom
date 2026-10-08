"""A/B compartment detection from chromatin-tracing data, and from linked Hi-C maps (cis eigenvector,
saddle strength)."""

from .axes_pc import call_compartments_axes_pc, compartment_segments, CompartmentCallerParams
from .single_cell import ScABParams, normalize_scab, scab_sums, single_cell_compartments
from .eig import (
    EigCompartmentParams,
    SaddleParams,
    call_compartments_eig,
    cis_eigs,
    compartment_strength,
    saddle_strength,
)
from .hic_pc1 import (
    HiCCompartmentParams,
    call_compartments_hic,
    compare_compartments,
    hic_compartment_pc1,
)

__all__ = [
    "call_compartments_axes_pc",
    "call_compartments_eig",
    "call_compartments_hic",
    "cis_eigs",
    "compare_compartments",
    "compartment_segments",
    "compartment_strength",
    "saddle_strength",
    "single_cell_compartments",
    "scab_sums",
    "normalize_scab",
    "CompartmentCallerParams",
    "EigCompartmentParams",
    "HiCCompartmentParams",
    "SaddleParams",
    "ScABParams",
    "hic_compartment_pc1",
]
