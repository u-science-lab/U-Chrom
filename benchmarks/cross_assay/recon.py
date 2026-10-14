"""Cross-assay comparison in distance space: single-cell Hi-C reconstructed (diploid where the contacts are phased,
haploid otherwise), stored as ChromData and summarised by the same call as the imaging data,
``uchrom.fea.separation_profile``.  The reconstruction method (``--method``): ``ember`` (EMber, frozen; the run of
2026-10-11) or ``nucdyn`` (the NucDynamics 2017 protocol of the same engine, phased contacts as one chain per
chromosome copy and the contacts with an unphased end as ambiguous restraints; the run of 2026-10-12, used by the
paper).  Both through ``benchmarks/screcon/run_diploid.py``.

Datasets (``--dataset``): ``tan2021`` (Dip-C of the adult cortex, Tan et al. 2021: phased CAST x B6 contacts,
the calibration) and ``hires_brain`` (HiRES adult brain, Liu et al. 2023: 63 % of the contact ends phased; cells
of ``data/hires_brain_cells.tsv``, the authors' 399 from the atlas store).  Variants:

* ``dip``        diploid on all contacts (the reference reconstruction);
* ``hap``        haploid on the same contacts (``ploidy="haploid"``: the two homologs one chain), the only
                 option for the inbred datasets (GAGE-seq, Droplet / Paired Hi-C, scHiCAR, dscHi-C);
* ``hap_c<N>``   haploid on a random subset of the contacts with about N cis contacts (150k ~ GAGE-seq,
                 45k ~ dscHi-C, 20k ~ Droplet Hi-C), the depth at which the haploid structures stop agreeing;
* ``dipc``       the authors' published structures (Dip-C ``20k.1.clean.3dg``; HiRES hickit ``20k.3dg``) averaged
                 into the same 1-Mb grid.

All at 1 Mb (particles covering (k - 1, k] Mb, so separations are whole Mb as in the 1-Mb contact maps),
2 models (model 0 the cell's structure, model 1 a replicate, layer ``model1``), seed 1, GPU.

Stages (``--stages``):

* ``run``      (GPU; ``uchrom_recon``, the frozen engine) per cell of this task's share (``--task`` / ``--n-tasks``,
               a Slurm array): ``<out>/<variant>/<cell>.npz`` via ``benchmarks/screcon/run_diploid.py``;
* ``collect``  npz / 3dg -> ``<out>/<variant>.chromdata.zarr`` (one trace per cell and chromosome copy);
* ``loci``     where ExN and Oligo differ: the detrended difference of the median distance of every cis pair of
               the imaging loci (Liu 2025, Takei 2021), imaging against each reconstruction, split-half ceilings,
               shuffled labels -> ``--results``/loci_<dataset>.json;
* ``loci_all`` every pair of the six classes, imaging against the dataset's first variant, imaging split-half
               ceilings -> ``--results``/loci_all_<dataset>.json;
* ``contacts`` the baseline without a 3D model: the same cells' contacts (each class's mean per-cell contact
               frequency at 1 Mb) on the imaging loci, against imaging and against each reconstruction on the
               same pairs, split-half ceilings -> ``--results``/contacts_<dataset>.json (after stage loci);
* ``analyze``  ``separation_profile`` on every variant -> per-cell tables, the class contrasts, scaling exponents,
               the agreement with ``dip``, next to the imaging datasets of ``cross_assay.py`` (``--xa-work``,
               ``--xa-results``) -> ``--results``/recon_<dataset>.json.

    python benchmarks/cross_assay/recon.py --dataset tan2021 --data-dir $UCHROM_DATA/tan2021_cortex/cells --out DIR \
        --stages run --task 0 --n-tasks 8
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SCRECON = HERE.parent / "screcon"
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SCRECON))

RES = 1_000_000
N_MODELS, SEED = 2, 1
DEPTHS = (150_000, 45_000, 20_000)                     # cis contacts: ~GAGE-seq, ~dscHi-C, ~Droplet Hi-C
VARIANTS = ["dip", "hap"] + [f"hap_c{d // 1000}k" for d in DEPTHS]
METHOD = "ember"                                       # set by --method
METHODS = {"ember": "EMber, frozen (engine build dipfrozen, tag ember-diploid-frozen)",
           "nucdyn": "NucDynamics 2017 protocol, diploid by ambiguous restraints (engine build dipfrozen)"}
TAN_CELLS = HERE.parent / "screcon" / "data" / "tan2021_adult_cortex_cells.tsv"
HIRES_CELLS = HERE / "data" / "hires_brain_cells.tsv"


def dataset_cells(dataset: str, data_dir: Path) -> pd.DataFrame:
    """The labelled cells (classes of pilot.TAN / pilot.DATASETS["hires_brain"]) with their pairs and published
    structures: Tan 2021 ``<dir>/<cell>/<cell>.contacts.pairs.txt.gz`` + ``.20k.1.clean.3dg.txt.gz``; HiRES
    ``<dir>/GSM*_<cell>.pairs.gz`` + ``.20k.3dg.txt.gz`` (``hires2023_brain``)."""
    import pilot as P

    if dataset == "tan2021":
        t = pd.read_csv(TAN_CELLS, sep="\t")
        t["cls"] = t["cell_type"].map(P.TAN["classes"])
        t["pairs"] = [str(data_dir / n / f"{n}.contacts.pairs.txt.gz") for n in t["name"]]
        t["dipc"] = [str(data_dir / n / f"{n}.20k.1.clean.3dg.txt.gz") for n in t["name"]]
    elif dataset == "hires_brain":
        t = pd.read_csv(HIRES_CELLS, sep="\t")
        t["cls"] = t["cell_type"].map(P.DATASETS["hires_brain"]["classes"])
        files = {p.name.split("_", 1)[1]: p for p in Path(data_dir).glob("GSM*_Val*")}
        t["pairs"] = [str(files.get(f"{n}.pairs.gz", "")) for n in t["name"]]
        t["dipc"] = [str(files.get(f"{n}.20k.3dg.txt.gz", "")) for n in t["name"]]
    else:                                      # exported from the per-cell 1-Mb maps (stage maps)
        t = pd.read_csv(Path(data_dir) / "cells.tsv", sep="\t", keep_default_na=False)
        t["dipc"] = ""
    t = t[t.cls.notna() & (t.cls != "") & (t["pairs"] != "")].copy()
    return t.set_index("name")


# ------------------------------------------------------------------------------------------------- run

def _subsample(src: str, dst: Path, target_cis: int, cell: str) -> dict:
    """A random subset of the contacts with about ``target_cis`` cis contacts: header and lines unchanged.  The
    columns come from the ``#columns:`` line, with or without a space after the colon (HiRES has none, which
    screcon's ``read_phased`` would misread)."""
    import gzip
    import re

    header, lines, cols = [], [], None
    with gzip.open(src, "rt") as fh:
        for line in fh:
            if line.startswith("#"):
                header.append(line)
                m = re.match(r"^#columns:\s*(.*)$", line.rstrip("\n"))
                if m:
                    cols = m.group(1).split()
            elif line.strip():
                lines.append(line)
    cols = cols or ["readID", "chr1", "pos1", "chr2", "pos2", "strand1", "strand2"]
    i1, i2 = cols.index("chr1"), cols.index("chr2")
    cis = np.array([(lambda r: r[i1] == r[i2])(ln.split("\t") if "\t" in ln else ln.split()) for ln in lines])
    n_cis = int(cis.sum())
    p = min(1.0, target_cis / max(n_cis, 1))
    rng = np.random.default_rng([SEED, zlib.crc32(cell.encode())])
    keep = np.sort(rng.choice(len(lines), int(round(p * len(lines))), replace=False))
    dst.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(dst, "wt") as fh:
        fh.writelines(header)
        fh.writelines(lines[i] for i in keep)
    return {"n_contacts": len(lines), "n_cis": n_cis, "kept": int(len(keep)), "kept_cis": int(cis[keep].sum()),
            "fraction": p}


