"""Atlas stores of single-cell Hi-C with the authors' 3-D structure of every cell (hickit / Dip-C ``.3dg``).

These studies deposit, per cell, the contact pairs and 20 kb structures (``python -m uchrom.datasets fetch NAME``):

  tan2019_dipc        Tan et al. 2019, Nat Struct Mol Biol 26:297 (GEO GSE121791): Dip-C of mouse retina and main
                      olfactory epithelium, 409 cells, three runs per cell (runs 1 and 2 read)
  xu2025_sperm        Xu et al. 2025, Nat Commun 16:3805 (GEO GSE276999): haploid human and mouse sperm, mESC
                      controls; two stores, xu2025_sperm_human (hg38) and xu2025_sperm_mouse (mm10)
  wu2024_limca        Wu et al. 2024, Nat Methods 21:974 (GEO GSE239969): LiMCA, 3-D genome and RNA of the same
                      mouse olfactory epithelium cells, 411 cells (runs 1 and 2 read), cell types, RNA counts
  wu2024_limca_human  the same paper's human cell lines (GEO GSE240114): 221 GM12878 cells with three 20 kb runs
                      (runs 1 and 2 read); store wu2024_limca_gm12878 (hg38), no RNA deposited
  liu2026_hires_xci   Liu et al. 2026, Genomics Proteomics Bioinformatics qzag002 (GEO GSE278310 + GSE310759):
                      HiRES of female hybrid mESC over the first days of random X inactivation, with RNA
  tan2023_cerebellum  Tan et al. 2023, Science 381:1112 (GEO GSE246785): Dip-C of the mouse cerebellum; the cells
                      of the F1-hybrid and Purkinje-enriched samples with a structure (one run, the model of the
                      cell's sex) and an RMSD of at most 1.5 (``TAN2023_MAX_RMSD``); store tan2023_cerebellum_3d

Every store (``<data>/<name>/<store>.chromdata.zarr``) has

* 3-D coordinates: the authors' first structure of each cell coarse-grained to ``res_3d`` (the mean of its 20 kb
  particles in each bin of each copy), one trace per cell, chromosome and copy (``<cell>_<chrom>[_<mat|pat>]``);
* where a second run of the cell is deposited, that run as layer ``run_2`` on the same particles, its deviation
  after superposition per cell (``cells``: ``rmsd_run_2``, ``median_dev_run_2``; rotation + translation, mirror
  allowed) and per particle (``spot_tracks['run_deviation']``, marked in ``uns['derived_spot_tracks']``);
* cells: the authors' labels (tissue, cell type, day, ...) and ``n_contacts``;
* links next to the store: ``<store>_cells_100kb.scool`` (each cell's pairs at 100 kb) and ``<store>_bulk.mcool``
  (all cells at 100 kb, 500 kb and 1 Mb; ICE weights from 500 kb); with RNA, ``<store>_rna.h5ad`` and an RNA PCA / UMAP.

Then, as for the other single-cell stores::

    python apps/atlas/recipes/derive_embeddings.py STORE --hic per_cell --leiden
    python -m chromdata.embedded STORE

Usage::

    python apps/atlas/recipes/build_dipc_structures.py tan2019_dipc [--workers 8] [--test 20]
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sc_hic_common import (HG38, MM10, ContactBinner, balance_mcool, bin_table, chromsizes,  # noqa: E402
                           empty_spots, hvg_zscores, log, rna_h5ad)

RES_MAP = 100_000                       # per-cell maps and the finest level of the bulk map


# -- the studies -------------------------------------------------------------------------------------------------

def _series_matrix(paths) -> pd.DataFrame:
    """Sample titles, source names and characteristics (``key: value`` -> column ``key``) of GEO series matrices."""
    frames = []
    for path in paths:
        rows = {}
        with gzip.open(path, "rt") as fh:
            for line in fh:
                if not line.startswith("!Sample_"):
                    continue
                key, *vals = line.rstrip("\n").split("\t")
                vals = [v.strip('"') for v in vals]
                if key == "!Sample_characteristics_ch1":
                    for i, v in enumerate(vals):
                        if ": " in v:
                            k, val = v.split(": ", 1)
                            rows.setdefault(k, [None] * len(vals))[i] = val
                elif key in ("!Sample_title", "!Sample_geo_accession", "!Sample_source_name_ch1"):
                    rows[key[8:]] = vals
                elif key == "!Sample_description" and "description" not in rows:
                    rows["description"] = vals
        frames.append(pd.DataFrame(rows))
    return pd.concat(frames, ignore_index=True)


def _cell_files(folder: Path, pattern: str) -> dict:
    """cell -> {role: path} of the files matching ``pattern`` (named groups ``cell`` and ``role``)."""
    out: dict = {}
    for p in sorted(folder.glob("GSM*")):
        m = re.match(pattern, p.name)
        if m:
            out.setdefault(m["cell"], {})[m["role"]] = p
    return out


def tan2019(raw: Path) -> dict:
    files = _cell_files(raw / "GSE121791" / "cells", r"^GSM\d+_(?P<cell>cell_\d+)\."
                        r"(?P<role>impute\.pairs|20k\.1\.clean|20k\.2\.clean)(?:\.3dg)?\.txt\.gz$")
    files = {c: (f["impute.pairs"], f["20k.1.clean"], f.get("20k.2.clean")) for c, f in files.items()
             if "impute.pairs" in f and "20k.1.clean" in f}
    m = _series_matrix(sorted((raw / "GSE121791").glob("GSE121791-GPL*_series_matrix.txt.gz")))
    m["cell_id"] = m["title"].str.replace(r"^Single Cell (\d+)$", r"cell_\1", regex=True)
    cells = m.set_index("cell_id")
    cells = pd.DataFrame({"gsm": cells["geo_accession"], "tissue": cells["source_name_ch1"],
                          **{k: cells[k] for k in cells.columns if k not in ("title", "geo_accession",
                                                                             "source_name_ch1", "description")
                             and not cells[k].equals(cells["source_name_ch1"])}})     # 'cell type' = the tissue
    cells["cell_type"] = cells["tissue"]
    return {"stores": {"tan2019_dipc": cells.reindex(sorted(files))}, "files": files, "assembly": "mm10",
            "res_3d": 100_000,
            "source": "Tan et al. 2019, Nat Struct Mol Biol 26:297 (Dip-C, mouse retina and main olfactory "
                      "epithelium; GEO GSE121791): imputed contact pairs and the authors' 20 kb clean structures "
                      "(runs 1 and 2) of each cell"}


def xu2025(raw: Path) -> dict:
    files = _cell_files(raw / "GSE276999" / "cells",
                        r"^GSM\d+_(?P<cell>(?:HS|BJ|ESCO)\d+)\.(?P<role>pairs|3dg)(?:\.txt)?\.gz$")
    files = {c: (f["pairs"], f["3dg"], None) for c, f in files.items() if "pairs" in f and "3dg" in f}
    kind = {"HS": ("human", "sperm", "Human sperm"), "BJ": ("mouse", "sperm", "Mouse sperm"),
            "ESCO": ("mouse", "mESC", "Mouse ES cells (control)")}
    rows = []
    for c in sorted(files, key=lambda c: (re.match(r"\D+", c).group(), int(re.search(r"\d+", c).group()))):
        species, ctype, label = kind[re.match(r"\D+", c).group()]
        rows.append({"cell_id": c, "species": species, "cell_type": ctype, "sample": label})
    cells = pd.DataFrame(rows).set_index("cell_id")
    return {"stores": {"xu2025_sperm_human": cells[cells["species"] == "human"].drop(columns="species"),
                       "xu2025_sperm_mouse": cells[cells["species"] == "mouse"].drop(columns="species")},
            "files": files, "assembly": {"xu2025_sperm_human": "hg38", "xu2025_sperm_mouse": "mm10"},
            "res_3d": 100_000,
            "source": "Xu et al. 2025, Nat Commun 16:3805 (scHi-C of single human and mouse sperm, mESC controls; "
                      "GEO GSE276999): contact pairs and the authors' 20 kb structures of the cells that have one "
                      "(haploid sperm: a trace per chromosome)"}


def wu2024(raw: Path) -> dict:
    files = _cell_files(raw / "GSE239969" / "cells", r"^GSM\d+_(?P<cell>p\d+-(?:bdf1|bc)_\d+)"
                        r"(?P<role>\.impute\.pairs|_20kb_1\.clean|_20kb_2\.clean)(?:\.3dg\.txt)?\.gz$")
    files = {c: (f[".impute.pairs"], f["_20kb_1.clean"], f.get("_20kb_2.clean")) for c, f in files.items()
             if ".impute.pairs" in f and "_20kb_1.clean" in f}
    m = _series_matrix([raw / "GSE239969" / "GSE239969_series_matrix.txt.gz"])
    m["cell_id"] = m["title"].str.replace(r"_rna$", "", regex=True)
    m = m.drop_duplicates("cell_id").set_index("cell_id")
    cells = pd.DataFrame({"gsm": m["geo_accession"], "cell_type": m["description"], "age": m.get("age"),
                          "strain": m.get("strain")}).reindex(sorted(files))
    return {"stores": {"wu2024_limca": cells}, "files": files, "assembly": "mm10", "res_3d": 100_000,
            # the count table names cells p014.bc_001, the structures p014-bc_001
            "rna": (raw / "GSE239969" / "GSE239969_LiMCA_olfactory_rna_gene_counts.tsv.gz", "tsv",
                    lambda c: c.replace(".", "-", 1)),
            "source": "Wu et al. 2024, Nat Methods 21:974 (LiMCA: 3-D genome and RNA of the same cells, mouse "
                      "olfactory epithelium; GEO GSE239969): imputed contact pairs, the authors' 20 kb clean "
                      "structures (runs 1 and 2), cell types and RNA counts of each cell"}


def wu2024h(raw: Path) -> dict:
    files = _cell_files(raw / "GSE240114" / "cells", r"^GSM\d+_(?P<cell>GM12878_cell_\d+)"
                        r"(?P<role>\.impute\.pairs|_20Kb_1\.clean|_20Kb_2\.clean)(?:\.3dg\.txt)?\.gz$")
    files = {c: (f[".impute.pairs"], f["_20Kb_1.clean"], f.get("_20Kb_2.clean")) for c, f in files.items()
             if ".impute.pairs" in f and "_20Kb_1.clean" in f}
    m = _series_matrix([raw / "GSE240114" / "GSE240114_series_matrix.txt.gz"])
    m["cell_id"] = m["title"].str.replace(r"_RNA$", "", regex=True)
    m = m.drop_duplicates("cell_id").set_index("cell_id")
    cells = pd.DataFrame({"gsm": m["geo_accession"], "cell_type": m["cell type"]}).reindex(sorted(files))
    return {"stores": {"wu2024_limca_gm12878": cells}, "files": files, "assembly": "hg38", "res_3d": 100_000,
            "source": "Wu et al. 2024, Nat Methods 21:974 (LiMCA, human cell lines; GEO GSE240114): imputed contact "
                      "pairs and the authors' 20 kb clean structures (runs 1 and 2) of each GM12878 cell"}


def _day(label) -> float:
    """'d05' -> 0.5, 'd15' -> 1.5, 'd2' -> 2 (the HiRES X-inactivation days: day 0 to 4, half days written without
    the point)."""
    s = str(label).lstrip("d")
    return float(s[0] + "." + s[1:] if len(s) > 1 else s)


def liu2026(raw: Path) -> dict:
    files = {}
    for gse, ext in (("GSE278310", r"\.3dg\.txt\.gz"), ("GSE310759", r"\.3dg\.gz")):
        got = _cell_files(raw / gse / "cells",
                          rf"^GSM\d+_(?P<cell>d\d+[A-D]\d+)\.(?P<role>pairs\.gz|clean\.20k\.0{ext})$")
        files.update({c: (f["pairs.gz"], next(v for k, v in f.items() if k != "pairs.gz"), None)
                      for c, f in got.items() if "pairs.gz" in f and len(f) == 2})
    meta = pd.concat([pd.read_csv(raw / "GSE278310" / "GSE278310_ESC_metadata.csv.gz"),
                      pd.read_csv(raw / "GSE310759" / "GSE310759_ESC_metadata_update.csv.gz")])
    meta = meta.drop_duplicates("cellname", keep="last").set_index("cellname")
    meta.index.name = "cell_id"
    keep = {"day": "day", "sample": "sample", "pairs_clean3": "n_contacts_published",
            "inter_pairs_clean3": "n_trans_published", "UMIs_gene": "n_counts_rna", "genes_gene": "n_genes_rna",
            "20k": "rmsd_20k", "200k": "rmsd_200k", "yperx": "y_over_x"}
    cells = meta[[k for k in keep if k in meta]].rename(columns=keep).reindex(sorted(files))
    days = sorted(cells["day"].dropna().unique(), key=_day)
    cells["day"] = pd.Categorical(cells["day"], categories=days)
    cells["cell_type"] = cells["day"].astype(str)
    return {"stores": {"liu2026_hires_xci": cells}, "files": files, "assembly": "mm10", "res_3d": 200_000,
            "rna": ([raw / "GSE278310" / "GSE278310_ESC_qc_total_umi.csv.gz",
                     raw / "GSE310759" / "GSE310759_ESC_qc_total_umi_update.csv.gz"], "csv"),
            "source": "Liu et al. 2026, Genomics Proteomics Bioinformatics qzag002 (HiRES of female C57BL/6J x "
                      "CAST/EiJ mESC over the first days of random X inactivation; GEO GSE278310 + GSE310759): "
                      "contact pairs, the authors' 20 kb clean structures, metadata and RNA UMI counts of each cell"}


#: Tan 2023 cells kept with a structure: the authors' RMSD between runs at most this (particle radii)
TAN2023_MAX_RMSD = 1.5


def _tar_texts(path: Path) -> dict:
    """cell -> the words of each small file of a tarball (per-cell info files)."""
    import tarfile
    out = {}
    with tarfile.open(path) as t:
        for mem in t:
            if mem.isfile():
                out[Path(mem.name).name.split(".")[0]] = t.extractfile(mem).read().decode().split()
    return out


def tan2023(raw: Path) -> dict:
    """Tan 2023 cerebellum: the cells with a structure of the sex their X-to-autosome ratio gives (female above 0.7,
    male below 0.6) and an RMSD of at most ``TAN2023_MAX_RMSD``; their structure and imputed pairs of that sex are
    taken out of the tarballs into ``raw/cells`` once."""
    import tarfile
    x2a = {c: float(w[1]) for c, w in _tar_texts(raw / "GSE246785_mouse.x2a.txt.tar.gz").items() if len(w) > 1}
    rows = []
    for sex in ("female", "male"):
        rmsd = _tar_texts(raw / f"GSE246785_mouse.3d_model_{sex}_clean.20k.rmsd.info.tar.gz")
        for cell, w in rmsd.items():
            r = x2a.get(cell, np.nan)
            if w and (r > 0.7 if sex == "female" else r < 0.6):
                rows.append({"cell_id": cell, "sex": sex, "x_to_autosome": r, "rmsd_published": float(w[0])})
    cells = pd.DataFrame(rows).set_index("cell_id").sort_index()
    n_all = len(cells)
    cells = cells[cells["rmsd_published"] <= TAN2023_MAX_RMSD]
    sample = cells.index.str.rsplit("_", n=1).str[0]
    cells.insert(0, "sample", sample.str.removeprefix("dipc-mouse-cerebellum-"))
    cells.insert(1, "age", sample.str.extract(r"-p(\d+)", expand=False).astype(int).map(lambda d: f"P{d}"))
    cells["f1_hybrid"] = sample.str.endswith("-f1hybrid")
    cells["purkinje_enriched"] = sample.str.endswith("-purkinje")
    cells["age"] = pd.Categorical(cells["age"], categories=sorted(cells["age"].unique(), key=lambda a: int(a[1:])))
    cells["cell_type"] = cells["age"]
    out = raw / "cells"
    out.mkdir(exist_ok=True)
    files = {}
    for sex in ("female", "male"):
        want = set(cells.index[cells["sex"] == sex])
        for role, name, ext in (("pairs", f"contacts_{sex}_with_imputed_haplotypes.pairs.gz", ".pairs.gz"),
                                ("3dg", f"3d_model_{sex}_clean.20k", ".3dg.gz")):
            got = {c: out / f"{c}{ext}" for c in want if (out / f"{c}{ext}").exists()}
            if len(got) < len(want):
                with tarfile.open(raw / f"GSE246785_mouse.{name}.tar.gz", "r|gz") as t:
                    for mem in t:
                        cell = Path(mem.name).name.split(".")[0]
                        if mem.isfile() and cell in want and cell not in got and mem.size:
                            data = t.extractfile(mem).read()
                            got[cell] = out / f"{cell}{ext}"
                            got[cell].write_bytes(data if ext == ".pairs.gz" else gzip.compress(data, 1))
            for c, p in got.items():
                files.setdefault(c, {})[role] = p
    files = {c: (f["pairs"], f["3dg"], None) for c, f in files.items() if len(f) == 2}
    log(f"tan2023: {len(cells):,} of {n_all:,} sex-matched structures with RMSD <= {TAN2023_MAX_RMSD}, "
        f"{len(files):,} with both files")
    return {"stores": {"tan2023_cerebellum_3d": cells.reindex(sorted(files))}, "files": files, "assembly": "mm10",
            "res_3d": 100_000,
            "source": "Tan et al. 2023, Science 381:1112 (Dip-C of the mouse cerebellum; GEO GSE246785): the cells of the "
                      "F1-hybrid and Purkinje-enriched samples with the authors' 20 kb clean structure of their sex "
                      f"(X-to-autosome ratio) and an RMSD between runs of at most {TAN2023_MAX_RMSD} particle radii, "
                      "with their imputed haplotype contact pairs"}


STUDIES = {"tan2019_dipc": tan2019, "xu2025_sperm": xu2025, "wu2024_limca": wu2024, "wu2024_limca_human": wu2024h,
           "liu2026_hires_xci": liu2026, "tan2023_cerebellum": tan2023}


# -- workers -----------------------------------------------------------------------------------------------------

_KM = None


def _init(km):
    global _KM
    _KM = km


def _bin_pairs(args):
    ci, path = args
    df = pd.read_csv(path, sep="\t", comment="#", header=None, usecols=[1, 2, 3, 4],
                     names=["chr1", "pos1", "chr2", "pos2"], dtype={"chr1": str, "chr2": str})
    ck, bk = _KM.keys(_KM.chrom_codes(df["chr1"]), df["pos1"].to_numpy(), _KM.chrom_codes(df["chr2"]),
                      df["pos2"].to_numpy())
    return ci, ck, bk, len(df)


def _coarse(path, sizes, res):
    """A 3dg coarse-grained: DataFrame (chrom, copy, bin, x, y, z), copy '' for a haploid structure."""
    df = pd.read_csv(path, sep="\t", header=None, comment="#", names=["name", "pos", "x", "y", "z"],
                     dtype={"name": str})
    parts = df["name"].str.extract(r"^([^()]+)(?:\((mat|pat)\))?$")
    df["chrom"], df["copy"] = parts[0], parts[1].fillna("")
    df = df[df["chrom"].isin(sizes)]
    df["bin"] = df["pos"].to_numpy() // res
    return df.groupby(["chrom", "copy", "bin"], sort=False)[["x", "y", "z"]].mean()


def _cell_structure(args):
    """One cell: spots (chrom, start, end, trace_id, cell_id), xyz, the second run on the same particles (or None),
    its deviation per particle and (rmsd, median deviation)."""
    from chromdata import ChromData
    from uchrom.io.dipc_3dg import replicate_deviation

    cell, main, rep, sizes, res = args
    g = _coarse(main, sizes, res)
    order = {c: i for i, c in enumerate(sizes)}
    keys = g.index.to_frame(index=False)
    idx = np.lexsort((keys["bin"].to_numpy(), keys["copy"].to_numpy(), keys["chrom"].map(order).to_numpy()))
    g = g.iloc[idx]
    keys = keys.iloc[idx].reset_index(drop=True)
    start = keys["bin"].to_numpy(np.int64) * res
    end = np.minimum(start + res, keys["chrom"].map(sizes).to_numpy())
    copy = keys["copy"].to_numpy()
    trace = np.where(copy == "", cell + "_" + keys["chrom"], cell + "_" + keys["chrom"] + "_" + copy)
    spots = pd.DataFrame({"chrom": keys["chrom"].to_numpy(), "start": start, "end": end, "trace_id": trace,
                          "cell_id": cell})
    xyz = g[["x", "y", "z"]].to_numpy(np.float32)
    if rep is None:
        return cell, spots, xyz, None, None, None
    r = _coarse(rep, sizes, res).reindex(g.index)[["x", "y", "z"]].to_numpy(np.float32)
    one = ChromData(xyz.astype(np.float64), spots, layers={"run_2": r.astype(np.float64)})
    per_cell, dev = replicate_deviation(one, ("run_2",), reflection=True)
    stats = (float(per_cell["rmsd_run_2"].iloc[0]), float(per_cell["median_dev_run_2"].iloc[0]))
    return cell, spots, xyz, r, dev.astype(np.float32), stats


# -- steps -------------------------------------------------------------------------------------------------------

def bin_contacts(cells, files, stem: Path, sizes, workers: int):
    binner = ContactBinner(sizes, cells.index, stem.parent / f".{stem.name}_bins", cell_res=RES_MAP,
                           bulk_res=RES_MAP)
    jobs = [(int(binner.cell_index.get_loc(c)), files[c][0]) for c in cells.index]
    t0 = time.time()
    with Pool(workers, initializer=_init, initargs=(binner.keymaker(),)) as pool:
        for k, (ci, ck, bk, n) in enumerate(pool.imap_unordered(_bin_pairs, jobs, chunksize=4)):
            binner.add_keys(ci, ck, bk, n)
            if (k + 1) % 200 == 0:
                log(f"  contacts of {k + 1:,} / {len(jobs):,} cells ({time.time() - t0:.0f} s)")
    binner.close()
    log(f"contacts: {binner.n_in:,} read, {binner.n_kept:,} on kept chromosomes, {len(jobs):,} cells")
    scool = stem.with_name(stem.name + f"_cells_{RES_MAP // 1000}kb.scool")
    binner.write_scool(scool)
    mcool = binner.write_mcool(stem.with_name(stem.name + "_bulk.mcool"),
                               resolutions=(100_000, 500_000, 1_000_000))
    per_cell = pd.Series(binner.per_cell, index=binner.cells)
    binner.cleanup()
    return scool, mcool, per_cell


def read_rna(spec, cells: pd.Index):
    """(cells x genes sparse counts, genes) from the study's count table(s), cells in ``cells`` order; ``spec`` =
    (path(s), "tsv" | "csv"[, the table's cell name -> the cell id])."""
    import scipy.sparse as sp

    paths, kind, rename = (*spec, None)[:3]
    paths = paths if isinstance(paths, list) else [paths]
    parts = []
    for p in paths:
        t = pd.read_csv(p, sep="\t" if kind == "tsv" else ",", index_col=0)
        if len(set(t.index.astype(str)) & set(cells)) > len(set(t.columns.astype(str)) & set(cells)):
            t = t.T                                     # cells as rows -> genes as rows
        t.columns = t.columns.astype(str)
        if rename is not None:
            t.columns = t.columns.map(rename)
        parts.append(t)
    t = pd.concat(parts, axis=1).fillna(0)
    t = t.loc[:, ~t.columns.duplicated(keep="last")]
    found = [c for c in cells if c in t.columns]
    t = t.reindex(columns=list(cells)).fillna(0)
    return sp.csr_matrix(t.to_numpy(np.float32).T), pd.DataFrame(index=pd.Index(t.index.astype(str), name="gene")), \
        len(found)


def build_store(name: str, cells: pd.DataFrame, study: dict, out_dir: Path, workers: int) -> Path:
    from uchrom import ChromData
    from uchrom.emb import embed_cells

    files = study["files"]
    assembly = study["assembly"][name] if isinstance(study["assembly"], dict) else study["assembly"]
    keep = HG38 if assembly.startswith("hg") else MM10
    sizes = chromsizes(files[cells.index[0]][0], assembly, keep=keep)
    res = study["res_3d"]
    stem = out_dir / name
    log(f"{name}: {len(cells):,} cells, {assembly}, {len(sizes)} chromosomes, structures at {res // 1000} kb")

    scool, mcool, per_cell = bin_contacts(cells, files, stem, sizes, workers)
    log(f"balanced {balance_mcool(mcool)} of {mcool.name}")
    cells = cells.copy()
    cells["n_contacts"] = per_cell.reindex(cells.index).fillna(0).astype(np.int64).to_numpy()

    meta = ChromData(np.zeros((0, 3)), empty_spots(), cells=cells)
    uns = {"genome_assembly": assembly, "source": study["source"], "xyz_unit": "particle radius",
           "coordinate_status": f"the authors' 20 kb structures (hickit / Dip-C .3dg; the first run of each cell) "
                                f"coarse-grained to {res // 1000} kb by averaging the particles of each bin of "
                                f"each copy"}
    if "rna" in study:
        counts, genes, found = read_rna(study["rna"], cells.index)
        log(f"RNA: {found:,} of {len(cells):,} cells in the counts, {counts.shape[1]:,} genes")
        if not found:
            raise ValueError(f"{name}: no cell of the RNA counts matches a cell id")
        uns["linked_anndata"] = rna_h5ad(counts, cells.index, genes, stem.with_name(stem.name + "_rna.h5ad"),
                                         description="RNA counts of every gene as deposited, one row per cell of "
                                                     "cells (zeros for cells without RNA)")
        z, hvg = hvg_zscores(counts)
        embed_cells(meta, source="rna", matrix=z, normalization="none", methods=("pca", "umap"), n_pcs=30,
                    features=f"the {len(hvg):,} most variable genes (log1p CP10k, z-score, clipped at 10)")
    meta.link_cool(mcool.name, key="bulk", label=f"All {len(cells):,} cells (merged)")
    meta.link_scool(scool.name, key="per_cell", label=f"Per cell ({RES_MAP // 1000} kb)", cell_name="cell_id",
                    genome_assembly=assembly, bin_size=RES_MAP)
    uns = {**meta.uns, **uns}

    out = stem.with_name(stem.name + ".chromdata.zarr")
    has_rep = any(files[c][2] is not None for c in cells.index)
    stats, traces = {}, []
    t0 = time.time()
    with Pool(workers) as pool, ChromData.writer(out, bins=bin_table(sizes, res), coord_dtype="float32",
                                                  memory_budget="8GB") as w:
        jobs = [(c, files[c][1], files[c][2], sizes, res) for c in cells.index]
        batch = []
        for k, item in enumerate(pool.imap(_cell_structure, jobs, chunksize=4)):
            cell, spots, xyz, rep, dev, st = item
            batch.append(item)
            if st is not None:
                stats[cell] = st
            t = spots.drop_duplicates("trace_id")[["trace_id", "cell_id", "chrom"]].copy()
            t["copy"] = t["trace_id"].str.extract(r"_(mat|pat)$")[0].fillna("")
            traces.append(t)
            if len(batch) == 100 or k == len(jobs) - 1:
                kw = {}
                if has_rep:
                    kw["layers"] = {"run_2": np.concatenate([b[3] if b[3] is not None else
                                                              np.full_like(b[2], np.nan) for b in batch])}
                    kw["spot_tracks"] = pd.DataFrame({"run_deviation": np.concatenate(
                        [b[4] if b[4] is not None else np.full(len(b[2]), np.nan, np.float32) for b in batch])})
                w.append(coords=np.concatenate([b[2] for b in batch]),
                         spots=pd.concat([b[1] for b in batch], ignore_index=True), **kw)
                batch = []
                log(f"  structures of {k + 1:,} / {len(jobs):,} cells ({time.time() - t0:.0f} s)")
        cells_out = meta.cells.copy()
        if has_rep:
            st = pd.DataFrame(stats, index=["rmsd_run_2", "median_dev_run_2"]).T
            cells_out = cells_out.join(st)
            uns["derived_spot_tracks"] = ["run_deviation"]
            uns["coordinate_status"] += ("; layer run_2: the cell's second run on the same particles, its deviation "
                                         "after superposition per cell (rmsd_run_2, median_dev_run_2) and per "
                                         "particle (spot_tracks run_deviation)")
            med = st["rmsd_run_2"].median()
            log(f"run 1 vs run 2: RMSD median {med:.2f} particle radii over {len(st):,} cells")
        traces = pd.concat(traces, ignore_index=True).set_index("trace_id")
        w.finish(cells=cells_out, cellm=dict(meta.cellm), traces=traces, uns=uns)
    log(f"wrote {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study", choices=sorted(STUDIES))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--test", type=int, default=0, help="only the first N cells of each store, into <store>_test")
    args = ap.parse_args()

    from uchrom.datasets import data_dir

    out_dir = data_dir() / args.study
    study = STUDIES[args.study](out_dir / "raw")
    for name, cells in study["stores"].items():
        cells = cells[cells.index.isin(list(study["files"]))]
        if args.test:
            cells = cells.iloc[:args.test]
            name = f"{name}_test"
        cells.index.name = "cell_id"
        build_store(name, cells, study, out_dir, args.workers)


if __name__ == "__main__":
    main()
