"""Writers for Higashi / FastHigashi input formats.

Higashi v2 expects:

- Per-cell text files of binned contacts with columns
  ``chrom1, pos1, chrom2, pos2, count`` (counts collapsed to one row per
  bin-pair).
- A ``filelist.txt`` with one line per cell: ``cell_name<TAB>path``.
- ``label_info.pickle``: ``dict[str, np.ndarray]``, one entry per metadata
  column, aligned to filelist order.
- ``config.JSON``: genome / resolution / chrom_list + the paths above.

See https://github.com/ma-compbio/Higashi/wiki/Input-Files for the full spec.
"""
from __future__ import annotations

import gzip
import json
import pickle
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd


def pairs_df_to_higashi(
    pairs: pd.DataFrame,
    *,
    resolution: int,
) -> pd.DataFrame:
    """Convert a ``read_pairs``-style DataFrame to Higashi's per-cell format.

    Input columns: ``chr1, pos1, chr2, pos2`` (extra columns are ignored).
    Output columns: ``chrom1, pos1, chrom2, pos2, count``.

    Positions are binned to ``resolution`` (floor), intra-chromosomal pairs
    are ordered so ``pos1 <= pos2``, and duplicates are collapsed by summing
    into ``count``.
    """
    df = pd.DataFrame({
        "chrom1": pairs["chr1"].astype(str),
        "pos1": (pairs["pos1"].astype("int64") // resolution) * resolution,
        "chrom2": pairs["chr2"].astype(str),
        "pos2": (pairs["pos2"].astype("int64") // resolution) * resolution,
    })

    intra = df["chrom1"] == df["chrom2"]
    swap = intra & (df["pos1"] > df["pos2"])
    if swap.any():
        df.loc[swap, ["pos1", "pos2"]] = df.loc[swap, ["pos2", "pos1"]].values

    out = (
        df.groupby(["chrom1", "pos1", "chrom2", "pos2"], sort=False)
          .size()
          .reset_index(name="count")
    )
    return out


def make_higashi_config(
    *,
    data_dir: str,
    genome_reference: str,
    resolution: int,
    chrom_list: list[str],
    temp_dir: str | None = None,
    cell_feats: list[str] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Higashi ``config.JSON`` dict.

    Fields follow the v2 schema from the Higashi wiki and FastHigashi's
    runtime expectations (``input_format``, ``contact_header``,
    ``header_included``).  ``overrides`` are merged last, so callers can
    tweak any field (including the required ones) without forking this
    helper.
    """
    cfg: dict[str, Any] = {
        "data_dir": data_dir,
        "temp_dir": temp_dir if temp_dir is not None else data_dir,
        "genome_reference": genome_reference,
        "resolution": int(resolution),
        # FastHigashi tries multiple resolutions; default to the same one.
        "resolution_fh": [int(resolution)],
        "chrom_list": list(chrom_list),
        "input_format": "higashi_v2",
        "cell_feats": list(cell_feats) if cell_feats else [],
        # FastHigashi reads per-cell files according to these:
        "header_included": False,
        "contact_header": ["chrom1", "pos1", "chrom2", "pos2", "count"],
    }
    if overrides:
        cfg.update(overrides)
    return cfg


def write_label_info(
    cells: pd.DataFrame,
    out_path: str | Path,
) -> Path:
    """Write a per-cell metadata DataFrame to Higashi's ``label_info.pickle``.

    Higashi expects a ``dict[str, np.ndarray]``, one entry per metadata
    column, aligned row-by-row to the filelist order.  Row order of
    ``cells`` is preserved.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, np.ndarray] = {
        col: cells[col].to_numpy() for col in cells.columns
    }
    with open(out_path, "wb") as f:
        pickle.dump(payload, f)
    return out_path


def write_higashi_inputs(
    pairs_files: Mapping[str, str | Path],
    out_dir: str | Path,
    *,
    label_info: pd.DataFrame,
    resolution: int,
    genome_reference: str,
    chrom_list: list[str],
    chromsizes: Mapping[str, int] | str | Path | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> Path:
    """Materialise a full Higashi v2 input directory.

    Produces under ``out_dir``:

    - ``data/<cell_name>.txt`` — one per cell, tab-separated
      ``chrom1, pos1, chrom2, pos2, count`` (no header).
    - ``filelist.txt`` — one absolute path per line, in ``label_info`` row order.
    - ``label_info.pickle`` — metadata aligned to filelist row order.
    - ``chromsizes.tsv`` — ``chrom<TAB>size`` (only if ``chromsizes`` given).
    - ``config.JSON`` — pointers + genome + resolution + chrom_list +
      ``genome_reference_path`` (when chromsizes were provided).

    ``label_info`` must contain a ``cell_name`` column whose values exactly
    match the keys of ``pairs_files``; filelist follows ``label_info``
    row order so FastHigashi's ``restore_order=True`` aligns to it.

    ``chromsizes`` is required by FastHigashi at runtime
    (``config['genome_reference_path']``).  Pass either a ``{chrom: size}``
    mapping (a chromsizes.tsv will be written to ``out_dir``) or an
    existing path to a tab-separated chromsizes file.
    """
    out_dir = Path(out_dir)
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    if "cell_name" not in label_info.columns:
        raise ValueError(
            "label_info must have a 'cell_name' column matching pairs_files keys"
        )
    label_names = list(label_info["cell_name"].astype(str))
    pair_names = set(pairs_files.keys())
    missing = [n for n in label_names if n not in pair_names]
    extra = [n for n in pair_names if n not in label_names]
    if missing or extra:
        raise ValueError(
            f"cell_name mismatch between label_info and pairs_files: "
            f"missing in pairs_files={missing}, extra in pairs_files={extra}"
        )

    filelist_lines: list[str] = []
    for name in label_names:
        src = Path(pairs_files[name])
        pairs = _read_pairs_file(src)
        higashi = pairs_df_to_higashi(pairs, resolution=resolution)
        out_path = data_dir / f"{name}.txt"
        # FastHigashi reads with header=None when config[header_included]=False,
        # so we write headerless tab-separated files in the column order from
        # config['contact_header'].
        higashi.to_csv(out_path, sep="\t", index=False, header=False)
        filelist_lines.append(str(out_path.resolve()))

    (out_dir / "filelist.txt").write_text("\n".join(filelist_lines) + "\n")

    write_label_info(label_info, out_dir / "label_info.pickle")

    overrides = dict(config_overrides or {})
    chromsizes_path = _materialise_chromsizes(chromsizes, out_dir)
    if chromsizes_path is not None:
        overrides.setdefault("genome_reference_path", str(chromsizes_path))

    cfg = make_higashi_config(
        data_dir=str(out_dir),
        genome_reference=genome_reference,
        resolution=resolution,
        chrom_list=chrom_list,
        overrides=overrides,
    )
    (out_dir / "config.JSON").write_text(json.dumps(cfg, indent=2))

    return out_dir


def _read_pairs_file(path: str | Path) -> pd.DataFrame:
    """Read the minimal .pairs columns needed for Higashi conversion."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as f:
        df = pd.read_csv(f, sep="\t", header=None, comment="#")
    columns = ["read", "chr1", "pos1", "chr2", "pos2", "strand1", "strand2"]
    df = df.iloc[:, :len(columns)]
    df.columns = columns[:len(df.columns)]
    return df


def _materialise_chromsizes(
    chromsizes: Mapping[str, int] | str | Path | None,
    out_dir: Path,
) -> Path | None:
    """Return a path to a chromsizes.tsv on disk, writing it if needed."""
    if chromsizes is None:
        return None
    if isinstance(chromsizes, (str, Path)):
        return Path(chromsizes)
    out_path = out_dir / "chromsizes.tsv"
    with open(out_path, "w") as f:
        for chrom, size in chromsizes.items():
            f.write(f"{chrom}\t{int(size)}\n")
    return out_path
