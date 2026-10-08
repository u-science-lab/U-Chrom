"""EMber reconstructions of Tan 2018 GM12878 cells vs the authors' Dip-C structures, through the tracing callers.

    .venv/bin/python benchmarks/sc_structures/structures_ember.py [--cells gm12878_05 ...] [--out DIR]

EMber (``uchrom.recon.sc.reconstruct_ember``) is run as it is — the frozen configuration (benchmarks/screcon
PREREG.md), its default particle sizes (down to 100 kb), whole genome, diploid (the hickit phased pairs of
the cell from GEO, as in the pre-registered diploid test), ``--models`` models, seed 1.  Its chr21 homologs
(model 0) and the published Dip-C chr21 homologs of the same cells (20 kb particles averaged into the same
100 kb bins) go through ``call_compartments_axes_pc``; each is compared with the Rao 2014 GM12878 E1 (100 kb)
and with the other; plus the distance-matrix correlation of each homolog between the two reconstructions.
TADs / loops need finer particles than EMber's default and are not compared here.

Results: ``structures_ember.json`` in ``--out``.
"""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import structures_common as sc  # noqa: E402

warnings.filterwarnings("ignore")
CHROM = "chr21"


def extract_pairs(cell: str, out: Path) -> Path:
    import re
    import tarfile

    import uchrom.datasets as ds

    folder = Path(ds.fetch("tan2018_gm12878"))
    tar = next(p for p in folder.glob("GSM*_gm12878_*.tar.gz") if re.search(cell, p.name))
    dst = out / f"{cell}.pairs.gz"
    if not dst.exists():
        with tarfile.open(tar) as tf:
            dst.write_bytes(tf.extractfile(f"{cell}.pairs.gz").read())
    return dst


def ember_cell(cell: str, out: Path, n_models: int):
    from chromdata import ChromData
    from uchrom.recon.sc import reconstruct_ember

    store = out / f"ember_{cell}.chromdata.zarr"
    if store.exists():
        return ChromData.read(store), None
    pairs = extract_pairs(cell, out)
    t = time.perf_counter()
    import os

    cd = reconstruct_ember(str(pairs), n_models=n_models, seed=1, cell_id=cell,
                           device=os.environ.get("EMBER_DEVICE", "auto"),
                           n_threads=int(os.environ.get("SLURM_CPUS_PER_TASK", "0")))
    secs = time.perf_counter() - t
    cd.write(store)
    return cd, secs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=sc.default_out("sc_structures_ember"))
    ap.add_argument("--cells", nargs="+", default=None, help="default: all 14 cells")
    ap.add_argument("--models", type=int, default=4)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    import uchrom.datasets as ds
    from chromdata import ChromData
    from uchrom.fea.compare import distance_correlation
    from uchrom.strc.comp import CompartmentCallerParams, call_compartments_axes_pc, compare_compartments
    from uchrom.strc.comp.eig import call_compartments_eig

    if a.cells is None:                    # the 14 cells with hickit pairs (the loader's cells)
        import re

        a.cells = sorted(re.search(r"(gm12878_\d\d)", p.name).group(1)
                         for p in Path(ds.fetch("tan2018_gm12878")).glob("GSM*_gm12878_*.tar.gz"))
    fasta = ds.fetch("hg19_chr21")
    p100 = sc.rebinned(ds.fetch("rao2014_gm12878_chr21"), 100_000, a.out / "maps", "rao_gm12878", chrom=CHROM)
    e1 = call_compartments_eig(str(p100), chrom=CHROM, phasing=str(fasta))
    dipc = sc.in_memory_chrom(ds.load("tan2018_gm12878", backed=True), CHROM)
    dipc = dipc[dipc.spots["cell_id"].astype(str).isin(set(a.cells)).to_numpy()]
    res = {"cells": a.cells, "n_models": a.models, "runtime_s": {}}
    parts = []
    for cell in a.cells:
        cd, secs = ember_cell(cell, a.out, a.models)
        info = cd.uns.get("ember", {})
        res["runtime_s"][cell] = {"engine_s": info.get("seconds"), "wall_s": secs, "device": info.get("device"),
                                  "particle_size": info.get("particle_size")}
        names = [str(c) for c in cd.bins["chrom"].cat.categories]
        sub = cd.get_chrom(CHROM if CHROM in names else CHROM.removeprefix("chr"))   # hickit pairs: "21"
        loci = sub.spots_with_loci()
        hap = loci["trace_id"].astype(str).str.extract(r"\((\w+)\)")[0]
        parts.append(pd.DataFrame({"chrom": CHROM, "start": loci["start"].to_numpy(), "end": loci["end"].to_numpy(),
                                   "trace_id": f"{cell}_{CHROM}_" + hap.to_numpy(), "cell_id": cell,
                                   "x": np.asarray(sub.coords)[:, 0], "y": np.asarray(sub.coords)[:, 1],
                                   "z": np.asarray(sub.coords)[:, 2]}))
        print(cell, "EMber", sub, flush=True)
    em = pd.concat(parts, ignore_index=True)
    # EMber's last particle of a chromosome ends at the next multiple of 100 kb, past the chromosome end
    from uchrom.datasets._load_schic import HG19

    em = em[em["start"] < HG19[CHROM]].assign(end=lambda d: np.minimum(d["end"], HG19[CHROM]))
    ember = ChromData(em[["x", "y", "z"]].to_numpy(), em.drop(columns=["x", "y", "z"]))
    co_e = sc.coarsen(ember, 100_000, CHROM)
    co_d = sc.coarsen(dipc, 100_000, CHROM)
    out = {}
    for name, co in (("ember", co_e), ("dipc", co_d)):
        sc.with_track(co, sc.gc_table(co.bins, fasta), "gc")
        t = call_compartments_axes_pc(co, chrom=CHROM, params=CompartmentCallerParams(a_track="gc"), device="cpu",
                                      key_added=None)
        out[name] = t
        res[f"{name}_vs_rao_e1"] = compare_compartments(co, t, e1)
    res["ember_vs_dipc"] = compare_compartments(co_d, out["ember"], out["dipc"])
    # distance-matrix correlation per homolog on the common 100 kb bins
    from uchrom.fea import rebin_coords

    bins = co_d.bins[co_d.bins["chrom"].astype(str) == CHROM][["chrom", "start", "end"]].reset_index(drop=True)
    ce, ge = rebin_coords(ember, bins, by="trace")
    cdp, gd = rebin_coords(dipc, bins, by="trace")
    r = {}
    for k, tid in enumerate(gd):
        if tid in list(ge):
            r[tid] = distance_correlation(cdp[k], ce[list(ge).index(tid)], min_size=10)
    res["distance_r_per_homolog"] = r
    res["distance_r_median"] = float(np.nanmedian(list(r.values()))) if r else None
    print({k: v for k, v in res.items() if k != "distance_r_per_homolog"}, flush=True)
    sc.dump(res, a.out / "structures_ember.json")


if __name__ == "__main__":
    main()
