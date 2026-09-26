"""Takei 2025 cerebellum DNA seqFISH+ — replicate 1, **all** fields of view.

Input (fetch explicitly first; nothing is downloaded silently)::

    python example-data/download_data.py --takei2025_cerebellum

which stages, under ``example-data/takei2025_cerebellum/``:

* ``cerebellum_rep1.tar.gz`` — Zenodo 7693825 (2.85 GB, CC-BY-4.0), one
  DNA-spot CSV per FOV;
* ``LC1-100k-09022022-mm10-25kb-meta.csv`` — the 25-kb locus map;
* ``cerebellum_mRNA_cluster_nuc_vol_filtered.csv`` — per-cell clustering.

The builder

1. streams the tarball once and extracts each FOV CSV to ``raw/`` (kept:
   the allele diagnostic, ``benchmarks/fig2/allele_qc.py``, re-reads the
   raw allele columns; ``--drop-raw`` deletes each CSV once its FOV is built);
2. loads every FOV **in its own subprocess** with
   :func:`uchrom.io.seqfish_multiomics.read_seqfish_multiomics` (default
   ``dbscan_ldp_nbr_allele`` traces, noise spots dropped) and writes
   ``fov/takei2025_cerebellum_rep1_pos<N>.chromdata.zarr`` — peak RSS stays
   at one FOV's worth (per-FOV files from older builds, ``.h5cd``, are
   reused as they are);
3. concatenates the per-FOV files into
   ``takei2025_cerebellum_rep1.chromdata.zarr`` (``--no-combined`` skips it;
   ``--format h5cd`` writes the deprecated HDF5 container instead);
4. writes ``build_summary.json``: per-FOV and combined n_spots / n_traces /
   n_cells, file sizes, wall time and peak RSS.

Usage::

    python example-data/takei2025_cerebellum/build.py [--data-dir DIR] [--fovs 0,1] [--no-combined]
                                                      [--format zarr|cdz|h5cd]

``--data-dir`` defaults to ``$UCHROM_EXAMPLE_DATA/takei2025_cerebellum`` or
``example-data/takei2025_cerebellum``.
"""

from __future__ import annotations

import argparse
import json
import re
import resource
import subprocess
import sys
import tarfile
import time
from pathlib import Path

# this script lives in its dataset folder: example-data/takei2025_cerebellum/
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))  # this checkout's uchrom, not an installed copy
TARBALL = "cerebellum_rep1.tar.gz"
LOCI = "LC1-100k-09022022-mm10-25kb-meta.csv"
CLUSTERS = "cerebellum_mRNA_cluster_nuc_vol_filtered.csv"
PREFIX = "takei2025_cerebellum_rep1"
SUFFIX = {"zarr": ".chromdata.zarr", "cdz": ".cdz", "h5cd": ".h5cd"}


def default_data_dir() -> Path:
    from uchrom.datasets import example_path  # $UCHROM_EXAMPLE_DATA, else this checkout

    return example_path("takei2025_cerebellum")


def peak_rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 2**20 if sys.platform == "darwin" else r / 1024  # bytes on macOS, KiB on Linux


def fov_of(name: str) -> int:
    m = re.search(r"_pos(\d+)\.csv$", name)
    if not m:
        raise ValueError(f"not a FOV CSV: {name}")
    return int(m.group(1))


def extract(data_dir: Path, fovs=None) -> list[Path]:
    """Stream the tarball once; extract FOV CSVs not yet on disk."""
    tar_path = data_dir / TARBALL
    if not tar_path.exists():
        raise SystemExit(f"{tar_path} missing — run: python example-data/download_data.py --takei2025_cerebellum")
    raw = data_dir / "raw"
    raw.mkdir(exist_ok=True)
    listing = data_dir / "raw" / "members.json"
    if listing.exists():
        members = json.loads(listing.read_text())
        wanted = [m for m in members if fovs is None or fov_of(m) in fovs]
        if all((raw / Path(m).name).exists() for m in wanted):
            return sorted((raw / Path(m).name for m in wanted), key=lambda p: fov_of(p.name))
    members = []
    with tarfile.open(tar_path, mode="r|gz") as tar:
        for m in tar:
            base = Path(m.name).name
            # skip macOS AppleDouble "._*" resource-fork entries shipped in the tarball
            if not (m.isfile() and base.endswith(".csv") and "_pos" in base) or base.startswith("._"):
                continue
            members.append(m.name)
            dest = raw / Path(m.name).name
            if (fovs is not None and fov_of(m.name) not in fovs) or (dest.exists() and dest.stat().st_size == m.size):
                continue
            print(f"[extract] {m.name} ({m.size / 1e9:.2f} GB)", flush=True)
            tmp = dest.with_suffix(".csv.part")
            with tar.extractfile(m) as src, open(tmp, "wb") as out:
                while chunk := src.read(1 << 24):
                    out.write(chunk)
            tmp.replace(dest)
    listing.write_text(json.dumps(members, indent=1))
    wanted = [m for m in members if fovs is None or fov_of(m) in fovs]
    return sorted((raw / Path(m).name for m in wanted), key=lambda p: fov_of(p.name))


