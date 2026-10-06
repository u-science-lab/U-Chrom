"""Convert ChromData files to the current container (``.chromdata.zarr``).

``ChromData.read`` no longer reads the HDF5 ``.h5cd`` container (format 1.x
and 2.0); this converts such a file once, after which it reads fast and can
be *backed* (``ChromData.read(path, backed=True)``)::

    python -m uchrom.io.upgrade old.h5cd new.chromdata.zarr
    python -m uchrom.io.upgrade data/*.h5cd --out-dir converted/        # <stem>.chromdata.zarr
    python -m uchrom.io.upgrade data/*.h5cd --out-dir converted/ --format cdz

What changes (see ``docs/source/guide/chromdata_2_0_design.md``):

* 1.x → 2.0 data model: ``bins`` = the unique spot loci; ``spots`` store
  ``bin_id`` instead of ``chrom/start/end`` (still available via
  ``cd.spots`` / ``cd.to_dataframe()``); the spot-aligned 1.x ``tracks``
  split into bin-level ``tracks`` (columns constant within every bin) and
  ``spot_tracks``;
* the container: Zarr v3 + Parquet, spots sorted by (cell, trace, bin)
  with an ``index/`` of row offsets (``index/source_row`` keeps the
  original order).

The target format follows the destination suffix (``.chromdata.zarr`` or
``.cdz``).  The source is never modified.  Older zarr / cdz stores are
rewritten in the current layout too.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, Path]

_SUFFIX = {"zarr": ".chromdata.zarr", "cdz": ".cdz"}


def file_format_version(path: PathLike) -> str:
    """The ``uchrom_format_version`` of a ChromData file (``"1.0"`` for an
    unversioned ``.h5cd``)."""
    from uchrom.core.zarrcd import container_kind

    path = Path(path)
    kind = container_kind(path)
    if kind == "zarr":
        attrs = json.loads((path / "zarr.json").read_text()).get("attributes", {})
        return str(attrs.get("uchrom", {}).get("format_version", attrs.get("uchrom_format_version")))
    if kind == "cdz":
        import zipfile

        with zipfile.ZipFile(path) as zf:
            attrs = json.loads(zf.read("zarr.json")).get("attributes", {})
        return str(attrs.get("uchrom", {}).get("format_version", attrs.get("uchrom_format_version")))
    import h5py

    with h5py.File(path, "r") as f:
        v = f.attrs.get("uchrom_format_version", "1.0")
    return v.decode() if isinstance(v, bytes) else str(v)


def default_target(src: PathLike, fmt: str = "zarr", out_dir: Optional[PathLike] = None) -> Path:
    """``<dir>/<stem>.chromdata.zarr`` (or ``.cdz``) for ``src``."""
    src = Path(src)
    name = src.name
    for suf in (".chromdata.zarr", ".zarr", ".cdz", ".h5cd"):
        if name.lower().endswith(suf):
            name = name[: -len(suf)]
            break
    else:
        name = src.stem
    return Path(out_dir or src.parent) / (name + _SUFFIX[fmt])


def upgrade_h5cd(src: PathLike, dst: Optional[PathLike] = None, *, overwrite: bool = False,
                 coord_dtype: str = "float64") -> dict:
    """Read ``src`` (``.h5cd`` 1.x / 2.0, or any ChromData store) and write
    it to ``dst`` in the current format (``.chromdata.zarr`` / ``.cdz``);
    a zarr / cdz source is read in its original row order.

    ``dst`` defaults to ``<src stem>.chromdata.zarr`` next to ``src``; its
    suffix picks the container.  ``coord_dtype`` is the storage dtype of
    ``coords`` / ``layers`` (see :meth:`ChromData.write`).

    Returns a summary: source / target versions and containers, ``n_spots``,
    ``n_bins`` and which tracks are bin- vs spot-level.  ``src`` is never
    modified; ``dst`` must differ from it.
    """
    from uchrom.core.cdata import ChromData
    from uchrom.core.zarrcd import container_kind

    from ._h5cd_legacy import read_h5cd

    src = Path(src)
    dst = Path(dst) if dst is not None else default_target(src)
    if src.resolve() == dst.resolve():
        raise ValueError("upgrade_h5cd: dst must differ from src (the source is never modified)")
    kind = container_kind(dst)
    if kind not in ("zarr", "cdz"):
        raise ValueError(f"{dst}: the target must be a .chromdata.zarr or .cdz path")
    if dst.exists() and not overwrite:
        raise FileExistsError(f"{dst} exists; pass overwrite=True")
    before = file_format_version(src)
    src_kind = container_kind(src) or "h5cd"
    if src_kind == "h5cd":
        cd = read_h5cd(src)
    else:
        # the rows of the object originally written (its index/source_row),
        # so the new store's original order is that one too
        cd = ChromData.read(src, original_order=True)
    cd.write(dst, coord_dtype=coord_dtype)
    names = cd.track_names()
    return {
        "src": str(src), "dst": str(dst),
        "from_version": before, "to_version": file_format_version(dst),
        "from_container": src_kind, "to_container": kind,
        "n_spots": int(cd.n_spots), "n_bins": int(cd.n_bins),
        "bin_tracks": names["bin"], "spot_tracks": names["spot"],
    }


#: the conversion is not specific to .h5cd sources
convert = upgrade_h5cd


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m uchrom.io.upgrade",
        description="Convert ChromData files (.h5cd 1.x / 2.0, older stores) to the "
                    "current .chromdata.zarr (or .cdz).",
    )
    ap.add_argument("paths", nargs="+", help="SRC DST, or one or more SRC with --out-dir")
    ap.add_argument("--out-dir", help="write each SRC to OUT_DIR/<stem>.chromdata.zarr (see --format)")
    ap.add_argument("--format", default="zarr", choices=["zarr", "cdz"],
                    help="target container with --out-dir or a single SRC (default zarr)")
    ap.add_argument("--overwrite", action="store_true", help="replace existing outputs")
    ap.add_argument("--coord-dtype", default="float64", choices=["float64", "float32"],
                    help="storage dtype of coords / layers in the zarr container")
    args = ap.parse_args(argv)

    if args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        pairs = [(Path(p), default_target(p, args.format, out)) for p in args.paths]
    elif len(args.paths) == 2:
        pairs = [(Path(args.paths[0]), Path(args.paths[1]))]
    elif len(args.paths) == 1:
        pairs = [(Path(args.paths[0]), default_target(args.paths[0], args.format))]
    else:
        ap.error("give SRC DST, one SRC, or several SRC with --out-dir")
    for src, dst in pairs:
        info = upgrade_h5cd(src, dst, overwrite=args.overwrite, coord_dtype=args.coord_dtype)
        print(f"{src} ({info['from_version']}, {info['from_container']}) -> {dst} "
              f"({info['to_version']}, {info['to_container']}): "
              f"{info['n_spots']} spots, {info['n_bins']} bins, "
              f"{len(info['bin_tracks'])} bin tracks, {len(info['spot_tracks'])} spot tracks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
