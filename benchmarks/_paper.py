"""Where the benchmarks that feed a paper figure write their results: the u-chrom-paper repository.

The manuscripts and figures moved from ``paper/`` to ``u-science-lab/u-chrom-paper`` on 2026-10-05.  A figure's
numbers are ``<paper>/manuscripts/full/figures/<fig>/results/*.json`` there, the only source the figures and manuscripts read.

The repository is ``$UCHROM_PAPER``, else the folder ``u-chrom-paper`` next to this repository's main checkout
(found through git, so worktrees resolve to it too) or next to this checkout.  Without one, results go to
``benchmarks/results/<fig>/`` here, with a warning.
"""

from __future__ import annotations

import os
import subprocess
import warnings
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]


def paper_root() -> Optional[Path]:
    """The u-chrom-paper checkout, or None."""
    env = os.environ.get("UCHROM_PAPER")
    if env:
        return Path(env).expanduser().resolve()
    bases = [REPO]
    try:
        common = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, check=True).stdout.strip()
        bases.insert(0, Path(common).parent)
    except (OSError, subprocess.CalledProcessError):
        pass
    for base in bases:
        cand = base.parent / "u-chrom-paper"
        if (cand / "manuscripts").is_dir():
            return cand
    return None


def results_dir(fig: str) -> Path:
    """``<paper>/manuscripts/full/figures/<fig>/results`` (not created here; writers create it)."""
    root = paper_root()
    if root is None:
        out = REPO / "benchmarks" / "results" / fig
        warnings.warn(f"u-chrom-paper not found (set UCHROM_PAPER): {fig} results go to {out}", stacklevel=2)
        return out
    return root / "manuscripts" / "full" / "figures" / fig / "results"


def paper_file(rel: str) -> Path:
    """A file of the paper repository, e.g. ``manuscripts/full/figures/fig2/tableS_capabilities.md``."""
    root = paper_root()
    if root is None:
        raise SystemExit(f"u-chrom-paper not found (set UCHROM_PAPER) for {rel}")
    return root / rel
