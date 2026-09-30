"""Single-cell 3-D genome structure from the in-repo cell1.pairs.

Runs NucDynamics (``uchrom.recon.sc.nucdyn``) on ``cell1.pairs`` (Stevens et
al. 2017, mESC G1 cell, mm10) and links the cell's own contact map, so the
browser can show structure, contacts and 3-D distances side by side:

  sim_cell1/sim_cell1.cdz         20 chromosomes, ~25.6k particles at 100 kb
                                  (one-file ChromData store, checked in; ``--format
                                  zarr`` for the directory store)
  sim_cell1/cell1_contacts.mcool  the same cell's contacts, 100 kb … 1 Mb

Usage::

    python example-data/build_sim_cell1.py [--arch cpu]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "sim_cell1"


def contacts_mcool(pairs: Path, out: Path) -> None:
    import cooler
    import cooler.util

    chromsizes = cooler.util.fetch_chromsizes("mm10")
    df = pd.read_csv(pairs, sep="\t", header=None, usecols=[1, 2, 3, 4], names=["c1", "p1", "c2", "p2"])
    chroms = [c for c in chromsizes.index if c in set(df["c1"]) | set(df["c2"])]
    chromsizes = chromsizes[chroms]
    res = 100_000
    bins = cooler.util.binnify(chromsizes, res)
    offsets = dict(zip(chroms, np.r_[0, np.cumsum(np.ceil(chromsizes.values / res).astype(int))[:-1]]))
    df = df[df["c1"].isin(chroms) & df["c2"].isin(chroms)]
    b1 = df["c1"].map(offsets).to_numpy() + df["p1"].to_numpy() // res
    b2 = df["c2"].map(offsets).to_numpy() + df["p2"].to_numpy() // res
    lo, hi = np.minimum(b1, b2), np.maximum(b1, b2)
    px = pd.DataFrame({"bin1_id": lo, "bin2_id": hi}).value_counts().rename("count").reset_index()
    px = px.sort_values(["bin1_id", "bin2_id"])
    tmp = out.with_suffix(".100kb.cool")
    cooler.create_cooler(str(tmp), bins, px, ordered=True, assembly="mm10")
    cooler.zoomify_cooler(str(tmp), str(out), [100_000, 200_000, 500_000, 1_000_000], chunksize=10_000_000)
    tmp.unlink()
    print(f"{out.name}: {len(df):,} contacts, {len(px):,} pixels at 100 kb")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arch", default="cpu", help="taichi arch for NucDynamics (cpu / gpu / cuda / metal)")
    ap.add_argument("--format", default="cdz", choices=["cdz", "zarr"],
                    help="output container (default cdz: one file, checked in)")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    pairs = HERE / "cell1.pairs"
    structure = OUT / ("sim_cell1" + {"cdz": ".cdz", "zarr": ".chromdata.zarr"}[args.format])
    if not structure.exists():
        subprocess.run([sys.executable, "-m", "uchrom.recon.sc.nucdyn", str(pairs), str(structure),
                        f"--arch={args.arch}"], check=True)
    mcool = OUT / "cell1_contacts.mcool"
    if not mcool.exists():
        contacts_mcool(pairs, mcool)

    from uchrom import ChromData

    cd = ChromData.read(structure)
    cd.uns.setdefault("genome_assembly", "mm10")
    cd.uns["xyz_unit"] = "model units (NucDynamics)"
    cd.uns["source"] = "NucDynamics on example-data/cell1.pairs (Stevens et al. 2017)"
    # relative to the dataset's folder, so the folder can be moved or shipped
    cd.link_cool(mcool.name, key="cell1_contacts", label="cell1 contacts (input to the model)")
    cd.write(structure)
    print(cd)


if __name__ == "__main__":
    main()
