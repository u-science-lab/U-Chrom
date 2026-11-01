"""Atlas stores of single-cell Hi-C deposited as one contact table per cell, without structures.

Five studies (``python -m uchrom.datasets fetch NAME``; the raw files under ``<data>/<NAME>/raw``):

  flyamer2017_snhic    Flyamer et al. 2017, Nature 544:110 (GEO GSE80006): snHi-C of single mouse oocytes (NSN, SN)
                       and zygote pronuclei (mm9) and of K562 cells (hg19); one ``-reads.csv.gz`` per nucleus (the
                       authors' filtered contacts); stores flyamer2017_oocyte_zygote and flyamer2017_k562
  collombet2020_snhic  Collombet et al. 2020, Nature 580:142 (GEO GSE129029): snHi-C of mouse oocytes and embryos
                       from the 1-cell to the 64-cell stage, HiC-Pro allele-specific valid pairs (mm10)
  zhou2024_mcf7        Zhou et al. 2024, Nat Commun 15:8310 (GEO GSE194308): scHi-C of MCF7 cells and of the two
                       derived lines of the deposit, MCF7TR and MCF7M1, HiC-Pro valid pairs (hg19)
  tan2023_cerebellum   Tan et al. 2023, Science 381:1112 (GEO GSE246785): Dip-C of the mouse cerebellum from birth
                       (P0) to P637, one tarball of every cell's contact pairs (``contacts_unisex``, mm10)
  ulianov2021_snhic    Ulianov et al. 2021, Nat Commun 12:41 (GEO GSE131811): the authors' 10 kb maps of their 20
                       best Drosophila BG3 nuclei and of the population (dm3); the maps are taken as deposited

Every store (``<data>/<NAME>/<store>.chromdata.zarr``) holds no 3-D coordinates, only cells and linked maps:

* cells: the labels of the deposit (stage, cell line, age, ...), ``n_contacts`` (contacts on the kept chromosomes,
  autosomes and X / Y; chrM and unplaced contigs dropped), ``n_cis``, ``frac_cis``;
* ``<store>_cells_1Mb.scool`` (each cell at 1 Mb, linked ``per_cell``; the contacts of both homologs summed, alleles
  ignored) and ``<store>_bulk.mcool`` (all cells, 50 kb - 1 Mb, ICE-balanced, linked ``bulk``); Ulianov: 10 kb;
* a scHiCluster embedding of the per-cell maps (``cellm['hic_pca']``, ``['hic_umap']``) and its Leiden clusters
  (``cells['hic_leiden']``).

Then ``python -m chromdata.embedded STORE``.  Usage::

    python apps/atlas/recipes/build_schic_pairs.py collombet2020_snhic [--workers 8] [--test 20]
"""

from __future__ import annotations

import argparse
import gzip
import io
import re
import sys
import tarfile
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_dipc_structures import _series_matrix  # noqa: E402
from sc_hic_common import (HG38, MM10, ContactBinner, balance_mcool, chromsizes, empty_spots, log)  # noqa: E402

CELL_RES = 1_000_000

#: how each deposit writes a contact: (separator, header row?, 0-based columns of chrom1, pos1, chrom2, pos2)
FORMATS = {"flyamer": (",", True, (0, 2, 1, 3)),        # chr1,chr2,pos1,pos2,strand1,strand2 (chromosomes "1".."X")
           "hicpro": ("\t", False, (1, 2, 4, 5)),       # readID chr1 pos1 strand1 chr2 pos2 strand2 ...
           "pairs": ("\t", False, (1, 2, 3, 4))}        # 4DN .pairs / hickit: readID chr1 pos1 chr2 pos2 ...


# -- the studies -------------------------------------------------------------------------------------------------

def _flyamer_label(label: str) -> dict:
    """A Flyamer 2017 nucleus label ('12_oocyte_SN-Hoechst', '58_pronucleus-female', '54_K562-B') -> fields."""
    rest = label.split("_", 1)[1]
    out = {"label": rest, "hoechst": "Hoechst" in rest}
    if "K562" in rest:
        out.update(stage="K562", cell_type="K562", set=rest[-1])
    elif "pronucleus" in rest:
        sex = re.search(r"(female|male|both|undef\w*)$", rest)
        kind = {"female": "maternal pronucleus", "male": "paternal pronucleus", "both": "both pronuclei"}
        out.update(stage="zygote", cell_type=kind.get(sex[1] if sex else "", "pronucleus, parent not identified"))
    else:
        kind = re.search(r"(NSN|SN|Intermediate)", rest)[1]
        out.update(stage="oocyte", cell_type=f"{kind} oocyte" if kind != "Intermediate" else "intermediate oocyte")
    return out