def stage_run(out: Path, cells: pd.DataFrame, task: int, n_tasks: int, variants, device: str,
              method: str = "ember") -> dict:
    """Each reconstruction in its own process (``run_diploid.py``, as the pre-registered runs): within one process
    the GPU engine stops finding an adapter after about 26 runs (wgpu: "no GPU adapter", job 47414760)."""
    import subprocess

    mine = cells.iloc[task::n_tasks]
    log = {"task": task, "n_tasks": n_tasks, "method": method, "cells": len(mine), "runs": 0, "seconds": 0.0,
           "failed": []}
    t_all = time.perf_counter()
    for cell, r in mine.iterrows():
        for v in variants:
            dest = out / v / f"{cell}.npz"
            if dest.exists():
                continue
            src = r["pairs"]
            if v.startswith("hap_c"):
                tab = out / "tables" / f"{cell}.{v}.pairs.gz"
                if not tab.exists():
                    info = _subsample(src, tab, int(v[5:-1]) * 1000, cell)
                    (out / "tables" / f"{cell}.{v}.json").write_text(json.dumps(info))
                src = str(tab)
            argv = ["--method", method, "--contacts", src, "--res", str(RES), "--device", device,
                    "--n-models", str(N_MODELS), "--seed", str(SEED), "--label", f"{method}_{v}", "--out", str(dest)]
            if v != "dip":
                argv += ["--ploidy", "haploid"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(str(dest)[:-4] + ".log", "w") as fh:
                rc = subprocess.run([sys.executable, str(SCRECON / "run_diploid.py"), *argv], stdout=fh,
                                    stderr=subprocess.STDOUT).returncode
            if rc == 0 and dest.exists():
                log["runs"] += 1
            else:                                         # recorded, the other cells go on
                tail = Path(str(dest)[:-4] + ".log").read_text().strip().splitlines()[-1:] or [""]
                log["failed"].append(f"{cell} {v}: exit {rc}: {tail[0]}"[:300])
                print(f"!!! {cell} {v}: exit {rc}: {tail[0][:200]}", flush=True)
    log["seconds"] = round(time.perf_counter() - t_all, 1)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    (out / "logs" / f"run_task{task}.json").write_text(json.dumps(log, indent=1))
    print(f"[run] {log}", flush=True)
    return log


# ------------------------------------------------------------------------------------------------- maps

MIN_CIS = 15_000                                       # cis contacts of a cell reconstructed from its 1-Mb map
CAP = 300                                              # cells per class at most (atlas datasets)
PAIRS_HEADER = "## pairs format v1.0\n#columns: readID chr1 pos1 chr2 pos2 strand1 strand2 phase0 phase1\n"


def _map_dataset(dataset: str, xa_work: Path):
    """(ChromData with the per-cell maps linked, class spec, name of the cross_assay tables)."""
    import pilot as P

    if dataset == "tan2021_maps":                      # the calibration: Tan's pairs binned at 1 Mb (cross_assay tan)
        from chromdata import ChromData

        meta = pd.read_csv(TAN_CELLS, sep="\t")
        cells = pd.DataFrame({"cell_type": meta["cell_type"].to_numpy()},
                             index=pd.Index(meta["name"].astype(str), name="cell_id"))
        no_spots = pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                                 "end": pd.Series(dtype=np.int64), "trace_id": pd.Series(dtype=str),
                                 "cell_id": pd.Series(dtype=str)})
        cd = ChromData(np.zeros((0, 3)), no_spots, cells=cells)
        cd.link_scool(str(xa_work / "tan2021_cortex_1mb.scool"), key="per_cell", cell_name="cell_id", bin_size=RES)
        return cd, {"column": "cell_type", "classes": P.TAN["classes"]}, "tan2021_cortex"
    import uchrom.datasets as ds

    P._pandas_compat()
    return ds.load(dataset), P.DATASETS[dataset], dataset


