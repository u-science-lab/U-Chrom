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