def flyamer2017(raw: Path) -> dict:
    files, rows = {}, []
    for p in sorted((raw / "cells").glob("GSM*-reads.csv.gz")):
        gsm, label = re.match(r"^(GSM\d+)_(.+)-reads\.csv\.gz$", p.name).groups()
        num, rest = label.split("_", 1)
        cell = f"{int(num):03d}_{rest}"
        files[cell] = p
        rows.append({"cell_id": cell, "gsm": gsm, **_flyamer_label(label)})
    cells = pd.DataFrame(rows).set_index("cell_id")
    mouse = cells[cells["stage"] != "K562"].drop(columns="set", errors="ignore")
    human = cells[cells["stage"] == "K562"].drop(columns="stage")
    return {"stores": {"flyamer2017_oocyte_zygote": mouse, "flyamer2017_k562": human}, "files": files,
            "format": "flyamer", "assembly": {"flyamer2017_oocyte_zygote": "mm9", "flyamer2017_k562": "hg19"},
            "source": "Flyamer et al. 2017, Nature 544:110 (snHi-C; GEO GSE80006): the authors' filtered contacts of "
                      "each nucleus (-reads.csv.gz: duplicates and repeated 500 bp bin pairs removed)"}


def collombet2020(raw: Path) -> dict:
    files = {re.match(r"^GSM\d+_(.+)\.allValidPairs\.txt\.gz$", p.name)[1]: p
             for p in sorted((raw / "cells").glob("GSM*.allValidPairs.txt.gz"))}
    m = _series_matrix([raw / "GSE129029_series_matrix.txt.gz"])
    m["cell_id"] = m["title"].str.extract(r"^(\S+)")[0].str.replace("-", "_", n=1)
    stage = {"oocyte": "oocyte", "1 cell stage": "1-cell", "2 cell stage": "2-cell", "4 cell stage": "4-cell",
             "8 cell stage": "8-cell", "64 cell stage": "64-cell",
             "1cell stage or oocyte (not identified)": "1-cell or oocyte"}
    cells = pd.DataFrame({"gsm": m["geo_accession"].to_numpy(),
                          "stage": m["source_name_ch1"].map(stage).to_numpy()}, index=m["cell_id"])
    if cells["stage"].isna().any():
        raise ValueError(f"collombet2020: unknown stages {sorted(set(m['source_name_ch1']) - set(stage))}")
    cells["stage"] = pd.Categorical(cells["stage"], categories=list(dict.fromkeys(stage.values())))
    cells["cell_type"] = cells["stage"]
    return {"stores": {"collombet2020_embryo": cells.reindex(sorted(files))}, "files": files, "format": "hicpro",
            "assembly": "mm10",
            "source": "Collombet et al. 2020, Nature 580:142 (snHi-C of mouse oocytes and early embryos, C57BL/6J x "
                      "CAST/EiJ; GEO GSE129029): HiC-Pro valid pairs of each nucleus (MAPQ > 30), alleles ignored"}


def zhou2024(raw: Path) -> dict:
    files = {re.match(r"^GSM\d+_(.+)\.allValidPairs\.txt\.gz$", p.name)[1]: p
             for p in sorted((raw / "cells").glob("GSM*.allValidPairs.txt.gz"))}
    m = _series_matrix([raw / "GSE194308_series_matrix.txt.gz"])
    m["cell_id"] = m["title"].str.extract(r"(\S+)$")[0]
    cells = pd.DataFrame({"gsm": m["geo_accession"].to_numpy(), "cell_line": m["source_name_ch1"].to_numpy()},
                         index=m["cell_id"])
    cells["cell_type"] = cells["cell_line"]
    return {"stores": {"zhou2024_mcf7": cells.reindex(sorted(files))}, "files": files, "format": "hicpro",
            "assembly": "hg19",
            "source": "Zhou et al. 2024, Nat Commun 15:8310 (scHi-C of MCF7 and the derived lines MCF7TR and MCF7M1; "
                      "GEO GSE194308): HiC-Pro valid pairs of each cell"}