def stage_maps(out: Path, dataset: str, xa_work: Path, seed: int) -> dict:
    """Every selected cell's 1-Mb map (cis and trans) as a pairs file ``<out>/pairs/<cell>.pairs.gz``: one line per
    contact, both ends drawn uniformly in their bin ((k Mb, k + 1 Mb], seeded per cell) -- placed at the bin
    midpoints, a pixel's contacts would be one position, which the isolated-contact filter (pos_error 100 bp) does
    not let support each other.  Cells: the classes of the dataset with >= MIN_CIS cis contacts (the cross_assay
    tables), at most CAP per class (atlas datasets; random, seeded); ``<out>/cells.tsv``."""
    import gzip

    from uchrom.fea.pseudobulk_maps import _Grid, _source_of
    from uchrom.fea.separation import _per_cell_map_keys

    t0 = time.perf_counter()
    cd, spec, tname = _map_dataset(dataset, xa_work)
    tab = pd.read_parquet(xa_work / f"cells_{tname}.parquet")
    tab["cls"] = tab[spec["column"]].astype(str).map(spec["classes"])
    tab = tab[tab.cls.notna() & (tab["n_cis"] >= MIN_CIS)]
    rng = np.random.default_rng(seed)
    if dataset != "tan2021_maps":
        tab = pd.concat([g if len(g) <= CAP else g.loc[rng.choice(g.index.to_numpy(), CAP, replace=False)]
                         for _, g in tab.groupby("cls")])
    want = set(tab.index.astype(str))
    pdir = out / "pairs"
    pdir.mkdir(parents=True, exist_ok=True)
    rows, stats = [], {}
    for key in _per_cell_map_keys(cd):
        source, desc, _ = _source_of(cd, key, 2_000_000)
        names = np.asarray([str(c) for c in source.cells])
        idx = np.flatnonzero(np.isin(names, list(want)))
        if not len(idx):
            continue
        base = int(source.base)
        grid = _Grid(source.chroms, source.sizes, base, base)
        acc: dict = {}

        def add(cell, ca, b1, cb, b2, c):
            order = np.argsort(cell, kind="stable")
            cell, ca, b1, cb, b2, c = (x[order] for x in (cell, ca, b1, cb, b2, c))
            cuts = np.flatnonzero(np.diff(cell)) + 1
            for lo, hi in zip(np.r_[0, cuts], np.r_[cuts, len(cell)]):
                acc.setdefault(int(cell[lo]), []).append((ca[lo:hi], b1[lo:hi], cb[lo:hi], b2[lo:hi], c[lo:hi]))

        if source.sequential:                           # embedded: cis partitions (local bins) and trans (global)
            for task in source.tasks(True, idx):
                p, cell, b1, b2, c = source.read(task)
                b1, b2 = b1.astype(np.int64), b2.astype(np.int64)
                if p >= 0:
                    ca = cb = np.full(len(b1), p, np.int64)
                else:
                    ca, cb = grid.chrom_of_fine[b1], grid.chrom_of_fine[b2]
                    b1, b2 = b1 - grid.first_fine[ca], b2 - grid.first_fine[cb]
                add(cell, ca, b1, cb, b2, c.astype(np.int64))
        else:                                           # .scool: genome-wide bins
            for cell, b1, b2, c in source.iter_cells(idx):
                ca, cb = grid.chrom_of_fine[b1], grid.chrom_of_fine[b2]
                add(cell, ca, b1 - grid.first_fine[ca], cb, b2 - grid.first_fine[cb], c.astype(np.int64))
        chroms = np.asarray(source.chroms)
        for i, parts in acc.items():
            name = names[i]
            ca, b1, cb, b2, c = (np.concatenate([p[k] for p in parts]) for k in range(5))
            r = np.random.default_rng([seed, zlib.crc32(name.encode())])
            n, n_cis = int(c.sum()), int(c[ca == cb].sum())
            ca, b1, cb, b2 = (np.repeat(x, c) for x in (ca, b1, cb, b2))
            p1 = b1 * base + r.integers(1, base + 1, n)
            p2 = b2 * base + r.integers(1, base + 1, n)
            dest = pdir / f"{name}.pairs.gz"
            with gzip.open(dest, "wt", compresslevel=3) as fh:
                fh.write(PAIRS_HEADER)
                pd.DataFrame({"r": ".", "c1": chroms[ca], "p1": p1, "c2": chroms[cb], "p2": p2, "s1": "+", "s2": "+",
                              "h1": ".", "h2": "."}).to_csv(fh, sep="\t", header=False, index=False)
            rows.append({"name": name, "cell_type": tab.loc[name, spec["column"]], "cls": tab.loc[name, "cls"],
                         "pairs": str(dest), "n_contacts": n, "n_cis": n_cis, "map": key})
        stats[key] = {"source": desc, "n_cells": int(len(acc)), "resolution": base}
    cells = pd.DataFrame(rows)
    cells.to_csv(out / "cells.tsv", sep="\t", index=False)
    log = {"dataset": dataset, "n_cells": int(len(cells)), "by_class": cells["cls"].value_counts().to_dict(),
           "min_cis": MIN_CIS, "cap": CAP if dataset != "tan2021_maps" else None, "maps": stats,
           "seconds": round(time.perf_counter() - t0, 1)}
    (out / "logs").mkdir(parents=True, exist_ok=True)
    (out / "logs" / "maps.json").write_text(json.dumps(log, indent=1, default=str))
    print(f"[maps] {log}", flush=True)
    return log


# ------------------------------------------------------------------------------------------------- collect

def _spots(cell: str, chrom_copy, start, end) -> pd.DataFrame:
    from diploid import split_copy

    base = [split_copy(c)[0] for c in chrom_copy]
    return pd.DataFrame({"chrom": base, "start": np.asarray(start, np.int64), "end": np.asarray(end, np.int64),
                         "trace_id": [f"{cell}:{c}" for c in chrom_copy], "cell_id": cell})


def _from_npz(path: Path, cell: str):
    z = np.load(path)
    pos = z["pos"].astype(np.int64)
    X = np.asarray(z["coords"], np.float64)
    s = _spots(cell, z["chrom"].astype(str), np.maximum(pos - RES, 0), pos)
    return s, X[0], (X[1] if len(X) > 1 else None)


