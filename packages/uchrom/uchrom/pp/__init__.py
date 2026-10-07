"""``uchrom.pp`` — flat, scanpy-style aliases for *preprocessing*.

Preprocessing changes coordinates / spots (impute, align, normalise,
rebin).  The implementations live in the domain modules; these aliases
forward to them::

    import uchrom as uc
    cd_imputed = uc.pp.impute(cd, method="snapfish")   # im.impute.impute_coordinates
    traced = uc.pp.align_spots(detections)             # im.trace.align_spots (jie)
    merged = uc.pp.merge_duplicate_spots(cd)           # im.merge_duplicate_spots
"""

from __future__ import annotations


def impute(cd, *, method: str = "linear", **kwargs):
    """Impute missing coordinates — :func:`uchrom.im.impute.impute_coordinates`.

    ``method``: ``"linear"``, ``"cubic"`` or ``"snapfish"``.  Returns the
    imputed ``ChromData`` (the input is not modified).
    """
    from uchrom.im.impute import impute_coordinates

    return impute_coordinates(cd, method=method, **kwargs)


def align_spots(spots, **kwargs):
    """Link detections into traces (the jie aligner) — :func:`uchrom.im.trace.align_spots`."""
    from uchrom.im.trace import align_spots as _f

    return _f(spots, **kwargs)


def merge_duplicate_spots(cd, **kwargs):
    """One spot per (trace, locus) — :func:`uchrom.im.merge_duplicate_spots`."""
    from uchrom.im import merge_duplicate_spots as _f

    return _f(cd, **kwargs)


__all__ = ["impute", "align_spots", "merge_duplicate_spots"]