def _tan_age(sample: str) -> str:
    m = re.match(r"dipc-mouse-cerebellum-p(\d+)(?:-p(\d+))?", sample)
    return f"P{int(m[1])}" + (f"-P{int(m[2])}" if m[2] else "")


def tan2023(raw: Path) -> dict:
    tars = {}
    for name in ("GSE246785_mouse.contacts_unisex.info.tar.gz", "GSE246785_mouse.x2a.txt.tar.gz"):
        with tarfile.open(raw / name) as t:
            for mem in t:
                if mem.isfile():
                    cell = Path(mem.name).name.split(".")[0]
                    tars.setdefault(name, {})[cell] = t.extractfile(mem).read().decode().split()
    info, x2a = tars["GSE246785_mouse.contacts_unisex.info.tar.gz"], tars["GSE246785_mouse.x2a.txt.tar.gz"]
    rows = []
    for cell in sorted(c for c in info if c.startswith("dipc-")):
        sample = cell.rsplit("_", 1)[0]
        r = float(x2a[cell][1]) if cell in x2a else np.nan
        rows.append({"cell_id": cell, "sample": sample.removeprefix("dipc-mouse-cerebellum-"), "age": _tan_age(sample),
                     "f1_hybrid": sample.endswith("-f1hybrid"), "purkinje_enriched": sample.endswith("-purkinje"),
                     "x_to_autosome": r, "sex": "female" if r > 0.7 else "male" if r < 0.6 else "unclear",
                     "n_contacts_published": int(info[cell][2])})
    cells = pd.DataFrame(rows).set_index("cell_id")
    ages = sorted(cells["age"].unique(), key=lambda a: int(re.match(r"P(\d+)", a)[1]))
    cells["age"] = pd.Categorical(cells["age"], categories=ages)
    cells["cell_type"] = cells["age"]
    return {"stores": {"tan2023_cerebellum": cells}, "tar": raw / "GSE246785_mouse.contacts_unisex.pairs.gz.tar.gz",
            "format": "pairs", "assembly": "mm10",
            "source": "Tan et al. 2023, Science 381:1112 (Dip-C of the mouse cerebellum, P0 to P637; GEO GSE246785): "
                      "every cell's contact pairs (contacts_unisex), the authors' contact counts and X-to-autosome "
                      "ratios (sex: female above 0.7, male below 0.6)"}


STUDIES = {"flyamer2017_snhic": flyamer2017, "collombet2020_snhic": collombet2020, "zhou2024_mcf7": zhou2024,
           "tan2023_cerebellum": tan2023}


# -- binning -----------------------------------------------------------------------------------------------------

_KM = None
_FMT = None


def _init(km, fmt):
    global _KM, _FMT
    _KM, _FMT = km, fmt


def _codes(col: pd.Series) -> np.ndarray:
    """Chromosome index of every value (names with or without 'chr'; -1: not kept)."""
    cat = col.astype("category")
    names = [c if str(c).startswith("chr") else f"chr{c}" for c in cat.cat.categories]
    table = np.r_[_KM.chrom_codes(names), -1]
    return table[cat.cat.codes.to_numpy()]


def _bin_cell(args):
    """One cell's contacts (a path or the bytes of a gzipped file) -> (cell, cell keys, bulk keys, n read, n cis)."""
    ci, src = args
    sep, header, cols = FORMATS[_FMT]
    fh = io.BytesIO(gzip.decompress(src)) if isinstance(src, bytes) else src
    dtype = {cols[0]: str, cols[1]: np.int64, cols[2]: str, cols[3]: np.int64}
    try:
        df = pd.read_csv(fh, sep=sep, comment=None if header else "#", header=None, skiprows=1 if header else 0,
                         usecols=list(cols), dtype=dtype, compression=None if isinstance(src, bytes) else "gzip")
    except pd.errors.EmptyDataError:                    # a cell without contacts (an empty file)
        df = pd.DataFrame({c: pd.Series(dtype=t) for c, t in dtype.items()})
    c1, c2 = _codes(df[cols[0]]), _codes(df[cols[2]])
    p1, p2 = df[cols[1]].to_numpy(), df[cols[3]].to_numpy()
    ck, bk = _KM.keys(c1, p1, c2, p2)
    ok = (c1 >= 0) & (c2 >= 0)
    return ci, ck, bk, len(df), int((c1[ok] == c2[ok]).sum())