def _from_3dg(path: str, cell: str):
    """The published 20-kb Dip-C structure averaged into 1-Mb bins per copy ((k - 1, k] Mb, as the models)."""
    from matched_data import read_dipc_3dg

    d = read_dipc_3dg(path)
    d["bin"] = (d["start"] + 10_000 - 1) // RES                 # 20-kb particle centre -> 1-Mb bin (end convention)
    g = d.groupby(["chrom", "hap", "bin"], sort=True)[["x", "y", "z"]].mean().reset_index()
    copy = np.where(g["hap"] == "mat", "(0)", "(1)")
    chrom_copy = (g["chrom"] + copy).to_numpy()
    s = _spots(cell, chrom_copy, g["bin"].to_numpy() * RES, (g["bin"].to_numpy() + 1) * RES)
    return s, g[["x", "y", "z"]].to_numpy(np.float64), None


def stage_collect(out: Path, cells: pd.DataFrame, variants) -> dict:
    from chromdata import ChromData

    log = {}
    for v in list(variants) + ["dipc"]:
        parts, X, X1, missing = [], [], [], 0
        for cell, r in cells.iterrows():
            try:
                s, x, x1 = _from_3dg(r["dipc"], cell) if v == "dipc" else _from_npz(out / v / f"{cell}.npz", cell)
            except FileNotFoundError:
                missing += 1
                continue
            parts.append(s); X.append(x); X1.append(x1 if x1 is not None else np.full_like(x, np.nan))
        if not parts:
            log[v] = "nothing"
            continue
        spots = pd.concat(parts, ignore_index=True)
        tab = cells[["cell_type", "cls"]].copy()
        tab.index = tab.index.astype(str)
        tab.index.name = "cell_id"
        cd = ChromData(np.concatenate(X), spots, cells=tab, uns={"xyz_unit": "model" if v != "dipc" else "dip-c",
                                                                  "reconstruction": v, "resolution": RES})
        if v != "dipc":
            cd.layers["model1"] = np.concatenate(X1)
        cd.write(out / f"{v}.chromdata.zarr")
        log[v] = {"n_cells": len(parts), "missing": missing, "n_spots": int(cd.n_spots)}
        print(f"[collect] {v}: {log[v]}", flush=True)
    return log


# ------------------------------------------------------------------------------------------------- analyze

def _exponent(prof: pd.DataFrame, lo=2, hi=50) -> float:
    """Slope of log median distance on log separation over [lo, hi] Mb (profile columns = 1-Mb offsets)."""
    k = np.arange(lo, hi + 1)
    y = np.log(prof.iloc[:, k].median(skipna=True).to_numpy())
    ok = np.isfinite(y)
    return float(np.polyfit(np.log(k[ok]), y[ok], 1)[0])


def stage_analyze(out: Path, results: Path, xa_work: Path, xa_results: Path, variants, seed: int, n_boot: int,
                  dataset: str = "tan2021"):
    import cross_assay as X
    import pilot as P
    from chromdata import ChromData
    from scipy.stats import spearmanr
    from uchrom.fea import separation_profile

    rng = np.random.default_rng(seed)
    tabs, profs = {}, {}
    for v in list(variants) + ["dipc"]:
        p = out / f"{v}.chromdata.zarr"
        if not p.exists():
            continue
        cd = ChromData.read(p)
        t = separation_profile(cd, source="coords", params=X.params(), key_added=None)
        t["cls"] = cd.cells["cls"].reindex(t.index).to_numpy()
        profs[v] = t.attrs["profile"]
        t.attrs = {}
        t.to_parquet(out / f"cells_{v}.parquet")
        tabs[v] = t
    res = {"variants": {}, "imaging": {}}
    ref = tabs.get("dip")
    for v, t in tabs.items():
        u = t[(t.n_pairs_short >= X.MIN_SHORT_PAIRS) & (t.n_pairs_long >= X.MIN_LONG_PAIRS)].copy()
        u["dist_ratio"] = u["log2_short_long"]
        r = {"n_cells": int(len(u)), "dist_ratio": P.summarize(u, "dist_ratio", rng, n_boot=n_boot),
             "exn_minus_oligo_cliff": X._cliff_ci(u.loc[u.cls == "ExN", "dist_ratio"],
                                                  u.loc[u.cls == "Oligo", "dist_ratio"], rng, min(n_boot, 1000)),
             "astro_minus_oligo_cliff": X._cliff_ci(u.loc[u.cls == "Astro", "dist_ratio"],
                                                    u.loc[u.cls == "Oligo", "dist_ratio"], rng, min(n_boot, 1000)),
             "exponent_2_50mb": {c: _exponent(profs[v].loc[u.index[u.cls == c]]) for c in P.CLASSES
                                 if (u.cls == c).sum() >= 10}}
        if ref is not None and v != "dip":
            j = u.index.intersection(ref.index)
            a, b = u.loc[j, "log2_short_long"], ref.loc[j, "log2_short_long"]
            ok = a.notna() & b.notna()
            r["vs_dip"] = {"n": int(ok.sum()), "spearman": float(spearmanr(a[ok], b[ok]).statistic),
                           "median_diff": float((a[ok] - b[ok]).median())}
        res["variants"][v] = r
        print(f"[analyze] {v}: ExN-Oligo {r['dist_ratio'].get('contrast', {}).get('diff')}", flush=True)
    R = json.loads((xa_results / "cross_assay.json").read_text())["results"]["datasets"]
    for name in ("liu2025_mop", "takei2021_brain_labels", "tan2021_dipc_rep1"):
        if name in R:
            lab, use = X._imaging_frame(xa_work, name)
            r = {"dist_ratio": R[name]["dist_ratio"]}
            z = xa_work / f"imaging_profile_{name}.npz"
            if z.exists():
                zz = np.load(z, allow_pickle=True)
                pr = pd.DataFrame(zz["profile"], index=pd.Index(zz["cells"].astype(str)))
                r["exponent_2_50mb"] = {c: _exponent(pr.loc[use.index[use.cls == c]]) for c in P.CLASSES
                                        if (use.cls == c).sum() >= 10}
            res["imaging"][name] = r
    from _record import save

    path = save(results / f"recon_{dataset}.json", res, script="benchmarks/cross_assay/recon.py",
                datasets=[{"tan2021": "tan2021_cortex", "hires_brain": "hires2023_brain", "tan2021_maps": "tan2021_cortex"}.get(dataset, dataset), "liu2025_mop",
                          "takei2021_brain"],
                params={"dataset": dataset, "res": RES, "n_models": N_MODELS, "seed": SEED, "depths_cis": list(DEPTHS),
                        "variants": list(tabs), "method": METHOD, "engine": METHODS[METHOD]})
    print(json.dumps({v: {"exn_oligo": r["dist_ratio"].get("contrast", {}).get("diff"),
                          "vs_dip": r.get("vs_dip")} for v, r in res["variants"].items()}, indent=1), flush=True)
    return {"results": str(path)}


