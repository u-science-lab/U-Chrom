"""Parameters of the IGM method (mirror of the native ``IgmParams``)."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


def _demo_stages() -> List[Dict[str, float]]:
    # IGM demo `custom_annealing_protocol` (pgs_spec.md §6.2)
    return [
        {"mdsteps": 5000, "tstart": 5000.0, "tstop": 500.0, "evfactor": 0.5, "envelope_factor": 1.2},
        {"mdsteps": 15000, "tstart": 500.0, "tstop": 50.0, "evfactor": 1.0, "envelope_factor": 1.0},
        {"mdsteps": 15000, "tstart": 50.0, "tstop": 1.0, "evfactor": 1.0, "envelope_factor": 1.0},
        {"mdsteps": 10000, "tstart": 1.0, "tstop": 0.0, "evfactor": 1.0, "envelope_factor": 1.0},
    ]


def _sigmas() -> List[float]:
    return [1.0, 0.2, 0.1, 0.05, 0.02, 0.01]


@dataclass
class IgmParams:
    """IGM population modelling parameters.

    Defaults: the IGM configuration schema with the annealing protocol of the
    IGM demo (``benchmarks/bulk/pgs_spec.md`` §2.2, §3.2, §4.3, §5, §6.2);
    the user-level defaults of U-Chrom are 10,000 structures (1 Mb bins) —
    for the IGM paper setting (200 kb, 1,000 structures, 40 % occupancy,
    prolate ellipsoid) see :meth:`boninsegna2022`.

    ``ploidy``: ``"diploid"`` (every chromosome twice, as IGM's default),
    ``"male"`` (autosomes ×2, X and Y ×1), ``"haploid"``, or a dict
    ``{chrom: copies}``.
    """

    n_structures: int = 10_000
    ploidy: Union[str, Dict[str, int]] = "diploid"
    occupancy: float = 0.2
    nucleus_shape: str = "sphere"
    nucleus_radius: float = 5000.0
    nucleus_semiaxes: List[float] = field(default_factory=lambda: [5000.0, 5000.0, 5000.0])
    init_radius: float = 0.0
    contact_range: float = 2.0
    evfactor: float = 1.0
    contact_kspring: float = 1.0
    polymer_kspring: float = 1.0
    nucleus_kspring: float = 1.0
    polymer_bonds_style: str = "simple"
    stages: List[Dict[str, float]] = field(default_factory=_demo_stages)
    relax: Optional[Dict[str, float]] = field(default_factory=lambda: {"mdsteps": 500, "temperature": 1.0, "max_velocity": 10.0})
    timestep: float = 0.25
    max_velocity: float = 1000.0
    rescale_window: float = 0.1
    rescale_fraction: float = 1.0
    cg_etol: float = 1e-4
    cg_ftol: float = 1e-6
    cg_max_iter: int = 500
    cg_max_eval: int = 500
    cg_dmax: float = 0.1
    intra_sigma_list: List[float] = field(default_factory=_sigmas)
    inter_sigma_list: List[float] = field(default_factory=_sigmas)
    max_violations: float = 0.01
    violation_tolerance: float = 0.05
    min_iterations: int = 5
    max_iterations: int = 10
    force_last_iteration: bool = False
    force_minimum_iterations_hic_cutoff: float = 0.0
    random_shuffling: bool = False
    skip_relax_init: bool = False
    n_threads: int = 0
    batch_size: int = 0
    verbose: bool = False

    @classmethod
    def boninsegna2022(cls, **kw: Any) -> "IgmParams":
        """The IGM paper's HFFc6 setting: 1,000 structures, 40 % occupancy,
        prolate ellipsoid (7,840, 6,470, 2,450) nm (use with 200 kb bins)."""
        base = dict(n_structures=1000, occupancy=0.4, nucleus_shape="ellipsoid",
                    nucleus_semiaxes=[7840.0, 6470.0, 2450.0])
        base.update(kw)
        return cls(**base)

    def replace(self, **kw: Any) -> "IgmParams":
        return dataclasses.replace(self, **kw)

    def to_native(self) -> Dict[str, Any]:
        """Fields understood by ``uchrom_nucdyn.calc_population`` (without ploidy)."""
        d = dataclasses.asdict(self)
        d.pop("ploidy")
        d["stages"] = [dict(s) for s in self.stages]
        d["nucleus_semiaxes"] = [float(x) for x in self.nucleus_semiaxes]
        return d
