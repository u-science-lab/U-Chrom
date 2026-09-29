"""NucDynamics: single-cell Hi-C genome structure calculation.

``reconstruct_nucdyn(contacts, ...)`` returns a ChromData ensemble computed
by the native engine (``uchrom_nucdyn``: Rust, multi-core CPU and wgpu GPU;
``pip install u-chrom[nucdyn]``).  ``main`` (also ``python -m
uchrom.recon.sc.nucdyn``) is the file-level entry point; it falls back to the
deprecated Taichi port when the native engine is not installed.
"""

from ._cli import main
from .native import engine_info, load_contacts, native_available, reconstruct_nucdyn

__all__ = ["reconstruct_nucdyn", "main", "native_available", "engine_info", "load_contacts", "Simulation"]


def __getattr__(name):
    # the Taichi port (deprecated) is imported only on demand
    if name == "Simulation":
        from .nucdyn import Simulation

        return Simulation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
