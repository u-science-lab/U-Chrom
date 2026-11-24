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


def _build_beckwith2025(source: str, archive: str, member: str):
    def build(root: Path, out: Path):
        """Beckwith et al. 2025 (Ellenberg lab), the authors' LoopTrace table (:func:`uchrom.io.read_looptrace`):
        one spot per fitted locus, loci = windows of the library's spot size around ``g_pos`` (hg38), nm."""
        import shutil

        from uchrom.io import read_looptrace

        from . import fetch

        fetch(source, root=root)
        raw = root / "beckwith2025" / "raw"
        table = raw / Path(member).name
        if not table.is_file():
            with zipfile.ZipFile(raw / archive) as z, z.open(member) as src, open(table.with_suffix(".part"), "wb") as dst:
                shutil.copyfileobj(src, dst)
            table.with_suffix(".part").rename(table)
        cd = read_looptrace(table)
        paper = ("Beckwith et al. 2025, Cell 188:2656 (doi:10.1016/j.cell.2025.02.028), figshare 27003022"
                 if source == "beckwith2025_mitosis" else
                 "Beckwith et al. 2025, Nat Commun 16:6673 (doi:10.1038/s41467-025-61689-y), figshare 27613239")
        cd.uns["source"] = f"{paper} (CC BY 4.0): the authors' table {Path(member).name}"
        return cd
    return build


register(Loader(
    name="beckwith2025_mitosis",
    build=_build_beckwith2025("beckwith2025_mitosis", "mitofold1_data_code.zip", "exp_data/mitofold_traces.csv.gz"),
    store="beckwith2025/beckwith2025_mitosis.chromdata.zarr", sources=("beckwith2025_mitosis",),
    description="Beckwith 2025 mitotic chromosome tracing, HeLa Kyoto WT, SMC4-depleted and TSA-treated (hg38): "
                "28,379 traces in 3,930 nuclei from interphase to metaphase, eight libraries (1-Mb regions at 12 kb "
                "to whole chromosomes at 1 Mb); coords = spots passing the authors' QC, layers['fit'] every fit"))
register(Loader(
    name="beckwith2025_looptrace",
    build=_build_beckwith2025("beckwith2025_looptrace", "looptrace_experimental_data.zip",
                              "looptrace_RPE1_HKWT_dRAD21_dCTCF_dWAPL_experimental_data_combined.csv.gz"),
    store="beckwith2025/beckwith2025_looptrace.chromdata.zarr", sources=("beckwith2025_looptrace",),
    description="Beckwith 2025 LoopTrace, RPE-1 and HeLa Kyoto WT / RAD21-, CTCF-, WAPL-depleted (hg38): 118,479 "
                "traces of ten regions (4-10 kb spots), no nuclei, coordinates in each trace's crop"))
register(Loader(
    name="beckwith2025_looptrace_fish",
    build=_build_beckwith2025("beckwith2025_looptrace", "looptrace_experimental_data.zip",
                              "looptrace_RPE1_denaturing_nondenaturing_FISH_comparison.csv.gz"),
    store="beckwith2025/beckwith2025_looptrace_fish.chromdata.zarr", sources=("beckwith2025_looptrace",),
    description="Beckwith 2025 LoopTrace, RPE-1 traced with non-denaturing vs denaturing FISH (hg38): 36,277 traces "
                "of six regions in 4,666 nuclei"))


# -- Cheng et al. 2026 (Science 393:eadw4243): MINA / DNA-MERFISH of human tonsil, B-cell lines, 10-kb Ig tracing --

_CHENG2026 = ("Cheng et al. 2026, Science 393:eadw4243 (doi:10.1126/science.adw4243), Zenodo 19959235 (CC BY 4.0)")
#: the 10-kb libraries (Data S3; bins numbered from 1 in genomic order): name -> (chrom, first start, bins)
CHENG2026_FINE = {"IGH": ("chr14", 105_496_000, 48), "IGL": ("chr22", 22_657_531, 25)}
#: the 3'RR library: bins 7-10 (3'RR2) and 19-22 (3'RR1) of the IGH library
CHENG2026_3RR_BINS = (7, 8, 9, 10, 19, 20, 21, 22)
CHENG2026_TIMES = ("0hr", "2hr", "6hr", "12hr")


