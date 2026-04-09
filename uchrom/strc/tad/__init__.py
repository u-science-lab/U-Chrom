# TAD (Topologically Associating Domain) Detection
# GPU-accelerated implementations

from .di import (
    calc_directionality_index,
    detect_tad_boundaries,
    get_domains,
)
from .utils import (
    load_tad_from_bed,
    substructures_from_tads,
)

__all__ = [
    'calc_directionality_index',
    'detect_tad_boundaries',
    'get_domains',
    'load_tad_from_bed',
    'substructures_from_tads',
]
