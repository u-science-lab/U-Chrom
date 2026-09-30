"""Parameters of the consensus reconstruction (``ConsensusParams``)."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple, Union

#: chromosomes left out by default (Y, mitochondria); unplaced / random /
#: alt contigs are always left out unless named in ``chroms=``.
DEFAULT_EXCLUDE = ("chrY", "Y", "chrM", "M", "MT", "chrMT")


@dataclass
class ConsensusParams:
    """Consensus-structure reconstruction of bulk Hi-C by hierarchical restraint annealing.

    Defaults are justified in ``benchmarks/bulk/consensus/design.md`` (section 2);
    lengths are in units of the distance between adjacent bins at the final
    resolution (``D_final = 1``) unless ``scale_nm`` is given.

    **Stages.**  ``stage_resolutions`` (bp, coarse → fine, the final
    resolution last) or, when ``None``, ``final × stage_factor^k`` up to
    ``coarsest`` (e.g. 250 kb → 4 Mb, 1 Mb, 250 kb).  The whole genome goes
    through every stage together; each stage starts from the previous one
    interpolated at the new bead positions.

    **Contacts → targets.**  Per stage the contact counts are balanced
    (``balance``: ``"kr"`` Knight–Ruiz, ``"ice"``, ``"none"``) after a
    coverage filter (``min_coverage`` of the median row sum); the target
    distance of a pair is ``D_s (f_ij / f_nn,s)^(-1/alpha)`` with ``f_nn,s`` the
    expected frequency of adjacent bins and ``D_s = (b_s / b_final)^nu`` the
    adjacent-bin distance of stage ``s``.  ``alpha = 4`` (imaging: Wang 2016,
    Su 2020; HIPPS; miniMDS) or ``"fit"`` (``alpha = gamma / nu_polymer`` from
    the contact-decay exponent gamma of the data); ``nu = "fit"`` sets the bead
    scaling to ``gamma / alpha`` so targets of different stages agree.  Bounds
    ``[lower, upper] x target``; targets below ``D_s`` are raised to ``D_s``.

    **Which pairs.**  First stage with at most ``dense_max_bins`` beads: every
    observed pair (cis and trans).  Later stages: cis pairs up to a band of
    ``max(band_min_bins, band_factor x previous / current)`` bins; beyond it,
    pairs with observed/expected ≥ ``oe_min`` and ≥ ``long_min_count`` reads,
    at most ``max_long_per_bin`` per bin (at cis-only stages up to ``long_cis_max_bins`` bins: the window read per chromosome);
    inter-chromosomal pairs only at stages with bins ≥
    ``trans_max_resolution`` (thresholded the same way with ``oe_min_trans``);
    every restraint of the previous stage that is not covered by the band is
    carried to the new stage between representative beads (``carry``).

    **Weights.**  ``n / (n + weight_n0)`` (n = reads of the pair; confidence
    saturating at high counts) × ``trans_weight`` for trans pairs; with
    ``relative_error`` also × ``(D_s / hi)^2`` (a relative distance error: the
    harmonic term is in the relative violation, and the saturated force of a
    long restraint is not larger than that of a short one).  Backbone
    (adjacent valid beads): target ``D_s gap^nu``, bounds ``[backbone_lower,
    backbone_upper] x`` target, weight ``backbone_weight``.

    **Potential.**  ``restraint_form="saturating"`` (NucDynamics release_1.3
    form: flat inside the bounds, harmonic up to 1.5 d_max, constant force
    beyond) or ``"lorentzian"`` (bounded, redescending; LorDG-like; the first
    stage stays saturating unless ``lorentzian_first_stage``); force constant
    ``K = force_scale × n_beads / sum(w)``; NucDynamics repulsion between
    non-adjacent beads closer than ``D_s``; optional spherical confinement
    (``confinement_radius``, 0 = off).

    **Annealing.**  First stage: ``temp_start`` → ``temp_end`` over
    ``temp_steps`` × ``dyn_steps`` MD steps (NucDynamics schedule); later
    stages from ``refine_temp_start``.  ``n_runs`` independent runs.

    **Consensus.**  Runs superposed (rotation + reflection); the output
    structure is the medoid (smallest summed RMSD) of the ``keep_fraction``
    runs with the lowest restraint energy (``consensus="medoid"``), or the
    superposed mean re-relaxed at low temperature (``"mean_refined"``;
    computed when ``refine_mean``).  Per-bead spread across runs →
    ``bin_tracks``.
    """

    # stages
    stage_resolutions: Optional[Sequence[int]] = None
    stage_factor: int = 4
    coarsest: int = 8_000_000
    # contacts -> targets
    balance: str = "kr"
    min_coverage: float = 0.05
    alpha: Union[float, str] = 4.0
    nu: Union[float, str] = "fit"
    nu_polymer: float = 1.0 / 3.0
    nu_bounds: Tuple[float, float] = (0.15, 0.6)
    ps_fit_max_bp: int = 10_000_000
    lower: float = 0.8
    upper: float = 1.2
    target_min: float = 1.0
    # which pairs
    dense_max_bins: int = 1500
    min_expected: float = 5.0
    min_count: int = 1
    band_factor: float = 3.0
    band_min_bins: int = 5
    long_cis_max_bins: int = 200
    oe_min: float = 2.0
    long_min_count: int = 5
    max_long_per_bin: int = 4
    long_sample_per_bin: int = 4
    use_trans: bool = True
    trans_max_resolution: int = 1_000_000
    oe_min_trans: float = 1.5
    max_trans_per_bin: int = 4
    trans_sample_per_bin: int = 4
    carry: bool = True
    carry_weight: float = 1.0
    # weights
    weight_n0: float = 10.0
    trans_weight: float = 1.0
    relative_error: bool = True
    backbone_weight: float = 3.0
    backbone_lower: float = 0.1
    backbone_upper: float = 1.2
    # potential
    restraint_form: str = "saturating"
    lorentz_width: float = 1.0
    lorentzian_first_stage: bool = False
    force_scale: float = 50.0
    confinement_radius: float = 0.0
    confinement_k: float = 1.0
    # annealing
    temp_start: float = 5000.0
    temp_end: float = 10.0
    temp_steps: int = 500
    dyn_steps: int = 100
    refine_temp_start: float = 500.0
    refine_temp_steps: int = 200
    refine_dyn_steps: int = 100
    random_radius: Optional[float] = None
    time_step: float = 0.001
    # runs and consensus
    n_runs: int = 8
    seed: int = 0
    keep_fraction: float = 0.5
    consensus: str = "medoid"
    refine_mean: bool = True
    mean_refine_temp_start: float = 50.0
    mean_refine_temp_steps: int = 50
    mean_refine_dyn_steps: int = 100
    # output
    scale_nm: Optional[float] = None
    exclude_chroms: Sequence[str] = DEFAULT_EXCLUDE
    n_threads: int = 0
    verbose: bool = False

    def replace(self, **kw: Any) -> "ConsensusParams":
        return dataclasses.replace(self, **kw)

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["stage_resolutions"] = None if self.stage_resolutions is None else [int(x) for x in self.stage_resolutions]
        d["exclude_chroms"] = list(self.exclude_chroms)
        d["nu_bounds"] = list(self.nu_bounds)
        return d

    def validate(self) -> None:
        if self.restraint_form not in ("saturating", "lorentzian"):
            raise ValueError(f"restraint_form must be 'saturating' or 'lorentzian', got {self.restraint_form!r}")
        if self.consensus not in ("medoid", "mean_refined"):
            raise ValueError(f"consensus must be 'medoid' or 'mean_refined', got {self.consensus!r}")
        if self.consensus == "mean_refined" and not self.refine_mean:
            raise ValueError("consensus='mean_refined' needs refine_mean=True")
        if self.balance not in ("kr", "ice", "none"):
            raise ValueError(f"balance must be 'kr', 'ice' or 'none', got {self.balance!r}")
        if not (isinstance(self.alpha, (int, float)) and self.alpha > 0) and self.alpha != "fit":
            raise ValueError("alpha must be a positive number or 'fit'")
        if not (isinstance(self.nu, (int, float)) and self.nu > 0) and self.nu != "fit":
            raise ValueError("nu must be a positive number or 'fit'")
        if self.alpha == "fit" and self.nu == "fit":
            pass  # alpha = gamma / nu_polymer, nu = nu_polymer
        if not 0 < self.lower <= 1 <= self.upper:
            raise ValueError("need 0 < lower <= 1 <= upper")
        if self.n_runs < 1 or not 0 < self.keep_fraction <= 1:
            raise ValueError("need n_runs >= 1 and 0 < keep_fraction <= 1")
        if self.stage_factor < 2:
            raise ValueError("stage_factor must be >= 2")
