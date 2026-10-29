"""Chromatin-tracing datasets as ``ChromData`` (spots with 3-D coordinates, traces, cells)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

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


def _fetched(name: str, file: str, root) -> Path:
    """A file of a fetched dataset (``fetch`` returns the file itself for a one-file entry, else its folder)."""
    from . import fetch

    p = Path(fetch(name, root=root))
    return p if p.is_file() else p / file


def build_su2020_chr2(root: Path, out: Path):
    """Su et al. 2020 sequential chromatin tracing of the whole chromosome 2 in IMR90 cells (hg38), loci of 50 kb,
    one trace per imaged chromosome copy; the authors' Rao et al. 2014 Hi-C summed into the same loci is linked as
    a ``.cool`` under the key ``rao2014`` (as :func:`build_su2020_chr21`)."""
    from uchrom.io import read_su2020_hic, read_su2020_tracing, write_locus_cool

    from . import fetch

    folder = fetch("su2020_chr2", root=root)
    cd = read_su2020_tracing(folder / "chromosome2.tsv")
    cd.uns["source"] = "Su et al. 2020, Cell 182:1641: IMR90 chromosome 2; chromosome2.tsv, Zenodo 3928890"
    loci, counts = read_su2020_hic(folder / "Hi-C_contacts_chromosome2.tsv")
    imaged = cd.bins[["chrom", "start", "end"]].astype({"chrom": str}).reset_index(drop=True)
    if not loci.astype({"chrom": str}).equals(imaged):
        raise ValueError("Su 2020: the Hi-C loci are not the imaged loci")
    cool = write_locus_cool(loci, counts, out.parent / "su2020_chr2_rao2014.cool", assembly="hg38")
    cd.link_cool(Path(cool).name, key="rao2014", label="Rao 2014 IMR90 Hi-C summed into the Su 2020 loci",
                 genome_assembly="hg38")
    return cd


def build_su2020_chr21_cell_cycle(root: Path, out: Path):
    """Su et al. 2020 chr21 tracing in IMR90 cells with the cell-cycle state of each imaged copy
    (``traces["cell_cycle"]``)."""
    from uchrom.io import read_su2020_tracing

    cd = read_su2020_tracing(_fetched("su2020_chr21_cell_cycle", "chromosome21-cell_cycle.tsv", root))
    cd.uns["source"] = ("Su et al. 2020, Cell 182:1641: IMR90 chr21 with the cell-cycle state of each copy; "
                        "chromosome21-cell_cycle.tsv, Zenodo 3928890")
    return cd


def _su2020_genome(name: str, file: str, what: str):
    def build(root: Path, out: Path):
        from uchrom.io import read_su2020_tracing

        cd = read_su2020_tracing(_fetched(name, file, root))
        cd.uns["source"] = f"Su et al. 2020, Cell 182:1641: IMR90 genome-scale DNA-MERFISH{what}; {file}, Zenodo 3928890"
        return cd
    build.__doc__ = (f"Su et al. 2020 genome-scale DNA-MERFISH of 1,041 loci in IMR90 cells{what} (hg38): one trace "
                     "per cell, chromosome and homolog, as :func:`uchrom.io.read_su2020_tracing` reads them.")
    return build


build_su2020_genome = _su2020_genome("su2020_genome", "genomic-scale.tsv", "")
build_su2020_genome_amanitin = _su2020_genome("su2020_genome_amanitin", "genomic-scale-amanitin.tsv",
                                              " after alpha-amanitin")
build_su2020_genome_transcription = _su2020_genome(
    "su2020_genome_transcription", "genomic-scale-with_transcription_and_nuclear_bodies.tsv",
    " with nascent transcription and distances to lamina, nucleoli and speckles")


#: loci of a 4DN deposit placed off the authors' coordinates: dataset -> (chrom, start from, start to, offset).  Bintu
#: et al. 2018's 18.6-20.6 Mb and 34.6-37.1 Mb regions are deposited from 18,000,001 and 34,000,001 in 30-kb steps;
#: the authors' hg38 coordinates (github.com/BogdanBintu/ChromatinImaging, Data/README.md: first to last probe) are
#: chr21:18,627,714-20,577,518 and chr21:34,628,096-37,117,534.  (28-30 Mb is deposited from 28,000,001, the
#: authors' 28,000,071: left as it is.)
_LOCUS_SHIFTS = {"bintu2018_4dn": [("chr21", 18_000_001, 19_950_000, 627_713),
                                   ("chr21", 34_000_001, 36_490_000, 628_095)]}


#: the cell-type numbers of a deposit's cell table and their names (from the table's own header): Takei et al. 2021,
#: "cluster label: Transcriptionally defined cell type cluster numbers (1: Pvalb, 2: Vip, 3: Ndnf, 4: Sst, 5: Astro,
#: 6: Micro, 7, Endo, 8: OPC/Oligo, 9: Exc)"
_CELL_LABELS = {"takei2021_brain_4dn": ("cluster label", {1: "Pvalb", 2: "Vip", 3: "Ndnf", 4: "Sst", 5: "Astro",
                                                          6: "Micro", 7: "Endo", 8: "OPC/Oligo", 9: "Exc"})}


#: deposits whose 3-D coordinates are local to each trace's image crop but which keep where the trace was in its field
#: of view, in pixels: (table, x column, y column, trace columns copied to the cells) — Hafner et al. 2023: LocusX /
#: LocusY per trace; Hung et al. 2024: Raw_X / Raw_Y per spot (spot quality), limb and section per trace
_FOV_POSITIONS = {"hafner2023_orca": ("traces", "LocusX", "LocusY", ()),
                  "hung2024_orca": ("spots", "Raw_X", "Raw_Y", ("Limb", "Section_ID"))}


def _fov_positions(cd, table: str, xcol: str, ycol: str, copy=()):
    """Cell positions in their field of view (pixels; ``cd.set_cell_positions`` key ``fov``, region
    ``<experiment>/FOV <n>``): the mean position of the cell's traces (``table="traces"``) or spots (``"spots"``)."""
    import numpy as np

    cell_of = cd.spots[["trace_id", "cell_id"]].astype(str).drop_duplicates("trace_id").set_index("trace_id")["cell_id"]
    if table == "traces":
        t = cd.traces[[xcol, ycol, "FOV"]].copy()
        t.index = t.index.astype(str)
        t["cell_id"] = cell_of.reindex(t.index).to_numpy()
        per = t.groupby("cell_id")[[xcol, ycol]].mean()
    else:
        v = pd.DataFrame({"x": cd.spot_tracks[xcol].to_numpy(float), "y": cd.spot_tracks[ycol].to_numpy(float),
                          "cell_id": cd.spots["cell_id"].astype(str).to_numpy()})
        per = v.groupby("cell_id")[["x", "y"]].mean().rename(columns={"x": xcol, "y": ycol})
    tr = cd.traces.copy()
    tr.index = tr.index.astype(str)
    tr["cell_id"] = cell_of.reindex(tr.index).to_numpy()
    first = tr.drop_duplicates("cell_id").set_index("cell_id")
    cells = cd.cells.copy()
    ids = cells.index.astype(str)
    cells["fov_x"] = per[xcol].reindex(ids).to_numpy()
    cells["fov_y"] = per[ycol].reindex(ids).to_numpy()
    fov = pd.to_numeric(first["FOV"].reindex(ids), errors="coerce").to_numpy()
    cells["fov_region"] = pd.Categorical([f"{e}/FOV {int(f)}" if np.isfinite(f) else None
                                          for e, f in zip(cells["experiment"].astype(str), fov)])
    for col in copy:
        cells[col.lower()] = pd.Categorical(first[col].reindex(ids).astype(object).where(lambda x: x.notna(), None))
    cd.cells = cells
    cd.set_cell_positions(key="fov", columns=["fov_x", "fov_y"], unit="px", frame="fov", region_col="fov_region",
                          in_coords_frame=False, status="measured",
                          source=f"the deposit's {xcol} / {ycol} ({table}): where each trace lies in its field of view, "
                                 "in camera pixels; the 3-D coordinates are local to each trace's image crop")


