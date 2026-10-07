"""Single-cell Hi-C datasets as ``ChromData`` (cells + linked per-cell contact maps)."""

from __future__ import annotations

import tarfile
from pathlib import Path

import numpy as np
import pandas as pd

from ._loaders import Loader, register

#: hg19 chromosome sizes (UCSC), the genome-wide bin numbering of the Kim et al. 2020 matrices (chrY: no
#: contacts in these cells, not numbered)
HG19 = {"chr1": 249250621, "chr2": 243199373, "chr3": 198022430, "chr4": 191154276, "chr5": 180915260,
        "chr6": 171115067, "chr7": 159138663, "chr8": 146364022, "chr9": 141213431, "chr10": 135534747,
        "chr11": 135006516, "chr12": 133851895, "chr13": 115169878, "chr14": 107349540, "chr15": 102531392,
        "chr16": 90354753, "chr17": 81195210, "chr18": 78077248, "chr19": 59128983, "chr20": 63025520,
        "chr21": 48129895, "chr22": 51304566, "chrX": 155270560}


def _bins(chromsizes: dict, res: int) -> pd.DataFrame:
    parts = []
    for c, size in chromsizes.items():
        starts = np.arange(0, size, res, dtype=np.int64)
        parts.append(pd.DataFrame({"chrom": c, "start": starts, "end": np.minimum(starts + res, size)}))
    return pd.concat(parts, ignore_index=True)


def build_kim2020(root: Path, out: Path):
    """Kim et al. 2020 sci-Hi-C of H1 ES cells and HFF fibroblasts mixed (H1Esc-HFF.R1): 1,931 cells with
    their published cell type, the 500 kb contact maps of every cell as one ``.scool`` linked under the
    key ``per_cell`` (the cells' genome-wide bin numbering checked against hg19)."""
    import cooler
    from chromdata import ChromData

    from . import fetch

    res = 500_000
    folder = fetch("kim2020_scihic", root=root, extract=False)
    labels = pd.read_csv(folder / "H1Esc-HFF.R1.labeled", sep="\t", header=None, names=["matrix", "cell_type"])
    bins = _bins(HG19, res)
    n_bins = {c: -(-s // res) for c, s in HG19.items()}
    offset = dict(zip(n_bins, np.r_[0, np.cumsum(list(n_bins.values()))[:-1]]))
    lo_bin = pd.Series(offset)
    hi_bin = lo_bin + pd.Series(n_bins)

    wanted = set(labels["matrix"])
    maps, totals = {}, {}
    with tarfile.open(folder / "H1Esc-HFF.R1.tar.gz", "r:gz") as tf:      # read in place, nothing extracted
        for member in tf:
            name = Path(member.name).name
            if not member.isfile() or name not in wanted:
                continue
            m = pd.read_csv(tf.extractfile(member), sep="\t", header=None,
                            names=["bin1", "bin2", "count", "weight", "chrom1", "chrom2"])
            c1, c2 = m["chrom1"].str.removeprefix("human_"), m["chrom2"].str.removeprefix("human_")
            ok = ((m["bin1"] >= c1.map(lo_bin)) & (m["bin1"] < c1.map(hi_bin))
                  & (m["bin2"] >= c2.map(lo_bin)) & (m["bin2"] < c2.map(hi_bin)))
            if not ok.all():
                raise ValueError(f"{name}: bins outside their chromosome under the hg19 numbering")
            b1, b2 = np.minimum(m["bin1"], m["bin2"]), np.maximum(m["bin1"], m["bin2"])
            px = (pd.DataFrame({"bin1_id": b1.astype(np.int64), "bin2_id": b2.astype(np.int64),
                                "count": m["count"].astype(np.int64)})
                  .groupby(["bin1_id", "bin2_id"], as_index=False)["count"].sum())
            cell = name.removesuffix(f"_{res}.matrix")
            maps[cell] = px
            totals[cell] = int(px["count"].sum())
    labels["cell_id"] = labels["matrix"].str.removesuffix(f"_{res}.matrix")
    missing = set(labels["cell_id"]) - set(maps)
    if missing:
        raise ValueError(f"{len(missing)} labelled cells have no matrix in the tarball, e.g. {sorted(missing)[:3]}")

    out.parent.mkdir(parents=True, exist_ok=True)
    scool = out.parent / "kim2020_scihic_500kb.scool"
    cooler.create_scool(str(scool), bins, {c: maps[c] for c in labels["cell_id"]}, ordered=True)

    cells = labels.set_index(pd.Index(labels["cell_id"], name="cell_id"))[["cell_type"]].copy()
    cells["n_contacts"] = [totals[c] for c in cells.index]
    no_spots = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                             [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str),
                              ("cell_id", str)]})
    cd = ChromData(np.zeros((0, 3)), no_spots, cells=cells,
                   uns={"genome_assembly": "hg19",
                        "source": "Kim et al. 2020, PLoS Comput Biol 16:e1008173 (sci-Hi-C, H1Esc-HFF.R1, "
                                  "Noble lab); 500 kb contact maps per cell"})
    cd.link_scool(scool.name, key="per_cell", cell_name="cell_id", genome_assembly="hg19", bin_size=res)
    return cd


