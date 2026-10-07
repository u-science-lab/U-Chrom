"""A/B compartment detection from chromatin-tracing data, and from linked Hi-C as the reference."""

from .axes_pc import call_compartments_axes_pc, compartment_segments, CompartmentCallerParams
from .hic_pc1 import (
    HiCCompartmentParams,
    call_compartments_hic,
    compare_compartments,
    hic_compartment_pc1,
)

__all__ = [
    "call_compartments_axes_pc",
    "call_compartments_hic",
    "compare_compartments",
    "compartment_segments",
    "CompartmentCallerParams",
    "HiCCompartmentParams",
    "hic_compartment_pc1",
]
