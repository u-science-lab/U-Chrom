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
