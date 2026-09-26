"""``uchrom.tl`` — flat, scanpy-style aliases for analysis *tools*.

Tools add annotations (structures, features, embeddings) to a
``ChromData``.  The implementations live in the domain modules
(``uchrom.strc``, ``uchrom.fea``, …); these aliases only dispatch on
``method=`` and forward every other keyword unchanged, so they follow the
same calling convention (``chrom=None``, ``params=``, ``key_added=``,
``copy=``)::

    import uchrom as uc
    uc.tl.call_tads(cd, method="arcfish")        # strc.tad.call_tads_by_pval
    uc.tl.call_loops(cd)                         # strc.loop.call_loops_axiswise_f
    uc.tl.call_compartments(cd)                  # strc.comp.call_compartments_axes_pc
"""

from __future__ import annotations

from typing import Callable, Dict


def _tad_methods() -> Dict[str, Callable]:
    from uchrom.strc.tad import call_domains_fishnet, call_tads_by_pval, call_tads_di

    return {
        "arcfish": call_tads_by_pval,
        "pval": call_tads_by_pval,
        "fishnet": call_domains_fishnet,
        "di": call_tads_di,
    }


def _dispatch(kind: str, methods: Dict[str, Callable], method: str):
    try:
        return methods[method]
    except KeyError:
        raise ValueError(f"unknown {kind} method {method!r}; choose from {sorted(methods)}") from None


def call_tads(cd, *, method: str = "arcfish", **kwargs):
    """Call TADs / domains.

    ``method``: ``"arcfish"`` (alias ``"pval"``) →
    :func:`uchrom.strc.tad.call_tads_by_pval`; ``"fishnet"`` →
    :func:`uchrom.strc.tad.call_domains_fishnet`; ``"di"`` →
    :func:`uchrom.strc.tad.call_tads_di` (linked Hi-C contacts).
    """
    return _dispatch("TAD", _tad_methods(), method)(cd, **kwargs)


def call_loops(cd, *, method: str = "axiswise_f", **kwargs):
    """Call loops.  ``method``: ``"axiswise_f"`` →
    :func:`uchrom.strc.loop.call_loops_axiswise_f`."""
    from uchrom.strc.loop import call_loops_axiswise_f

    return _dispatch("loop", {"axiswise_f": call_loops_axiswise_f}, method)(cd, **kwargs)


def call_compartments(cd, *, method: str = "axes_pc", **kwargs):
    """Call A/B compartments.  ``method``: ``"axes_pc"`` →
    :func:`uchrom.strc.comp.call_compartments_axes_pc`."""
    from uchrom.strc.comp import call_compartments_axes_pc

    return _dispatch("compartment", {"axes_pc": call_compartments_axes_pc}, method)(cd, **kwargs)


__all__ = ["call_compartments", "call_loops", "call_tads"]
