"""Chromatin-tracing datasets as ``ChromData`` (spots with 3-D coordinates, traces, cells)."""

from __future__ import annotations

from pathlib import Path

from ._loaders import Loader, register


def build_takei2021_mesc(root: Path, out: Path):
    """Takei et al. 2021 DNA seqFISH+ of mouse ES cells as 4DN FOF-CT (4DNFIHF3JCBY): 201 cells, 1,200 loci
    at 25 kb (8,285 traces), with the cell table (nuclear area, RNA counts per gene as ``rna.<gene>``) and the
    nascent-RNA spots (``points["rna"]``)."""
    from chromdata import ChromData

    from . import fetch

    core = fetch("takei", root=root)
    tables = fetch("takei_tables", root=root)
    return ChromData.from_fofct(core, cell_table=tables / "4DNFIFINA2U9.csv", rna_table=tables / "4DNFIJ52NVDV.csv")


def _bintu(root: Path, start_bp: int, assembly: str):
    from uchrom.io import read_bintu_tracing

    from . import fetch

    cd = read_bintu_tracing(str(fetch("bintu_imr90", root=root)), chrom="chr21", start_bp=start_bp,
                            resolution_bp=30_000, genome_assembly=assembly)
    cd.uns["source"] = ("Bintu et al. 2018, Science 362:eaau1783: IMR90 chr21, 65 segments of 30 kb, "
                        "1,277 imaged chromosomes (one trace per cell); coordinates in nm")
    return cd


def build_bintu_imr90(root: Path, out: Path):
    """Bintu et al. 2018 chromatin tracing of IMR90 chr21:18,627,714-20,577,714 (hg38)."""
    return _bintu(root, 18_627_714, "hg38")


def build_bintu_imr90_hg19(root: Path, out: Path):
    """The same traces on hg19 (chr21:20,000,032-21,950,032), to pair with Rao et al. 2014 Hi-C."""
    return _bintu(root, 20_000_032, "hg19")


def build_su2020_chr21(root: Path, out: Path):
    """Su et al. 2020 sequential chromatin tracing of chromosome 21 in IMR90 cells (hg38): 651 loci of 50 kb
    over 10.4-46.7 Mb, one trace per imaged chromosome copy (7,591; ``trace_id`` = the authors' copy number),
    coordinates in µm (undetected loci left out).  ``bin_tracks["n_genes"]``: the genes the authors list for
    each locus (those whose nascent transcription they imaged).  The authors' Rao et al. 2014 IMR90 Hi-C
    summed into the same loci is linked as a ``.cool`` under the key ``rao2014`` (raw counts + ICE weights;
    cooler bins tile chr21, so each bin runs from one locus to the next, after an empty leading bin)."""
    from uchrom.io import read_su2020_hic, read_su2020_tracing, write_locus_cool

    from . import fetch

    folder = fetch("su2020_chr21", root=root)
    cd = read_su2020_tracing(folder / "chromosome21.tsv", extras=["n_genes"])
    cd.uns["source"] = ("Su et al. 2020, Cell 182:1641: IMR90 chr21, 651 loci of 50 kb, 7,591 imaged "
                        "chromosome copies (one trace each); chromosome21.tsv, Zenodo 3928890")
    loci, counts = read_su2020_hic(folder / "Hi-C_contacts_chromosome21.tsv")
    imaged = cd.bins[["chrom", "start", "end"]].astype({"chrom": str}).reset_index(drop=True)
    if not loci.astype({"chrom": str}).equals(imaged):
        raise ValueError("Su 2020: the Hi-C loci are not the imaged loci")
    cool = write_locus_cool(loci, counts, out.parent / "su2020_chr21_rao2014.cool", assembly="hg38")
    cd.link_cool(Path(cool).name, key="rao2014", label="Rao 2014 IMR90 Hi-C summed into the Su 2020 loci",
                 genome_assembly="hg38")
    return cd


register(Loader(
    name="takei2021_mesc", build=build_takei2021_mesc, store="takei2021_mesc/takei2021_mesc.chromdata.zarr",
    sources=("takei", "takei_tables"),
    description="Takei 2021 mESC DNA seqFISH+ (4DN FOF-CT): 201 cells, 1,200 loci at 25 kb, cell table, nascent RNA"))
register(Loader(
    name="bintu_imr90", build=build_bintu_imr90, store="bintu_imr90/bintu_imr90.chromdata.zarr",
    sources=("bintu_imr90",),
    description="Bintu 2018 IMR90 chr21:18.6-20.6 Mb (hg38) tracing: 1,277 chromosomes x 65 segments of 30 kb"))
register(Loader(
    name="bintu_imr90_hg19", build=build_bintu_imr90_hg19, store="bintu_imr90/bintu_imr90_hg19.chromdata.zarr",
    sources=("bintu_imr90",),
    description="Bintu 2018 IMR90 chr21 tracing on hg19 (20.0-21.95 Mb), to pair with Rao 2014 Hi-C"))
register(Loader(
    name="su2020_chr21", build=build_su2020_chr21, store="su2020_chr21/su2020_chr21.chromdata.zarr",
    sources=("su2020_chr21",),
    description="Su 2020 IMR90 chr21 tracing: 7,591 chromosome copies x 651 loci of 50 kb (hg38), genes per "
                "locus; Rao 2014 Hi-C in the same loci (linked .cool, key rao2014)"))
