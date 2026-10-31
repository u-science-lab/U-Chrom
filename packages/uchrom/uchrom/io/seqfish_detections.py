"""Raw DNA seqFISH+ detections (Cai lab releases: Takei et al. 2021 *Nature* / *Science*).

The Zenodo releases of DNA seqFISH+ (e.g. record 3735329, ``DNAseqFISH+.zip`` of Takei et al. 2021,
*Nature* 590:344) hold one CSV per experiment with one row per **decoded detection**: field of view
``fov``, ``cellID`` (numbered within the FOV), the locus — ``chromID`` + ``regionID (hyb1-60)`` (25-kb
loci) or a locus name ``geneID`` (1-Mb loci) —, ``x, y`` in pixels and ``z`` in z-steps, intensities, and
in some files ``labelID``, the authors' homolog call (0, 1, …; -1 = rejected).  The detections are not
linked into chromatin fibres yet: that is :func:`uchrom.im.trace.align_spots`'s job.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np
import pandas as pd

#: voxel size of the Takei et al. 2021 DNA seqFISH+ images (nm): 103-nm pixels, 250-nm z-steps
VOXEL_NM = (103.0, 103.0, 250.0)

_REGION_25KB = "regionID (hyb1-60)"


def mouse_chrom_name(chrom_id: int) -> str:
    """``chromID`` of the mouse DNA seqFISH+ files -> chromosome name (1-19, 20 = X)."""
    return "chrX" if int(chrom_id) == 20 else f"chr{int(chrom_id)}"


def _read_csv(path, member):
    path = Path(path)
    if member is None and path.suffix != ".zip":
        return pd.read_csv(path)
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if member is None:
            raise ValueError(f"{path.name} is a zip: pass member= (one of {names})")
        hits = [n for n in names if n == member or n.endswith("/" + member)]
        if len(hits) != 1:
            raise KeyError(f"member {member!r} not in {path.name} (it has {names})")
        with zf.open(hits[0]) as fh:
            return pd.read_csv(fh)


def read_seqfish_detections(
    path,
    *,
    loci: pd.DataFrame,
    member: Optional[str] = None,
    voxel_nm: Sequence[float] = VOXEL_NM,
    chrom_name: Callable[[int], str] = mouse_chrom_name,
    cell_prefix: str = "",
):
    """Read raw DNA seqFISH+ detections into a ``ChromData`` of **untraced** spots.

    Parameters
    ----------
    path : path
        A detection CSV, or a zip of them (then ``member`` names the CSV, e.g.
        ``"DNAseqFISH+25kbloci-E14-replicate1.csv"``); read in place, nothing is extracted.
    loci : DataFrame
        The genomic locus of every probe: ``chrom, start, end`` and the key of the file's locus column —
        ``region`` (the ``regionID`` within its chromosome, 25-kb files) or ``name`` (the ``geneID``,
        1-Mb files).  Every detection's locus must be in it.
    member : str, optional
        The CSV inside a zip.
    voxel_nm : (float, float, float)
        Voxel size: coordinates become nm (``x * voxel_nm[0]`` …).
    chrom_name : callable
        ``chromID`` -> chromosome name (default: mouse, 20 = chrX).
    cell_prefix : str
        Prefixed to the cell ids (``"<prefix><fov>_<cellID>"``), e.g. to tell replicates apart.

    Returns
    -------
    ChromData
        One spot per detection, in the file's order; coordinates in nm.  ``cell_id = "<fov>_<cellID>"``;
        ``trace_id = "<cell_id>_<chrom>"``: one *candidate set* per (cell, chromosome) — all detections
        of a chromosome in a cell, both homologs together, not a fibre (``uns['trace_kind'] = 'set'``).  Spot columns ``spot_id`` (row
        number in the file), ``fov``, ``channel``, the locus key (``region`` or ``name``) and ``label``
        (``labelID``, when the file has it); the other numeric columns (intensities) are ``spot_tracks``.

    See Also
    --------
    uchrom.im.trace.align_spots : link the detections into fibres.
    """
    from chromdata import ChromData

    raw = _read_csv(path, member)
    for c in ("fov", "cellID", "x", "y", "z"):
        if c not in raw.columns:
            raise ValueError(f"not a DNA seqFISH+ detection table: no column {c!r} (columns {list(raw.columns)})")
    loci = loci.copy()
    loci["start"] = loci["start"].astype(np.int64)
    loci["end"] = loci["end"].astype(np.int64)

    if _REGION_25KB in raw.columns:                  # 25-kb loci: (chromID, regionID)
        if "chromID" not in raw.columns:
            raise ValueError(f"a {_REGION_25KB!r} column needs 'chromID'")
        key_cols, keys = ["chrom", "region"], pd.DataFrame({
            "chrom": raw["chromID"].map(chrom_name).to_numpy(),
            "region": raw[_REGION_25KB].to_numpy(dtype=np.int64)})
        loci["chrom"] = loci["chrom"].astype(str)
        loci["region"] = loci["region"].astype(np.int64)
        used = ["chromID", _REGION_25KB]
    elif "geneID" in raw.columns:                    # named loci (1 Mb)
        key_cols, keys = ["name"], pd.DataFrame({"name": raw["geneID"].astype(str).to_numpy()})
        loci["name"] = loci["name"].astype(str)
        used = ["geneID"] + (["chromID"] if "chromID" in raw.columns else [])
    else:
        raise ValueError(f"no locus column ({_REGION_25KB!r} or 'geneID') in {list(raw.columns)}")
    missing = [c for c in key_cols + ["chrom", "start", "end"] if c not in loci.columns]
    if missing:
        raise ValueError(f"loci misses the columns {missing}")
    if loci.duplicated(key_cols).any():
        raise ValueError(f"loci repeats a {key_cols} key")
    lk = loci.set_index(key_cols, drop=False)
    row = lk.index.get_indexer(pd.MultiIndex.from_frame(keys) if len(key_cols) > 1 else keys[key_cols[0]])
    if (row < 0).any():
        bad = keys[row < 0].drop_duplicates().head(3).to_dict("records")
        raise ValueError(f"{int((row < 0).sum())} detections at loci missing from loci=, e.g. {bad}")
    locus = lk.iloc[row]

    cell = cell_prefix + raw["fov"].astype(str) + "_" + raw["cellID"].astype(str)
    chrom = locus["chrom"].astype(str).to_numpy()
    spots = pd.DataFrame({"chrom": chrom, "start": locus["start"].to_numpy(), "end": locus["end"].to_numpy(),
                          "trace_id": (cell + "_" + chrom).to_numpy(), "cell_id": cell.to_numpy(),
                          "spot_id": np.arange(len(raw), dtype=np.int64),
                          "fov": raw["fov"].to_numpy()})
    if "channel" in raw.columns:
        spots["channel"] = raw["channel"].to_numpy()
    key = key_cols[-1]                               # "region" or "name"
    spots[key] = keys[key].to_numpy()
    if "labelID" in raw.columns:
        spots["label"] = raw["labelID"].fillna(-1).astype(np.int64).to_numpy()
        used.append("labelID")
    rest = [c for c in raw.columns if c not in {"fov", "cellID", "channel", "x", "y", "z", *used}]
    tracks = raw[[c for c in rest if pd.api.types.is_numeric_dtype(raw[c])]].reset_index(drop=True)
    for c in rest:
        if c not in tracks.columns:
            spots[c] = raw[c].to_numpy()

    v = np.asarray(voxel_nm, dtype=np.float64)
    coords = raw[["x", "y", "z"]].to_numpy(dtype=np.float64) * v
    bins = (loci[["chrom", "start", "end"]].drop_duplicates()
            .sort_values(["chrom", "start", "end"], kind="mergesort").reset_index(drop=True))
    cells = pd.DataFrame({"fov": raw["fov"].to_numpy(), "cell_id": cell.to_numpy()}).drop_duplicates("cell_id")
    cells = cells.set_index("cell_id")
    src = Path(path).name + (f"!{member}" if member else "")
    return ChromData(coords, spots, bins=bins, cells=cells, spot_tracks=tracks,
                     uns={"xyz_unit": "nm", "voxel_nm": [float(x) for x in v], "trace_kind": "set",
                          "source": f"DNA seqFISH+ detections {src}"})


__all__ = ["read_seqfish_detections", "mouse_chrom_name", "VOXEL_NM"]
