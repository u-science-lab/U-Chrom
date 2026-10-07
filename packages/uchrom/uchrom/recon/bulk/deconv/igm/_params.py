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

    Opt-in options (IGM-Plus / IGM_2.0; every default is the IGM 1.0
    behaviour, see ``packages/uchrom-recon/README.md``):

    ``occupancy`` / ``bead_radius``
        Bead radii from the genome-to-nucleus volume occupancy (default 0.2
        when neither is given) or one radius in nm for every bead
        (IGM-Plus ``model/bead_radius``); mutually exclusive.
    ``occupancy_scope``
        What the occupancy refers to when only some chromosomes are
        modelled (``deconvolve(..., chrom=)``): ``"model"`` (default; the
        modelled chromosomes fill ``occupancy`` of the whole nucleus, as
        IGM / IGM-Plus compute it), ``"genome"`` (all bins of the input,
        times their copies: beads keep their whole-genome size and the
        modelled chromosomes occupy their share of the nucleus), or a
        genome size in bp (all copies).
    ``iterative_correction``
        False: the A-step uses ``p = f`` instead of the iteratively
        corrected probability (IGM-Plus ``iter_corr_knob = 0``).
    ``assignment_pooling``
        ``"igm"`` (IGM 1.0) or ``"gp"`` (G. Polles' approximation, IGM_2.0
        ``GP_ActivationDistanceStep``: all copy combinations pooled,
        ``n_possible = min(copies)`` smallest per structure) — for the
        sensitivity analysis of ``benchmarks/bulk/design.md``.
    ``init_noise``
        Gaussian noise (nm, standard deviation) added to every initial
        coordinate (IGM-Plus ``model/init_noise``; with
        ``deconvolve(..., init_positions=)``).

    EMber-pop options (``method="ember_pop"`` sets them; every default here
    is IGM; ``benchmarks/bulk/PREREG_POP.md``):

    ``nucleus_shape="none"``
        No envelope (``nucleus_radius`` still sets the bead volumes).
    ``gyration_prior`` / ``gyration_targets`` / ``gyration_kspring``
        Orientation-free, wall-free shape prior: the standard deviations
        σ1 ≥ σ2 ≥ σ3 (nm) along each structure's own principal axes
        (``gyration_targets``: one triple per structure, e.g. the imaged
        cells' shapes).
    ``noncontact_kspring`` / ``noncontact_range`` / ``noncontact_from_sigma``
        Two-sided assignment: bead pairs closer than ``noncontact_range``
        × (r_i + r_j) without an assigned contact are pushed apart (from that
        σ index on).
    ``assignment="soft"`` (+ ``soft_*``), ``rg_cap`` / ``rg_kspring`` /
    ``rg_two_sided``, ``advance_on_max_iterations``
        Soft contact weights around the activation distance; a
        radius-of-gyration cap or prior; go on with the next σ when an
        iteration limit is reached.
    """

    n_structures: int = 10_000
    ploidy: Union[str, Dict[str, int]] = "diploid"
    #: None = 0.2 unless ``bead_radius`` is given
    occupancy: Optional[float] = None
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
    # ---- opt-in (IGM-Plus / IGM_2.0); defaults = IGM 1.0 ----
    bead_radius: Optional[float] = None
    occupancy_scope: Union[str, float] = "model"
    iterative_correction: bool = True
    assignment_pooling: str = "igm"
    init_noise: float = 0.0
    # ---- EMber-pop (defaults = IGM) ----
    noncontact_kspring: float = 0.0
    noncontact_range: float = 0.0
    noncontact_from_sigma: int = 0
    advance_on_max_iterations: bool = False
    assignment: str = "igm"
    soft_beta0: float = 4.0
    soft_beta_growth: float = 1.0
    soft_beta_max: float = 64.0
    soft_commit: float = 1.0
    soft_min_weight: float = 0.02
    rg_cap: float = 0.0
    rg_kspring: float = 1.0
    rg_two_sided: bool = False
    gyration_prior: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    gyration_kspring: float = 1.0
    gyration_targets: List[List[float]] = field(default_factory=list)
    gyration_wall: float = 0.0

    def __post_init__(self) -> None:
        if self.bead_radius is not None and self.occupancy is not None:
            raise ValueError("bead_radius and occupancy are mutually exclusive (radii are either set "
                             "directly or derived from the occupancy)")
        if self.bead_radius is not None and not self.bead_radius > 0:
            raise ValueError("bead_radius must be > 0 nm")
        if self.assignment_pooling not in ("igm", "gp"):
            raise ValueError(f"assignment_pooling must be 'igm' or 'gp', got {self.assignment_pooling!r}")
        sc = self.occupancy_scope
        if not (sc in ("model", "genome") or (isinstance(sc, (int, float)) and not isinstance(sc, bool) and sc > 0)):
            raise ValueError(f"occupancy_scope must be 'model', 'genome' or a genome size in bp, got {sc!r}")

    @property
    def effective_occupancy(self) -> Optional[float]:
        """The occupancy used (None when ``bead_radius`` sets the radii)."""
        if self.bead_radius is not None:
            return None
        return 0.2 if self.occupancy is None else float(self.occupancy)

    @classmethod
    def boninsegna2022(cls, **kw: Any) -> "IgmParams":
        """The IGM paper's HFFc6 setting: 1,000 structures, 40 % occupancy,
        prolate ellipsoid (7,840, 6,470, 2,450) nm (use with 200 kb bins)."""
        base = dict(n_structures=1000, occupancy=0.4, nucleus_shape="ellipsoid",
                    nucleus_semiaxes=[7840.0, 6470.0, 2450.0])
        if kw.get("bead_radius") is not None:
            base.pop("occupancy")
        base.update(kw)
        return cls(**base)

    def replace(self, **kw: Any) -> "IgmParams":
        """A copy with fields replaced; giving ``bead_radius`` alone drops the
        occupancy (and vice versa), since the two are mutually exclusive."""
        if kw.get("bead_radius") is not None and "occupancy" not in kw:
            kw["occupancy"] = None
        if kw.get("occupancy") is not None and "bead_radius" not in kw:
            kw["bead_radius"] = None
        return dataclasses.replace(self, **kw)

    def to_native(self) -> Dict[str, Any]:
        """Fields understood by ``uchrom_recon.calc_population`` (without ploidy
        and ``occupancy_scope``, which the caller resolves to
        ``occupancy_total_bp``)."""
        d = dataclasses.asdict(self)
        d.pop("ploidy")
        d.pop("occupancy_scope")
        occ = self.effective_occupancy
        d["occupancy"] = 0.0 if occ is None else occ
        d["bead_radius"] = 0.0 if self.bead_radius is None else float(self.bead_radius)
        # "model": the modelled beads; "genome" is resolved by deconvolve_igm from the input bins
        sc = self.occupancy_scope
        d["occupancy_total_bp"] = float(sc) if not isinstance(sc, str) and self.bead_radius is None else 0.0
        d["stages"] = [dict(s) for s in self.stages]
        d["nucleus_semiaxes"] = [float(x) for x in self.nucleus_semiaxes]
        d["gyration_prior"] = [float(x) for x in self.gyration_prior]
        d["gyration_targets"] = [[float(x) for x in t] for t in self.gyration_targets]
        return d
