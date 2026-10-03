"""Compare populations of the native IGM protocol with populations of the original IGM
on the same input (the IGM demo, WTC11 2 Mb), relative to each code's own
seed-to-seed spread (design.md §7(d)).

    python benchmarks/bulk/igm_demo_compare.py \
        --ours runs/igm_demo/ours_s1 runs/igm_demo/ours_s2 \
        --igm runs/igm_demo/orig_s1/igm-model.hss runs/igm_demo/orig_s2/igm-model.hss \
        --out runs/igm_demo/compare.json

For every population: fit to the input (Pearson / MAE of the population contact
probability vs the input, restrained / unrestrained, intra / inter) and per-bin mean
radial position; for every pair of populations: Pearson of their contact
probabilities over the input pairs and of their radial profiles.  The report lists
ours-vs-IGM next to ours-vs-ours and IGM-vs-IGM.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _igm_bench as B  # noqa: E402


def load_ours(d: Path, bins):
    z = np.load(d / "population.npz", allow_pickle=True)
    return {"name": f"ours:{d.name}", "coords": z["coords"], "bead_bin": z["bead_bin"],
            "bead_copy": z["bead_copy"], "radii": z["radii"]}


def load_igm(path: Path, bins):
    h = B.read_hss(path)
    key = {(c, s): k for k, (c, s) in enumerate(zip(bins["chrom"], bins["start"]))}
    bead_bin = np.array([key[(c, s)] for c, s in zip(h["chrom"], h["start"])])
    return {"name": f"igm:{path.parent.name}", "coords": h["coords"], "bead_bin": bead_bin,
            "bead_copy": h["copy"], "radii": h["radii"]}


def radial(pop, nb):
    r = np.linalg.norm(pop["coords"].astype(np.float64), axis=2).mean(0)
    out = np.zeros(nb)
    cnt = np.zeros(nb)
    np.add.at(out, pop["bead_bin"], r)
    np.add.at(cnt, pop["bead_bin"], 1)
    return out / np.maximum(cnt, 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hcs", type=Path, default=None)
    ap.add_argument("--ours", type=Path, nargs="*", default=[])
    ap.add_argument("--igm", type=Path, nargs="*", default=[])
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    d = B.read_hcs(a.hcs or B.fetch_igm_demo())
    bins = {"chrom": d["chrom"], "start": d["start"]}
    nb = len(d["chrom"])
    i, j, v = d["i"], d["j"], d["v"]
    intra = d["chrom"][i] == d["chrom"][j]
    pops = [load_ours(p, bins) for p in a.ours] + [load_igm(p, bins) for p in a.igm]
    rep = {"populations": {}, "pairs": []}
    maps, rads = {}, {}
    for p in pops:
        pc = B.contact_probability(p["coords"], p["bead_bin"], p["bead_copy"], p["radii"], d["chrom"], i, j)
        maps[p["name"]] = pc
        rads[p["name"]] = radial(p, nb)
        rep["populations"][p["name"]] = {"n_structures": int(p["coords"].shape[0]), "n_beads": int(p["coords"].shape[1]),
                                         "fit": B.fit_summary(v, pc, intra)}
        print(p["name"], json.dumps(rep["populations"][p["name"]]["fit"]), flush=True)
    for x, y in itertools.combinations(maps, 2):
        kind = "-".join(sorted({x.split(":")[0], y.split(":")[0]}))
        row = {"a": x, "b": y, "kind": kind,
               "pearson_contact": float(np.corrcoef(maps[x], maps[y])[0, 1]),
               "pearson_contact_intra": float(np.corrcoef(maps[x][intra], maps[y][intra])[0, 1]),
               "pearson_contact_inter": float(np.corrcoef(maps[x][~intra], maps[y][~intra])[0, 1]),
               "pearson_radial": float(np.corrcoef(rads[x], rads[y])[0, 1]),
               "mean_abs_diff_contact": float(np.abs(maps[x] - maps[y]).mean())}
        rep["pairs"].append(row)
        print(json.dumps(row), flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
