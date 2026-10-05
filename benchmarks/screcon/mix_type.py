"""Cell-type-assisted few-cell deconvolution (PREREG §12.1): Tan 2021 Dip-C adult cortex.

Subcommands
-----------
``split``      reference / development / held-back roles of the cells (registered rule)::

                   python benchmarks/screcon/mix_type.py split --out MIX/type/split.tsv

``download``   the cells' hickit contacts (``*.contacts.pairs.txt.gz``, GEO GSE146397; the layout of
               ``example-data/download_data.py --tan2021_cortex``) for the given roles::

                   python benchmarks/screcon/mix_type.py download --split MIX/type/split.tsv --roles ref dev --data DATA

``reference``  per type, the pseudo-bulk contact map of the reference cells (every cell weighted
               1 / its contact count; phases ignored) on a genome-wide grid of ``--res``::

                   python benchmarks/screcon/mix_type.py reference --split ... --data DATA --res 1e6 --out MIX/type/ref_1mb.npz

``pools``      the registered pools of a set (compositions PO, PA, PM, OM, PAM, PP, PPO); also phased
               ``.pairs.gz`` versions of the pool and the per-cell tables (same rows, for the diploid runs)::

                   python benchmarks/screcon/mix_type.py pools --split ... --data DATA --set dev --out MIX/type/pools

               ``<name>.txt.gz`` (GEO 4-column table, rows of the cells in random order, phases dropped),
               ``.origin.npz`` (cell index per row), ``.json`` (cells, their types), per-cell tables
               ``<name>_cell<j>.txt.gz`` (the references are built from them).

``prior``      the type prior of a pool (``--params`` JSON: smooth, pseudo, gamma, radius)::

                   python benchmarks/screcon/mix_type.py prior --pool POOL.txt.gz --ref ref_1mb.npz --out POOL.prior.npy

               L_t = pseudo-bulk of type t, box-smoothed over (2 smooth + 1)^2 bins, plus pseudo x its
               mean, normalised; per pool row the log-propensity of its bin pair under each cell's type,
               summed over the pool's rows within ``radius`` bins (box, incl. the row itself) and
               multiplied by gamma; prior = softmax over the pool's cells (same-type cells tie).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

HERE = Path(__file__).resolve().parent
CELLS = HERE / "data" / "tan2021_adult_cortex_cells.tsv"
TYPES = {"P": "Cortical L2–5 Pyramidal Cell", "O": "Mature Oligodendrocyte", "A": "Adult Astrocyte",
         "M": "Microglia Etc."}
COMPOSITIONS = ["PO", "PA", "PM", "OM", "PAM", "PP", "PPO"]
N_POOLS = {"dev": 4, "test": 6}
SEED_SPLIT = 20261006
CHROMS = [f"chr{i}" for i in range(1, 20)] + ["chrX"]


def gsm_url(name: str) -> str:
    gsm = name.split("_", 1)[0]
    return f"https://ftp.ncbi.nlm.nih.gov/geo/samples/{gsm[:-3]}nnn/{gsm}/suppl/{name}"


def cell_file(data: Path, name: str) -> Path:
    return Path(data) / "tan2021_cortex" / "cells" / name / f"{name}.contacts.pairs.txt.gz"


# --------------------------------------------------------------------------- split

def split_table() -> pd.DataFrame:
    d = pd.read_csv(CELLS, sep="\t")
    rows = []
    for code, t in TYPES.items():
        sub = d[d.cell_type == t].sort_values("gsm").reset_index(drop=True)
        perm = np.random.default_rng(SEED_SPLIT).permutation(len(sub))
        n = len(sub)
        r = n // 2
        dv = (n - r) // 2
        for q, i in enumerate(perm):
            role = "ref" if q < r else ("dev" if q < r + dv else "test")
            rows.append({"gsm": sub.gsm[i], "name": sub["name"][i], "type": code, "cell_type": t, "role": role})
    return pd.DataFrame(rows)


def cmd_split(args) -> None:
    s = split_table()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    s.to_csv(args.out, sep="\t", index=False)
    print(s.groupby(["type", "role"]).size().unstack())


def cmd_download(args) -> None:
    s = pd.read_csv(args.split, sep="\t")
    s = s[s.role.isin(args.roles)]

    def get(row):
        f = cell_file(Path(args.data), row["name"])
        if f.exists():
            return 0
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".part")
        urllib.request.urlretrieve(gsm_url(f"{row['gsm']}_{row['name']}.contacts.pairs.txt.gz"), tmp)
        tmp.rename(f)
        return f.stat().st_size

    with ThreadPoolExecutor(args.threads) as ex:
        sizes = list(ex.map(get, [r for _, r in s.iterrows()]))
    print(f"{len(s)} cells, downloaded {sum(sizes) / 1e6:.0f} MB")


# --------------------------------------------------------------------------- contacts

def read_pairs(path) -> pd.DataFrame:
    """hickit pairs -> DataFrame chrom1, pos1, chrom2, pos2, phase0, phase1 ("." / 0 / 1), chromosomes of
    CHROMS only."""
    df = pd.read_csv(path, sep="\t", comment="#", header=None, usecols=[1, 2, 3, 4, 7, 8],
                     names=["chrom1", "pos1", "chrom2", "pos2", "phase0", "phase1"],
                     dtype={"chrom1": str, "chrom2": str, "pos1": np.int64, "pos2": np.int64, "phase0": str, "phase1": str})
    keep = df.chrom1.isin(CHROMS) & df.chrom2.isin(CHROMS)
    return df[keep].reset_index(drop=True)


def write_pairs(path, df) -> None:
    """hickit-style phased pairs (phase0 / phase1), strands unknown."""
    with gzip.open(path, "wt") as fh:
        fh.write("## pairs format v1.0\n#columns: readID chr1 pos1 chr2 pos2 strand1 strand2 phase0 phase1\n")
        for q, r in enumerate(zip(df.chrom1, df.pos1, df.chrom2, df.pos2, df.phase0, df.phase1)):
            fh.write("r%d\t%s\t%d\t%s\t%d\t.\t.\t%s\t%s\n" % ((q,) + r))


class Grid:
    """Genome-wide bins of `res` over CHROMS (mm10 lengths)."""

    def __init__(self, res: int):
        from contacts import MM10
        self.res = int(res)
        self.off = {}
        o = 0
        for c in CHROMS:
            self.off[c] = o
            o += MM10[c] // self.res + 1
        self.n = o

    def index(self, chrom, pos) -> np.ndarray:
        off = np.array([self.off[c] for c in chrom]) if not isinstance(chrom, str) else self.off[chrom]
        return off + np.asarray(pos) // self.res


def cmd_reference(args) -> None:
    s = pd.read_csv(args.split, sep="\t")
    g = Grid(args.res)
    out = {"res": g.res, "n": g.n}
    for code in TYPES:
        cells = s[(s.role == "ref") & (s.type == code)]
        M = np.zeros((g.n, g.n), np.float64)
        for name in cells["name"]:
            df = read_pairs(cell_file(Path(args.data), name))
            i, j = g.index(df.chrom1.to_numpy(), df.pos1.to_numpy()), g.index(df.chrom2.to_numpy(), df.pos2.to_numpy())
            a, b = np.minimum(i, j), np.maximum(i, j)
            np.add.at(M, (a, b), 1.0 / len(df))
        M = M + np.triu(M, 1).T
        out[code] = M.astype(np.float32)
        out[code + "_n_cells"] = len(cells)
        print(code, len(cells), "cells", flush=True)
    np.savez_compressed(args.out, **out)


# --------------------------------------------------------------------------- pools

def pool_cells(split: pd.DataFrame, comp: str, ci: int, p: int, set_name: str) -> list[str]:
    rng = np.random.default_rng((60_000 if set_name == "dev" else 70_000) + 100 * ci + p)
    out = []
    for code in sorted(set(comp)):
        need = comp.count(code)
        cand = split[(split.role == set_name) & (split.type == code)]["name"].tolist()
        pick = rng.choice(len(cand), size=need, replace=False)
        out += [cand[q] for q in sorted(pick)]
    # cell order = the composition order (types as declared)
    order = []
    for code in comp:
        for name in out:
            if name not in order and split.set_index("name").loc[name, "type"] == code:
                order.append(name)
                break
    return order


def write_geo(path, df) -> None:
    with gzip.open(path, "wt") as fh:
        fh.write("#chr_A\tpos_A\tchr_B\tpos_B\n")
        for r in zip(df.chrom1, df.pos1, df.chrom2, df.pos2):
            fh.write("%s\t%d\t%s\t%d\n" % r)


def cmd_pools(args) -> None:
    s = pd.read_csv(args.split, sep="\t")
    out = Path(args.out) / args.set
    out.mkdir(parents=True, exist_ok=True)
    tmap = s.set_index("name")["type"]
    man = []
    cache = {}
    for ci, comp in enumerate(COMPOSITIONS):
        for p in range(1, N_POOLS[args.set] + 1):
            cells = pool_cells(s, comp, ci, p, args.set)
            name = f"{comp}_p{p}"
            f = out / f"{name}.txt.gz"
            man.append((name, str(f), len(comp), p, comp, ",".join(cells)))
            if f.exists() and (out / f"{name}.pairs.gz").exists() and not args.overwrite:
                continue
            parts = []
            for j, c in enumerate(cells):
                if c not in cache:
                    cache[c] = read_pairs(cell_file(Path(args.data), c))
                parts.append(cache[c])
                if not (out / f"{name}_cell{j}.txt.gz").exists() or args.overwrite:
                    write_geo(out / f"{name}_cell{j}.txt.gz", cache[c])
                write_pairs(out / f"{name}_cell{j}.pairs.gz", cache[c])
            df = pd.concat(parts, ignore_index=True)
            cell = np.concatenate([np.full(len(x), j, np.int16) for j, x in enumerate(parts)])
            order = np.random.default_rng(7 * p + 11 * ci).permutation(len(df))
            if not f.exists() or args.overwrite:
                write_geo(f, df.iloc[order])
            write_pairs(out / f"{name}.pairs.gz", df.iloc[order])
            np.savez_compressed(out / f"{name}.origin.npz", cell=cell[order], cells=np.array(cells),
                                n_reads=np.array([len(x) for x in parts]))
            (out / f"{name}.json").write_text(json.dumps({
                "name": name, "k": len(comp), "pool": p, "composition": comp, "set": args.set, "dataset": "tan2021",
                "cells": cells, "types": [tmap[c] for c in cells],
                "tables": [str(out / f"{name}_cell{j}.txt.gz") for j in range(len(cells))]}, indent=1))
            print(name, len(df), flush=True)
    with open(out / "manifest.tsv", "w") as fh:
        for row in man:
            fh.write("\t".join(map(str, row)) + "\n")


# --------------------------------------------------------------------------- prior

def box(M: np.ndarray, r: int) -> np.ndarray:
    if r <= 0:
        return M
    from scipy.ndimage import uniform_filter
    return uniform_filter(M, size=2 * r + 1, mode="constant") * (2 * r + 1) ** 2


def type_prior(pool: str, ref, params: dict) -> np.ndarray:
    from contacts import read_contacts
    meta = json.loads(Path(pool[:-7] + ".json").read_text())
    types = meta["types"]
    k = len(types)
    smooth = int(params.get("smooth", 1))
    pseudo = float(params.get("pseudo", 0.1))
    gamma = float(params.get("gamma", 1.0))
    radius = int(params.get("radius", -1))
    res, n = int(ref["res"]), int(ref["n"])
    g = Grid(res)
    c = read_contacts(pool)
    ok = np.isin(c.chrom_a.astype(str), CHROMS) & np.isin(c.chrom_b.astype(str), CHROMS)
    i = np.zeros(len(c), np.int64)
    j = np.zeros(len(c), np.int64)
    i[ok] = g.index(c.chrom_a[ok].astype(str), c.pos_a[ok])
    j[ok] = g.index(c.chrom_b[ok].astype(str), c.pos_b[ok])
    a, b = np.minimum(i, j), np.maximum(i, j)
    # pool counts per bin pair (upper triangle)
    C = np.zeros((n, n), np.float32)
    np.add.at(C, (a[ok], b[ok]), 1.0)
    agg = {}
    for t in sorted(set(types)):
        L = box(ref[t].astype(np.float64), smooth)
        L = L + pseudo * L.mean()
        L = np.log(L / L.sum())
        if radius < 0:
            # every row on its own: the log-propensity of its bin pair
            agg[t] = L[a, b]
            continue
        L = np.triu(L)
        # neighbourhood sum over the pool's rows: Σ_{bins within radius} count x log L
        A = box(C * L, radius)
        agg[t] = A[a, b]
    S = np.stack([gamma * agg[t] for t in types], 1)
    grad = int(params.get("group_radius", 0))
    if grad > 0:
        # must-link groups (2-D single linkage of the long-range contacts, mostly of one cell): every
        # member gets the group's summed log-likelihood, tempered by gamma_group
        import uchrom_nucdyn as un
        grp = un.mix_groups(c.chrom_a.astype(str), c.pos_a, c.chrom_b.astype(str), c.pos_b, radius=grad,
                            min_sep=int(params.get("group_min_sep", 2_000_000)), tri_min=int(params.get("group_tri_min", 0)))
        inn = (grp >= 0) & ok
        ng = int(grp.max()) + 1 if inn.any() else 0
        G = np.zeros((ng, k))
        np.add.at(G, grp[inn], np.stack([agg[t] for t in types], 1)[inn])
        S[inn] = float(params.get("gamma_group", gamma)) * G[grp[inn]]
    S = S - S.max(1, keepdims=True)
    E = np.exp(S)
    # mixing proportions of the cells (depths differ): EM on the prior's own mixture
    pi = np.full(k, 1.0 / k)
    for _ in range(int(params.get("pi_iter", 20))):
        P = E * pi
        P /= P.sum(1, keepdims=True)
        pi = P[ok].mean(0)
        # cells of the same type are exchangeable: share their proportion
        for t in set(types):
            idx = [q for q in range(k) if types[q] == t]
            pi[idx] = pi[idx].mean()
    P = E * pi
    P /= P.sum(1, keepdims=True)
    P[~ok] = 1.0 / k
    return P


def cmd_prior(args) -> None:
    ref = dict(np.load(args.ref))
    P = type_prior(args.pool, ref, json.loads(args.params))
    np.save(args.out, P)
    if args.score:
        o = np.load(args.pool[:-7] + ".origin.npz")
        cell = o["cell"].astype(int)
        meta = json.loads(Path(args.pool[:-7] + ".json").read_text())
        best = P.argmax(1)
        print(f"{Path(args.pool).name}: types {meta['types']}, prior-only accuracy {np.mean(best == cell):.3f}, "
              f"mean max prior {P.max(1).mean():.3f}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_split)
    s = sub.add_parser("download")
    s.add_argument("--split", required=True)
    s.add_argument("--roles", nargs="+", required=True)
    s.add_argument("--data", required=True)
    s.add_argument("--threads", type=int, default=8)
    s.set_defaults(fn=cmd_download)
    s = sub.add_parser("reference")
    s.add_argument("--split", required=True)
    s.add_argument("--data", required=True)
    s.add_argument("--res", type=float, default=1e6)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_reference)
    s = sub.add_parser("pools")
    s.add_argument("--split", required=True)
    s.add_argument("--data", required=True)
    s.add_argument("--set", required=True, choices=["dev", "test"])
    s.add_argument("--overwrite", action="store_true")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_pools)
    s = sub.add_parser("prior")
    s.add_argument("--pool", required=True)
    s.add_argument("--ref", required=True)
    s.add_argument("--params", default="{}")
    s.add_argument("--score", action="store_true", help="DEVELOPMENT ONLY: print the prior-only accuracy")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_prior)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