def _cheng2026_raw(root: Path) -> Path:
    """The two archives fetched and unpacked once (``raw/Imaging_analyzed_data/``, ``raw/supp/``)."""
    from . import fetch

    fetch("cheng2026_mina", root=root)
    raw = root / "cheng2026_mina" / "raw"
    for archive, dest in (("Imaging_analyzed_data.zip", raw), ("science.adw4243_data_s1_to_s7.zip", raw / "supp")):
        done = raw / f".{archive}.unpacked"
        if not done.exists():                    # the imaging zip is Deflate64 (Windows), which zipfile cannot read
            import subprocess

            dest.mkdir(parents=True, exist_ok=True)
            subprocess.run(["unzip", "-q", "-o", str(raw / archive), "-d", str(dest)], check=True)
            done.touch()
    return raw


def cheng2026_targets() -> pd.DataFrame:
    """The 1,151 genome-wide targets with their hg38 coordinates as derived from the authors' probe sequences
    (``apps/atlas/recipes/cheng2026_mina/map_probes.py``): ``chrom_id`` (1-22, X = 23) and ``locus`` (1-based,
    genomic order within the chromosome) index the traces of the ``.mat`` files."""
    t = pd.read_csv(Path(__file__).with_name("cheng2026_targets_hg38.tsv"), sep="\t")
    return t.sort_values(["chrom_id", "locus"]).reset_index(drop=True)


def _cheng2026_fine_loci(library: str) -> pd.DataFrame:
    if library == "3RR":
        chrom, first, _ = CHENG2026_FINE["IGH"]
        starts = [first + (b - 1) * 10_000 for b in CHENG2026_3RR_BINS]
        names = [f"IGH bin {b}" for b in CHENG2026_3RR_BINS]
    else:
        chrom, first, n = CHENG2026_FINE[library]
        starts = [first + i * 10_000 for i in range(n)]
        names = [f"{library} bin {i + 1}" for i in range(n)]
    return pd.DataFrame({"chrom": chrom, "start": starts, "end": [s + 10_000 for s in starts], "name": names})


def _cheng2026_cell_lists(raw: Path, rep: int, prefix: str):
    """Cells of a tonsil section: the authors' RNA cell list (all segmented cells) joined with the zone-filtered
    list (zone scores, the cell type kept after removing mislocated cells); RNA counts of the 447 genes (Data S2
    order = the codebook order)."""
    import h5py
    from uchrom.io.mina_mat import mat_struct

    folder = raw / "Imaging_analyzed_data" / "Tonsil_DNAMER" / f"Rep{rep}" / "CellList_WithRNA"
    s2 = pd.read_excel(raw / "supp" / "science.adw4243_data_s2.xlsx", sheet_name=0)
    genes = list(dict.fromkeys(s2["Name"].str.extract(r"^\d+_T\d+_([^_]+)_.*_Code[01]+$")[0].dropna()))
    rows, rna = [], []
    with h5py.File(folder / "CellListRNA_250602.mat", "r") as f:
        for e in mat_struct(f, f["CellListRNA"]):
            fov, cid = int(np.ravel(e["FOV"])[0]), int(np.ravel(e["CellID"])[0])
            c = np.ravel(e["Center"])
            rows.append({"cell_id": f"{prefix}{fov}_{cid}", "center_px_1": c[0], "center_px_2": c[1],
                         "on_edge": bool(np.ravel(e["OnEdge"])[0]),
                         "n_rna": float(np.ravel(e["TotalRNACopyNumber"])[0]),
                         "cell_type_rna": e["seurat_midgroup"] if isinstance(e["seurat_midgroup"], str) else None})
            rna.append(np.ravel(e["RNACopyNumber"])[:len(genes)])
    cells = pd.DataFrame(rows).set_index("cell_id")
    counts = pd.DataFrame(np.asarray(rna, np.float32), index=cells.index, columns=[f"rna.{g}" for g in genes])
    zone = []
    with h5py.File(folder / "CellListRNA_RemovedMislocated.mat", "r") as f:
        for e in mat_struct(f, f["CellListRNA"]):
            fov, cid = int(np.ravel(e["FOV"])[0]), int(np.ravel(e["CellID"])[0])
            zone.append({"cell_id": f"{prefix}{fov}_{cid}", "cell_type": e["seurat_midgroup"],
                         "dz_zone_score": float(np.ravel(e["DZ_ZoneScore"])[0]),
                         "lz_zone_score": float(np.ravel(e["LZ_ZoneScore"])[0]),
                         "mz_zone_score": float(np.ravel(e["MZ_ZoneScore"])[0])})
    zone = pd.DataFrame(zone).set_index("cell_id")
    return cells.join(zone), counts