def _tar_cells(tar: Path, index: pd.Index):
    """(cell index, bytes) of every cell's pairs file in a .tar.gz, streamed in archive order."""
    with tarfile.open(tar, "r|gz") as t:
        for mem in t:
            if not mem.isfile():
                continue
            cell = Path(mem.name).name.split(".")[0]
            if cell in index:
                yield int(index.get_loc(cell)), t.extractfile(mem).read()


def bin_contacts(cells: pd.DataFrame, study: dict, stem: Path, sizes: dict, workers: int):
    binner = ContactBinner(sizes, cells.index, stem.parent / f".{stem.name}_bins", cell_res=CELL_RES)
    if "tar" in study:
        jobs = _tar_cells(study["tar"], binner.cell_index)
    else:
        jobs = [(int(binner.cell_index.get_loc(c)), study["files"][c]) for c in cells.index]
    n_cis = np.zeros(len(binner.cells), np.int64)
    t0 = time.time()
    with Pool(workers, initializer=_init, initargs=(binner.keymaker(), study["format"])) as pool:
        for k, (ci, ck, bk, n, cis) in enumerate(pool.imap_unordered(_bin_cell, jobs, chunksize=2)):
            binner.add_keys(ci, ck, bk, n)
            n_cis[ci] += cis
            if (k + 1) % 200 == 0:
                log(f"  contacts of {k + 1:,} / {len(cells):,} cells ({time.time() - t0:.0f} s)")
    binner.close()
    log(f"contacts: {binner.n_in:,} read, {binner.n_kept:,} on kept chromosomes, {len(cells):,} cells")
    scool = stem.with_name(stem.name + "_cells_1Mb.scool")
    names = binner.write_scool(scool)
    mcool = binner.write_mcool(stem.with_name(stem.name + "_bulk.mcool"))
    stats = pd.DataFrame({"n_contacts": binner.per_cell, "n_cis": n_cis}, index=binner.cells)
    binner.cleanup()
    return scool, mcool, stats, names


def embed(cd, scool: Path, key: str = "per_cell") -> None:
    from uchrom.emb import cluster_cells, embed_contacts

    embed_contacts(cd, contacts=key, key_added="hic", methods=("pca", "umap"))
    labels = cluster_cells(cd, use="hic_pca", resolution=1.0, key_added="hic_leiden")
    log(f"hic_leiden: {labels.value_counts().to_dict()}")


def build_store(name: str, cells: pd.DataFrame, study: dict, out_dir: Path, workers: int) -> Path:
    from uchrom import ChromData

    assembly = study["assembly"][name] if isinstance(study["assembly"], dict) else study["assembly"]
    sizes = chromsizes(None, assembly, keep=HG38 if assembly.startswith("hg") else MM10)
    stem = out_dir / name
    log(f"{name}: {len(cells):,} cells, {assembly}, {len(sizes)} chromosomes")
    scool, mcool, stats, names = bin_contacts(cells, study, stem, sizes, workers)
    log(f"balanced {balance_mcool(mcool)} of {mcool.name}")
    cells = cells.join(stats)
    cells["frac_cis"] = cells["n_cis"] / cells["n_contacts"].where(cells["n_contacts"] > 0)
    empty = cells.index[cells["n_contacts"] == 0]
    if len(empty):
        log(f"dropped {len(empty)} cells without contacts on the kept chromosomes: {list(empty[:5])}")
        cells = cells.drop(index=empty)
    cd = ChromData(np.zeros((0, 3)), empty_spots(), cells=cells,
                   uns={"genome_assembly": assembly, "source": study["source"],
                        "coordinate_status": "no 3-D coordinates: contacts only",
                        "haplotypes": "ignored: each contact counted once (a cell's map sums its homologs)"})
    cd.link_cool(mcool.name, key="bulk", label=f"All {len(cells):,} cells (merged)")
    cd.link_scool(scool.name, key="per_cell", label="Per cell (1 Mb)", cell_name="cell_id", genome_assembly=assembly,
                  bin_size=CELL_RES)
    for kind in ("linked_scool", "linked_cool"):             # absolute while embedding, relative in the store
        for rec in cd.uns[kind].values():
            rec["path"] = str(out_dir / Path(rec["path"]).name)
    embed(cd, scool)
    for kind in ("linked_scool", "linked_cool"):
        for rec in cd.uns[kind].values():
            rec["path"] = Path(rec["path"]).name
    out = stem.with_name(stem.name + ".chromdata.zarr")
    cd.write(out)
    log(f"wrote {out}: {cd}")
    return out


