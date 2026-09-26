"""Move files of the old flat ``example-data/`` layout into dataset folders.

Until the one-folder-per-dataset layout, every example file sat directly in
``example-data/``.  Tracked files move with ``git pull``; downloaded and
built files (Takei 2021 core CSV, seqFISH+ zip, Bintu CSV, sci-Hi-C tarball,
tutorial outputs, ...) do not.  This script moves them.

Idempotent: an entry is moved only when it exists at its old place and its
new place is free; anything else is reported and left alone, so re-running
is a no-op.  ``MOVES`` below is the single source of truth for old -> new.

Usage::

    python example-data/migrate_layout.py --dry-run   # show what would move
    python example-data/migrate_layout.py             # move
    python example-data/migrate_layout.py --root /path/to/example-data
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (old, new), both relative to example-data/.  ``old`` may be a glob
# (non-recursive, matched in example-data/ itself); a ``new`` ending in "/"
# is a folder that keeps the entry's name.  Order matters: the first entry
# that claims a path wins.
MOVES: list[tuple[str, str]] = [
    # Takei 2021 mESC DNA seqFISH+ (4DN FOF-CT + Zenodo raw spots)
    ("4DNFIHF3JCBY.*", "takei2021_mesc/"),
    ("4DNFIFINA2U9.csv", "takei2021_mesc/4DNFIFINA2U9.csv"),
    ("4DNFIJ52NVDV.csv", "takei2021_mesc/4DNFIJ52NVDV.csv"),
    ("DNAseqFISH+.zip", "takei2021_mesc/DNAseqFISH+.zip"),
    ("DNAseqFISH+", "takei2021_mesc/DNAseqFISH+"),
    # Takei 2025 cerebellum
    ("build_takei2025_fov0.py", "takei2025_fov0/build.py"),
    ("build_takei2025_cerebellum.py", "takei2025_cerebellum/build.py"),
    ("takei2025_cerebellum_fixture", "takei2025_cerebellum/fixture"),
    # Bintu 2018 IMR90 chr21 tracing
    ("IMR90_chr21-18-20Mb.csv", "bintu2018_imr90/IMR90_chr21-18-20Mb.csv"),
    ("IMR90_chr21_pyhim.ecsv", "bintu2018_imr90/IMR90_chr21_pyhim.ecsv"),
    ("bintu_to_pyhim_ecsv.py", "bintu2018_imr90/to_pyhim_ecsv.py"),
    # Huang 2021 mESC Sox2
    ("mESC_Sox2_README.md", "mesc_sox2/README.md"),
    ("mESC_Sox2_*", "mesc_sox2/"),
    # Stevens 2017 single-cell Hi-C
    ("cell1.pairs", "stevens2017_mesc/cell1.pairs"),
    ("cell2.pairs.gz", "stevens2017_mesc/cell2.pairs.gz"),
    # Rao 2014 Hi-C
    ("IMR90_chr21_30kb.cool", "imr90_hic/IMR90_chr21_30kb.cool"),
    ("GSE63525_GM12878_insitu_primary+replicate_combined_30.hic",
     "gm12878_hic/GSE63525_GM12878_insitu_primary+replicate_combined_30.hic"),
    # Kim 2020 sci-Hi-C (higashi tutorial)
    ("H1Esc-HFF.R1.tar.gz", "h1esc_hff_scihic/H1Esc-HFF.R1.tar.gz"),
    ("H1Esc-HFF.R1.labeled", "h1esc_hff_scihic/H1Esc-HFF.R1.labeled"),
    ("H1Esc-HFF.R1", "h1esc_hff_scihic/H1Esc-HFF.R1"),
    # build scripts of datasets whose folder name did not change
    ("build_schicar_mop.py", "schicar_mop/build.py"),
    ("build_liu2025_mop.py", "liu2025_mop/build.py"),
    ("build_sim_cell1.py", "sim_cell1/build.py"),
    # tutorial / benchmark outputs
    ("with_loops.h5cd", "generated/with_loops.h5cd"),
    ("with_loops.chromdata.zarr", "generated/with_loops.chromdata.zarr"),
    ("fofct_core.csv", "generated/fofct_core.csv"),
    ("fig2_work", "generated/fig2_work"),
]


def plan(root: Path) -> list[tuple[Path, Path]]:
    """(old, new) pairs for every MOVES entry present at its old place."""
    out: list[tuple[Path, Path]] = []
    claimed: set[Path] = set()
    for old, new in MOVES:
        if any(ch in old for ch in "*?["):
            olds = sorted(p for p in root.glob(old) if p.parent == root)
        else:
            p = root / old
            olds = [p] if os.path.lexists(p) else []
        for src in olds:
            if src in claimed:
                continue
            claimed.add(src)
            dst = root / new / src.name if new.endswith("/") else root / new
            out.append((src, dst))
    return out


def migrate(root: Path, dry_run: bool = False) -> dict[str, int]:
    root = Path(root).resolve()
    counts = {"moved": 0, "conflict": 0}
    verb = "would move" if dry_run else "moved"
    for src, dst in plan(root):
        rel_s, rel_d = src.relative_to(root), dst.relative_to(root)
        if os.path.lexists(dst):
            print(f"[keep] {rel_s}: {rel_d} already exists — left in place, resolve by hand")
            counts["conflict"] += 1
            continue
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.rename(src, dst)
        print(f"[{'plan' if dry_run else 'move'}] {rel_s} -> {rel_d}")
        counts["moved"] += 1
    n = counts["moved"]
    tail = f", {counts['conflict']} left in place" if counts["conflict"] else ""
    print(f"{verb} {n} entr{'y' if n == 1 else 'ies'} under {root}{tail}"
          + ("" if n or counts["conflict"] else " (already on the new layout)"))
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=HERE, help="the example-data/ folder (default: this script's folder)")
    ap.add_argument("--dry-run", action="store_true", help="only print what would move")
    args = ap.parse_args(argv)
    if not args.root.is_dir():
        ap.error(f"{args.root} is not a directory")
    migrate(args.root, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