#: trace fields that describe the cell (deposits without Cell_ID: one trace per cell), copied to ``cells``: dataset ->
#: (trace column, cells column) — Cheng et al. 2025: the gene a cell's sgRNA targets (or NTC) per trace
_TRACE_FIELDS = {"cheng2025_perturb": [("Perturbation", "perturbation")]}


def _trace_fields_to_cells(cd, fields):
    tr = cd.traces.copy()
    tr.index = tr.index.astype(str)
    cell_of = cd.spots[["trace_id", "cell_id"]].astype(str).drop_duplicates("trace_id").set_index("trace_id")["cell_id"]
    tr["cell_id"] = cell_of.reindex(tr.index).to_numpy()
    first = tr.drop_duplicates("cell_id").set_index("cell_id")
    cells = cd.cells.copy()
    for col, name in fields:
        v = first[col].reindex(cells.index.astype(str))
        cells[name] = pd.Categorical(v.astype(object).where(v.notna(), None).to_numpy())
    cd.cells = cells


def _fourdn(dataset: str, source: str):
    """A loader of a 4DN FOF-CT chromatin-tracing study (fourdn_tracing.tsv): every experiment with a core table,
    its companions joined (:func:`uchrom.io.read_4dn_tracing`); ``cells`` carry the experiment set (``set``), its
    4DN description (``condition``) and ``biosample``.  Experiments of RNA counts only (Hafner et al. 2023's RNA
    FISH sets) have no traces and are left out."""
    def build(root: Path, out: Path):
        from uchrom.io import read_4dn_tracing

        from . import fetch
        from ._sources import fourdn_tracing_files

        fetch(dataset, root=root)
        by_exp = {}
        for r in fourdn_tracing_files(dataset):
            by_exp.setdefault((r["set"], r["experiment"]), {}).setdefault(r["kind"], []).append(r)
        experiments = []
        for (set_, exp), files in sorted(by_exp.items()):
            if "core" not in files:
                continue
            cores = sorted(files["core"], key=lambda r: r["file"])
            one = lambda k: [_data_path(root, r["path"]) for r in sorted(files.get(k, []), key=lambda r: r["file"])]  # noqa: E731
            entry = {"name": exp or set_, "core": one("core") if len(cores) > 1 else one("core")[0],
                     "meta": {"set": set_, "condition": cores[0]["description"], "biosample": cores[0]["biosample"]},
                     "locus_shifts": _LOCUS_SHIFTS.get(dataset, ())}
            for k in ("spot_quality", "spot_bio"):
                if k in files:
                    entry[k] = one(k)
            for k in ("trace_data", "cell_data"):
                if k in files:
                    entry[k] = one(k)[0]
            experiments.append(entry)
        cd = read_4dn_tracing(experiments)
        if dataset in _CELL_LABELS:                     # the authors' numbered cell types, named
            col, names = _CELL_LABELS[dataset]
            cells = cd.cells.copy()
            cells["cell_type"] = pd.Categorical(pd.to_numeric(cells[col], errors="coerce").map(names))
            cd.cells = cells
        if dataset in _FOV_POSITIONS:
            _fov_positions(cd, *_FOV_POSITIONS[dataset])
        if dataset in _TRACE_FIELDS:
            _trace_fields_to_cells(cd, _TRACE_FIELDS[dataset])
        cd.uns["source"] = source
        return cd
    build.__doc__ = f"{source}: every experiment of the 4DN deposit in one object (``cells``: set, condition, biosample)."
    return build


