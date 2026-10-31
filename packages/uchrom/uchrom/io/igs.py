"""In situ genome sequencing (IGS; Payne et al. 2021, *Science* 371:eaay3446): reads sequenced in place.

The authors' tables (GitHub zchiang/in_situ_genome_sequencing_analysis, ``data/``, described in
``Table_S3_description_of_data.xlsx``) hold one row per **read**: its position in the nucleus (µm), the genomic
position of its alignment and the authors' calls — the chromosome territory (homolog) it falls in, and in the
embryos the parent of that territory.  Two tables:

* ``Table_S1_pgp1_data_table.csv`` — 106 human PGP1 fibroblasts (hg38): ``cell_id``, ``x_um, y_um, z_um``,
  ``hg38_chr`` (1-22, 23 = X, 24 = Y; higher codes are not primary chromosomes), ``hg38_pos``, ``cluster``
  (territory: 1 / 2, 0 = none) and ``mle_cluster``;
* ``Table_S2_embryo_data_table.csv`` — 113 cells of 57 mouse zygotes, 2-cell and 4-cell embryos (mm10):
  ``embryo_id, cell_id`` (within the embryo), ``stage``, ``x_um_abs, …`` (in the embryo's frame), ``chr_name``,
  ``pos``, ``cluster`` (1 / 2, 0 = none, -1 = territories overlap) and ``cluster_hap_imputed`` (the territory's
  parent: 0 maternal, 1 paternal, -1 not known).

A read is one observation of its locus, a chromosome territory is not an ordered fibre: each territory is a
trace that holds its reads as an unordered set (``uns['trace_kind'] = 'set'``).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

#: genome assembly of each table (detected from its columns)
ASSEMBLY = {"pgp1": "hg38", "embryo": "mm10"}

# column roles: the read's keys and position, kept as spot columns (labels), dropped (folded into others)
_KEYS = {
    "pgp1": dict(cell="cell_id", x="x_um", y="y_um", z="z_um", chrom="hg38_chr", pos="hg38_pos"),
    "embryo": dict(cell="cell_index", x="x_um_abs", y="y_um_abs", z="z_um_abs", chrom="chr_name", pos="pos"),
}
_LABELS = ("amp_ind", "cluster", "mle_cluster", "hap_assignment", "cluster_hap", "cluster_hap_imputed",
           "inlier", "npb_ind", "cen_ind", "hg38_ind", "umi_ind", "ab_comp", "lads", "compartment_ind",
           "lads_both", "lads_mat", "lads_pat")
_DROP = {"pgp1": (), "embryo": ("embryo_id", "cell_id", "stage", "chr", "rel_chr_pos")}
_PARENT = {0: "mat", 1: "pat"}


def _kind(columns) -> str:
    if "hg38_chr" in columns:
        return "pgp1"
    if "chr_name" in columns and "embryo_id" in columns:
        return "embryo"
    raise ValueError(f"not an IGS data table (Table S1 / S2): columns {list(columns)}")


def _chrom_names(raw: pd.DataFrame, kind: str) -> pd.Series:
    """Primary chromosome of each read (``chr1`` …, ``chrX``, ``chrY``), None for the others."""
    if kind == "pgp1":
        code = raw["hg38_chr"].to_numpy()
        names = {**{i: f"chr{i}" for i in range(1, 23)}, 23: "chrX", 24: "chrY"}
        return pd.Series([names.get(int(c)) for c in code], index=raw.index, dtype=object)
    name = raw["chr_name"].astype(str)
    primary = name.str.fullmatch(r"chr(\d+|X|Y)")
    return name.where(primary, None).astype(object)


def _homolog(raw: pd.DataFrame, kind: str) -> np.ndarray:
    """The territory of each read: ``mat`` / ``pat`` (embryos, a territory whose parent is known), ``h1`` /
    ``h2``, ``none`` (not in a territory), ``overlap`` (territories overlap), ``c<k>`` (other calls)."""
    cluster = raw["cluster"].to_numpy()
    tag = np.array([f"h{c}" if c in (1, 2) else "none" if c == 0 else "overlap" if c == -1 else f"c{c}"
                    for c in cluster], dtype=object)
    if kind == "embryo":
        parent = raw["cluster_hap_imputed"].to_numpy()
        for p, name in _PARENT.items():
            tag[(parent == p) & np.isin(cluster, (1, 2))] = name
    return tag


def read_igs(path, *, resolution: int = 1_000_000):
    """Read an IGS data table (Payne et al. 2021) into a ``ChromData`` of reads.

    Parameters
    ----------
    path : path
        ``Table_S1_pgp1_data_table.csv`` (human fibroblasts) or ``Table_S2_embryo_data_table.csv`` (mouse
        embryos); the table is recognised by its columns.
    resolution : int
        Size of the genomic bins (bp) the reads are placed in; the read's own position stays in the spot
        column ``pos``.

    Returns
    -------
    ChromData
        One spot per read on a primary chromosome, coordinates in µm.  ``trace_id =
        "<cell>_<chrom>_<homolog>"``: the reads of one chromosome territory, an unordered set
        (``uns['trace_kind'] = 'set'``; several reads may share a bin), ``homolog`` as in the traces table —
        ``mat`` / ``pat`` (embryos), ``h1`` / ``h2``, ``none`` (reads outside the territories), ``overlap``.
        Spot columns ``spot_id`` (row in the file), ``pos``, the authors' labels (``cluster``,
        ``cluster_hap_imputed``, ``amp_ind``, …) and text columns (``umi_seq``, repeat annotations); the other
        numeric columns (quality scores, distances to the lamina / nucleolar bodies, GC) are ``spot_tracks``.
        Cells: PGP1 ``"<cell_id>"``; embryos ``"e<embryo_id>.<cell_id>"`` with ``embryo``, ``stage``,
        ``cell_index``.  Reads off the primary chromosomes (chrM, unplaced contigs, several UMIs, codes the
        authors leave undescribed) are ``points['other_reads']`` with their ``chrom_label`` and ``pos``.
    """
    from chromdata import ChromData

    path = Path(path)
    raw = pd.read_csv(path)
    kind = _kind(raw.columns)
    k = _KEYS[kind]
    if kind == "embryo":
        cell = "e" + raw["embryo_id"].astype(str) + "." + raw["cell_id"].astype(str)
    else:
        cell = raw["cell_id"].astype(str)
    chrom = _chrom_names(raw, kind)
    on = chrom.notna().to_numpy()
    homolog = _homolog(raw, kind)
    xyz = raw[[k["x"], k["y"], k["z"]]].to_numpy(dtype=np.float64)

    order = [c for c in (f"chr{i}" for i in range(1, 23)) if c in set(chrom[on])] + \
        [c for c in ("chrX", "chrY") if c in set(chrom[on])]
    pos = raw[k["pos"]].to_numpy(dtype=np.int64)
    start = pos // resolution * resolution
    r = raw[on].reset_index(drop=True)
    spots = pd.DataFrame({
        "chrom": pd.Categorical(chrom[on].to_numpy(), categories=order),
        "start": start[on], "end": start[on] + resolution,
        "trace_id": (cell[on] + "_" + chrom[on] + "_" + homolog[on]).to_numpy(),
        "cell_id": cell[on].to_numpy(),
        "spot_id": np.flatnonzero(on).astype(np.int64),
        "pos": pos[on]})
    used = {k["cell"], k["x"], k["y"], k["z"], k["chrom"], k["pos"], *_DROP[kind]}
    tracks = {}
    for c in r.columns:
        if c in used:
            continue
        if c in _LABELS or not pd.api.types.is_numeric_dtype(r[c]):
            spots[c] = r[c].to_numpy()
        else:
            tracks[c] = r[c].to_numpy()

    traces = (spots.groupby("trace_id", sort=False, observed=True)
              .agg(cell_id=("cell_id", "first"), chrom=("chrom", "first"), n_reads=("pos", "size")))
    traces["chrom"] = traces["chrom"].astype(str)
    traces["homolog"] = [t.rsplit("_", 1)[1] for t in traces.index]
    traces.index.name = "trace_id"

    cells = pd.DataFrame({"cell_id": cell.to_numpy()})
    if kind == "embryo":
        cells = cells.assign(embryo=raw["embryo_id"].to_numpy(), stage=raw["stage"].astype(str).to_numpy(),
                             cell_index=raw["cell_index"].to_numpy())
    cells = cells.drop_duplicates("cell_id").set_index("cell_id")
    cells["n_reads"] = cell.value_counts().reindex(cells.index).to_numpy()
    cells["n_reads_primary"] = cell[on].value_counts().reindex(cells.index).fillna(0).astype(np.int64).to_numpy()

    off = ~on
    label = raw[k["chrom"]].astype(str)
    other = pd.DataFrame({"x": xyz[off, 0], "y": xyz[off, 1], "z": xyz[off, 2], "cell_id": cell[off].to_numpy(),
                          "chrom_label": label[off].to_numpy(), "pos": pos[off],
                          "spot_id": np.flatnonzero(off).astype(np.int64)})
    bins = (spots[["chrom", "start", "end"]].drop_duplicates()
            .sort_values(["chrom", "start"], kind="mergesort").reset_index(drop=True))
    bins["resolution"] = resolution
    uns = {"xyz_unit": "um", "genome_assembly": ASSEMBLY[kind], "trace_kind": "set",
           "source": f"IGS data table {path.name} (Payne et al. 2021, Science 371:eaay3446)",
           "igs": {"table": kind, "resolution": int(resolution),
                   "trace": "the reads of one chromosome territory (cluster), not an ordered fibre",
                   "homolog": "mat / pat: cluster_hap_imputed; h1 / h2: cluster; none: cluster 0; "
                              "overlap: cluster -1"}}
    return ChromData(xyz[on], spots, bins=bins, cells=cells, traces=traces,
                     spot_tracks=pd.DataFrame(tracks), points={"other_reads": other} if len(other) else None,
                     uns=uns)


__all__ = ["read_igs", "ASSEMBLY"]
