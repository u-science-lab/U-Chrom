"""Atlas stores of single-cell Hi-C with the authors' NucDynamics structures (``.ncc`` contacts, ``.n3d`` / PDB).

  lando2024_mesc   Lando et al. 2024, Mol Cell 84:1406 (GEO GSE214264): haploid mESC (129/Ola, Rex1-GFPd2) leaving
                   naive pluripotency (naive, 24 h Rex1 high / low, 48 h); 100 kb structures, 10 models per cell
  zhou2019_rice    Zhou et al. 2019, Nat Plants 5:795 (GEO GSE123109): rice (Nipponbare, IRGSP-1.0) egg, sperm,
                   unicellular zygote and shoot cells; one 5 kb structure per cell (NucDynamics PDB)

Every store (``<data>/<name>/<name>.chromdata.zarr``) has

* 3-D coordinates: the authors' first model of each cell, one trace per cell and chromosome; particles placed at
  the position the file gives (the particle's start, as in the Stevens 2017 store);
* lando2024_mesc: model 2 as layer ``model_2`` on the same particles, its deviation from model 1 after superposition
  per cell (``rmsd_model_2``, ``median_dev_model_2``) and per particle (``spot_tracks['model_deviation']``, marked
  in ``uns['derived_spot_tracks']``);
* cells: the authors' labels and ``n_contacts``;
* links next to the store: ``<name>_cells_100kb.scool`` and ``<name>_bulk.mcool`` (100 kb, 500 kb, 1 Mb).

Then ``derive_embeddings.py STORE --hic per_cell`` (``--leiden`` for lando2024_mesc; zhou2019_rice's 15 cells form one
cluster) and ``python -m chromdata.embedded STORE``.

Usage::

    python apps/atlas/recipes/build_nuc_structures.py lando2024_mesc
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_dipc_structures import _series_matrix  # noqa: E402
from sc_hic_common import MM10, ContactBinner, chromsizes, log  # noqa: E402

RES_MAP = 100_000
#: rice IRGSP-1.0 chromosome sizes (Ensembl Plants, assembly IRGSP-1.0; the MSU7 pseudomolecules are the same)
IRGSP1 = {"Chr1": 43270923, "Chr2": 35937250, "Chr3": 36413819, "Chr4": 35502694, "Chr5": 29958434,
          "Chr6": 31248787, "Chr7": 29697621, "Chr8": 28443022, "Chr9": 23012720, "Chr10": 23207287,
          "Chr11": 29021106, "Chr12": 27531856}


def read_n3d(path: Path) -> list:
    """The models of a NucDynamics ``.n3d`` file: per model a DataFrame (chrom, pos, x, y, z)."""
    blocks = []
    with gzip.open(path, "rt") as fh:
        chrom, n, rows = None, 0, []
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 3:
                chrom, n = parts[0], int(parts[2])
                continue
            rows.append((chrom, int(float(parts[0])), np.asarray(parts[1:], dtype=np.float64).reshape(n, 3)))
    models = []
    for k in range(rows[0][2].shape[0]):
        models.append(pd.DataFrame({"chrom": [r[0] for r in rows], "pos": [r[1] for r in rows],
                                    "x": [r[2][k, 0] for r in rows], "y": [r[2][k, 1] for r in rows],
                                    "z": [r[2][k, 2] for r in rows]}))
    return models


def read_pdb(path: Path, chains: dict) -> list:
    """The models of an extended NucDynamics PDB (particle position in the last column; chain -> chromosome)."""
    models, rows = [], []
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith("MODEL"):
                rows = []
            elif line.startswith("HETATM"):
                rows.append((chains[line[21]], int(float(line.split()[-1])),
                             float(line[30:38]), float(line[38:46]), float(line[46:54])))
            elif line.startswith("ENDMDL") or (line.startswith("END") and rows and not models):
                models.append(pd.DataFrame(rows, columns=["chrom", "pos", "x", "y", "z"])
                              .drop_duplicates(["chrom", "pos"]).reset_index(drop=True))
                rows = []
    if rows:
        models.append(pd.DataFrame(rows, columns=["chrom", "pos", "x", "y", "z"])
                      .drop_duplicates(["chrom", "pos"]).reset_index(drop=True))
    return models


def read_ncc(path: Path) -> pd.DataFrame:
    """The contacts of an ``.ncc`` file: chr1, pos1, chr2, pos2 (the first coordinate of each end)."""
    return pd.read_csv(path, sep=r"\s+", header=None, usecols=[0, 1, 6, 7], names=["chr1", "pos1", "chr2", "pos2"],
                       dtype={"chr1": str, "chr2": str})


def lando2024(raw: Path) -> dict:
    files = {}
    for p in sorted((raw / "GSE214264").glob("GSM*")):
        m = re.match(r"^GSM\d+_(P\d+[A-H]\d+)(\.ncc\.gz|_ambig_10x_100kb\.n3d\.txt\.gz)$", p.name)
        if m:
            files.setdefault(m[1], {})["ncc" if m[2] == ".ncc.gz" else "n3d"] = p
    files = {c: (f["ncc"], f["n3d"]) for c, f in files.items() if len(f) == 2}
    mx = _series_matrix([raw / "GSE214264" / "GSE214264-GPL21103_series_matrix.txt.gz"])
    mx = mx[mx["title"].str.startswith("Single nucleus Hi-C cell")]
    mx["cell_id"] = mx["title"].str.replace("Single nucleus Hi-C cell ", "", regex=False)
    mx = mx.set_index("cell_id")
    cells = pd.DataFrame({"gsm": mx["geo_accession"], "condition": mx["treatment"],
                          "cell_type": mx["cell type"]}).reindex(sorted(files))
    order = ["Naive ES", "24 hr Rex1 High", "24 hr Rex1 Low/formative", "48 hr primed"]
    cells["condition"] = pd.Categorical(cells["condition"], categories=[o for o in order if o in
                                                                         set(cells["condition"])])
    return {"name": "lando2024_mesc", "cells": cells, "files": files, "assembly": "mm10",
            "sizes": chromsizes(None, "mm10", keep=MM10), "res": 100_000, "read": read_n3d,
            "source": "Lando et al. 2024, Mol Cell 84:1406 (single-nucleus Hi-C of haploid mESC exiting naive "
                      "pluripotency; GEO GSE214264): contacts (.ncc) and the authors' NucDynamics structures "
                      "(100 kb particles, 10 models; models 1 and 2 read)"}


def zhou2019(raw: Path) -> dict:
    base = raw / "GSE123109"
    with gzip.open(base / "GSE123109_chromosome_chain_annotation.txt.gz", "rt") as fh:
        chains = {line.split()[1]: line.split()[0] for line in fh if not line.startswith("chromosome")}
    files = {}
    for p in sorted(base.glob("GSM*")):
        m = re.match(r"^GSM\d+_(\w+?_\d+)\.(ncc\.txt|pdb)\.gz$", p.name)
        if m:
            files.setdefault(m[1], {})[m[2]] = p
    files = {c: (f["ncc.txt"], f["pdb"]) for c, f in files.items() if len(f) == 2}
    names = sorted(files, key=lambda c: (c.rsplit("_", 1)[0], int(c.rsplit("_", 1)[1])))
    cells = pd.DataFrame({"cell_type": [c.rsplit("_", 1)[0].replace("_", " ").lower() for c in names]},
                         index=pd.Index(names, name="cell_id"))
    return {"name": "zhou2019_rice", "cells": cells, "files": files, "assembly": "IRGSP-1.0", "sizes": IRGSP1,
            "res": 5_000, "read": lambda p: read_pdb(p, chains),
            "source": "Zhou et al. 2019, Nat Plants 5:795 (single-cell Hi-C of rice egg, sperm, unicellular zygote "
                      "and shoot cells; GEO GSE123109): contacts (.ncc) and the authors' NucDynamics structure "
                      "(5 kb particles; chains named by GSE123109_chromosome_chain_annotation)"}


STUDIES = {"lando2024_mesc": lando2024, "zhou2019_rice": zhou2019}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study", choices=sorted(STUDIES))
    args = ap.parse_args()

    from uchrom import ChromData
    from uchrom.datasets import data_dir
    from uchrom.io.dipc_3dg import replicate_deviation

    out_dir = data_dir() / args.study
    s = STUDIES[args.study](out_dir / "raw")
    cells, files, sizes, res = s["cells"], s["files"], s["sizes"], s["res"]
    names = list(cells.index)
    stem = out_dir / s["name"]
    log(f"{s['name']}: {len(names)} cells with contacts and a structure")

    binner = ContactBinner(sizes, names, out_dir / ".bins", cell_res=RES_MAP, bulk_res=RES_MAP)
    for name in names:
        df = read_ncc(files[name][0])
        binner.add(np.full(len(df), binner.cell_index.get_loc(name)), binner.chrom_codes(df["chr1"]),
                   df["pos1"].to_numpy(), binner.chrom_codes(df["chr2"]), df["pos2"].to_numpy())
    binner.close()
    scool = stem.with_name(stem.name + f"_cells_{RES_MAP // 1000}kb.scool")
    binner.write_scool(scool)
    mcool = binner.write_mcool(stem.with_name(stem.name + "_bulk.mcool"),
                               resolutions=(100_000, 500_000, 1_000_000))
    per_cell = pd.Series(binner.per_cell, index=binner.cells)
    binner.cleanup()
    log(f"contacts: {binner.n_kept:,} of {binner.n_in:,} on kept chromosomes")

    spots, coords, second = [], [], []
    for name in names:
        models = s["read"](files[name][1])
        ref = models[0][models[0]["chrom"].isin(sizes)].reset_index(drop=True)
        if len(models) > 1:
            m2 = ref[["chrom", "pos"]].merge(models[1], on=["chrom", "pos"], how="left")
            second.append(m2[["x", "y", "z"]].to_numpy())
        sp = pd.DataFrame({"chrom": ref["chrom"], "start": ref["pos"].astype(np.int64)})
        sp["end"] = np.minimum(sp["start"] + res, sp["chrom"].map(sizes))
        sp["trace_id"] = name + "_" + sp["chrom"]
        sp["cell_id"] = name
        spots.append(sp)
        coords.append(ref[["x", "y", "z"]].to_numpy())
        log(f"{name}: {len(ref):,} particles, {len(models)} model(s)")
    spots = pd.concat(spots, ignore_index=True)
    cells = cells.copy()
    cells["n_contacts"] = per_cell.reindex(names).fillna(0).astype(np.int64).to_numpy()
    status = f"the authors' NucDynamics structures ({res // 1000} kb particles, placed at the file's position)"
    uns = {"genome_assembly": s["assembly"], "xyz_unit": "particle radius", "source": s["source"]}
    layers, tracks = {}, None
    if second and len(second) == len(names):
        layers = {"model_2": np.concatenate(second)}
        cd = ChromData(np.concatenate(coords), spots, cells=cells, layers=layers)
        per, dev = replicate_deviation(cd, ("model_2",), reflection=True)
        cells = cells.join(per[["rmsd_model_2", "median_dev_model_2"]])
        tracks = pd.DataFrame({"model_deviation": dev})
        uns["derived_spot_tracks"] = ["model_deviation"]
        status += ("; model 1 in coords, model 2 in layers, their deviation after superposition per cell "
                   "(rmsd_model_2, median_dev_model_2) and per particle (spot_tracks model_deviation)")
        log(f"model 1 vs 2: RMSD median {per['rmsd_model_2'].median():.2f} particle radii")
    uns["coordinate_status"] = status
    cd = ChromData(np.concatenate(coords), spots, cells=cells, layers=layers, spot_tracks=tracks, uns=uns)
    cd.link_cool(mcool.name, key="bulk", label=f"All {len(names)} cells (merged)")
    cd.link_scool(scool.name, key="per_cell", label=f"Per cell ({RES_MAP // 1000} kb)", cell_name="cell_id",
                  genome_assembly=s["assembly"], bin_size=RES_MAP)
    out = stem.with_name(stem.name + ".chromdata.zarr")
    cd.write(out)
    log(f"wrote {out}: {cd}")


if __name__ == "__main__":
    main()