# ------------------------------------------------------------------------------------------------- loci (S2)

SEP_BANDS = np.geomspace(1e6, 2e8, 25)                 # separation bands of the detrending (bp)


def _class_maps(cd, cells_of: dict, chroms) -> dict:
    """{class: {chrom: DistanceMap}}: the median distance of every pair of the chromosome's observed bins over the
    traces of the class's cells (``uchrom.fea.distance_map``)."""
    from uchrom.fea import distance_map

    out = {}
    for c, ids in cells_of.items():
        sub = cd.get_cells(list(ids), columns="coords")
        have = set(sub.bins["chrom"].astype(str)[np.unique(sub.spots["bin_id"].to_numpy())])
        out[c] = {ch: distance_map(sub, ch, stat="median") for ch in chroms if ch in have}
    return out


def _panel_values(maps: dict, panel: pd.DataFrame, a: str, b: str) -> pd.DataFrame:
    """log(median d of class a) - log(class b) for every cis pair of panel loci; a locus takes the map row whose
    bin holds its midpoint (start < mid <= end)."""
    rows = []
    for ch, loci in panel.groupby("chrom", sort=False):
        if ch not in maps[a] or ch not in maps[b]:
            continue
        mid = ((loci["start"].to_numpy() + loci["end"].to_numpy()) // 2).astype(np.int64)
        idx = {}
        for c in (a, b):
            bins = maps[c][ch].bins
            s, e = bins["start"].to_numpy(), bins["end"].to_numpy()
            k = np.searchsorted(e, mid, side="left")            # first bin with end >= mid
            ok = (k < len(e)) & (s[np.minimum(k, len(e) - 1)] < mid)
            idx[c] = np.where(ok, k, -1)
        i, j = np.triu_indices(len(loci), 1)
        ia, ja, ib, jb = idx[a][i], idx[a][j], idx[b][i], idx[b][j]
        ok = (ia >= 0) & (ja >= 0) & (ib >= 0) & (jb >= 0) & (ia != ja)
        ma, mb = maps[a][ch].matrix, maps[b][ch].matrix
        with np.errstate(divide="ignore", invalid="ignore"):
            d = np.log(ma[ia[ok], ja[ok]]) - np.log(mb[ib[ok], jb[ok]])
        rows.append(pd.DataFrame({"chrom": ch, "i": loci.index.to_numpy()[i[ok]], "j": loci.index.to_numpy()[j[ok]],
                                  "sep": np.abs(mid[j[ok]] - mid[i[ok]]), "diff": d}))
    t = pd.concat(rows, ignore_index=True)
    t = t[np.isfinite(t["diff"])]
    band = np.searchsorted(SEP_BANDS, t["sep"].to_numpy())
    t["resid"] = t["diff"] - t.groupby(band)["diff"].transform("median")      # the locus-specific part
    # stricter: per chromosome and band (no chromosome-wide offsets), then without each locus's additive effect
    t["chromband"] = t["diff"] - t.groupby([t["chrom"].to_numpy(), band])["diff"].transform("median")
    r = t["chromband"].to_numpy().copy()
    key_i, key_j = t["chrom"] + ":" + t["i"].astype(str), t["chrom"] + ":" + t["j"].astype(str)
    for _ in range(10):
        eff = pd.concat([pd.Series(r, index=key_i.to_numpy()), pd.Series(r, index=key_j.to_numpy())]).groupby(level=0).mean()
        r = r - (eff.reindex(key_i).to_numpy() + eff.reindex(key_j).to_numpy()) / 2
    t["pair"] = r
    return t.set_index(["chrom", "i", "j"])


def _corrs(x: pd.DataFrame, y: pd.DataFrame) -> dict:
    return {c: _corr(x, y, c) for c in ("diff", "resid", "chromband", "pair")}


def _corr(x: pd.DataFrame, y: pd.DataFrame, col: str) -> dict:
    from scipy.stats import spearmanr

    j = x.index.intersection(y.index)
    return {"n_pairs": int(len(j)), "spearman": float(spearmanr(x.loc[j, col], y.loc[j, col]).statistic)}


def _halves(ids, rng):
    ids = rng.permutation(np.asarray(list(ids)))
    return ids[: len(ids) // 2], ids[len(ids) // 2:]


def stage_loci(out: Path, results: Path, xa_sets: Path, liu_path: Path, variants, dataset: str, seed: int,
               a: str = "ExN", b: str = "Oligo") -> dict:
    """Where the classes differ: the a - b difference of the median distance of every cis pair of the imaging loci
    (Liu 2025, Takei 2021), detrended by separation, in imaging and in each reconstruction, and how they agree
    (Spearman over pairs), against split-half ceilings (imaging, reconstruction ``dip``)."""
    import cross_assay as X
    from _record import save
    from chromdata import ChromData
    from matched_data import load_set

    rng = np.random.default_rng(seed)
    autos = [f"chr{k}" for k in range(1, 20)]
    liu = ChromData.read(str(liu_path), columns="coords")
    lc = liu.cells.copy()
    lc.index = lc.index.astype(str)
    lcls = X.liu_classes(lc)
    traced = set(liu.spots["cell_id"].astype(str).unique())
    liu_cells = {c: [i for i in lcls.index[lcls == c] if i in traced] for c in (a, b)}
    tk = X.set_to_chromdata(load_set(xa_sets / "takei2021_brain_labels.npz"))
    tcls = tk.cells["cell_type"].map(__import__("pilot").TAKEI)
    tcls.index = tcls.index.astype(str)
    tk_cells = {c: list(tcls.index[tcls == c]) for c in (a, b)}
    panels = {"liu2025": liu.bins[liu.bins["chrom"].astype(str).isin(autos)][["chrom", "start", "end"]].astype(
                  {"chrom": str}),
              "takei2021": tk.bins[tk.bins["chrom"].astype(str).isin(autos)][["chrom", "start", "end"]].astype(
                  {"chrom": str})}
    imaging = {"liu2025": (liu, liu_cells), "takei2021": (tk, tk_cells)}
    ref, res = {}, {"contrast": f"{a} - {b}", "panels": {k: int(len(v)) for k, v in panels.items()},
                    "imaging_cells": {k: {c: len(v) for c, v in cells.items()} for k, (_, cells) in imaging.items()},
                    "ceiling": {}, "variants": {}}
    for name, (cd, cells) in imaging.items():
        ref[name] = _panel_values(_class_maps(cd, cells, autos), panels[name], a, b)
        h = {c: _halves(v, rng) for c, v in cells.items()}
        A = _panel_values(_class_maps(cd, {c: h[c][0] for c in cells}, autos), panels[name], a, b)
        B = _panel_values(_class_maps(cd, {c: h[c][1] for c in cells}, autos), panels[name], a, b)
        res["ceiling"][name] = _corrs(A, B)
        ref[name].to_parquet(out / f"loci_{name}_imaging.parquet")
        print(f"[loci] {name}: {len(ref[name]):,} pairs, split-half {res['ceiling'][name]}", flush=True)
    for v in list(variants) + ["dipc"]:
        p = out / f"{v}.chromdata.zarr"
        if not p.exists():
            continue
        cd = ChromData.read(p)
        cls = cd.cells["cls"]
        cls.index = cls.index.astype(str)
        cells = {c: list(cls.index[cls == c]) for c in (a, b)}
        maps = _class_maps(cd, cells, autos)
        r = {"cells": {c: len(x) for c, x in cells.items()}}
        for name in panels:
            t = _panel_values(maps, panels[name], a, b)
            t.to_parquet(out / f"loci_{name}_{v}.parquet")
            r[name] = _corrs(t, ref[name])
        if v == variants[0]:                                         # the reference reconstruction of the dataset
            h = {c: _halves(x, rng) for c, x in cells.items()}
            for name in panels:
                A = _panel_values(_class_maps(cd, {c: h[c][0] for c in cells}, autos), panels[name], a, b)
                B = _panel_values(_class_maps(cd, {c: h[c][1] for c in cells}, autos), panels[name], a, b)
                res["ceiling"][f"{name}_{v}"] = _corrs(A, B)
            perm = rng.permutation(cls.to_numpy())                    # class labels shuffled: no signal expected
            pc = pd.Series(perm, index=cls.index)
            shuf = _class_maps(cd, {c: list(pc.index[pc == c]) for c in (a, b)}, autos)
            r["shuffled_labels"] = {name: _corrs(_panel_values(shuf, panels[name], a, b), ref[name])
                                    for name in panels}
        res["variants"][v] = r
        print(f"[loci] {v}: " + json.dumps({k: {c: round(x["spearman"], 3) for c, x in r[k].items()} for k in panels}),
              flush=True)
    path = save(results / f"loci_{dataset}.json", res, script="benchmarks/cross_assay/recon.py",
                datasets=[{"tan2021": "tan2021_cortex", "hires_brain": "hires2023_brain", "tan2021_maps": "tan2021_cortex"}.get(dataset, dataset), "liu2025_mop",
                          "takei2021_brain"],
                params={"dataset": dataset, "contrast": [a, b], "sep_bands_bp": [float(SEP_BANDS[0]),
                        float(SEP_BANDS[-1]), len(SEP_BANDS)], "seed": seed, "stat": "median (distance_map)"})
    return {"results": str(path)}


N_BINS = 260                                           # 1-Mb bins per chromosome (mm10 chr1: 196)


def _cis_counts(path: str, chroms) -> dict:
    """{chrom: (bin1, bin2) of every cis contact between two 1-Mb bins}: bins (k Mb, k + 1 Mb], the particles'
    grid; contacts within one bin dropped.  Columns from the ``#columns:`` line (HiRES has no space after the
    colon); a chromosome name loses any ``(mat)`` / ``(pat)`` suffix."""
    import gzip
    import re

    cols = None
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if not line.startswith("#"):
                break
            m = re.match(r"^#columns:\s*(.*)$", line.rstrip("\n"))
            if m:
                cols = m.group(1).split()
    cols = cols or ["readID", "chr1", "pos1", "chr2", "pos2", "strand1", "strand2"]
    use = [cols.index(c) for c in ("chr1", "pos1", "chr2", "pos2")]
    t = pd.read_csv(path, sep=r"\s+", comment="#", header=None, usecols=use, dtype={use[0]: str, use[2]: str})
    t.columns = ["c1", "p1", "c2", "p2"]
    c1, c2 = t["c1"].str.replace(r"\(.*$", "", regex=True), t["c2"].str.replace(r"\(.*$", "", regex=True)
    t = t[(c1 == c2) & c1.isin(chroms)].assign(c=c1)
    b1, b2 = (t["p1"].to_numpy(np.int64) - 1) // RES, (t["p2"].to_numpy(np.int64) - 1) // RES
    lo, hi, ch = np.minimum(b1, b2), np.maximum(b1, b2), t["c"].to_numpy()
    keep = (lo != hi) & (hi < N_BINS)
    return {c: (lo[keep & (ch == c)], hi[keep & (ch == c)]) for c in chroms}


def stage_contacts(out: Path, results: Path, cells: pd.DataFrame, variants, dataset: str, seed: int,
                   liu_path: Path, xa_sets: Path, a: str = "ExN", b: str = "Oligo") -> dict:
    """The baseline without a 3D model: the same cells' contacts, as each class's mean per-cell contact frequency
    at 1 Mb (a cell's cis contacts between two bins over its cis contacts between bins: every cell weighs the
    same, as in a median over cells), put on the imaging loci like the reconstructions (stage loci) with the
    sign of a distance (log of 1 / frequency: more contacts in ExN = closer in ExN) and detrended the same way.
    Against imaging (Spearman over pairs), next to each reconstruction on the same pairs (``loci_<panel>_<v>``
    of stage loci, run first), and split-half ceilings (cells halved per class) -> ``--results``/contacts_<dataset>.json."""
    from types import SimpleNamespace

    from _record import save

    rng = np.random.default_rng(seed)
    autos = [f"chr{k}" for k in range(1, 20)]
    sub = cells[cells["cls"].isin([a, b])]
    half = {}
    for c, g in sub.groupby("cls"):
        h0, _ = _halves(g.index, rng)
        half.update({n: 0 if n in set(h0) else 1 for n in g.index})
    acc = {(c, h): {ch: np.zeros((N_BINS, N_BINS)) for ch in autos} for c in (a, b) for h in (0, 1)}
    n_cells = {(c, h): 0 for c in (a, b) for h in (0, 1)}
    t0 = time.perf_counter()
    for k, (name, row) in enumerate(sub.iterrows()):
        cc = _cis_counts(row["pairs"], autos)
        total = sum(len(lo) for lo, _ in cc.values())
        if not total:
            continue
        key = (row["cls"], half[name])
        for ch, (lo, hi) in cc.items():
            np.add.at(acc[key][ch], (lo, hi), 1.0 / total)
        n_cells[key] += 1
        if k % 100 == 0:
            print(f"[contacts] {k}/{len(sub)} cells, {time.perf_counter() - t0:.0f} s", flush=True)
    bins = pd.DataFrame({"start": np.arange(N_BINS) * RES, "end": (np.arange(N_BINS) + 1) * RES})

    def maps(groups):
        """{class: {chrom: namespace(bins, matrix = 1 / mean frequency)}} over the given (class, half) groups."""
        res = {}
        for c in (a, b):
            ks = [(c, h) for h in groups]
            n = sum(n_cells[k] for k in ks)
            res[c] = {}
            for ch in autos:
                m = sum(acc[k][ch] for k in ks) / max(n, 1)
                m = m + m.T
                with np.errstate(divide="ignore"):
                    res[c][ch] = SimpleNamespace(bins=bins, matrix=1.0 / m)
        return res

    full, A, B = maps((0, 1)), maps((0,)), maps((1,))
    panels = _imaging_panels(liu_path, xa_sets)
    res = {"contrast": f"{a} - {b}", "cells": {f"{c}": n_cells[(c, 0)] + n_cells[(c, 1)] for c in (a, b)},
           "seconds_reading": round(time.perf_counter() - t0, 1), "panels": {}}
    for name in ("liu2025", "takei2021"):
        p = out / f"loci_{name}_imaging.parquet"
        if not p.exists():
            continue
        ref = pd.read_parquet(p)
        loci = panels[name]
        t = _panel_values(full, loci, a, b)
        t.to_parquet(out / f"loci_{name}_contacts.parquet")
        r = {"contacts_vs_imaging": _corrs(t, ref),
             "contacts_split_half": _corrs(_panel_values(A, loci, a, b), _panel_values(B, loci, a, b)),
             "same_pairs": {}}
        for v in list(variants) + ["dipc"]:
            q = out / f"loci_{name}_{v}.parquet"
            if not q.exists():
                continue
            R = pd.read_parquet(q)
            j = t.index.intersection(R.index).intersection(ref.index)
            r["same_pairs"][v] = {"n_pairs": int(len(j)), "contacts": _corrs(t.loc[j], ref.loc[j]),
                                  "recon": _corrs(R.loc[j], ref.loc[j])}
        res["panels"][name] = r
        print(f"[contacts] {name}: contacts vs imaging "
              + json.dumps({k: round(x["spearman"], 3) for k, x in r["contacts_vs_imaging"].items()})
              + "; same pairs: " + json.dumps({v: {s: round(x[s]["resid"]["spearman"], 3) for s in ("contacts", "recon")}
                                               for v, x in r["same_pairs"].items()}), flush=True)
    path = save(results / f"contacts_{dataset}.json", res, script="benchmarks/cross_assay/recon.py",
                datasets=[{"tan2021": "tan2021_cortex", "hires_brain": "hires2023_brain"}.get(dataset, dataset),
                          "liu2025_mop", "takei2021_brain"],
                params={"dataset": dataset, "contrast": [a, b], "resolution_bp": RES, "seed": seed,
                        "stat": "mean per-cell contact frequency (cis contacts between bins over the cell's total)",
                        "sign": "log(1 / frequency), as a distance"})
    return {"results": str(path)}


def _imaging_panels(liu_path: Path, xa_sets: Path) -> dict:
    """The imaging loci on the autosomes as stage loci takes them: the bins of the Liu 2025 store and of the
    Takei 2021 set (chrom, start, end; indexed by bin id)."""
    import cross_assay as X
    from chromdata import ChromData
    from matched_data import load_set

    autos = [f"chr{k}" for k in range(1, 20)]
    sets = {"liu2025": ChromData.read(str(liu_path), backed=True),
            "takei2021": X.set_to_chromdata(load_set(xa_sets / "takei2021_brain_labels.npz"))}
    return {k: cd.bins[cd.bins["chrom"].astype(str).isin(autos)][["chrom", "start", "end"]].astype({"chrom": str})
            for k, cd in sets.items()}


CLASS_PAIRS = [("InN", "ExN"), ("ExN", "OPC"), ("ExN", "Astro"), ("ExN", "Oligo"), ("ExN", "Micro"), ("InN", "OPC"),
               ("InN", "Astro"), ("InN", "Oligo"), ("InN", "Micro"), ("OPC", "Astro"), ("OPC", "Oligo"),
               ("OPC", "Micro"), ("Astro", "Oligo"), ("Astro", "Micro"), ("Oligo", "Micro")]


def stage_loci_all(out: Path, results: Path, liu_path: Path, variant: str, dataset: str, seed: int) -> dict:
    """Every pair of classes (both present): the a - b difference map of the Liu 2025 loci in imaging and in the
    dataset's reference reconstruction, Spearman of the detrended maps; imaging split-half ceilings per pair."""
    import cross_assay as X
    from _record import save
    from chromdata import ChromData

    rng = np.random.default_rng(seed)
    autos = [f"chr{k}" for k in range(1, 20)]
    liu = ChromData.read(str(liu_path), columns="coords")
    lc = liu.cells.copy()
    lc.index = lc.index.astype(str)
    lcls = X.liu_classes(lc)
    traced = set(liu.spots["cell_id"].astype(str).unique())
    panel = liu.bins[liu.bins["chrom"].astype(str).isin(autos)][["chrom", "start", "end"]].astype({"chrom": str})
    cd = ChromData.read(out / f"{variant}.chromdata.zarr")
    cls = cd.cells["cls"].copy()
    cls.index = cls.index.astype(str)
    present = [c for c in sorted(set(cls.dropna())) if (cls == c).sum() >= 10]
    liu_cells = {c: [i for i in lcls.index[lcls == c] if i in traced] for c in present}
    rec_cells = {c: list(cls.index[cls == c]) for c in present}
    t0 = time.perf_counter()
    img = _class_maps(liu, liu_cells, autos)
    rec = _class_maps(cd, rec_cells, autos)
    halves = {c: _halves(v, rng) for c, v in liu_cells.items()}
    hA = _class_maps(liu, {c: h[0] for c, h in halves.items()}, autos)
    hB = _class_maps(liu, {c: h[1] for c, h in halves.items()}, autos)
    res = {"variant": variant, "cells": {c: [len(liu_cells[c]), len(rec_cells[c])] for c in present}, "pairs": {}}
    for a, b in CLASS_PAIRS:
        if a not in present or b not in present:
            continue
        ti = _panel_values(img, panel, a, b)
        tr = _panel_values(rec, panel, a, b)
        A, B = _panel_values(hA, panel, a, b), _panel_values(hB, panel, a, b)
        res["pairs"][f"{a}-{b}"] = {"recon_vs_imaging": _corrs(tr, ti), "imaging_split_half": _corrs(A, B)}
        print(f"[loci_all] {dataset} {a}-{b}: recon~imaging {res['pairs'][f'{a}-{b}']['recon_vs_imaging']['resid']['spearman']:.3f} "
              f"split-half {res['pairs'][f'{a}-{b}']['imaging_split_half']['resid']['spearman']:.3f}", flush=True)
    res["seconds"] = round(time.perf_counter() - t0, 1)
    path = save(results / f"loci_all_{dataset}.json", res, script="benchmarks/cross_assay/recon.py",
                datasets=[{"tan2021": "tan2021_cortex", "hires_brain": "hires2023_brain",
                           "tan2021_maps": "tan2021_cortex"}.get(dataset, dataset), "liu2025_mop"],
                params={"dataset": dataset, "variant": variant, "seed": seed, "pairs": CLASS_PAIRS})
    return {"results": str(path)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--stages", nargs="+", default=["run"])
    ap.add_argument("--dataset", default="tan2021",
                    help="tan2021, hires_brain (pairs), tan2021_maps (Tan's 1-Mb maps) or an atlas dataset of "
                         "pilot.DATASETS (its per-cell 1-Mb maps; run stage maps first)")
    ap.add_argument("--data-dir", "--tan-dir", type=Path, required=True,
                    help="tan2021: the cells folder; hires_brain: hires2023/raw/GSE223917/cells; maps: --out")
    ap.add_argument("--variants", nargs="+", default=VARIANTS)
    ap.add_argument("--task", type=int, default=0)
    ap.add_argument("--n-tasks", type=int, default=1)
    ap.add_argument("--device", default="gpu", choices=["cpu", "gpu"])
    ap.add_argument("--method", default="ember", choices=sorted(METHODS),
                    help="the reconstruction method of stage run, recorded by stage analyze")
    ap.add_argument("--limit", type=int, help="first N cells only (smoke test)")
    ap.add_argument("--xa-work", type=Path)
    ap.add_argument("--xa-results", type=Path, default=HERE / "results")
    ap.add_argument("--xa-sets", type=Path, help="the pilot's structure sets (Takei 2021 brain)")
    ap.add_argument("--liu", type=Path, help="the Liu 2025 store")
    ap.add_argument("--results", type=Path, default=HERE / "results")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()
    global METHOD
    METHOD = a.method
    a.out.mkdir(parents=True, exist_ok=True)
    if "maps" in a.stages:
        stage_maps(a.out, a.dataset, a.xa_work, a.seed)
        a.stages = [st for st in a.stages if st != "maps"]
        if not a.stages:
            return
    cells = dataset_cells(a.dataset, a.data_dir)
    if a.limit:
        cells = cells.head(a.limit)
    for st in a.stages:
        if st == "run":
            stage_run(a.out, cells, a.task, a.n_tasks, a.variants, a.device, a.method)
        elif st == "collect":
            log = stage_collect(a.out, cells, a.variants)
            (a.out / "logs").mkdir(exist_ok=True)
            (a.out / "logs" / "collect.json").write_text(json.dumps(log, indent=1))
        elif st == "analyze":
            stage_analyze(a.out, a.results, a.xa_work, a.xa_results, a.variants, a.seed, a.boot, a.dataset)
        elif st == "loci":
            stage_loci(a.out, a.results, a.xa_sets, a.liu, a.variants, a.dataset, a.seed)
        elif st == "loci_all":
            stage_loci_all(a.out, a.results, a.liu, a.variants[0], a.dataset, a.seed)
        elif st == "contacts":
            stage_contacts(a.out, a.results, cells, a.variants, a.dataset, a.seed, a.liu, a.xa_sets)


if __name__ == "__main__":
    main()
