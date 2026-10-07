"""``python -m uchrom.datasets list | atlas | load NAME ... [--rebuild] | fetch NAME ... [--default] [--fig3] [--root DIR] | path NAME``."""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv=None) -> None:
    from . import _sources, data_dir, fetch, list_atlas, list_datasets, load, path

    ap = argparse.ArgumentParser(prog="python -m uchrom.datasets", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="datasets fetch() knows")
    sub.add_parser("atlas", help="datasets of the public atlas")
    f = sub.add_parser("fetch", help="download datasets from their sources")
    f.add_argument("names", nargs="*")
    f.add_argument("--default", action="store_true", help="the inputs of the tutorials")
    f.add_argument("--fig3", action="store_true", help="every input of the paper's Fig. 3")
    f.add_argument("--no-extract", action="store_true", help="skip members streamed out of archives")
    f.add_argument("--root", type=Path, default=None, help=f"data directory (default: {data_dir()})")
    ld = sub.add_parser("load", help="build datasets as ChromData stores in the data directory (cached)")
    ld.add_argument("names", nargs="+")
    ld.add_argument("--rebuild", action="store_true", help="build again even when cached")
    ld.add_argument("--root", type=Path, default=None, help=f"data directory (default: {data_dir()})")
    p = sub.add_parser("path", help="where a dataset is")
    p.add_argument("name")
    args = ap.parse_args(argv)
    if args.cmd == "list":
        print(list_datasets().to_string())
    elif args.cmd == "atlas":
        print(list_atlas()[["title", "n_cells", "size_mb"]].to_string())
    elif args.cmd == "path":
        print(path(args.name))
    elif args.cmd == "load":
        for name in args.names:
            print(f"{name}: {load(name, root=args.root, rebuild=args.rebuild, backed=True)}")
    else:
        names = list(args.names)
        if args.default:
            names += [k for k, v in _sources.DATASETS.items() if v.get("default", False) and k not in names]
        if args.fig3:
            names += [k for k, v in _sources.DATASETS.items() if (v.get("fig3") or k == "bintu_imr90") and k not in names]
        if not names:
            ap.error("name datasets, or --default / --fig3")
        for name in names:
            print(f"{name}: {fetch(name, root=args.root, extract=not args.no_extract)}")


if __name__ == "__main__":
    main()
