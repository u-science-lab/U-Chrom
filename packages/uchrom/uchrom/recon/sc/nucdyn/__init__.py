"""NucDynamics: single-cell Hi-C genome structure calculation.

``reconstruct_nucdyn(contacts, ...)`` returns a ChromData ensemble computed
by the native engine (``uchrom_recon``: Rust, multi-core CPU and wgpu GPU;
``pip install u-chrom[recon]``).  ``main`` (also ``python -m
uchrom.recon.sc.nucdyn``) is the file-level entry point.
"""

from ._cli import main
from .native import engine_info, load_contacts, native_available, reconstruct_nucdyn

__all__ = ["reconstruct_nucdyn", "main", "native_available", "engine_info", "load_contacts"]
