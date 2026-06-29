# TAD (Topologically Associating Domain) Detection

from .utils import (
    load_tad_from_bed,
    substructures_from_tads,
)
from .arc_pval import (
    call_tads_by_pval,
    TADCallerParams,
)
from .fishnet import (
    call_domains_fishnet,
    call_domains_fishnet_trace,
    FISHnetParams,
)

try:
    from .di import (
        calc_directionality_index,
        detect_tad_boundaries,
        get_domains,
    )
except ModuleNotFoundError as exc:
    if exc.name != "torch":
        raise
    _torch_import_error = exc

    def _missing_torch(*args, **kwargs):
        raise ModuleNotFoundError(
            "The DI-based TAD caller requires optional dependency 'torch'. "
            "Use call_tads_by_pval for the numpy-compatible caller or install torch."
        ) from _torch_import_error

    calc_directionality_index = _missing_torch
    detect_tad_boundaries = _missing_torch
    get_domains = _missing_torch

__all__ = [
    "calc_directionality_index",
    "detect_tad_boundaries",
    "get_domains",
    "load_tad_from_bed",
    "substructures_from_tads",
    "call_tads_by_pval",
    "TADCallerParams",
    "call_domains_fishnet",
    "call_domains_fishnet_trace",
    "FISHnetParams",
]
