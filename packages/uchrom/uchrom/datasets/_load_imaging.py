"""Imaging datasets as ``ChromData``: traces with missing loci, raw (untraced) detections."""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from ._loaders import Loader, register

#: the 25-kb replicate-1 detections of Takei et al. 2021 inside the Zenodo zip (``fetch("seqfish")``)
TAKEI2021_25KB_REP1 = "DNAseqFISH+/DNAseqFISH+25kbloci-E14-replicate1.csv"


def build_huang2021_sox2(root: Path, out: Path):
    """Huang et al. 2021 ORCA tracing of the Sox2 locus in 129 x CAST mouse ES cells at 5 kb, as distributed
    with SnapFISH-IMPUTE: 1,416 cells x 2 alleles (129, CAST) x 41 loci of chr3 (mm10), undetected loci kept
    as NaN rows (29 %).  Trace ``"<cell>_<allele>"``, spot / trace column ``allele``; the cell ids are the
    4DN ones (``cell_id.11`` -> ``11``), so traces carry the ids of 4DN 4DNFI9KE6AII."""
    from uchrom.io import read_snapfish

    from . import fetch

    folder = fetch("huang2021_sox2", root=root)
    coor = pd.read_csv(folder / "mESC_Sox2_coor_wnan.txt", sep="\t", dtype={"region": str, "haploid": str})
    coor["haploid"] = coor["haploid"].str.removeprefix("cell_id.")
    ann = pd.read_csv(folder / "mESC_Sox2_ann.txt", sep="\t", dtype={"region": str})
    cd = read_snapfish(coor, ann, chrom="chr3", region_name="allele", cell_id=True, genome_assembly="mm10")
    cd.uns["source"] = (
        "Huang et al. 2021, Nat Genet 53:1064 (doi:10.1038/s41588-021-00863-6): ORCA chromatin tracing of the "
        "Sox2 locus (chr3:34,601,078-34,806,078, mm10; 41 x 5 kb) in 129 x CAST mouse ES cells; tables of "
        "SnapFISH-IMPUTE (github.com/hyuyu104/SnapFISH-IMPUTE @7f7f1a7, from 4DN 4DNFI9KE6AII), whose "
        "preprocessing left locus 26 of the 129 allele empty in every cell; coordinates in nm")
    return cd


def takei2021_locus_map(raw: pd.DataFrame, fofct: pd.DataFrame, *, voxel_um=(0.103, 0.103, 0.25)):
    """The mm10 locus of every (chromosome, regionID) of the Takei et al. 2021 25-kb detections, recovered
    from the traced FOF-CT table of the same experiment (4DN 4DNFIHF3JCBY): its coordinates are the
    detections' (pixels x voxel size in um, 3 decimals), so the two tables match spot for spot.

    Returns ``(loci, check)``: ``loci`` with ``chrom, region, start, end``; ``check`` the counts behind it
    (matched detections, same cell, FOF-CT homolog suffix == ``labelID``).  Raises when a detection has no
    match or a (chromosome, regionID) maps to two loci."""
    from uchrom.io.seqfish_detections import mouse_chrom_name

    def key(x, y, z):
        return pd.MultiIndex.from_arrays([np.round(x, 3), np.round(y, 3), np.round(z, 3)])

    f_idx = pd.Series(np.arange(len(fofct)), index=key(fofct["x"], fofct["y"], fofct["z"]))
    if f_idx.index.has_duplicates:
        raise ValueError("two FOF-CT spots share a position: cannot match by position")
    row = f_idx.reindex(key(raw["x"] * voxel_um[0], raw["y"] * voxel_um[1], raw["z"] * voxel_um[2])).to_numpy()
    if np.isnan(row).any():
        raise ValueError(f"{int(np.isnan(row).sum())} detections have no FOF-CT spot at their position")
    m = fofct.iloc[row.astype(np.int64)]
    cell = raw["fov"].astype(str) + "_" + raw["cellID"].astype(str)
    same_cell = float(np.mean(m["cell_id"].astype(str).to_numpy() == cell.to_numpy()))
    suffix = m["trace_id"].astype(str).str.rsplit("_", n=1).str[-1].to_numpy()
    same_label = float(np.mean(suffix == raw["labelID"].astype(str).to_numpy())) if "labelID" in raw else None
    loci = pd.DataFrame({"chrom": raw["chromID"].map(mouse_chrom_name).to_numpy(),
                         "region": raw["regionID (hyb1-60)"].to_numpy(),
                         "start": m["start"].to_numpy(), "end": m["end"].to_numpy()}).drop_duplicates()
    if loci.duplicated(["chrom", "region"]).any():
        raise ValueError("a (chromosome, regionID) matches two loci")
    loci = loci.sort_values(["chrom", "start"]).reset_index(drop=True)
    check = {"matched": int(len(row)), "detections": int(len(raw)), "same_cell": same_cell,
             "label_equals_fofct_homolog": same_label, "loci": int(len(loci))}
    return loci, check


