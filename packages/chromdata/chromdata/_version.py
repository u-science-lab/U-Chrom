"""The package version, and the version recorded with what a store or a result was written by."""

from __future__ import annotations

from importlib import metadata

__version__ = "0.1.0"


def producer_version() -> str:
    """The version recorded as ``uchrom_version`` (store attributes, result provenance): the analysis library
    ``u-chrom`` when it is installed -- it produces the results -- else ``chromdata <version>``."""
    try:
        return metadata.version("u-chrom")
    except metadata.PackageNotFoundError:
        return f"chromdata {__version__}"