def build_cheng2026_tonsil(root: Path, out: Path):  # noqa: D401
    """Cheng 2026 genome-wide DNA-MERFISH (MINA) of five human tonsil sections (three donors; Data S5): every cell
    with a trace, 1,151 loci of 100 kb on chromosomes 1-22 and X (hg38 coordinates derived from the probe
    sequences), one trace per chromosome copy, µm in the field of view; the cells' RNA MERFISH counts of 447 genes
    (``rna.<gene>``), the authors' cell type after their zone filter (``cell_type``; missing for the cells they
    removed as mislocated or that have no RNA cell) and the dark / light / mantle zone scores."""
    from uchrom.io import read_mina_mat

    raw = _cheng2026_raw(root)
    loci = cheng2026_targets()
    donors = {1: ("tonsil 1", "5 years", "male"), 2: ("tonsil 2", "2 years", "male"), 3: ("tonsil 2", "2 years", "male"),
              4: ("tonsil 3", "2 years", "male"), 5: ("tonsil 3", "2 years", "male")}     # Data S5
    parts = []
    for rep in range(1, 6):
        folder = raw / "Imaging_analyzed_data" / "Tonsil_DNAMER" / f"Rep{rep}" / "ChrList"
        files = sorted(folder.glob("ChrFOV_withAnnotation_*.mat"), key=lambda p: int(p.stem.rsplit("_", 1)[1]))
        cd = read_mina_mat(files, loci, cell_prefix=f"rep{rep}_", cell_fields=("TraceNum",))
        info, counts = _cheng2026_cell_lists(raw, rep, f"rep{rep}_")
        cells = cd.cells.join(info, how="left").join(counts, how="left")
        tonsil, age, sex = donors[rep]
        cells.insert(0, "replicate", f"Rep-{rep}")
        cells.insert(1, "tonsil", tonsil)
        cells.insert(2, "donor_age", age)
        cells.insert(3, "donor_sex", sex)
        cells["region"] = [f"rep{rep}_fov{f}" for f in cells["fov"]]
        cd.cells = cells
        parts.append(cd)
    cd = _concat(parts)
    cd.uns.update({"genome_assembly": "hg38", "xyz_unit": "micron",
                   "loci": "hg38 coordinates of the 1,151 targets derived from the authors' probe sequences (Data S1) "
                           "by exact matching; see apps/atlas/recipes/cheng2026_mina/map_probes.py",
                   "source": f"{_CHENG2026}: Tonsil_DNAMER Rep1-5 (ChrList, CellList_WithRNA)"})
    return cheng2026_tonsil_finish(cd)


#: µm per pixel of the tonsil images (the authors' code: ``UmPerPxl = 0.108``); the cell centres of the cell lists
#: are in pixels of the field of view, the traces in µm of the same frame
CHENG2026_UM_PER_PX = 0.108


def cheng2026_tonsil_finish(cd):
    """Cell centres (µm, the field of view's frame: the traces' frame) and the flag of the cells the paper's
    genome-wide analyses use (``in_paper_analysis``: a cell type other than ``unknown`` and 3 < ``TraceNum`` < 30, the
    authors' filter in ``runMerge_8_RadialScore.m``; 121,373 cells, the paper's N)."""
    c = cd.cells
    c["in_paper_analysis"] = (c["cell_type"].notna() & (c["cell_type"].astype(str) != "unknown")
                              & (c["TraceNum"] > 3) & (c["TraceNum"] < 30))
    pos = c[["center_px_1", "center_px_2"]] * CHENG2026_UM_PER_PX
    has = pos.notna().all(axis=1)
    cd.set_cell_positions(pos[has].to_numpy(), cell_ids=list(pos.index[has]), unit="um", frame="fov",
                          region_col="region", in_coords_frame=True, status="measured",
                          source="the authors' cell centres (CellListRNA_250602.mat, pixels x 0.108 µm)")
    return cd


def _concat(parts):
    """Concatenate ChromData objects with the same bins (cells / traces / spots stacked)."""
    from chromdata import ChromData

    bins = parts[0].bins
    for p in parts[1:]:
        if not p.bins.equals(bins):
            raise ValueError("cheng2026: parts with different bins")
    spots = pd.concat([p.spots[["trace_id", "cell_id", "bin_id"]].astype({"trace_id": str, "cell_id": str})
                       for p in parts], ignore_index=True)
    return ChromData(coords=np.concatenate([p.coords for p in parts]), spots=spots, bins=bins,
                     cells=pd.concat([p.cells for p in parts]), traces=pd.concat([p.traces for p in parts]),
                     uns=dict(parts[0].uns))


