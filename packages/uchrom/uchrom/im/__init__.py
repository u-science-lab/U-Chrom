"""Imaging-side processing: spot-to-trace alignment (:mod:`uchrom.im.trace`), coordinate imputation
(:mod:`uchrom.im.impute`) and spot-level preprocessing (:func:`merge_duplicate_spots`)."""

from .spots import merge_duplicate_spots

__all__ = ["merge_duplicate_spots"]
