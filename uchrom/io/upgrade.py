"""Convert ``.h5cd`` files from format 1.x to 2.0 on disk.

``ChromData.read`` already upgrades 1.x files in memory; this rewrites
them so later reads skip the conversion::

    python -m uchrom.io.upgrade old.h5cd new.h5cd
    python -m uchrom.io.upgrade data/*.h5cd --out-dir upgraded/

What changes (see ``docs/source/guide/chromdata_2_0_design.md``):

* ``bins`` = the unique spot loci; ``spots`` store ``bin_id`` instead of
  ``chrom/start/end`` (still available via ``cd.spots`` /
  ``cd.to_dataframe()``);
* the spot-aligned 1.x ``tracks`` split into bin-level ``tracks/`` (columns
  constant within every bin) and ``spot_tracks/``;
* categorical columns stored as codes + categories.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Union

import h5py

PathLike = Union[str, Path]


def file_format_version(path: PathLike) -> str:
    """The ``uchrom_format_version`` of an ``.h5cd`` (``"1.0"`` if absent)."""
    with h5py.File(path, "r") as f:
        v = f.attrs.get("uchrom_format_version", "1.0")
    return v.decode() if isinstance(v, bytes) else str(v)


def upgrade_h5cd(src: PathLike, dst: PathLike, *, overwrite: bool = False,
                 compression: Optional[str] = "gzip", compression_opts: Optional[int] = 4,
                 compress_floats: bool = False) -> dict:
    """Read ``src`` (any supported format) and write it as format 2.0 to ``dst``.

    ``compression`` / ``compression_opts`` / ``compress_floats`` are passed
    to :meth:`ChromData.write` (gzip level 4 on integer / string data by
    default; ``"lzf"`` or ``None``).

    Returns a summary: source / target versions, ``n_spots``, ``n_bins``
    and which tracks became bin- vs spot-level.  ``src`` is never
    modified; ``dst`` must differ from it.
    """
    from uchrom.core.cdata import FORMAT_VERSION, ChromData

    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        raise ValueError("upgrade_h5cd: dst must differ from src (the source is never modified)")
    if dst.exists() and not overwrite:
        raise FileExistsError(f"{dst} exists; pass overwrite=True")
    before = file_format_version(src)
    cd = ChromData.read(src)
    cd.write(dst, compression=compression, compression_opts=compression_opts,
             compress_floats=compress_floats)
    names = cd.track_names()
    return {
        "src": str(src), "dst": str(dst),
        "from_version": before, "to_version": FORMAT_VERSION,
        "n_spots": int(cd.n_spots), "n_bins": int(cd.n_bins),
        "bin_tracks": names["bin"], "spot_tracks": names["spot"],
    }


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m uchrom.io.upgrade",
        description="Rewrite .h5cd files as format 2.0 (the bins axis).",
    )
    ap.add_argument("paths", nargs="+", help="SRC DST, or several SRC with --out-dir")
    ap.add_argument("--out-dir", help="write each SRC to OUT_DIR/<name>")
    ap.add_argument("--overwrite", action="store_true", help="replace existing outputs")
    ap.add_argument("--compression", default="gzip", choices=["gzip", "lzf", "none"],
                    help="dataset filter (default gzip)")
    ap.add_argument("--level", type=int, default=4, help="gzip level (default 4)")
    ap.add_argument("--compress-floats", action="store_true",
                    help="also compress coords / float tracks (smaller, slower reads)")
    args = ap.parse_args(argv)

    if args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        pairs = [(Path(p), out / Path(p).name) for p in args.paths]
    elif len(args.paths) == 2:
        pairs = [(Path(args.paths[0]), Path(args.paths[1]))]
    else:
        ap.error("give SRC DST, or several SRC with --out-dir")
    for src, dst in pairs:
        comp = None if args.compression == "none" else args.compression
        info = upgrade_h5cd(src, dst, overwrite=args.overwrite, compression=comp,
                            compression_opts=args.level, compress_floats=args.compress_floats)
        print(f"{src} ({info['from_version']}) -> {dst} ({info['to_version']}): "
              f"{info['n_spots']} spots, {info['n_bins']} bins, "
              f"{len(info['bin_tracks'])} bin tracks, {len(info['spot_tracks'])} spot tracks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
