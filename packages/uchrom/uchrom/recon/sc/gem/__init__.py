"""GEM: single-cell genome structure by energy minimisation (Taichi autodiff).

Needs Taichi, an optional dependency of u-chrom: ``pip install "u-chrom[gem]"``.
"""

try:
    from .gem import main, Simulation
except ModuleNotFoundError as exc:          # pragma: no cover - depends on the installation
    if exc.name != "taichi":
        raise
    raise ImportError('uchrom.recon.sc.gem needs Taichi: pip install "u-chrom[gem]"') from exc

__all__ = ["main", "Simulation"]