def _data_path(root, rel: str) -> Path:
    from ._paths import data_dir

    return Path(root if root is not None else data_dir()) / rel


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
register(Loader(
    name="su2020_chr2", build=build_su2020_chr2, store="su2020_chr2/su2020_chr2.chromdata.zarr",
    sources=("su2020_chr2",),
    description="Su 2020 IMR90 chromosome 2 tracing, loci of 50 kb (hg38); Rao 2014 Hi-C in the same loci (linked "
                ".cool, key rao2014)"))
register(Loader(
    name="su2020_chr21_cell_cycle", build=build_su2020_chr21_cell_cycle,
    store="su2020_chr21_cell_cycle/su2020_chr21_cell_cycle.chromdata.zarr", sources=("su2020_chr21_cell_cycle",),
    description="Su 2020 IMR90 chr21 tracing with the cell-cycle state of each copy"))
for _name, _source, _what in (
        ("bintu2018_4dn", "Bintu et al. 2018, Science 362:eaau1783 (4DN FOF-CT)",
         "Bintu 2018 chromatin tracing, 10 sets: chr21 28-30 Mb in IMR90 / K562 / A549 / HCT116 RAD21-AID +- auxin "
         "(and the IMR90 cell cycle), 34.6-37.1 Mb in HCT116, 18.6-20.6 Mb in IMR90 (hg38)"),
        ("mateo2019_orca", "Mateo et al. 2019, Nature 568:49 (4DN FOF-CT)",
         "Mateo 2019 ORCA of the Drosophila bithorax complex, 7 sets (dm6), RNAs of the same cells"),
        ("hafner2023_orca", "Hafner et al. 2023, Mol Cell 83:1377 (4DN FOF-CT)",
         "Hafner 2023 ORCA of mESC chr3 / chr6 at 150 Mb and 3 Mb, CTCF-AID / RAD21-AID +- auxin (mm10)"),
        ("murphy2024_orca", "Murphy & Boettiger 2024, Nat Genet 56:493 (4DN FOF-CT)",
         "Murphy 2024 ORCA of HoxA: mESC with Polycomb degrons, neural progenitors, E10.5 brain (mm10)"),
        ("takei2021_brain_4dn", "Takei et al. 2021, Science 374:586 (4DN FOF-CT)",
         "Takei 2021 mouse cortex DNA seqFISH+: 1 Mb and 25 kb loci (traces c1- / c2-), cell types, RNA per cell (mm10)"),
        ("liu2020_mina", "Liu et al. 2020, Nat Commun 11:2907 (4DN FOF-CT)",
         "Liu 2020 MINA of fetal mouse liver: chr19 tracing with RNA MERFISH and nucleoli of the same cells (mm10)"),
        ("hung2024_orca", "Hung et al. 2024, Nat Genet 56:306 (4DN FOF-CT)",
         "Hung 2024 ORCA of the Pitx1 locus in mouse limb buds (mm10)"),
        ("huang2021_4dn", "Huang et al. 2021, Nat Genet 53:1064 (4DN FOF-CT)",
         "Huang 2021 Sox2 locus tracing in mESC, with RNA FISH of the same cells (mm10)"),
        ("liu2025_kras", "Liu et al. 2025, Nat Genet 57:3075 (4DN FOF-CT)",
         "Liu 2025 genome-wide and 5-kb chromatin tracing in Kras-driven mouse lung and pancreatic cancers (mm10)"),
        ("cheng2025_perturb", "Cheng et al. 2025, Nat Methods 22:950 (4DN FOF-CT)",
         "Cheng 2025 Perturb-tracing: chr22 / chr21 tracing of pooled CRISPR screens, each cell's perturbation (hg38)"),
        ("chen2023_sox9", "Chen et al. 2023, Mol Cell 83:1446 (4DN FOF-CT)",
         "Chen 2023 ORCA of the SOX9 4-Mb region in hESC and cranial neural crest, CTCF-site deletions (hg38)"),
        ("patterson2023_chrx", "Patterson et al. 2023, Sci Adv 9:eadf2245 (4DN FOF-CT)",
         "Patterson 2023 chrX tracing in naive and primed human pluripotent stem cells (hg38)"),
        ("sawh2020_celegans", "Sawh et al. 2020, Mol Cell 78:96 (4DN FOF-CT)",
         "Sawh 2020 tracing of chrI / chrV TADs in C. elegans embryos (ce10)"),
        ("gutnik2024_celegans", "Gutnik et al. 2024, Genome Biol 25:71 (4DN FOF-CT)",
         "Gutnik 2024 maternal vs paternal chromosome tracing in C. elegans embryos (ce10)"),
        ("messina2023_him", "Messina et al. 2023, Nat Commun 14:6678 (4DN FOF-CT)",
         "Messina 2023 Hi-M of Drosophila embryos, nuclear cycles 12 and 14 (dm6)")):
    register(Loader(name=_name, build=_fourdn(_name, _source), store=f"{_name}/{_name}.chromdata.zarr",
                    sources=(_name,), description=_what))
for _name, _build, _what in (
        ("su2020_genome", build_su2020_genome, ""),
        ("su2020_genome_amanitin", build_su2020_genome_amanitin, " after alpha-amanitin"),
        ("su2020_genome_transcription", build_su2020_genome_transcription,
         " with nascent transcription and distances to nuclear bodies")):
    register(Loader(name=_name, build=_build, store=f"{_name}/{_name}.chromdata.zarr", sources=(_name,),
                    description=f"Su 2020 IMR90 genome-scale DNA-MERFISH, 1,041 loci (hg38){_what}"))
