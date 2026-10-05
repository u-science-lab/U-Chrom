"""Build the Stevens 2017 store of the atlas (Stevens et al. 2017, Nature, doi:10.1038/nature21429; GEO GSE80280).

Eight haploid mouse ES cells (G1) with single-cell Hi-C contacts and the authors' 3-D genome structures
(NucDynamics, 100 kb particles, 10 models per cell; coordinates in particle radii):

  stevens2017_mesc/stevens2017_mesc.chromdata.zarr

* 3-D coordinates: model 1 of each cell; models 2-10 as layers ``model_2`` ... ``model_10`` (same particles).
  One trace per cell and chromosome.
* links, next to the store: ``stevens2017_mesc_cells_1Mb.scool`` (one map per cell, 1 Mb, from the cell's contact
  pairs) and ``stevens2017_mesc_bulk.mcool`` (the 8 cells merged, 100 kb - 1 Mb).

Input: ``python example-data/download_data.py --stevens2017`` (43 MB).

Usage::

    python example-data/build_stevens2017.py
"""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sc_hic_common import ContactBinner, chromsizes, empty_spots, log  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "stevens2017_mesc"
CHAINS = {chr(ord("a") + i): f"chr{i + 1}" for i in range(19)} | {"t": "chrX"}
RES = 100_000


def read_pdb(path: Path) -> list:
    """The models of an extended Nuc3D PDB (chain a..t = chr1..chrX, particle start in the last column)."""
    models, rows = [], []
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith("MODEL"):
                rows = []
            elif line.startswith("HETATM"):
                rows.append((CHAINS.get(line[21], line[21]), int(line.split()[-1]),
                             float(line[30:38]), float(line[38:46]), float(line[46:54])))
            elif line.startswith("ENDMDL"):
                df = pd.DataFrame(rows, columns=["chrom", "start", "x", "y", "z"])
                models.append(df.drop_duplicates(["chrom", "start"]).reset_index(drop=True))
    return models


def main() -> None:
    from uchrom import ChromData

    sizes = chromsizes(None, "mm10", keep=[f"chr{i}" for i in range(1, 20)] + ["chrX"])
    cells = sorted(OUT.glob("GSM*_Cell_*_contact_pairs.txt.gz"), key=lambda p: int(p.name.split("_")[2]))
    names = [f"Cell_{p.name.split('_')[2]}" for p in cells]
    gsm = {n: p.name.split("_")[0] for n, p in zip(names, cells)}

    # contacts
    binner = ContactBinner(sizes, names, OUT / ".bins", bulk_res=RES)
    for name, path in zip(names, cells):
        df = pd.read_csv(path, sep="\t", comment="#", header=None, names=["chr1", "pos1", "chr2", "pos2"],
                         dtype={"chr1": str, "chr2": str})
        ci = np.full(len(df), binner.cell_index.get_loc(name))
        binner.add(ci, binner.chrom_codes(df["chr1"]), df["pos1"].to_numpy(), binner.chrom_codes(df["chr2"]),
                   df["pos2"].to_numpy())
    binner.close()
    stem = OUT / "stevens2017_mesc"
    scool = stem.with_name(stem.name + "_cells_1Mb.scool")
    binner.write_scool(scool)
    mcool = binner.write_mcool(stem.with_name(stem.name + "_bulk.mcool"), resolutions=(100_000, 250_000, 500_000, 1_000_000))
    per_cell = pd.Series(binner.per_cell, index=binner.cells)
    binner.cleanup()
    log(f"contacts: {binner.n_kept:,} of {binner.n_in:,} on kept chromosomes")

    # structures
    spots, coords, layers = [], [], {f"model_{k}": [] for k in range(2, 11)}
    for name in names:
        pdb = OUT / f"{gsm[name]}_{name}_genome_structure_model.pdb.gz"
        models = read_pdb(pdb)
        ref = models[0]
        key = ref[["chrom", "start"]]
        for k, m in enumerate(models[1:], start=2):
            m = key.merge(m, on=["chrom", "start"], how="left")
            if m[["x", "y", "z"]].isna().any().any():
                raise SystemExit(f"{pdb.name}: model {k} has other particles than model 1")
            layers[f"model_{k}"].append(m[["x", "y", "z"]].to_numpy())
        s = pd.DataFrame({"chrom": ref["chrom"], "start": ref["start"].astype(np.int64)})
        s["end"] = np.minimum(s["start"] + RES, s["chrom"].map(sizes))
        s["trace_id"] = name + "_" + s["chrom"]
        s["cell_id"] = name
        spots.append(s)
        coords.append(ref[["x", "y", "z"]].to_numpy())
        log(f"{name}: {len(ref):,} particles, {len(models)} models")
    spots = pd.concat(spots, ignore_index=True)
    cells = pd.DataFrame({"gsm": [gsm[n] for n in names], "n_contacts": per_cell.reindex(names).to_numpy(),
                          "cell_type": "haploid mESC (G1)"}, index=pd.Index(names, name="cell_id"))
    cd = ChromData(np.concatenate(coords), spots, cells=cells,
                   layers={k: np.concatenate(v) for k, v in layers.items()},
                   uns={"genome_assembly": "mm10", "xyz_unit": "particle radius",
                        "source": "Stevens et al. 2017, Nature (doi:10.1038/nature21429); GEO GSE80280",
                        "coordinate_status": "the authors' NucDynamics structures, 100 kb particles: model 1 in coords, "
                                             "models 2-10 in layers"})
    cd.link_cool(mcool.name, key="bulk", label="All 8 cells (merged)")
    cd.link_scool(scool.name, key="per_cell", label="Per cell", cell_name="cell_id", genome_assembly="mm10",
                  bin_size=1_000_000)
    out = stem.with_name(stem.name + ".chromdata.zarr")
    cd.write(out)
    log(f"wrote {out}: {cd}")


if __name__ == "__main__":
    main()