def size_bytes(p: Path) -> int:
    """File size, or the total size of a directory store."""
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size


def existing(stem: Path):
    """The file as built by this or an older version of the script."""
    return next((stem.with_name(stem.name + s) for s in SUFFIX.values()
                 if stem.with_name(stem.name + s).exists()), None)


def save(cd, out: Path) -> None:
    """Write ``cd`` to ``out``, replacing it atomically (the zarr / cdz
    writer is atomic itself; HDF5 goes through a temp file)."""
    if out.suffix == ".h5cd":
        tmp = out.with_suffix(".tmp.h5cd")
        cd.write(tmp)
        tmp.replace(out)
    else:
        cd.write(out)


def build_one(csv: Path, out: Path, data_dir: Path) -> dict:
    """Child process: one FOV CSV → one ChromData store (+ its stats)."""
    from uchrom.io.seqfish_multiomics import read_seqfish_multiomics

    t0 = time.perf_counter()
    cd = read_seqfish_multiomics(csv, locus_annotation=data_dir / LOCI, cell_clustering=data_dir / CLUSTERS)
    cd.uns["fov"] = fov_of(csv.name)
    save(cd, out)
    return {"fov": fov_of(csv.name), "csv": csv.name, "csv_bytes": csv.stat().st_size,
            "file": out.name, "file_bytes": size_bytes(out),
            "n_spots": int(cd.n_spots), "n_traces": int(cd.n_traces), "n_cells": int(cd.n_cells),
            "n_cells_annotated": int(len(cd.cells)),
            "n_tracks": int(cd.bin_tracks.shape[1] + cd.spot_tracks.shape[1]),
            "seconds": round(time.perf_counter() - t0, 1), "peak_rss_mb": round(peak_rss_mb(), 1)}


