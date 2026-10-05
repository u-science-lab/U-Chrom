"""Few-cell deconvolution benchmark (PREREG §12): imaging-truth mixtures and real-cell pools.

Subcommands
-----------
``truths``  Pseudo-haploid truth cells of a dataset with the registered development / test split::

                python benchmarks/screcon/mix_sim.py truths --dataset takei2021_1mb --out MIX/truth/takei2021_1mb

            * ``takei2021_1mb``: ``truth.takei1mb_cells`` (min_detect 0.6, min_sep 1 Rg); eligible =
              all 20 chromosomes accepted (61 cells); ids sorted as strings, permuted with
              ``default_rng(20261005)``: first 30 development, the rest test.
            * ``su2020_genome``: Su 2020 IMR90 genome-scale, 1,041 loci; one copy per chromosome
              (experimental homolog 1); eligible = detection of that copy >= 0.85; cells sorted by
              (experiment, cell), permuted with the same seed: first 100 development, next 100 test.
            Writes ``<set>/truth_<cell>.npz`` (screcon truth format) and ``split.json``.

``pools``   Pooled tables of a set (``dev`` / ``test``)::

                python benchmarks/screcon/mix_sim.py pools --truth-dir MIX/truth/takei2021_1mb --set dev --out MIX/pools/takei2021_1mb

            Per k in {2, 3, 5, 10, 20} and pool p (4 development / 6 test): cells drawn without
            replacement from the set (``default_rng(1000 k + p)``; test ``2000 + 1000 k + p``); per
            condition (depth 10 / 40 reads per Mb per cell, eps 0.05 / 0.2, Gaussian kernel, rc 1.0 x
            median consecutive-locus distance) the reads of every cell (``simulate.simulate_reads``,
            seed 100 p + cell index), concatenated and shuffled (``default_rng(7 p + k)``).  Writes
            ``k<k>_p<p>_d<depth>_e<eps>.txt.gz`` (GEO table), ``.origin.npz`` (``cell`` = index into
            the pool's cells per row, ``noise`` flag, ``cells`` = truth files) and per-cell tables
            ``..._cell<j>.txt.gz`` (oracle inputs); ``manifest.tsv`` lists the tables.

``real``    Pools of real single cells (haploid)::

                python benchmarks/screcon/mix_sim.py real --dataset nagano --manifest SPLIT/dev_manifest.tsv --set dev --out MIX/real/nagano
                python benchmarks/screcon/mix_sim.py real --dataset stevens --tables GEO/*_contact_pairs.txt.gz --set dev --out MIX/real/stevens

            Nagano (serum halves of ``robust_matched_split.py``): k in {2, 3, 5, 10, 20}, 4 / 6 pools,
            seeds as above + 50,000.  Stevens: development cells 1-4 (all pairs, triples, the 4-cell
            pool), test cells 5-8.  The rows of the cells' tables are concatenated (lines unchanged)
            and shuffled; ``.origin.npz`` as above.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contacts import read_contacts, write_contacts, write_geo  # noqa: E402
from simulate import simulate_reads  # noqa: E402
from truth import interpolate_missing, load_truth, save_truth  # noqa: E402

SPLIT_SEED = 20261005
KS = (2, 3, 5, 10, 20)
N_POOLS = {"dev": 4, "test": 6}
DEPTHS = (10.0, 40.0)
EPSS = (0.05, 0.2)
RC_REL = 1.0


def example_data() -> Path:
    import os
    if os.environ.get("UCHROM_EXAMPLE_DATA"):
        return Path(os.environ["UCHROM_EXAMPLE_DATA"])
    return Path(__file__).resolve().parents[2] / "example-data"


# --------------------------------------------------------------------------- truths

def takei_truths(path):
    from truth import takei1mb_cells
    loci, cells = takei1mb_cells(path, min_sep=1.0, min_detect=0.6)
    chrom = loci.Chrom.to_numpy().astype(str)
    start = loci.Chrom_Start.to_numpy()
    end = loci.Chrom_End.to_numpy()
    elig = sorted([str(c) for c, r in cells.items() if sum(v["accepted"] for v in r["chroms"].values()) >= 20])
    by_id = {str(c): r for c, r in cells.items()}
    perm = np.random.default_rng(SPLIT_SEED).permutation(len(elig))
    order = [elig[i] for i in perm]
    sets = {"dev": order[:30], "test": order[30:]}
    out = {}
    for name, ids in sets.items():
        out[name] = [(cid, chrom, start, end, by_id[cid]["coords"],
                      {"dataset": "takei2021_1mb", "cell": cid, "homolog_assignment": "heuristic (truth.split_homologs)"})
                     for cid in ids]
    return out, {"n_eligible": len(elig), "rule": "all 20 chromosomes accepted (min_detect 0.6, min_sep 1 Rg)"}


def su_truths(path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bulk"))
    import truths as bulk_truths
    pop = bulk_truths.su2020_genome(path)
    X = pop.coords[:, 0]                       # homolog 1 ("homolog number" 1) of every chromosome
    det = np.isfinite(X[..., 0]).mean(1)
    ids = pop.meta["cell_ids"]                 # sorted by (experiment, cell)
    elig = [i for i in range(len(ids)) if det[i] >= 0.85]
    perm = np.random.default_rng(SPLIT_SEED).permutation(len(elig))
    order = [elig[i] for i in perm]
    sets = {"dev": order[:100], "test": order[100:200]}
    out = {}
    for name, idx in sets.items():
        out[name] = [(ids[i], pop.chrom, pop.start, pop.end, X[i],
                      {"dataset": "su2020_genome", "cell": ids[i], "copy": "homolog 1", "detection": float(det[i])})
                     for i in idx]
    return out, {"n_eligible": len(elig), "rule": "detection of homolog 1 >= 0.85"}


def cmd_truths(args) -> None:
    if args.dataset == "takei2021_1mb":
        sets, info = takei_truths(Path(args.data) if args.data else example_data() / "4DNFIFLJGGNR.csv")
    elif args.dataset == "su2020_genome":
        sets, info = su_truths(Path(args.data) if args.data else example_data() / "su2020_imr90/genomic-scale.tsv")
    else:
        raise SystemExit(f"unknown dataset {args.dataset}")
    out = Path(args.out)
    split = {"dataset": args.dataset, "seed": SPLIT_SEED, **info}
    for name, rows in sets.items():
        split[name] = []
        for cid, chrom, start, end, X, meta in rows:
            _, measured = interpolate_missing(chrom, start, X)
            safe = str(cid).replace("/", "_")
            f = out / name / f"truth_{safe}.npz"
            meta = {**meta, "n_loci": int(len(chrom)), "n_measured": int(measured.sum()), "set": name, "unit": "nm"}
            save_truth(f, chrom, start, end, X, measured, meta)
            split[name].append(str(f.name))
    (out / "split.json").write_text(json.dumps(split, indent=1))
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in split.items()}))


# --------------------------------------------------------------------------- simulated pools

def pool_cells(files: list[str], k: int, pool: int, test: bool) -> list[str]:
    rng = np.random.default_rng((2000 if test else 0) + 1000 * k + pool)
    idx = rng.choice(len(files), size=k, replace=False)
    return [files[i] for i in idx]


def cmd_pools(args) -> None:
    tdir = Path(args.truth_dir)
    split = json.loads((tdir / "split.json").read_text())
    files = split[args.set]
    out = Path(args.out) / args.set
    out.mkdir(parents=True, exist_ok=True)
    test = args.set == "test"
    ks = args.ks or KS
    man = []
    for k in ks:
        for p in range(1, N_POOLS[args.set] + 1):
            cells = pool_cells(files, k, p, test)
            truths = [load_truth(tdir / args.set / f) for f in cells]
            for depth, eps in itertools.product(DEPTHS, EPSS):
                name = f"k{k}_p{p}_d{depth:g}_e{eps:g}"
                f = out / f"{name}.txt.gz"
                if f.exists() and not args.overwrite:
                    man.append((name, str(f), k, p, depth, eps))
                    continue
                parts = []
                infos = []
                for j, t in enumerate(truths):
                    ca, pa, cb, pb, info = simulate_reads(t, reads_per_mb=depth, rc_rel=RC_REL, kind="gauss", eps=eps,
                                                          seed=100 * p + j, missing="interp")
                    # noise flag: simulate_reads shuffles signal and noise reads; re-run its draws
                    from robust_diag import noise_flags
                    is_noise, ra, rb, _ = noise_flags(t, info)
                    assert np.array_equal(ra, pa) and np.array_equal(rb, pb)
                    parts.append((ca, pa, cb, pb, np.full(len(pa), j, np.int16), is_noise))
                    infos.append(info)
                    write_geo(out / f"{name}_cell{j}.txt.gz", ca, pa, cb, pb)
                ca = np.concatenate([x[0] for x in parts]); pa = np.concatenate([x[1] for x in parts])
                cb = np.concatenate([x[2] for x in parts]); pb = np.concatenate([x[3] for x in parts])
                cell = np.concatenate([x[4] for x in parts])
                noise = np.concatenate([x[5] for x in parts])
                order = np.random.default_rng(7 * p + k).permutation(len(pa))
                write_geo(f, ca[order], pa[order], cb[order], pb[order])
                np.savez_compressed(str(f)[:-7] + ".origin.npz", cell=cell[order], noise=noise[order], cells=np.array(cells),
                                    n_reads=np.array([len(x[1]) for x in parts]))
                Path(str(f)[:-7] + ".json").write_text(json.dumps(
                    {"name": name, "k": k, "pool": p, "depth": depth, "eps": eps, "rc_rel": RC_REL, "set": args.set,
                     "truths": cells, "truth_dir": str(tdir / args.set), "cells": infos}, indent=1))
                man.append((name, str(f), k, p, depth, eps))
                print(name, len(pa), flush=True)
    with open(out / "manifest.tsv", "w") as fh:
        for row in man:
            fh.write("\t".join(map(str, row)) + "\n")


# --------------------------------------------------------------------------- real pools

STEVENS_SETS = {"dev": [1, 2, 3, 4], "test": [5, 6, 7, 8]}


def real_pools(dataset: str, cells: list[str], set_name: str):
    """(name, k, pool, member cells) of the registered real pools."""
    if dataset == "stevens":
        out = []
        for k in (2, 3, 4):
            for p, combo in enumerate(itertools.combinations(cells, k), 1):
                out.append((f"k{k}_p{p}", k, p, list(combo)))
        return out
    test = set_name == "test"
    out = []
    for k in KS:
        for p in range(1, N_POOLS[set_name] + 1):
            rng = np.random.default_rng(50_000 + (2000 if test else 0) + 1000 * k + p)
            idx = rng.choice(len(cells), size=k, replace=False)
            out.append((f"k{k}_p{p}", k, p, [cells[i] for i in sorted(idx)]))
    return out


def cmd_real(args) -> None:
    import pandas as pd
    out = Path(args.out) / args.set
    out.mkdir(parents=True, exist_ok=True)
    if args.dataset == "nagano":
        m = pd.read_csv(args.manifest, sep="\t")
        tables = dict(zip(m["cell"].astype(str), m["table"].astype(str)))
        cells = sorted(tables)
    else:
        files = sorted(args.tables)
        want = STEVENS_SETS[args.set]
        tables = {}
        for f in files:
            name = Path(f).name
            for c in want:
                if f"_Cell_{c}_" in name:
                    tables[f"cell{c}"] = f
        cells = [f"cell{c}" for c in want]
    cache = {}
    man = []
    for name, k, p, members in real_pools(args.dataset, cells, args.set):
        f = out / f"{name}.txt.gz"
        man.append((name, str(f), k, p, ",".join(members)))
        if f.exists() and not args.overwrite:
            continue
        parts = []
        for c in members:
            if c not in cache:
                cache[c] = read_contacts(tables[c])
            parts.append(cache[c])
        lines = [ln for c in parts for ln in c.lines]
        cell = np.concatenate([np.full(len(c), j, np.int16) for j, c in enumerate(parts)])
        order = np.random.default_rng(7 * p + k).permutation(len(lines))
        f.parent.mkdir(parents=True, exist_ok=True)
        import gzip
        with gzip.open(f, "wt") as fh:
            fh.write("#chr_A\tpos_A\tchr_B\tpos_B\n")
            for i in order:
                r = lines[i].split()
                if parts[0].fmt == "pairs":
                    r = r[1:5]
                fh.write("\t".join(r[:4]) + "\n")
        np.savez_compressed(str(f)[:-7] + ".origin.npz", cell=cell[order], cells=np.array(members),
                            n_reads=np.array([len(c) for c in parts]))
        Path(str(f)[:-7] + ".json").write_text(json.dumps(
            {"name": name, "k": k, "pool": p, "set": args.set, "dataset": args.dataset, "cells": members,
             "tables": [tables[c] for c in members]}, indent=1))
        print(name, len(lines), flush=True)
    with open(out / "manifest.tsv", "w") as fh:
        for row in man:
            fh.write("\t".join(map(str, row)) + "\n")
    with open(out / "cells.tsv", "w") as fh:
        for c in cells:
            fh.write(f"{c}\t{tables[c]}\n")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("truths")
    s.add_argument("--dataset", required=True, choices=["takei2021_1mb", "su2020_genome"])
    s.add_argument("--data")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_truths)
    s = sub.add_parser("pools")
    s.add_argument("--truth-dir", required=True)
    s.add_argument("--set", required=True, choices=["dev", "test"])
    s.add_argument("--ks", type=int, nargs="*")
    s.add_argument("--overwrite", action="store_true")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_pools)
    s = sub.add_parser("real")
    s.add_argument("--dataset", required=True, choices=["nagano", "stevens"])
    s.add_argument("--manifest", help="nagano: dev_manifest.tsv / heldback_manifest.tsv")
    s.add_argument("--tables", nargs="*", help="stevens: the 8 GEO contact tables")
    s.add_argument("--set", required=True, choices=["dev", "test"])
    s.add_argument("--overwrite", action="store_true")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_real)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
