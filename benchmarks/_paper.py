"""Where the benchmarks that feed a paper figure write their results: the uchrom-reproducibility repository.

The papers' benchmarks, results and figure scripts live in ``u-science-lab/uchrom-reproducibility`` (split out of this
repository and of u-chrom-paper on 2026-10-17).  The benchmarks that stay here validate the library and also make a
figure's numbers (``benchmarks/fig3``, ``cd21_streaming_validation.py``, ``cd22_convert_validate.py``); they write
``<repro>/manuscripts/full/figures/<fig>/results/*.json`` there, the only source its figure scripts read.

The repository is ``$UCHROM_REPRO``, else the folder ``uchrom-reproducibility`` next to this repository's main
checkout (found through git, so worktrees resolve to it too) or next to this checkout.  Without one, results go to
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
    """The uchrom-reproducibility checkout, or None."""
    env = os.environ.get("UCHROM_REPRO")
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
        cand = base.parent / "uchrom-reproducibility"
        if (cand / "manuscripts").is_dir():
            return cand
    return None


def results_dir(fig: str) -> Path:
    """``<repro>/manuscripts/full/figures/<fig>/results`` (not created here; writers create it)."""
    root = paper_root()
    if root is None:
        out = REPO / "benchmarks" / "results" / fig
        warnings.warn(f"uchrom-reproducibility not found (set UCHROM_REPRO): {fig} results go to {out}", stacklevel=2)
        return out
    return root / "manuscripts" / "full" / "figures" / fig / "results"


def paper_file(rel: str) -> Path:
    """A file of the reproducibility repository, e.g. ``manuscripts/full/figures/fig3/results/x.json``."""
    root = paper_root()
    if root is None:
        raise SystemExit(f"uchrom-reproducibility not found (set UCHROM_REPRO) for {rel}")
    return root / rel