register(Loader(
    name="kim2020_scihic", build=build_kim2020, store="kim2020_scihic/kim2020_scihic.chromdata.zarr",
    sources=("kim2020_scihic",),
    description="Kim 2020 sci-Hi-C, H1 ES + HFF: 1,931 cells, cell types, 500 kb maps per cell (linked .scool)"))


# ----------------------------------------------------------------------------------------------------------
# GM12878 single cells with contact pairs: per-cell maps at 5 kb (pseudo-bulk maps fine enough for loops)
# ----------------------------------------------------------------------------------------------------------

#: bin size of the per-cell maps built from contact pairs: fine enough for loops in a pseudo-bulk (Rao et al.
#: 2014 call loops at 5-10 kb); coarser maps are summed from it (``pseudobulk(resolution=)``, ``rebin_map``)
PAIRS_RESOLUTION = 5000


def _no_spots():
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                         [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str),
                          ("cell_id", str)]})


def _check_sizes(declared: dict, sizes: dict, label: str) -> None:
    """The chromosome sizes a pairs file declares must be the genome's (names with or without ``chr``)."""
    strip = (lambda c: c[3:] if c.lower().startswith("chr") else c)  # noqa: E731
    got = {strip(c): n for c, n in declared.items()}
    bad = [c for c, n in sizes.items() if got.get(strip(c)) not in (None, n)]
    if bad:
        raise ValueError(f"{label}: chromosome sizes differ from the genome's for {bad[:5]}")


def _pairs_cells(sources: dict, out: Path, name: str, sizes: dict, assembly: str, cells: pd.DataFrame,
                 uns: dict):
    """Bin every cell's pairs into ``<name>_5kb.scool`` next to ``out`` and give the ChromData (cells + the
    per-cell maps linked as ``per_cell``)."""
    from chromdata import ChromData

    from ..io.pairs_maps import pairs_to_scool

    out.parent.mkdir(parents=True, exist_ok=True)
    scool = out.parent / f"{name}_{PAIRS_RESOLUTION // 1000}kb.scool"
    stats = pairs_to_scool(sources, scool, chromsizes=sizes, resolution=PAIRS_RESOLUTION, assembly=assembly,
                           metadata={"source": uns["source"]}, verbose=True)
    cells = cells.join(stats.rename(columns={"n_pixels": "n_pixels_5kb"}))
    cells["frac_cis"] = cells["n_cis"] / cells["n_contacts"]
    cd = ChromData(np.zeros((0, 3)), _no_spots(), cells=cells, uns={"genome_assembly": assembly, **uns})
    cd.link_scool(scool.name, key="per_cell", cell_name="cell_id", genome_assembly=assembly,
                  bin_size=PAIRS_RESOLUTION, label="Per cell (5 kb, homologs summed)")
    return cd


def build_tan2018_gm12878(root: Path, out: Path):
    """Tan et al. 2018 Dip-C of GM12878 (Science 361:924; GEO GSE117876): the 14 cells with hickit's
    re-processed contact pairs on GEO (cells 4, 8 and 16 have none), binned at 5 kb (hg19) into one ``.scool``
    linked as ``per_cell``.  Every contact counted once: the legs' haplotypes (``phase0`` / ``phase1``, the
    imputed ``phase_prob*``) are ignored, so a cell's map sums its two homologs."""
    import re

    from . import fetch
    from ..io.pairs_maps import pairs_chromsizes, tar_member

    folder = fetch("tan2018_gm12878", root=root)
    sources, rows = {}, []
    for tar in sorted(folder.glob("GSM*_gm12878_*.tar.gz")):
        cell = re.search(r"(gm12878_\d\d)", tar.name).group(1)
        sources[cell] = (tar_member(tar, f"{cell}.pairs.gz"), f"{cell}.pairs.gz")
        rows.append({"cell_id": cell, "gsm": tar.name.split("_", 1)[0], "cell_type": "GM12878",
                     "dataset": "Tan 2018 Dip-C"})
    if len(sources) != 14:
        raise ValueError(f"expected the hickit pairs of 14 cells in {folder}, found {len(sources)}")
    _check_sizes(pairs_chromsizes(next(iter(sources.values()))[0]), HG19, "tan2018_gm12878")
    cells = pd.DataFrame(rows).set_index("cell_id")
    uns = {"source": "Tan et al. 2018, Science 361:924 (Dip-C, GM12878; GEO GSE117876); hickit pairs of the 14 "
                     "cells re-processed on GEO, binned at 5 kb, both homologs counted",
           "haplotypes": "ignored: each contact counted once (the per-cell map sums both homologs)"}
    return _pairs_cells(sources, out, "tan2018_gm12878", HG19, "hg19", cells, uns)


