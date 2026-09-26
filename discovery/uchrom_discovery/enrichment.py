"""Auto-discovery enrichment orchestration.

This module is deliberately thin: it coordinates reusable U-Chrom feature
callers before discovery, while the actual computations stay in ``uchrom.fea``
and ``uchrom.strc``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DiscoveryEnrichmentConfig:
    """Optional feature-enrichment inputs for an auto-discovery run."""

    fasta: str | Path | None = None
    sequence_features: list[str] | None = None
    gtf: str | Path | None = None
    annotation_features: list[str] | None = None
    promoter_window: tuple[int, int] = (-2000, 500)
    structures: list[str] = field(default_factory=list)
    project_existing_structure: bool = False
    chroms: list[str] | None = None
    device: str = "auto"
    peak_tracks: list[str] = field(default_factory=list)
    peak_control_tracks: list[str] = field(default_factory=list)
    peak_method: str = "auto"
    peak_agg: str = "mean"
    peak_threshold: float | None = None
    peak_quantile: float = 0.95
    peak_cutoff: float | None = None
    peak_min_length: int = 200
    peak_max_gap: int = 30
    peak_qvalue: float | None = 0.05
    peak_pvalue: float | None = None
    peak_genome_size: float | None = None
    peak_small_local_window_bins: int = 10
    peak_large_local_window_bins: int = 100
    peak_fragment_size_bins: int = 1
    peak_min_width_bins: int = 1
    peak_max_gap_bins: int = 0
    peak_signal_scale: float = 1.0
    peak_control_scale: float | None = None
    peak_negative: str = "clip"
    peak_nolambda: bool = False
    project: bool = True
    overwrite: bool = False
    hash_sources: bool = True
    verbose: bool = False

    def enabled(self) -> bool:
        """Return true when at least one enrichment action is configured."""
        return bool(
            self.fasta
            or self.gtf
            or self.structures
            or self.project_existing_structure
            or self.peak_tracks
        )


def enrich_for_discovery(cdata, config: DiscoveryEnrichmentConfig | dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """Apply configured enrichment steps to ``cdata`` in place and summarize them."""
    if config is None:
        config = DiscoveryEnrichmentConfig(**kwargs)
    elif not isinstance(config, DiscoveryEnrichmentConfig):
        merged = dict(config)
        merged.update(kwargs)
        config = DiscoveryEnrichmentConfig(**merged)
    elif kwargs:
        merged = config.__dict__.copy()
        merged.update(kwargs)
        config = DiscoveryEnrichmentConfig(**merged)

    summary: dict[str, Any] = {
        "enabled": config.enabled(),
        "sequence_features": [],
        "annotation_features": [],
        "structures": [],
        "structural_features": [],
        "peak_tracks": {},
    }
    if not config.enabled():
        return summary

    from uchrom.fea import add_annotation_features, add_sequence_features, call_peaks_from_track
    from uchrom.strc import add_structural_features
    from uchrom.strc.comp import call_compartments_axes_pc
    from uchrom.strc.loop import call_loops_axiswise_f
    from uchrom.strc.tad import call_tads_by_pval

    if config.fasta:
        table = add_sequence_features(
            cdata,
            config.fasta,
            features=config.sequence_features,
            project=config.project,
            overwrite=config.overwrite,
            hash_source=config.hash_sources,
        )
        summary["sequence_features"] = [c for c in table.columns if c not in {"chrom", "start", "end"}]
        summary["fasta"] = str(config.fasta)
    if config.gtf:
        table = add_annotation_features(
            cdata,
            config.gtf,
            features=config.annotation_features,
            promoter_window=config.promoter_window,
            project=config.project,
            overwrite=config.overwrite,
            hash_source=config.hash_sources,
        )
        summary["annotation_features"] = [c for c in table.columns if c not in {"chrom", "start", "end"}]
        summary["gtf"] = str(config.gtf)
    if config.structures:
        callers = {
            "tads": call_tads_by_pval,
            "loops": call_loops_axiswise_f,
            "compartments": call_compartments_axes_pc,
        }
        unknown = set(config.structures) - set(callers)
        if unknown:
            raise ValueError(f"unknown structural callers: {sorted(unknown)}")
        called = {}
        for name in config.structures:
            called[name] = callers[name](
                cdata,
                chrom=None if config.chroms is None else [str(c) for c in config.chroms],
                device=config.device,
                verbose=config.verbose,
            )
        table = add_structural_features(cdata, project=config.project, overwrite=config.overwrite)
        summary["structures"] = sorted(called.keys())
        summary["structural_features"] = [c for c in table.columns if c not in {"chrom", "start", "end"}]
    elif config.project_existing_structure:
        table = add_structural_features(cdata, project=config.project, overwrite=config.overwrite)
        summary["structures"] = ["existing"]
        summary["structural_features"] = [c for c in table.columns if c not in {"chrom", "start", "end"}]

    controls = list(config.peak_control_tracks or [])
    if len(controls) > 1 and len(controls) != len(config.peak_tracks):
        raise ValueError("peak_control_tracks must be provided once or once per peak track")
    for i, track in enumerate(config.peak_tracks):
        control_track = None
        if len(controls) == 1:
            control_track = controls[0]
        elif len(controls) == len(config.peak_tracks):
            control_track = controls[i]
        peaks = call_peaks_from_track(
            cdata,
            track,
            method=config.peak_method,
            control_track=control_track,
            agg=config.peak_agg,
            threshold=config.peak_threshold,
            quantile=config.peak_quantile,
            cutoff=config.peak_cutoff,
            min_length=config.peak_min_length,
            max_gap=config.peak_max_gap,
            qvalue=(None if config.peak_pvalue is not None else config.peak_qvalue),
            pvalue=config.peak_pvalue,
            genome_size=config.peak_genome_size,
            small_local_window_bins=config.peak_small_local_window_bins,
            large_local_window_bins=config.peak_large_local_window_bins,
            fragment_size_bins=config.peak_fragment_size_bins,
            nolambda=config.peak_nolambda,
            min_width_bins=config.peak_min_width_bins,
            max_gap_bins=config.peak_max_gap_bins,
            signal_scale=config.peak_signal_scale,
            control_scale=config.peak_control_scale,
            negative=config.peak_negative,
            project=config.project,
            overwrite=config.overwrite,
        )
        method = "threshold" if config.peak_method == "auto" and config.peak_threshold is not None else config.peak_method
        if method == "auto":
            method = "macs_bdgpeakcall"
        elif method in {"macs", "bdgpeakcall"}:
            method = "macs_bdgpeakcall"
        summary["peak_tracks"][track] = {
            "n_peaks": int(len(peaks)),
            "method": method,
            "control_track": control_track,
        }
    return summary


__all__ = ["DiscoveryEnrichmentConfig", "enrich_for_discovery"]
