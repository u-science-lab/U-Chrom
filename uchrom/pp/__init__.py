"""``uchrom.pp`` — flat, scanpy-style aliases for *preprocessing*.

Preprocessing changes coordinates / spots (impute, align, normalise,
rebin).  The implementations live in the domain modules; these aliases
forward to them::

    import uchrom as uc
    cd_imputed = uc.pp.impute(cd, method="snapfish")   # im.impute.impute_coordinates
"""

from __future__ import annotations


def impute(cd, *, method: str = "linear", **kwargs):
    """Impute missing coordinates — :func:`uchrom.im.impute.impute_coordinates`.

    ``method``: ``"linear"``, ``"cubic"`` or ``"snapfish"``.  Returns the
    imputed ``ChromData`` (the input is not modified).
    """
    from uchrom.im.impute import impute_coordinates

    return impute_coordinates(cd, method=method, **kwargs)


__all__ = ["impute"]
