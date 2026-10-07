"""Chromatin-tracing tables and binned Hi-C of Su et al. 2020 (Zhuang lab; Zenodo 3928890).

Su, Zheng, Kinrot, Bintu & Zhuang 2020, *Cell* 182:1641 ("Genome-scale imaging of the 3D organization and
transcriptional activity of chromatin") publish their traces as tab-separated tables, one row per (imaged
chromosome copy, locus), coordinates in nm, hg38.  Two layouts:

* **chromosome scale** (sequential hybridization: ``chromosome21.tsv``, ``chromosome2.tsv``,
  ``chromosome2_p-arm_replicate.tsv``, ``chromosome21-cell_cycle.tsv``): ``Z(nm)``, ``X(nm)``, ``Y(nm)``,
  ``Genomic coordinate`` (``chr21:10400001-10450001``), ``Chromosome copy number`` (one trace per imaged
  copy; copies are not grouped into cells), optionally ``Gene names`` (per locus, ``;``-separated),
  ``Transcription`` (per spot, one ``on`` / ``off`` per gene), ``TSS ZXY(nm)`` and ``Cell cycle state``;
* **genome scale** (DNA-MERFISH: ``genomic-scale.tsv`` and its ``-with transcription and nuclear bodies`` /
  ``-amanitin`` variants): ``z(nm)``, ``x(nm)``, ``y(nm)``, ``genomic coordinate`` (``chr1:2950000-3050000``),
  ``homolog number``, ``cell number`` (unique over the experiments), ``experiment number``, optionally
  ``gene names`` (``,``-separated), ``transciption`` [sic], and ``distance to lamina / nucleoli / speckles
  (nm)``.

Undetected loci are rows with ``nan`` coordinates.  The binned Hi-C files (``Hi-C_contacts_*.tsv``: Rao et
al. 2014 IMR90 reads summed into bins centred on the imaged loci — 50 kb for the chromosome-scale loci,
500 kb for the genome-scale ones) are square tables labelled with the same locus names.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional, Tuple, Union

import numpy as np
import pandas as pd

__all__ = ["read_su2020_tracing", "read_su2020_hic"]

_LABEL = re.compile(r"^(chr[^:]+):(\d+)-(\d+)$")
_SOURCE = "Su et al. 2020 (Cell 182:1641), Zenodo 3928890"

#: optional outputs of read_su2020_tracing(extras=...) -> where they go
EXTRAS = {
    "genes": "bin_tracks", "n_genes": "bin_tracks", "transcription": "spot_tracks",
    "distance_to_lamina": "spot_tracks", "distance_to_nucleoli": "spot_tracks",
    "distance_to_speckles": "spot_tracks", "cell_cycle": "traces",
}


def _parse_labels(labels, offset: Optional[int], what: str) -> pd.DataFrame:
    """Locus labels ``chrN:a-b`` -> chrom, start, end (``offset`` subtracted from both; ``None``: 1 when every
    start and end is odd — the chromosome-scale labels count from 1 — else 0)."""
    labels = pd.Series(np.asarray(labels, dtype=object), dtype=object)
    parts = labels.str.extract(_LABEL)
    bad = parts[0].isna().to_numpy()
    if bad.any():
        raise ValueError(f"{what}: locus labels must look like 'chr21:10400001-10450001'; got "
                         f"{labels[bad].head(3).tolist()}")
    start = parts[1].astype(np.int64).to_numpy()
    end = parts[2].astype(np.int64).to_numpy()
    if offset is None:
        offset = 1 if ((start % 2 == 1).all() and (end % 2 == 1).all()) else 0
    return pd.DataFrame({"chrom": parts[0].to_numpy(dtype=object), "start": start - int(offset),
                         "end": end - int(offset)})


def _split(values: pd.Series, sep: str) -> pd.Series:
    """``"A;B;"`` -> ``"A;B"`` (empty / missing -> ``""``)."""
    parts = values.fillna("").astype(str).str.split(sep)
    return parts.map(lambda xs: ";".join(x.strip() for x in xs if x.strip()))


def _extras(extras, available: Iterable[str]) -> list:
    available = list(available)
    if extras is True:
        return available
    if extras is False or extras is None:
        return []
    names = [extras] if isinstance(extras, str) else list(extras)
    unknown = [n for n in names if n not in EXTRAS]
    if unknown:
        raise ValueError(f"extras: unknown {unknown}; known: {sorted(EXTRAS)}")
    missing = [n for n in names if n not in available]
    if missing:
        raise ValueError(f"extras: {missing} not in this file (it has {available or 'none'})")
    return names


def read_su2020_tracing(
    path,
    *,
    unit: str = "micron",
    keep_missing: bool = False,
    extras: Union[bool, str, Iterable[str]] = True,
    label_offset: Optional[int] = None,
    genome_assembly: str = "hg38",
):
    """Read a Su et al. 2020 chromatin-tracing table into a ``ChromData``.

    Reads both layouts of the authors' Zenodo record 3928890 (module docstring): the chromosome-scale
    tables (``chromosome21.tsv``, ``chromosome2.tsv``, ...: one trace per imaged chromosome copy,
    ``trace_id`` = the authors' copy number, no cells) and the genome-scale DNA-MERFISH tables
    (``genomic-scale.tsv``, ...: ``cell_id`` = the authors' cell number, one trace per cell, chromosome and
    homolog, ``trace_id = "<cell>_<chrom>_h<homolog>"``; ``cells["experiment"]``, ``traces[["cell_id",
    "chrom", "homolog"]]``).  Every locus of the file is a bin, also one that was never detected.

    Parameters
    ----------
    path : str or Path
        The ``.tsv`` table.
    unit : {"micron", "nm"}
        Unit of the coordinates (and of the distance columns); the files are in nm.
    keep_missing : bool
        Keep undetected loci as rows with NaN coordinates; by default they are left out.
    extras : bool, str or list of str
        The optional columns to read — ``True`` (default): all the file has; ``False``: none; or names
        among ``"genes"`` (``bin_tracks``: the genes listed for the locus, ``;``-separated), ``"n_genes"``
        (``bin_tracks``: their number), ``"transcription"`` (``spot_tracks``: ``on`` / ``off`` per gene of
        the locus, ``;``-separated, in the order of ``genes``), ``"distance_to_lamina"`` /
        ``"distance_to_nucleoli"`` / ``"distance_to_speckles"`` (``spot_tracks``, in ``unit``) and
        ``"cell_cycle"`` (``traces``: the cell-cycle state of the copy).  ``TSS ZXY(nm)`` is not read.
    label_offset : int, optional
        Subtracted from both ends of a locus label.  Default: 1 for the chromosome-scale tables (their
        labels count from 1: ``chr21:10400001-10450001`` is the 50 kb locus starting at 10,400,000 and
        ``chr2:1-50001`` the first 50 kb of chr2), 0 for the genome-scale ones (``chr1:2950000-3050000``,
        100 kb).
    genome_assembly : str
        Recorded in ``uns`` (the files are on hg38).

    Returns
    -------
    ChromData
        ``uns``: ``genome_assembly``, ``xyz_unit``, ``source``.
    """
    from chromdata import ChromData
    from chromdata.bins import bins_from_loci

    if unit not in ("micron", "nm"):
        raise ValueError(f"unit must be 'micron' or 'nm', got {unit!r}")
    path = Path(path)
    header = pd.read_csv(path, sep="\t", nrows=0).columns
    cols = {str(c).strip().lower(): c for c in header}
    need = ["z(nm)", "x(nm)", "y(nm)", "genomic coordinate"]
    if "chromosome copy number" in cols:
        genome_scale = False
        need += ["chromosome copy number"]
    elif {"homolog number", "cell number"} <= set(cols):
        genome_scale = True
        need += ["homolog number", "cell number"] + (["experiment number"] if "experiment number" in cols else [])
    else:
        raise ValueError(f"{path.name}: not a Su 2020 tracing table (no 'Chromosome copy number' or "
                         f"'homolog number' / 'cell number' column); columns: {list(header)}")
    missing = [c for c in need if c not in cols]
    if missing:
        raise ValueError(f"{path.name}: missing column(s) {missing}")

    source_of = {}                       # extra output -> file column
    if "gene names" in cols:
        source_of["genes"] = source_of["n_genes"] = "gene names"
    for name in ("transcription", "transciption"):
        if name in cols:
            source_of["transcription"] = name
    for c in cols:
        m = re.fullmatch(r"distance to (\w+) \(nm\)", c)
        if m and f"distance_to_{m.group(1)}" in EXTRAS:
            source_of[f"distance_to_{m.group(1)}"] = c
    if "cell cycle state" in cols:
        source_of["cell_cycle"] = "cell cycle state"
    wanted = _extras(extras, [k for k in EXTRAS if k in source_of])

    use = need + sorted({source_of[k] for k in wanted})
    text = {cols[c]: str for c in use if c in ("genomic coordinate", "gene names", "transcription", "transciption",
                                               "cell cycle state")}
    raw = pd.read_csv(path, sep="\t", usecols=[cols[c] for c in use], dtype=text)
    raw.columns = [str(c).strip().lower() for c in raw.columns]

    # loci: parse each distinct label once
    codes, labels = pd.factorize(raw["genomic coordinate"], sort=False)
    loci = _parse_labels(labels, (1 if not genome_scale else 0) if label_offset is None else label_offset,
                         path.name)
    bins, label_bin = bins_from_loci(loci)
    bin_tracks = pd.DataFrame(index=bins.index)
    if "genes" in wanted or "n_genes" in wanted:
        first = np.unique(codes, return_index=True)[1]          # the genes are listed per locus: first row
        genes = _split(raw["gene names"].iloc[first], "," if genome_scale else ";").to_numpy(dtype=object)
        per_bin = np.full(len(bins), "", dtype=object)
        per_bin[label_bin] = genes
        if "genes" in wanted:
            bin_tracks["genes"] = per_bin
        if "n_genes" in wanted:
            bin_tracks["n_genes"] = np.array([len(g.split(";")) if g else 0 for g in per_bin], dtype=np.int64)

    if not keep_missing:
        ok = raw[["x(nm)", "y(nm)", "z(nm)"]].notna().all(axis=1).to_numpy()
        raw, codes = raw[ok].reset_index(drop=True), codes[ok]
    scale = 1000.0 if unit == "micron" else 1.0
    coords = raw[["x(nm)", "y(nm)", "z(nm)"]].to_numpy(float)
    if scale != 1.0:
        coords = coords / scale
    bin_id = label_bin[codes]

    cells = traces = None
    if not genome_scale:
        spots = pd.DataFrame({"trace_id": raw["chromosome copy number"].to_numpy(np.int64), "bin_id": bin_id})
        if "cell_cycle" in wanted:
            per_copy = raw.drop_duplicates("chromosome copy number")
            traces = pd.DataFrame({"cell_cycle": per_copy["cell cycle state"].to_numpy(dtype=object)},
                                  index=pd.Index(per_copy["chromosome copy number"].to_numpy(np.int64), name="trace_id"))
    else:                                # one trace per (cell, chromosome, homolog)
        cell = raw["cell number"].to_numpy(np.int64)
        key = pd.DataFrame({"cell": cell, "chrom": bins["chrom"].astype(str).to_numpy(dtype=object)[bin_id],
                            "homolog": raw["homolog number"].to_numpy(np.int64)})
        tcode = key.groupby(["cell", "chrom", "homolog"], sort=False).ngroup().to_numpy()
        tkeys = key.drop_duplicates().reset_index(drop=True)          # the groups in order of first appearance
        names = np.array([f"{c}_{ch}_h{h}" for c, ch, h in zip(tkeys["cell"], tkeys["chrom"], tkeys["homolog"])],
                         dtype=object)
        spots = pd.DataFrame({"trace_id": names[tcode], "cell_id": cell, "bin_id": bin_id})
        traces = pd.DataFrame({"cell_id": tkeys["cell"].to_numpy(), "chrom": tkeys["chrom"].to_numpy(dtype=object),
                               "homolog": tkeys["homolog"].to_numpy()}, index=pd.Index(names, name="trace_id"))
        per_cell = raw.drop_duplicates("cell number")
        cells = pd.DataFrame(index=pd.Index(per_cell["cell number"].to_numpy(np.int64), name="cell_id"))
        if "experiment number" in raw.columns:
            cells["experiment"] = per_cell["experiment number"].to_numpy(np.int64)

    spot_tracks = None
    spot_cols = [k for k in wanted if EXTRAS[k] == "spot_tracks"]
    if spot_cols:
        spot_tracks = pd.DataFrame(index=pd.RangeIndex(len(raw)))
        for k in spot_cols:
            col = raw[source_of[k]]
            if k == "transcription":
                spot_tracks[k] = _split(col, "," if genome_scale else ";").to_numpy(dtype=object)
            else:
                spot_tracks[k] = col.to_numpy(float) / scale

    cd = ChromData(coords=coords, spots=spots, bins=bins, cells=cells, traces=traces, spot_tracks=spot_tracks,
                   uns={"genome_assembly": genome_assembly, "xyz_unit": unit, "source": f"{_SOURCE}: {path.name}"})
    if len(bin_tracks.columns):
        cd.bin_tracks = bin_tracks
    return cd


def read_su2020_hic(path, *, label_offset: Optional[int] = None) -> Tuple[pd.DataFrame, np.ndarray]:
    """Read one of the Su et al. 2020 binned Hi-C tables (``Hi-C_contacts_chromosome21.tsv``, ...).

    The authors summed Rao et al. 2014 IMR90 Hi-C reads into bins centred on their imaged loci (50 kb for the
    chromosome-scale loci, 500 kb around each 100 kb genome-scale locus) and label rows and columns with the
    locus names of the tracing tables.  :func:`uchrom.io.write_locus_cool` writes the result as a ``.cool``.

    Parameters
    ----------
    path : str or Path
        The square tab-separated table (first column and header: locus labels).
    label_offset : int, optional
        Subtracted from both ends of a label; default 1 when every label start and end is odd (the
        chromosome-scale labels count from 1, ``chr21:10400001-10450001``), else 0 (genome scale) — as in
        :func:`read_su2020_tracing`.

    Returns
    -------
    loci : DataFrame
        ``chrom``, ``start``, ``end`` of the rows / columns, in file order (index 0..n-1).
    counts : ndarray (n, n)
        float64, as in the file (read counts).
    """
    path = Path(path)
    table = pd.read_csv(path, sep="\t", index_col=0)
    rows, columns = [str(x) for x in table.index], [str(x) for x in table.columns]
    if rows != columns:
        raise ValueError(f"{path.name}: the row and column labels differ (not a square locus x locus table)")
    return _parse_labels(rows, label_offset, path.name), table.to_numpy(np.float64)
