"""Build the Nagano 2017 haploid store of the atlas: single-cell Hi-C of haploid mouse ES cells with 3-D structures
computed by U-Chrom's NucDynamics (Nagano et al. 2017, Nature 547:61, doi:10.1038/nature23001; GEO GSE94489).

The authors published contacts, not structures; the cells are haploid, so every contact has one chromosome copy
and NucDynamics (Stevens et al. 2017) applies as to the Stevens 2017 cells:

  nagano2017_hap/nagano2017_hap.chromdata.zarr

* cells: 603 of the 1,772 — serum (``cond == "Serum_G1/S"``) and 2i (``2i_all`` / ``2i_G1``) cells with
  ``passed_qc == 1``, not mitotic (``group`` G1 / early-S / late-S/G2), with at least 100,000 (serum) / 50,000
  (2i) contacts; all 403 serum cells and 200 of the 2i cells drawn with seed 1.  ``cells``: the GEO feature
  table's columns, ``condition`` (serum / 2i), the contacts used and the model deviation.
* contacts: the Tanay lab's fend pairs (``adj``, mm9 GATC fragment ends) placed with ``GATC.fends`` and lifted
  to mm10 with the UCSC chain, one contact per fend pair, chr1-19 and X.
* 3-D coordinates: NucDynamics (``uchrom.recon.sc.nucdyn``, protocol ``nuc_dynamics_2017``, particles of 8, 4, 2,
  0.4, 0.2, 0.1 Mb), two models per cell (seed 1): model 1 in ``coords``, model 2 as layer ``model_2``; one trace
  per cell and chromosome; coordinates in particle radii.  ``cells["rmsd_model_2"]``: the RMSD of the two
  models after superposition (mirror images allowed), ``spot_tracks["model_deviation"]`` per particle.
* links, next to the store: ``nagano2017_hap_cells_100kb.scool`` (one map per cell) and
  ``nagano2017_hap_bulk.mcool`` (the cells merged, 100 kb - 1 Mb).

Steps (``WORK`` = ``<data dir>/nagano2017_hap/build``, or ``--work``)::

    python -m uchrom.datasets fetch nagano2017_hap
    python apps/atlas/recipes/build_nagano2017_hap.py contacts       # WORK/contacts/{serum,2i}/<cell>.txt.gz
    python apps/atlas/recipes/build_nagano2017_hap.py reconstruct [--task K --n-tasks N] [--device gpu]
    python apps/atlas/recipes/build_nagano2017_hap.py store
    python apps/atlas/recipes/derive_embeddings.py <data dir>/nagano2017_hap/nagano2017_hap.chromdata.zarr \\
        --hic per_cell --leiden

``reconstruct`` writes ``WORK/models/<cell>.npz`` (``chrom``, ``pos`` = particle end, ``coords`` (models,
particles, 3)) for the cells that have none, ~40 s per cell on a GPU; split it over tasks with ``--task`` /
``--n-tasks``.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import tarfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sc_hic_common import ContactBinner, chromsizes, log  # noqa: E402

CHROMS = [f"chr{i}" for i in range(1, 20)] + ["chrX"]
RES = 100_000
PARTICLE_SIZES = (8e6, 4e6, 2e6, 4e5, 2e5, 1e5)
N_MODELS, SEED = 2, 1
NOT_MITOTIC = '["G1", "early-S", "late-S/G2"]'
RULES = {"serum": f'cond == "Serum_G1/S" and passed_qc == 1 and group in {NOT_MITOTIC} and total_contacts >= 100000',
         "2i": f'cond in ["2i_all", "2i_G1"] and passed_qc == 1 and group in {NOT_MITOTIC} and total_contacts >= 50000'}
MAX_CELLS = {"serum": None, "2i": 200}
FEATURES = "GSE94489_haploids_features_table.txt.gz"
TARBALLS = {"serum": "schic_hap_serum_adj_files.tar.gz", "2i": "schic_hap_2i_adj_files.tar.gz"}  # NST.<n>/adj, NXT.<n>/adj
ADJ_DIRS = {"serum": "adj_serum", "2i": "adj_2i"}       # the same, extracted


def paths(args):
    from uchrom.datasets import data_dir

    root = Path(args.data) if args.data else data_dir()
    src = root / "nagano2017_hap"
    work = Path(args.work) if args.work else src / "build"
    return src, work


def select(features: pd.DataFrame, cond: str) -> pd.DataFrame:
    s = features.query(RULES[cond])
    if MAX_CELLS[cond] and len(s) > MAX_CELLS[cond]:
        s = s.sample(MAX_CELLS[cond], random_state=SEED).sort_index()
    return s


def adj_tables(src: Path, cond: str):
    """``(cell name, adj table)`` of one condition: from the fetched tarball (read in one pass, nothing extracted),
    else from an extracted folder."""
    tarball = src / TARBALLS[cond]
    if tarball.exists():
        with tarfile.open(tarball, "r|gz") as tf:
            for m in tf:
                if m.isfile() and m.name.endswith("/adj"):
                    yield m.name.split("/")[-2].replace(".", "_"), pd.read_csv(tf.extractfile(m), sep="\t")
        return
    for adj in sorted((src / ADJ_DIRS[cond]).glob("*/adj")):
        yield adj.parent.name.replace(".", "_"), pd.read_csv(adj, sep="\t")


def cmd_contacts(args) -> None:
    """adj (mm9 fend pairs) of the selected cells -> mm10 contact tables ``chr_A pos_A chr_B pos_B`` (1-based)."""
    from uchrom.datasets._load_snaphic import _Chain, _fends

    src, work = paths(args)
    feats = pd.read_csv(src / FEATURES, sep="\t")
    fid, fchr, fpos = _fends(src / "GATC.fends")
    chain = _Chain(src / "mm9ToMm10.over.chain.gz")
    for cond in RULES:
        sel = select(feats, cond).set_index("cell_nm")
        out = work / "contacts" / cond
        out.mkdir(parents=True, exist_ok=True)
        rows = []
        for cell, a in adj_tables(src, cond):
            if cell not in sel.index:
                continue
            ends = []
            for col in ("fend1", "fend2"):
                f = a[col].to_numpy(np.int64)
                k = np.clip(np.searchsorted(fid, f), 0, len(fid) - 1)
                c, p = chain.map(fchr[k], fpos[k])
                ends.append((fid[k] == f, c, p))
            (ok1, c1, p1), (ok2, c2, p2) = ends
            ok = ok1 & ok2 & (p1 >= 0) & (p2 >= 0)
            ok &= np.isin(c1.astype(str), CHROMS) & np.isin(c2.astype(str), CHROMS)
            dest = out / f"{cell}.txt.gz"
            with gzip.open(dest, "wt") as fh:
                fh.write("#chr_A\tpos_A\tchr_B\tpos_B\n")
                pd.DataFrame({"a": c1[ok], "pa": p1[ok] + 1, "b": c2[ok], "pb": p2[ok] + 1}).to_csv(
                    fh, sep="\t", header=False, index=False)
            r = sel.loc[cell]
            rows.append({"cell": cell, "cond": r.cond, "group": r.group, "total_contacts": r.total_contacts,
                         "table": dest.name, "n_adj_rows": len(a), "n_written": int(ok.sum())})
        missing = sorted(set(sel.index) - {r["cell"] for r in rows})
        if missing:
            log(f"{cond}: no adj table for {len(missing)} selected cells, e.g. {missing[:3]}")
        pd.DataFrame(rows).to_csv(out / "manifest.tsv", sep="\t", index=False)
        log(f"{cond}: {len(rows)} cells -> {out}")


def tables(work: Path) -> dict:
    """``{cell: (condition, contact table)}`` of ``WORK/contacts/*/<cell>.txt.gz``."""
    out = {}
    for cond in RULES:
        for f in sorted((work / "contacts" / cond).glob("*.txt.gz")):
            out[f.name.removesuffix(".txt.gz")] = (cond, f)
    return out


def cmd_reconstruct(args) -> None:
    from uchrom.recon.sc.nucdyn import reconstruct_nucdyn

    _, work = paths(args)
    models = work / "models"
    models.mkdir(parents=True, exist_ok=True)
    cells = sorted(tables(work).items())[args.task::args.n_tasks]
    for cell, (_, table) in cells:
        out = models / f"{cell}.npz"
        if out.exists():
            continue
        t0 = time.time()
        cd = reconstruct_nucdyn(str(table), n_models=N_MODELS, seed=SEED, device=args.device,
                                particle_sizes=PARTICLE_SIZES, key_added=None)
        xyz = np.stack([cd.layers[f"model_{k}"] for k in range(N_MODELS)])
        tmp = out.with_name(out.stem + ".part.npz")
        np.savez_compressed(tmp, chrom=cd.spots["chrom"].astype(str).to_numpy(),
                            pos=cd.spots["end"].to_numpy(np.int64), coords=xyz)
        tmp.replace(out)
        out.with_suffix(".npz.json").write_text(json.dumps(
            {"contacts": table.name, "protocol": "nuc_dynamics_2017", "particle_sizes": list(PARTICLE_SIZES),
             "n_models": N_MODELS, "seed": SEED, "device": args.device, "wall_seconds": time.time() - t0}))
        log(f"{cell}: {cd.n_spots:,} particles ({time.time() - t0:.0f} s)")


def cmd_store(args) -> None:
    from uchrom import ChromData
    from uchrom.io.dipc_3dg import replicate_deviation

    src, work = paths(args)
    sizes = chromsizes(None, "mm10", keep=CHROMS)
    cells_in = tables(work)
    missing = [c for c in cells_in if not (work / "models" / f"{c}.npz").exists()]
    if missing:
        raise SystemExit(f"{len(missing)} cells without models, e.g. {missing[:3]}: run reconstruct")
    names = sorted(cells_in, key=lambda c: (c.split("_")[0], int(c.split("_")[1])))
    out = src                                            # next to the fetched files, as the Stevens store
    stem = out / "nagano2017_hap"

    binner = ContactBinner(sizes, names, out / ".bins", cell_res=RES, bulk_res=RES)
    for name in names:
        df = pd.read_csv(cells_in[name][1], sep="\t", comment="#", header=None,
                         names=["chr1", "pos1", "chr2", "pos2"], dtype={"chr1": str, "chr2": str})
        binner.add(np.full(len(df), binner.cell_index.get_loc(name)), binner.chrom_codes(df["chr1"]),
                   df["pos1"].to_numpy(), binner.chrom_codes(df["chr2"]), df["pos2"].to_numpy())
    binner.close()
    scool = stem.with_name(stem.name + f"_cells_{RES // 1000}kb.scool")
    binner.write_scool(scool)
    mcool = binner.write_mcool(stem.with_name(stem.name + "_bulk.mcool"),
                               resolutions=(100_000, 250_000, 500_000, 1_000_000))
    per_cell = pd.Series(binner.per_cell, index=binner.cells)
    binner.cleanup()
    log(f"contacts: {binner.n_kept:,} of {binner.n_in:,} on kept chromosomes")

    spots, coords, model_2 = [], [], []
    for name in names:
        z = np.load(work / "models" / f"{name}.npz")
        pos = z["pos"].astype(np.int64)
        start = np.maximum(pos - RES, 0)                 # 2017 protocol: a particle at p holds (p - size, p]
        s = pd.DataFrame({"chrom": z["chrom"].astype(str), "start": start, "end": np.maximum(pos, start + 1)})
        s["trace_id"] = name + "_" + s["chrom"]
        s["cell_id"] = name
        spots.append(s)
        coords.append(z["coords"][0])
        model_2.append(z["coords"][1])
    spots = pd.concat(spots, ignore_index=True)

    feats = pd.read_csv(src / FEATURES, sep="\t").set_index("cell_nm")
    cells = feats.loc[names].drop(columns=["batch_id"], errors="ignore")
    cells.index.name = "cell_id"
    cells.insert(0, "condition", [cells_in[n][0] for n in names])
    cells.insert(0, "cell_type", "haploid mESC")
    cells["n_contacts"] = per_cell.reindex(names).to_numpy()
    cd = ChromData(np.concatenate(coords), spots, cells=cells, layers={"model_2": np.concatenate(model_2)},
                   uns={"genome_assembly": "mm10", "xyz_unit": "particle radius",
                        "source": "Nagano et al. 2017, Nature 547:61 (doi:10.1038/nature23001; GEO GSE94489): "
                                  "haploid mESC single-cell Hi-C, Tanay lab fend pairs (mm9) lifted to mm10",
                        "selection": {k: {"rule": RULES[k], "max_cells": MAX_CELLS[k], "seed": SEED} for k in RULES},
                        "coordinate_status": "computed: U-Chrom NucDynamics (protocol nuc_dynamics_2017, 100 kb "
                                             "particles, seed 1); model 1 in coords, model 2 in layers"})
    per, dev = replicate_deviation(cd, ("model_2",), reflection=True)
    cells = cd.cells.join(per[["rmsd_model_2", "median_dev_model_2"]])
    cd = ChromData(cd.coords, cd.spots, bins=cd.bins, cells=cells, layers=cd.layers,
                   spot_tracks=pd.DataFrame({"model_deviation": dev}),
                   uns={**cd.uns, "derived_spot_tracks": ["model_deviation"]})
    cd.link_cool(mcool.name, key="bulk", label=f"All {len(names)} cells (merged)")
    cd.link_scool(scool.name, key="per_cell", label="Per cell (100 kb)", cell_name="cell_id",
                  genome_assembly="mm10", bin_size=RES)
    dest = stem.with_name(stem.name + ".chromdata.zarr")
    cd.write(dest)
    log(f"wrote {dest}: {cd}; model RMSD median {per['rmsd_model_2'].median():.2f} particle radii")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("step", choices=["contacts", "reconstruct", "store"])
    ap.add_argument("--data", help="data directory (default $UCHROM_DATA, else ~/.cache/uchrom)")
    ap.add_argument("--work", help="intermediate files (default <data>/nagano2017_hap/build)")
    ap.add_argument("--task", type=int, default=0)
    ap.add_argument("--n-tasks", type=int, default=1)
    ap.add_argument("--device", default="auto")
    a = ap.parse_args()
    {"contacts": cmd_contacts, "reconstruct": cmd_reconstruct, "store": cmd_store}[a.step](a)


if __name__ == "__main__":
    main()
