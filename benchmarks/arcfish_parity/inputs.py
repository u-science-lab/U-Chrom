"""Inputs of the ArcFISH parity check: FOF-CT core tables that both the authors' package and U-Chrom read, and a
manifest of what each dataset runs.

    python benchmarks/arcfish_parity/inputs.py --data $SCRATCH/uchrom-nd/data \
        --takei2025 $SCRATCH/uchrom-nd/agentbench/data/takei2025_fov0/takei2025_fov0.chromdata.zarr --out OUT

Datasets (all registered: ``apps/atlas/recipes/README.md``):

* ``takei2021_chr6`` — the authors' loop / domain tutorial: Takei et al. 2021 mESC DNA seqFISH+ (25 kb), replicates
  1 and 2 (4DN 4DNFIHF3JCBY, 4DNFIQXONUUH) read together, chr6, coordinates µm → nm.
* ``su2020_chr2p`` — the authors' compartment tutorial: Su et al. 2020 IMR90 chromosome 2 p-arm (Zenodo 3928890
  ``chromosome2_p-arm_replicate.tsv``), the first 100 traces, nm.
* ``takei2025_chr15_1mb`` — question T1 of the agent benchmark: Takei et al. 2025 cerebellum FOV 0, chr15, each
  trace's spots averaged into 1-Mb bins (by the spot's midpoint), µm → nm; TAD window 4 Mb.
* ``bintu2018`` — Bintu et al. 2018 IMR90 chr21:18.6-20.6 Mb, 30 kb (registered ``bintu_imr90``), nm.
* ``su2020_chr21`` — Su et al. 2020 IMR90 chr21, 651 loci of 50 kb (``chromosome21.tsv``), nm.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _write(cd, path: Path) -> str:
    cd.to_fofct(path)
    return str(path)


def binned_chrom(cd, chrom, bin_bp=1_000_000):
    """Per trace, the mean xyz of its spots in each ``bin_bp`` bin (bin of the spot's midpoint)."""
    from chromdata import ChromData

    sp = cd.spots_with_loci()
    on = (sp["chrom"].astype(str) == chrom).to_numpy()
    df = pd.DataFrame({"trace_id": sp["trace_id"].astype(str).to_numpy()[on],
                       "b": ((sp["start"].to_numpy()[on] + sp["end"].to_numpy()[on]) // 2) // bin_bp})
    xyz = np.asarray(cd.coords)[on]
    df["x"], df["y"], df["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    g = df.groupby(["trace_id", "b"], sort=True).agg(x=("x", "mean"), y=("y", "mean"), z=("z", "mean")).reset_index()
    spots = pd.DataFrame({"chrom": chrom, "start": (g["b"] * bin_bp).astype(np.int64),
                          "end": ((g["b"] + 1) * bin_bp).astype(np.int64), "trace_id": g["trace_id"]})
    out = ChromData(coords=g[["x", "y", "z"]].to_numpy(float), spots=spots)
    out.uns["xyz_unit"] = cd.uns.get("xyz_unit", "micron")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--takei2025", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    from chromdata import ChromData
    from uchrom.io import read_bintu_tracing, read_su2020_tracing

    a.out.mkdir(parents=True, exist_ok=True)
    man = {}
    man["takei2021_chr6"] = {"files": {"rep1": str(a.data / "4DNFIHF3JCBY.csv"),
                                       "rep2": str(a.data / "4DNFIQXONUUH.csv")},
                             "chrom": "chr6", "nm_ratio": 1000, "window": 1e5, "min_cpmt": 0}
    su2 = read_su2020_tracing(a.data / "su2020_imr90" / "chromosome2_p-arm_replicate.tsv", unit="nm", extras=False)
    # loci 250 kb apart: the TAD window and the loop background scaled to them (the defaults test nothing, and the
    # authors' code stops when nothing is tested)
    man["su2020_chr2p"] = {"files": _write(su2, a.out / "su2020_chr2p.csv"), "chrom": "chr2", "nm_ratio": None,
                           "n_traces": 100, "window": 1e6, "min_cpmt": 0,
                           "loop": {"cut_lo": 5e5, "cut_up": 5e6, "outer_cut": 5e5, "gap": 5e5}}
    t25 = binned_chrom(ChromData.read(a.takei2025), "chr15")
    man["takei2025_chr15_1mb"] = {"files": _write(t25, a.out / "takei2025_chr15_1mb.csv"), "chrom": "chr15",
                                  "nm_ratio": 1000, "window": 4e6, "min_cpmt": 0,
                                  "loop": {"cut_lo": 2e6, "cut_up": 2e7, "outer_cut": 2e6, "gap": 2e6}}
    import uchrom.datasets as ds
    bt = read_bintu_tracing(str(ds.fetch("bintu_imr90", root=a.data)), chrom="chr21", start_bp=18_627_714,
                            resolution_bp=30_000, genome_assembly="hg38")
    man["bintu2018"] = {"files": _write(bt, a.out / "bintu2018.csv"), "chrom": "chr21", "nm_ratio": None,
                        "window": 1e5, "min_cpmt": 0, "insulation": {"window": 1.5e5, "prominence": 0.01}}
    su21 = read_su2020_tracing(a.data / "su2020_imr90" / "chromosome21.tsv", unit="nm", extras=False)
    # the first 1,000 traces: the authors' loop caller holds all traces' pairwise differences at once (7,591 traces:
    # ~77 GB) and runs out of memory on the whole table
    man["su2020_chr21"] = {"files": _write(su21, a.out / "su2020_chr21.csv"), "chrom": "chr21", "nm_ratio": None,
                           "n_traces": 1000, "window": 1e5, "min_cpmt": 0}
    (a.out / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