def concat(paths: list[Path]):
    """Concatenate per-FOV ChromData files (disjoint cell / trace ids).

    Each FOV derives its own bin table, so ``bin_id`` is dropped and
    re-derived from the loci; tracks go through the spot-aligned view
    and are split into bin / spot tracks again by the constructor."""
    import numpy as np
    import pandas as pd
    from pandas.api.types import union_categoricals

    from uchrom import ChromData

    parts = [ChromData.read(p) for p in paths]
    spots = {}
    for col in [c for c in parts[0].spots.columns if c != "bin_id"]:
        cols = [cd.spots[col] for cd in parts]
        if all(isinstance(c.dtype, pd.CategoricalDtype) for c in cols):
            spots[col] = union_categoricals(cols, ignore_order=True)
        else:
            spots[col] = np.concatenate([c.to_numpy() for c in cols])
    spots = pd.DataFrame(spots)
    coords = np.concatenate([cd.coords for cd in parts])
    tracks = pd.concat([cd.tracks_spot_view() for cd in parts], ignore_index=True)
    traces = pd.concat([cd.traces for cd in parts])
    cells = pd.concat([cd.cells for cd in parts])
    cellm = {k: np.concatenate([cd.cellm[k] for cd in parts]) for k in parts[0].cellm}
    uns = dict(parts[0].uns)
    uns.pop("fov", None)
    uns["fovs"] = [int(cd.uns.get("fov", -1)) for cd in parts]
    del parts
    cd = ChromData(coords, spots, cells=cells, cellm=cellm, traces=traces, uns=uns)
    cd.tracks = tracks  # spot-aligned: split into bin_tracks / spot_tracks
    return cd


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--fovs", default=None, help="comma-separated FOV numbers (default: all)")
    ap.add_argument("--no-combined", action="store_true")
    ap.add_argument("--drop-raw", action="store_true", help="delete each raw CSV after its FOV is built")
    ap.add_argument("--force", action="store_true", help="rebuild FOV files that already exist")
    ap.add_argument("--format", default="zarr", choices=sorted(SUFFIX),
                    help="output container (default zarr: .chromdata.zarr)")
    ap.add_argument("--one", nargs=2, metavar=("CSV", "OUT"), help=argparse.SUPPRESS)
    args = ap.parse_args()
    data_dir = (args.data_dir or default_data_dir()).resolve()

    if args.one:  # child mode
        print("__RESULT__" + json.dumps(build_one(Path(args.one[0]), Path(args.one[1]), data_dir)), flush=True)
        return

    fovs = None if args.fovs is None else {int(x) for x in args.fovs.split(",")}
    for name in (LOCI, CLUSTERS):
        if not (data_dir / name).exists():
            raise SystemExit(f"{data_dir / name} missing — run: python example-data/download_data.py --takei2025_cerebellum")
    csvs = extract(data_dir, fovs)
    fov_dir = data_dir / "fov"
    fov_dir.mkdir(exist_ok=True)
    summary_path = data_dir / "build_summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    per_fov = {int(r["fov"]): r for r in summary.get("fovs", [])}
    outs = []
    for csv in csvs:
        stem = fov_dir / f"{PREFIX}_pos{fov_of(csv.name)}"
        out = stem.with_name(stem.name + SUFFIX[args.format])
        old = existing(stem)
        if old is not None and not args.force and fov_of(csv.name) in per_fov:
            print(f"[skip] {old.name}")
            outs.append(old)
            continue
        outs.append(out)
        print(f"[build] {csv.name} → {out.name}", flush=True)
        proc = subprocess.run([sys.executable, __file__, "--data-dir", str(data_dir), "--one", str(csv), str(out)],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            raise SystemExit(f"FOV {csv.name} failed")
        rec = json.loads(proc.stdout.split("__RESULT__", 1)[1])
        per_fov[rec["fov"]] = rec
        print(f"        {rec['n_spots']:,} spots, {rec['n_traces']:,} traces, {rec['n_cells']} cells, "
              f"{rec['file_bytes'] / 1e9:.2f} GB, {rec['seconds']} s, peak RSS {rec['peak_rss_mb'] / 1024:.1f} GB",
              flush=True)
        if args.drop_raw:
            csv.unlink()
        summary["fovs"] = [per_fov[k] for k in sorted(per_fov)]
        summary_path.write_text(json.dumps(summary, indent=1))

    if not args.no_combined:
        t0 = time.perf_counter()
        cd = concat(outs)
        combined = data_dir / f"{PREFIX}{SUFFIX[args.format]}"
        save(cd, combined)
        summary["combined"] = {
            "file": combined.name, "file_bytes": size_bytes(combined), "fovs": cd.uns["fovs"],
            "n_spots": int(cd.n_spots), "n_traces": int(cd.n_traces), "n_cells": int(cd.n_cells),
            "n_cells_annotated": int(len(cd.cells)),
            "n_tracks": int(cd.bin_tracks.shape[1] + cd.spot_tracks.shape[1]),
            "seconds": round(time.perf_counter() - t0, 1), "peak_rss_mb": round(peak_rss_mb(), 1)}
        print(cd)
        print(f"combined: {combined} ({size_bytes(combined) / 1e9:.2f} GB), peak RSS "
              f"{summary['combined']['peak_rss_mb'] / 1024:.1f} GB")
    summary["tarball_bytes"] = (data_dir / TARBALL).stat().st_size
    summary["raw_csv_bytes"] = sum(int(r["csv_bytes"]) for r in summary.get("fovs", []))
    summary["max_fov_peak_rss_mb"] = max((r["peak_rss_mb"] for r in summary.get("fovs", [])), default=None)
    summary_path.write_text(json.dumps(summary, indent=1))
    print(f"summary → {summary_path}")


if __name__ == "__main__":
    main()