def build_takei2021_mesc_detections(root: Path, out: Path):
    """Takei et al. 2021 raw DNA seqFISH+ detections of mouse ES cells (Zenodo 3735329, 25-kb loci, replicate
    1): 316,995 detections in 201 cells, 20 chromosomes x 60 loci, coordinates in nm, untraced (one
    candidate set per cell and chromosome), the authors' homolog call as spot column ``label``; the mm10
    locus of every probe recovered from the traced FOF-CT table of the same experiment
    (:func:`takei2021_locus_map`, recorded in ``uns["locus_map"]``)."""
    from chromdata import ChromData

    from uchrom.io import read_seqfish_detections

    from . import fetch

    zpath = fetch("seqfish", root=root)
    with zipfile.ZipFile(zpath) as zf, zf.open(TAKEI2021_25KB_REP1) as fh:
        raw = pd.read_csv(fh)
    fofct = ChromData.from_fofct(fetch("takei", root=root)).to_dataframe()
    loci, check = takei2021_locus_map(raw, fofct)
    if check["same_cell"] < 1 or (check["label_equals_fofct_homolog"] or 0) < 1:
        raise ValueError(f"the detections do not match the FOF-CT table: {check}")
    cd = read_seqfish_detections(zpath, member=TAKEI2021_25KB_REP1, loci=loci)
    cd.uns["genome_assembly"] = "mm10"
    cd.uns["locus_map"] = {"source": "4DN 4DNFIHF3JCBY (FOF-CT) matched by position", **check}
    cd.uns["source"] = (
        "Takei et al. 2021, Nature 590:344: DNA seqFISH+ of E14 mouse ES cells, raw detections of the 25-kb "
        "loci, replicate 1 (Zenodo 3735329, DNAseqFISH+.zip); label = the authors' homolog call (labelID, "
        "-1 = rejected)")
    return cd


register(Loader(
    name="huang2021_sox2", build=build_huang2021_sox2, store="huang2021_sox2/huang2021_sox2.chromdata.zarr",
    sources=("huang2021_sox2",),
    description="Huang 2021 mESC Sox2 ORCA tracing (SnapFISH-IMPUTE tables): 1,416 cells x 2 alleles x 41 loci "
                "of 5 kb, undetected loci as NaN rows"))
register(Loader(
    name="takei2021_mesc_detections", build=build_takei2021_mesc_detections,
    store="takei2021_mesc/takei2021_mesc_detections.chromdata.zarr", sources=("seqfish", "takei"),
    description="Takei 2021 mESC raw DNA seqFISH+ detections (Zenodo, 25-kb loci, rep 1): 316,995 untraced "
                "spots in 201 cells, the authors' homolog call as `label`"))


def _build_payne2021_igs(table: str):
    def build(root: Path, out: Path):
        """Payne et al. 2021 in situ genome sequencing (IGS), the authors' read table (:func:`uchrom.io.read_igs`):
        one spot per read on 1-Mb bins, a trace per chromosome territory (an unordered set of reads)."""
        from uchrom.io import read_igs

        from . import fetch

        fetch("payne2021_igs", root=root)
        cd = read_igs(root / "payne2021_igs" / "raw" / table)
        cd.uns["source"] = (
            "Payne et al. 2021, Science 371:eaay3446: in situ genome sequencing, the authors' read table "
            f"{table} (GitHub zchiang/in_situ_genome_sequencing_analysis, MIT licence)")
        return cd
    return build


register(Loader(
    name="payne2021_igs_pgp1", build=_build_payne2021_igs("Table_S1_pgp1_data_table.csv"),
    store="payne2021_igs/payne2021_igs_pgp1.chromdata.zarr", sources=("payne2021_igs",),
    description="Payne 2021 IGS of PGP1 human fibroblasts (hg38): 29,707 reads in 106 cells placed on 1-Mb bins, "
                "a trace per chromosome territory (homologs h1 / h2), other reads as points"))
register(Loader(
    name="payne2021_igs_embryo", build=_build_payne2021_igs("Table_S2_embryo_data_table.csv"),
    store="payne2021_igs/payne2021_igs_embryo.chromdata.zarr", sources=("payne2021_igs",),
    description="Payne 2021 IGS of mouse zygotes, 2-cell and 4-cell embryos (mm10): 247,593 reads in 113 cells of "
                "57 embryos, a trace per chromosome territory (maternal / paternal), other reads as points"))