#: cells with fewer cis contacts than this are flagged (``qc_pass``): Wu 2025 cells 026 / 051 (33 % / 12 %
#: cis) look like damaged nuclei or doublets
MIN_FRAC_CIS = 0.5


def build_wu2025_scmicroc(root: Path, out: Path):
    """Wu et al. 2025 scMicro-C of GM12878 (Nat Genet 57:1777; GEO GSE192759, hg38): the 12 deepest cells'
    hickit contact pairs, binned at 5 kb into one ``.scool`` linked as ``per_cell``; ``qc_pass`` flags the two
    cells with under 50 % cis contacts.  Each contact counted once (haplotypes ignored)."""
    import re

    from . import fetch
    from ..io.pairs_maps import pairs_chromsizes

    folder = fetch("wu2025_scmicroc", root=root, extract=False)     # the pairs only (no 102 GB 3dg tarball)
    files = sorted(folder.glob("GSM*_cell_*.impute.pairs.gz"))
    if len(files) != 12:
        raise ValueError(f"expected the pairs of 12 cells in {folder}, found {len(files)}")
    sizes = pairs_chromsizes(files[0])
    for f in files[1:]:
        if pairs_chromsizes(f) != sizes:
            raise ValueError(f"{f.name}: chromosome sizes differ from {files[0].name}'s")
    _check_sizes(sizes, HG38, "wu2025_scmicroc")
    sources = {re.search(r"(cell_\d{3})", f.name).group(1): f for f in files}
    cells = pd.DataFrame({"cell_id": list(sources), "gsm": [f.name.split("_", 1)[0] for f in files],
                          "cell_type": "GM12878", "dataset": "Wu 2025 scMicro-C"}).set_index("cell_id")
    uns = {"source": "Wu et al. 2025, Nat Genet 57:1777 (scMicro-C, GM12878; GEO GSE192759); hickit pairs of the "
                     "12 deepest cells, binned at 5 kb, both homologs counted",
           "haplotypes": "ignored: each contact counted once (the per-cell map sums both homologs)"}
    cd = _pairs_cells(sources, out, "wu2025_scmicroc", sizes, "hg38", cells, uns)
    cells = cd.cells.copy()
    cells["qc_pass"] = cells["frac_cis"] >= MIN_FRAC_CIS
    cd.cells = cells
    return cd


#: hg38 chromosome sizes (UCSC), chr1-22 and chrX (the GM12878 maps: a female line)
HG38 = {"chr1": 248956422, "chr2": 242193529, "chr3": 198295559, "chr4": 190214555, "chr5": 181538259,
        "chr6": 170805979, "chr7": 159345973, "chr8": 145138636, "chr9": 138394717, "chr10": 133797422,
        "chr11": 135086622, "chr12": 133275309, "chr13": 114364328, "chr14": 107043718, "chr15": 101991189,
        "chr16": 90338345, "chr17": 83257441, "chr18": 80373285, "chr19": 58617616, "chr20": 64444167,
        "chr21": 46709983, "chr22": 50818468, "chrX": 156040895}

register(Loader(
    name="tan2018_gm12878", build=build_tan2018_gm12878,
    store="tan2018_gm12878/tan2018_gm12878.chromdata.zarr", sources=("tan2018_gm12878",),
    description="Tan 2018 Dip-C GM12878: 14 cells with hickit pairs, 5 kb maps per cell (linked .scool), hg19"))

register(Loader(
    name="wu2025_scmicroc", build=build_wu2025_scmicroc,
    store="wu2025_scmicroc/wu2025_scmicroc.chromdata.zarr", sources=("wu2025_scmicroc",),
    description="Wu 2025 scMicro-C GM12878: 12 deep cells, 5 kb maps per cell (linked .scool), hg38"))