def build_cheng2026_bcell_lines(root: Path, out: Path):
    """Cheng 2026 genome-wide DNA-MERFISH of Ramos (Burkitt lymphoma) and TMD8 (diffuse large B-cell lymphoma)
    cells, two replicates each: 1,151 loci (hg38, derived from the probe sequences), one trace per chromosome copy."""
    from uchrom.io import read_mina_mat

    raw = _cheng2026_raw(root)
    loci = cheng2026_targets()
    parts = []
    for line in ("Ramos", "TMD8"):
        for rep in (1, 2):
            path = raw / "Imaging_analyzed_data" / "BCellLine_DNAMER" / line / f"ChrFOV_{line}_Rep{rep}.mat"
            cd = read_mina_mat(path, loci, cell_prefix=f"{line}_rep{rep}_", cell_fields=("TraceNum",))
            cd.cells.insert(0, "cell_line", line)
            cd.cells.insert(1, "replicate", f"Rep-{rep}")
            parts.append(cd)
    cd = _concat(parts)
    cd.uns.update({"genome_assembly": "hg38", "xyz_unit": "micron",
                   "source": f"{_CHENG2026}: BCellLine_DNAMER (Ramos, TMD8; Rep1, Rep2)"})
    return cd


def _build_cheng2026_fine(libraries):
    def build(root: Path, out: Path):
        from uchrom.io import read_mina_mat

        raw = _cheng2026_raw(root)
        parts = []
        for t in CHENG2026_TIMES:
            paths, loci = [], []
            for lib in libraries:
                folder = (raw / "Imaging_analyzed_data" / "Ramos_3PRR_10kb" if lib == "3RR"
                          else raw / "Imaging_analyzed_data" / "Ramos_IgG_10kb" / lib)
                paths.append(folder / f"ChrAll_{t}.mat")
                loci.append(_cheng2026_fine_loci(lib))
            cd = read_mina_mat(paths, loci, cell_prefix=f"{t}_", replicates_by_fov_order=True)
            cd.cells.insert(0, "dtag_time", t.replace("hr", " h"))
            cd.cells["replicate"] = "Rep-" + cd.cells["replicate"].astype(str)
            parts.append(cd)
        cd = _concat(parts)
        names = pd.concat([_cheng2026_fine_loci(lib) for lib in libraries]).drop_duplicates(["chrom", "start"])
        cd.bins["name"] = cd.bins.merge(names, on=["chrom", "start", "end"], how="left")["name"].to_numpy()
        cd.traces["library"] = np.where(cd.traces["chrom"].astype(str) == "chr22", "IGL", "IGH") \
            if "IGL" in libraries else "3'RR"
        cd.uns.update({"genome_assembly": "hg38", "xyz_unit": "micron",
                       "source": f"{_CHENG2026}: {', '.join(libraries)} 10-kb tracing of RAD21-degron RASH-1C Ramos "
                                 "cells, 0 / 2 / 6 / 12 h of dTAGV-1 (barcoded cells imaged together; two replicates "
                                 "merged by the authors, told apart by the field numbering); bins from Data S3"})
        return cd
    return build


build_cheng2026_ramos_igh_igl = _build_cheng2026_fine(("IGH", "IGL"))
build_cheng2026_ramos_3rr = _build_cheng2026_fine(("3RR",))

register(Loader(
    name="cheng2026_tonsil", build=build_cheng2026_tonsil, store="cheng2026_mina/cheng2026_tonsil.chromdata.zarr",
    sources=("cheng2026_mina",),
    description="Cheng 2026 MINA of five human tonsil sections: genome-wide DNA-MERFISH (1,151 loci, hg38 derived from "
                "the probes), RNA MERFISH of 447 genes and the authors' cell types and zone scores per cell"))
register(Loader(
    name="cheng2026_bcell_lines", build=build_cheng2026_bcell_lines,
    store="cheng2026_mina/cheng2026_bcell_lines.chromdata.zarr", sources=("cheng2026_mina",),
    description="Cheng 2026 genome-wide DNA-MERFISH of Ramos and TMD8 lymphoma cells (1,151 loci, hg38)"))
register(Loader(
    name="cheng2026_ramos_igh_igl", build=build_cheng2026_ramos_igh_igl,
    store="cheng2026_mina/cheng2026_ramos_igh_igl.chromdata.zarr", sources=("cheng2026_mina",),
    description="Cheng 2026 10-kb tracing of IGH (48 bins) and IGL (25 bins) in RAD21-degron Ramos cells, 0-12 h of "
                "RAD21 degradation"))
register(Loader(
    name="cheng2026_ramos_3rr", build=build_cheng2026_ramos_3rr,
    store="cheng2026_mina/cheng2026_ramos_3rr.chromdata.zarr", sources=("cheng2026_mina",),
    description="Cheng 2026 10-kb tracing of the IGH 3'RR super-enhancers (8 bins) in RAD21-degron Ramos cells, 0-12 h "
                "of RAD21 degradation"))