# -- Ulianov 2021: maps as deposited -----------------------------------------------------------------------------

def build_ulianov2021(raw: Path, out_dir: Path) -> Path:
    import cooler
    from uchrom import ChromData

    cools = {}
    for p in sorted(raw.glob("GSM*_*.10000.cool.gz"), key=lambda p: p.name):
        name = re.match(r"^GSM\d+_(.+)\.10000\.cool\.gz$", p.name)[1]
        dest = raw / p.name.removesuffix(".gz")
        if not dest.exists():
            dest.write_bytes(gzip.decompress(p.read_bytes()))
        cools[name] = dest
    pop = cools.pop("Population")
    order = sorted(cools, key=lambda c: int(c.removeprefix("Cell")))
    bins = cooler.Cooler(str(cools[order[0]])).bins()[:][["chrom", "start", "end"]]
    rows, pixels = [], {}
    for c in order:
        clr = cooler.Cooler(str(cools[c]))
        if not clr.bins()[:][["chrom", "start", "end"]].equals(bins):
            raise ValueError(f"ulianov2021: {c} has other bins than {order[0]}")
        px = clr.pixels()[:]
        chrom = bins["chrom"].to_numpy()
        cis = int(px.loc[chrom[px["bin1_id"]] == chrom[px["bin2_id"]], "count"].sum())
        rows.append({"cell_id": c, "n_contacts": int(px["count"].sum()), "n_cis": cis, "cell_type": "BG3"})
        pixels[c] = px[["bin1_id", "bin2_id", "count"]]
    cells = pd.DataFrame(rows).set_index("cell_id")
    cells["frac_cis"] = cells["n_cis"] / cells["n_contacts"]
    stem = out_dir / "ulianov2021_bg3"
    scool = stem.with_name(stem.name + "_cells_10kb.scool")
    if scool.exists():
        scool.unlink()
    cooler.create_scool(str(scool), bins, pixels, ordered=True)
    mcool = stem.with_name(stem.name + "_population.mcool")
    cooler.zoomify_cooler(str(pop), str(mcool), resolutions=[10_000, 20_000, 50_000, 100_000], chunksize=10_000_000)
    balance_mcool(mcool, min_res=10_000)
    log(f"{len(cells)} nuclei, {cells['n_contacts'].sum():,} contacts; population map {mcool.name}")
    cd = ChromData(np.zeros((0, 3)), empty_spots(), cells=cells,
                   uns={"genome_assembly": "dm3", "coordinate_status": "no 3-D coordinates: contacts only",
                        "source": "Ulianov et al. 2021, Nat Commun 12:41 (snHi-C of Drosophila BG3 cells; GEO "
                                  "GSE131811): the authors' 10 kb maps of their 20 best nuclei (chimeric reads across "
                                  "DpnII sites, one contact per restriction-fragment pair; chr2L, 2R, 3L, 3R, 4) and "
                                  "the population map"})
    cd.link_cool(mcool.name, key="bulk", label="Population Hi-C of BG3 cells (the authors' map)")
    cd.link_scool(scool.name, key="per_cell", label="Per nucleus (10 kb)", cell_name="cell_id",
                  genome_assembly="dm3", bin_size=10_000)
    out = stem.with_name(stem.name + ".chromdata.zarr")
    cd.write(out)
    log(f"wrote {out}: {cd}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study", choices=sorted([*STUDIES, "ulianov2021_snhic"]))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--test", type=int, default=0, help="only the first N cells of each store, into <store>_test")
    args = ap.parse_args()

    from uchrom.datasets import data_dir

    out_dir = data_dir() / args.study
    if args.study == "ulianov2021_snhic":
        build_ulianov2021(out_dir / "raw", out_dir)
        return
    study = STUDIES[args.study](out_dir / "raw")
    for name, cells in study["stores"].items():
        if "files" in study:
            cells = cells[cells.index.isin(list(study["files"]))]
        if args.test:
            cells = cells.iloc[:args.test]
            name = f"{name}_test"
        if cells.empty:
            log(f"{name}: no cells with files, skipped")
            continue
        cells.index.name = "cell_id"
        build_store(name, cells, study, out_dir, args.workers)


if __name__ == "__main__":
    main()
