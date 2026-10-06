"""A spot reconstructed as one cell (PREREG §13): dominant-cell recovery of few-cell mixtures and spot QC.

Subcommands
-----------
``cells``      contact counts of the cells of a set (rows, cis >= 1 kb, other)::

                   python benchmarks/screcon/dominant.py cells --dataset nagano --set dev --manifest SPLIT/dev_manifest.tsv --out DOM/nagano/dev
                   python benchmarks/screcon/dominant.py cells --dataset stevens --set dev --tables GEO/*_contact_pairs.txt.gz --out DOM/stevens/dev
                   python benchmarks/screcon/dominant.py cells --dataset tan --set dev --data DATA --out DOM/tan/dev

``designs``    dominants and minor cells (registered rules) -> ``designs.json``::

                   python benchmarks/screcon/dominant.py designs --dir DOM/nagano/dev

``build``      per dominant ``<dir>/<dominant>/``: the cells' tables (``cells/``), the pure controls, the
               mixtures and the D-only controls (``tables/``) and ``manifest.tsv``::

                   python benchmarks/screcon/dominant.py build --dir DOM/nagano/dev [--only CELL]

``run``        every reconstruction of one dominant (references, pure, mixtures, D-only; skips existing
               outputs), in one process::

                   python benchmarks/screcon/dominant.py run --dir DOM/nagano/dev --dominant NST_2 --device gpu

``score``      E1 / E2 and the QC metrics of one dominant -> ``<dominant>/scores.tsv``::

                   python benchmarks/screcon/dominant.py score --dir DOM/nagano/dev --dominant NST_2

``aggregate``  tables over the scores of one or more sets -> ``--out`` (json + markdown)::

                   python benchmarks/screcon/dominant.py aggregate --scores DOM/*/dev/*/scores.tsv --out RESULTS

Conventions: cis = same chromosome with separation >= 1 kb; structures at 200 kb, 2 models per run; run
outputs ``runs/<table>.<method>.s<seed>.npz`` (+ ``.json``); methods ``ember`` / ``nucdyn``.
"""

from __future__ import annotations

import argparse
import gzip
import itertools
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

FS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)
LEVELS = (10_000, 30_000, 100_000, "full")
RES = 200_000
N_MODELS = 2
CIS_MIN = 1_000
SEED_DOM = {"dev": 20261013, "test": 20261014}
SEED_OFF = {"dev": 0, "test": 500_000}
N_DOM_NAGANO = 12
TAN_TYPES = ("P", "O", "A", "M")
TAN_CHROMS = [f"chr{i}" for i in range(1, 20)] + ["chrX", "chrY"]
#: EMber deep diploid (tag ember-deep-frozen): frozen haploid defaults + the deep settings
DEEP = {"robust_dip_commit": 0.75, "robust_dip_commit_drop": True, "robust_dip_readmit_stage": 4}
#: QC metrics and their registered direction (+1: larger = more mixed)
QC_DIR = {"q1_eps": 1, "q2_down": 1, "q3_viol": 1, "q4_repro": -1, "q5_trans_lr": -1, "q6_tri": -1, "q7_conflict": 1}


def flabel(f: float) -> str:
    return f"{f:.1f}"


# --------------------------------------------------------------------------- tables

def is_diploid(dataset: str) -> bool:
    return dataset == "tan"


def load_cell(path: str, dataset: str):
    """Contacts of a cell: ``contacts.Contacts`` (haploid) or ``diploid.Phased`` (Tan: chromosomes of
    ``TAN_CHROMS`` only)."""
    if is_diploid(dataset):
        from diploid import read_phased
        c = read_phased(path)
        keep = np.isin(c.chrom_a, TAN_CHROMS) & np.isin(c.chrom_b, TAN_CHROMS)
        c = c.subset(keep)
        c.lines = None
        return c
    from contacts import read_contacts
    c = read_contacts(path)
    c.chrom_a = c.chrom_a.astype(str)
    c.chrom_b = c.chrom_b.astype(str)
    c.lines = None
    return c


def cis_mask(c) -> np.ndarray:
    return (c.chrom_a == c.chrom_b) & (np.abs(c.pos_a - c.pos_b) >= CIS_MIN)


def write_table(path: Path, c, dataset: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if is_diploid(dataset):
        from diploid import write_phased
        write_phased(path, c)
    else:
        from contacts import write_geo
        write_geo(path, c.chrom_a, c.pos_a, c.chrom_b, c.pos_b)


def concat(parts, dataset: str):
    if is_diploid(dataset):
        from diploid import Phased
        return Phased(*(np.concatenate([getattr(p, a) for p in parts])
                        for a in ("chrom_a", "pos_a", "hap_a", "chrom_b", "pos_b", "hap_b")))
    from contacts import Contacts
    return Contacts(*(np.concatenate([getattr(p, a) for p in parts]) for a in ("chrom_a", "pos_a", "chrom_b", "pos_b")))


def table_ext(dataset: str) -> str:
    return ".pairs.gz" if is_diploid(dataset) else ".txt.gz"


# --------------------------------------------------------------------------- cells

def cmd_cells(args) -> None:
    import pandas as pd
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    if args.dataset == "nagano":
        m = pd.read_csv(args.manifest, sep="\t")
        items = sorted(zip(m["cell"].astype(str), m["table"].astype(str)))
        items = [(c, t, "") for c, t in items]
    elif args.dataset == "stevens":
        want = {"dev": [1, 2, 3, 4], "test": [5, 6, 7, 8]}[args.set]
        items = []
        for c in want:
            f = [t for t in args.tables if f"_Cell_{c}_" in Path(t).name]
            assert len(f) == 1, (c, f)
            items.append((f"cell{c}", f[0], ""))
    else:
        from mix_type import cell_file, split_table
        s = split_table()
        s = s[s.role == args.set].sort_values("gsm")
        items = [(n, str(cell_file(Path(args.data), n)), f"{t}:{g}") for n, t, g in zip(s["name"], s["type"], s["gsm"])]
    for cell, table, typ in items:
        c = load_cell(table, args.dataset)
        cis = cis_mask(c)
        rows.append({"cell": cell, "table": table, "type": typ, "n_rows": len(c), "n_cis": int(cis.sum()),
                     "n_other": int((~cis).sum())})
        print(cell, len(c), int(cis.sum()), flush=True)
    pd.DataFrame(rows).to_csv(out / "cells.tsv", sep="\t", index=False)
    (out / "set.json").write_text(json.dumps({"dataset": args.dataset, "set": args.set}))


# --------------------------------------------------------------------------- designs

def choose_designs(cells, dataset: str, set_name: str) -> dict:
    """Registered dominants and minor cells (PREREG §13).  ``cells``: DataFrame of ``cells.tsv``."""
    ncis = dict(zip(cells.cell, cells.n_cis))
    names = sorted(cells.cell)
    off = SEED_OFF[set_name]
    doms, designs = [], []
    if dataset == "nagano":
        elig = [c for c in names if ncis[c] >= 100_000]
        perm = np.random.default_rng(SEED_DOM[set_name]).permutation(len(elig))
        doms = [elig[i] for i in perm[:N_DOM_NAGANO]]
        for i, d in enumerate(doms):
            for m in (1, 2):
                cand = [c for c in names if c != d and ncis[c] >= ncis[d] / (2 * m)]
                if len(cand) < m:
                    cand = [c for c in names if c != d]
                rng = np.random.default_rng(130_000 + 10 * i + m + off)
                pick = rng.choice(len(cand), size=m, replace=False)
                designs.append({"dominant": d, "m": m, "minors": [cand[q] for q in pick]})
    elif dataset == "stevens":
        doms = names
        for d in doms:
            others = [c for c in names if c != d]
            for c in others:
                designs.append({"dominant": d, "m": 1, "minors": [c]})
            for pair in itertools.combinations(others, 2):
                designs.append({"dominant": d, "m": 2, "minors": list(pair)})
    else:
        typ = {c: t.split(":")[0] for c, t in zip(cells.cell, cells["type"])}
        gsm = {c: t.split(":")[1] for c, t in zip(cells.cell, cells["type"])}
        for t_i, t in enumerate(TAN_TYPES):
            sub = sorted([c for c in names if typ[c] == t], key=lambda c: gsm[c])
            perm = np.random.default_rng(SEED_DOM[set_name] + t_i).permutation(len(sub))
            doms += [sub[q] for q in perm[:2]]
        for i, d in enumerate(doms):
            for m in (1, 2):
                rng = np.random.default_rng(131_000 + 10 * i + m + off)
                need = ncis[d] / (2 * m)
                minors = []
                pools = ([("same", lambda c: typ[c] == typ[d])] if m == 2 else []) + [("other", lambda c: typ[c] != typ[d])]
                for _, rule in pools:
                    cand = [c for c in names if c != d and c not in minors and rule(c) and ncis[c] >= need]
                    if not cand:
                        cand = [c for c in names if c != d and c not in minors and rule(c)]
                    minors.append(cand[int(rng.integers(len(cand)))])
                designs.append({"dominant": d, "m": m, "minors": minors})
    for q, de in enumerate(designs):
        de["design"] = q
    return {"dataset": dataset, "set": set_name, "dominants": doms, "designs": designs}


def cmd_designs(args) -> None:
    import pandas as pd
    d = Path(args.dir)
    meta = json.loads((d / "set.json").read_text())
    cells = pd.read_csv(d / "cells.tsv", sep="\t", dtype={"cell": str, "type": str}).fillna("")
    res = choose_designs(cells, meta["dataset"], meta["set"])
    ncis = dict(zip(cells.cell, cells.n_cis))
    res["n_cis"] = {c: int(ncis[c]) for c in {*res["dominants"], *(x for de in res["designs"] for x in de["minors"])}}
    (d / "designs.json").write_text(json.dumps(res, indent=1))
    for de in res["designs"]:
        print(de["design"], de["dominant"], ncis[de["dominant"]], de["m"], [(x, ncis[x]) for x in de["minors"]])


# --------------------------------------------------------------------------- mixtures

class Sampler:
    """Nested row sampling of one cell: cis rows and other rows permuted once; ``take(t)`` = the first t
    cis rows and the same fraction of the other rows (indices into the cell's table)."""

    def __init__(self, c, seed: int):
        cis = cis_mask(c)
        rng = np.random.default_rng(seed)
        self.cis = np.flatnonzero(cis)[rng.permutation(int(cis.sum()))]
        self.oth = np.flatnonzero(~cis)[rng.permutation(int((~cis).sum()))]
        self.n_cis = len(self.cis)

    def take(self, t: int) -> np.ndarray:
        t = int(t)
        assert t <= self.n_cis, (t, self.n_cis)
        k = int(round(t * len(self.oth) / max(self.n_cis, 1)))
        return np.concatenate([self.cis[:t], self.oth[:k]])


def design_n(level, n_dom: int, n_minors: list[int], m: int) -> int:
    """N of a design at a level: the level (full = n_cis(D)) lowered so that every f is feasible."""
    n = n_dom if level == "full" else int(level)
    n = min(n, n_dom)
    for nm in n_minors:
        n = min(n, int(np.floor(nm * m / (1 - min(FS)))))
    return int(n)


def level_name(level) -> str:
    return "full" if level == "full" else f"{int(level) // 1000}k"


def cmd_build(args) -> None:
    d = Path(args.dir)
    meta = json.loads((d / "set.json").read_text())
    ds = meta["dataset"]
    des = json.loads((d / "designs.json").read_text())
    import pandas as pd
    cells = pd.read_csv(d / "cells.tsv", sep="\t", dtype={"cell": str, "type": str}).fillna("")
    tables = dict(zip(cells.cell, cells.table))
    ext = table_ext(ds)
    off = SEED_OFF[meta["set"]]
    for i, dom in enumerate(des["dominants"]):
        if args.only and dom not in args.only:
            continue
        od = d / dom
        (od / "tables").mkdir(parents=True, exist_ok=True)
        my = [de for de in des["designs"] if de["dominant"] == dom]
        used = [dom] + sorted({x for de in my for x in de["minors"]})
        cc = {}
        for c in used:
            cc[c] = load_cell(tables[c], ds)
            f = od / "cells" / f"{c}{ext}"
            if not f.exists():
                write_table(f, cc[c], ds)
        sd = Sampler(cc[dom], 140_000 + i + off)
        man = []

        def emit(name, kind, parts, info):
            f = od / "tables" / f"{name}{ext}"
            idx_cells = [np.full(len(ix), j, np.int16) for j, (_, ix) in enumerate(parts)]
            if not f.exists() or args.overwrite:
                sub = concat([cc[c].subset(ix) for c, ix in parts], ds)
                origin = np.concatenate(idx_cells)
                order = np.random.default_rng(7).permutation(len(origin))
                write_table(f, sub.subset(order), ds)
                np.savez_compressed(od / "tables" / f"{name}.origin.npz", cell=origin[order],
                                    cells=np.array([c for c, _ in parts]))
                cis_n = [int(cis_mask(cc[c].subset(ix)).sum()) for c, ix in parts]
                info = {**info, "name": name, "kind": kind, "cells": [c for c, _ in parts], "rows": [len(ix) for _, ix in parts],
                        "cis": cis_n, "f_realised": cis_n[0] / max(sum(cis_n), 1)}
                (od / "tables" / f"{name}.json").write_text(json.dumps(info, indent=1))
            man.append({"name": name, "kind": kind, **{k: info.get(k) for k in ("level", "N", "f", "m", "design")}})

        seen = set()
        for level in LEVELS:
            if level != "full" and sd.n_cis < int(level):
                continue
            for de in my:
                m = de["m"]
                n = design_n(level, sd.n_cis, [int(cis_mask(cc[x]).sum()) for x in de["minors"]], m)
                sm = [Sampler(cc[x], 150_000 + 100 * de["design"] + r + off) for r, x in enumerate(de["minors"])]
                base = {"level": level_name(level), "N": n, "m": m, "design": de["design"], "dominant": dom,
                        "minors": de["minors"]}
                pure = f"pure_N{n}"
                if pure not in seen:
                    seen.add(pure)
                    emit(pure, "pure", [(dom, sd.take(n))], {**base, "f": 1.0, "m": 0, "design": -1})
                for f in FS[1:]:
                    td = int(round(f * n))
                    tm = int(round((1 - f) * n / m))
                    parts = [(dom, sd.take(td))] + [(x, s.take(tm)) for x, s in zip(de["minors"], sm)]
                    emit(f"mix_d{de['design']}_N{n}_f{flabel(f)}", "mix", parts, {**base, "f": f})
                    don = f"donly_N{n}_f{flabel(f)}"
                    if don not in seen:
                        seen.add(don)
                        emit(don, "donly", [(dom, sd.take(td))], {**base, "f": f, "m": 0, "design": -1})
        # one manifest row per (table, level): pure / D-only tables shared across levels keep every level
        pd.DataFrame(man).drop_duplicates().to_csv(od / "manifest.tsv", sep="\t", index=False)
        (od / "dominant.json").write_text(json.dumps({"dataset": ds, "set": meta["set"], "dominant": dom, "index": i,
                                                       "cells": used, "designs": my}, indent=1))
        print(dom, len(man), "tables", flush=True)


# --------------------------------------------------------------------------- reconstruction

def reconstruct(table: Path, out: Path, method: str, seed: int, ds: str, device: str) -> dict:
    """One reconstruction (2 models, 200 kb) -> ``out`` (.npz) and ``out.json``."""
    import uchrom_nucdyn as un
    from run_nucdyn import schedule
    from run_robust import ROBUST_DEFAULTS
    sizes = schedule(RES)
    if method == "ember":
        proto, params = "robust", {**ROBUST_DEFAULTS, **(DEEP if is_diploid(ds) else {})}
    else:
        proto, params = "nuc_dynamics_2017", {}
    t0 = time.time()
    if is_diploid(ds):
        from diploid import copy_name
        c = un.read_phased_contacts(str(table))
        res = un.calc_genome_structure(c["chrom_a"].astype(str), c["pos_a"], c["chrom_b"].astype(str), c["pos_b"],
                                       protocol=proto, hap_a=c["hap_a"], hap_b=c["hap_b"], ploidy="male",
                                       particle_sizes=sizes, n_models=N_MODELS, seed=seed, device=device,
                                       verbose=False, **params)
        k = res["ploidy"]
        chrom = np.array([copy_name(ch, h, k[ch]) for ch, h in zip(res["chrom"].astype(str), res["copy"])])
        n_rows = len(c["pos_a"])
    else:
        from contacts import read_contacts
        c = read_contacts(table)
        res = un.calc_genome_structure(c.chrom_a.astype(str), c.pos_a, c.chrom_b.astype(str), c.pos_b, protocol=proto,
                                       particle_sizes=sizes, n_models=N_MODELS, seed=seed, device=device,
                                       verbose=False, **params)
        chrom = res["chrom"].astype(str)
        n_rows = len(c)
    wall = time.time() - t0
    pos = np.asarray(res["position"], np.int64)
    if res["position_convention"] == "start":
        pos = pos + int(res["particle_size"])
    extra = {}
    if res.get("contact_weights") is not None:
        extra["contact_weights"] = np.asarray(res["contact_weights"], np.float32)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, chrom=chrom, pos=pos, coords=np.asarray(res["coords"], np.float32), **extra)
    meta = {"table": str(table), "method": method, "protocol": proto, "seed": seed, "n_rows": n_rows,
            "particle_sizes": sizes, "n_models": N_MODELS, "wall_seconds": wall, "stages": res["stages"],
            "engine_version": un.__version__, "slurm_job_id": os.environ.get("SLURM_JOB_ID")}
    Path(str(out) + ".json").write_text(json.dumps(meta, default=str))
    return meta


def run_list(od: Path, ds: str) -> list[tuple[Path, str, int]]:
    """(table, method, seed) of every run of a dominant, references first."""
    import pandas as pd
    dj = json.loads((od / "dominant.json").read_text())
    ext = table_ext(ds)
    jobs = [(od / "cells" / f"{dj['dominant']}{ext}", "ember", 1), (od / "cells" / f"{dj['dominant']}{ext}", "nucdyn", 1)]
    jobs += [(od / "cells" / f"{c}{ext}", "ember", 1) for c in dj["cells"][1:]]
    man = pd.read_csv(od / "manifest.tsv", sep="\t").drop_duplicates("name")
    order = {"pure": 0, "mix": 1, "donly": 2}
    man = man.assign(o=man.kind.map(order)).sort_values(["o", "N", "f"], ascending=[True, True, False])
    for name, kind in zip(man.name, man.kind):
        t = od / "tables" / f"{name}{ext}"
        if kind == "donly":
            jobs.append((t, "ember", 2))
        else:
            jobs += [(t, "ember", 2), (t, "ember", 3), (t, "nucdyn", 2)]
    return jobs


def run_path(table: Path, method: str, seed: int) -> Path:
    stem = table.name.split(".")[0]
    return table.parent.parent / "runs" / f"{table.parent.name}.{stem}.{method}.s{seed}.npz"


def cmd_run(args) -> None:
    d = Path(args.dir)
    ds = json.loads((d / "set.json").read_text())["dataset"]
    od = d / args.dominant
    jobs = run_list(od, ds)
    t0 = time.time()
    done = 0
    for table, method, seed in jobs:
        out = run_path(table, method, seed)
        if out.exists() and not args.force:
            continue
        meta = reconstruct(table, out, method, seed, ds, args.device)
        done += 1
        print(f"{out.name}\t{meta['n_rows']}\t{meta['wall_seconds']:.1f}", flush=True)
    print(f"{args.dominant}: {done} runs of {len(jobs)} in {time.time() - t0:.0f} s", flush=True)


# --------------------------------------------------------------------------- scoring

def load_run(path: Path):
    z = np.load(path, allow_pickle=False)
    X = np.asarray(z["coords"], np.float64)
    w = np.asarray(z["contact_weights"], float) if "contact_weights" in z.files else None
    return z["chrom"].astype(str), z["pos"].astype(np.int64), X, w


def _keys(chrom, pos):
    return np.char.add(np.char.add(chrom, ":"), pos.astype(str))


class Comparer:
    """Distances of a reference structure on its particles; ``compare`` matches another run by (chain,
    position) and returns per-copy (median over chains, all within-chain pairs), whole-genome (random
    pairs) and per-band r."""

    def __init__(self, chrom, pos, X, n_whole=200_000, seed=0):
        self.key = _keys(chrom, pos)
        self.chrom, self.pos = chrom, pos
        self.Xm = X                           # (M, N, 3)
        self.rng_seed = seed
        self.n_whole = n_whole

    def compare(self, chrom, pos, X) -> dict:
        from scipy import stats
        k = _keys(chrom, pos)
        common, ia, ib = np.intersect1d(self.key, k, return_indices=True)
        if len(common) < 100:
            return {"per_copy_r": np.nan, "whole_r": np.nan, "n_matched": int(len(common))}
        A, B = self.Xm[:, ia], X[:, ib]
        ch, ps = self.chrom[ia], self.pos[ia]
        out_c, out_s = [], []
        bands = {"lt2mb": ([], []), "2-20mb": ([], []), "gt20mb": ([], [])}
        for c in np.unique(ch):
            sel = np.flatnonzero(ch == c)
            if len(sel) < 50:
                continue
            sel = sel[np.argsort(ps[sel])]
            iu, ju = np.triu_indices(len(sel), 1)
            da = np.linalg.norm(A[:, sel[iu]] - A[:, sel[ju]], axis=2).mean(0)
            db = np.linalg.norm(B[:, sel[iu]] - B[:, sel[ju]], axis=2).mean(0)
            out_c.append(np.corrcoef(da, db)[0, 1])
            out_s.append(stats.spearmanr(da, db).statistic)
            sep = np.abs(ps[sel[iu]] - ps[sel[ju]])
            for name, lo, hi in (("lt2mb", 0, 2e6), ("2-20mb", 2e6, 2e7), ("gt20mb", 2e7, 1e12)):
                s = (sep >= lo) & (sep < hi)
                bands[name][0].append(da[s]); bands[name][1].append(db[s])
        rng = np.random.default_rng(self.rng_seed)
        i, j = rng.integers(0, len(common), self.n_whole), rng.integers(0, len(common), self.n_whole)
        ok = i != j
        wa = np.linalg.norm(A[:, i[ok]] - A[:, j[ok]], axis=2).mean(0)
        wb = np.linalg.norm(B[:, i[ok]] - B[:, j[ok]], axis=2).mean(0)
        res = {"per_copy_r": float(np.median(out_c)) if out_c else np.nan,
               "per_copy_rho": float(np.median(out_s)) if out_s else np.nan,
               "whole_r": float(np.corrcoef(wa, wb)[0, 1]), "whole_rho": float(stats.spearmanr(wa, wb).statistic),
               "n_matched": int(len(common)), "n_chains": len(out_c)}
        for name, (u, v) in bands.items():
            u, v = np.concatenate(u) if u else np.array([]), np.concatenate(v) if v else np.array([])
            res[f"band_{name}_r"] = float(np.corrcoef(u, v)[0, 1]) if len(u) > 10 else np.nan
        return res


def last_eps(meta: dict):
    for st in reversed(meta.get("stages") or []):
        em = st.get("robust") or []
        if em:
            return float(em[-1]["eps"]), float(em[-1].get("frac_low", np.nan))
    return np.nan, np.nan


def violation_rate(c, chrom, pos, X, diploid: bool) -> float:
    """Fraction of the input contacts >= 400 kb apart (or trans) whose model-mean distance exceeds 2 bead
    units; diploid: the closest copy pair consistent with the phased ends."""
    from contacts import ParticleIndex
    from metrics import bead_unit
    unit = bead_unit(chrom, X)
    pidx = ParticleIndex(chrom, pos)
    sep = np.where(c.chrom_a == c.chrom_b, np.abs(c.pos_a - c.pos_b), 10 ** 12)
    sel = sep >= 2 * RES
    ca, pa, cb, pb = c.chrom_a[sel], c.pos_a[sel], c.chrom_b[sel], c.pos_b[sel]

    def cands(ch, p, hap):
        plain = pidx(ch, p)
        if not diploid:
            return [plain, plain]
        c0 = pidx(np.char.add(ch.astype(str), "(0)"), p)
        c1 = pidx(np.char.add(ch.astype(str), "(1)"), p)
        c0 = np.where(c0 >= 0, c0, plain)
        c1 = np.where(c1 >= 0, c1, plain)
        if hap is not None:
            c0 = np.where(hap == 1, c1, c0)
            c1 = np.where(hap == 0, c0, c1)
        return [c0, c1]

    ha = c.hap_a[sel] if diploid else None
    hb = c.hap_b[sel] if diploid else None
    A, B = cands(ca, pa, ha), cands(cb, pb, hb)
    Xm = X
    dmin = np.full(len(pa), np.inf)
    for ia in A:
        for ib in B:
            ok = (ia >= 0) & (ib >= 0)
            d = np.full(len(pa), np.inf)
            d[ok] = np.linalg.norm(Xm[:, ia[ok]] - Xm[:, ib[ok]], axis=2).mean(0)
            dmin = np.minimum(dmin, d)
    fin = np.isfinite(dmin)
    return float((dmin[fin] / unit > 2.0).mean()) if fin.any() else np.nan


def graph_metrics(c) -> dict:
    """Q5 long-range transitivity, Q6 trans-triangle closure (1 Mb bins), Q7 partner conflict (10 kb)."""
    from scipy import sparse
    res = 1_000_000
    chroms = sorted(set(c.chrom_a) | set(c.chrom_b))
    off, o = {}, 0
    for ch in chroms:
        mx = max(c.pos_a[c.chrom_a == ch].max(initial=0), c.pos_b[c.chrom_b == ch].max(initial=0))
        off[ch] = o
        o += int(mx // res) + 1
    n = o
    ci = {ch: q for q, ch in enumerate(chroms)}
    a = np.array([off[x] for x in c.chrom_a]) + c.pos_a // res
    b = np.array([off[x] for x in c.chrom_b]) + c.pos_b // res
    trans = c.chrom_a != c.chrom_b
    lr = trans | (np.abs(c.pos_a - c.pos_b) >= 2_000_000)
    bin_chrom = np.zeros(n, np.int64)
    for ch in chroms:
        bin_chrom[off[ch]:] = ci[ch]

    def adj(sel):
        u, v = a[sel], b[sel]
        k = u != v
        u, v = u[k], v[k]
        M = sparse.coo_matrix((np.ones(len(u)), (u, v)), shape=(n, n)).tocsr()
        M = ((M + M.T) > 0).astype(np.float64)
        return M

    A = adj(lr)
    deg = np.asarray(A.sum(1)).ravel()
    wedges = float((deg * (deg - 1)).sum())
    closed = float(A.multiply(A @ A).sum())
    out = {"q5_trans_lr": closed / wedges if wedges > 0 else np.nan, "n_lr_edges": int(A.nnz // 2)}
    T = adj(trans)
    closed_t = float(T.multiply(T @ T).sum()) / 2.0             # closed wedges (b; p, q), p-q trans
    Tc = T.tocoo()
    # wedges at b with partners on two different chromosomes: C(deg, 2) - sum over chroms C(n_bc, 2)
    deg_t = np.asarray(T.sum(1)).ravel()
    per = sparse.coo_matrix((np.ones(Tc.nnz), (Tc.row, bin_chrom[Tc.col])), shape=(n, len(chroms))).tocsr()
    per.sum_duplicates()
    same = np.asarray(per.multiply(per).sum(1)).ravel() - np.asarray(per.sum(1)).ravel()
    w = float((deg_t * (deg_t - 1)).sum() - same.sum()) / 2.0
    out["q6_tri"] = closed_t / w if w > 0 else np.nan
    # Q7: ends of long-range rows sorted by (chrom, pos); pairs within 10 kb
    ec = np.concatenate([c.chrom_a[lr], c.chrom_b[lr]])
    ep = np.concatenate([c.pos_a[lr], c.pos_b[lr]])
    pc = np.concatenate([c.chrom_b[lr], c.chrom_a[lr]])
    pp = np.concatenate([c.pos_b[lr], c.pos_a[lr]])
    rid = np.concatenate([np.arange(lr.sum()), np.arange(lr.sum())])
    eci = np.array([ci[x] for x in ec]); pci = np.array([ci[x] for x in pc])
    o_ = np.lexsort((ep, eci))
    eci, ep, pci, pp, rid = eci[o_], ep[o_], pci[o_], pp[o_], rid[o_]
    n_pairs = n_conf = 0
    for k in range(1, 10_000):
        if k >= len(ep):
            break
        near = (eci[k:] == eci[:-k]) & (ep[k:] - ep[:-k] <= 10_000)
        if not near.any():
            break
        near &= rid[k:] != rid[:-k]
        conf = (pci[k:] != pci[:-k]) | (np.abs(pp[k:] - pp[:-k]) > 5_000_000)
        n_pairs += int(near.sum())
        n_conf += int((near & conf).sum())
    out["q7_conflict"] = n_conf / n_pairs if n_pairs else np.nan
    out["n_conflict_pairs"] = n_pairs
    return out


def cmd_score(args) -> None:
    import pandas as pd
    d = Path(args.dir)
    meta = json.loads((d / "set.json").read_text())
    ds = meta["dataset"]
    dip = is_diploid(ds)
    od = d / args.dominant
    dj = json.loads((od / "dominant.json").read_text())
    ext = table_ext(ds)
    dom = dj["dominant"]
    ref = lambda c, m="ember": run_path(od / "cells" / f"{c}{ext}", m, 1)  # noqa: E731
    cmp_e = Comparer(*load_run(ref(dom))[:3])
    cmp_n = Comparer(*load_run(ref(dom, "nucdyn"))[:3])
    cmp_minor = {c: Comparer(*load_run(ref(c))[:3]) for c in dj["cells"][1:]}
    # reference self-agreement (seed 1 vs seed 2 on the full table is the pure "full" control)
    man = pd.read_csv(od / "manifest.tsv", sep="\t")
    rows = []
    tinfo = {}
    for name in man.name.unique():
        info = json.loads((od / "tables" / f"{name}.json").read_text())
        tinfo[name] = info
    for _, r in man.iterrows():
        name = r["name"]
        info = tinfo[name]
        t = od / "tables" / f"{name}{ext}"
        row = {"dataset": ds, "set": meta["set"], "dominant": dom, "name": name, "kind": r["kind"], "level": r["level"],
               "N": info["N"], "f": info["f"], "f_realised": info["f_realised"], "m": info["m"], "design": info["design"],
               "minors": ",".join(info.get("minors") or []) if r["kind"] == "mix" else "", "n_rows": int(sum(info["rows"])),
               "n_cis": int(sum(info["cis"]))}
        p2 = run_path(t, "ember", 2)
        if not p2.exists():
            row["missing"] = 1
            rows.append(row)
            continue
        ch, ps, X2, w2 = load_run(p2)
        e = cmp_e.compare(ch, ps, X2)
        row.update({f"e1_{k}": v for k, v in e.items()})
        m2 = json.loads(Path(str(p2) + ".json").read_text())
        row["wall_ember"] = m2["wall_seconds"]
        if r["kind"] != "donly":
            eps, frac_low = last_eps(m2)
            row["q1_eps"] = eps
            row["frac_low_engine"] = frac_low
            row["q2_down"] = float(np.mean(~(np.nan_to_num(w2, nan=-1.0) >= 0.5))) if w2 is not None else np.nan
            row["frac_filtered"] = float(np.mean(~np.isfinite(w2))) if w2 is not None else np.nan
            c = load_cell(str(t), ds)
            row["q3_viol"] = violation_rate(c, ch, ps, X2, dip)
            p3 = run_path(t, "ember", 3)
            if p3.exists():
                ch3, ps3, X3, _ = load_run(p3)
                row["q4_repro"] = Comparer(ch, ps, X2).compare(ch3, ps3, X3)["per_copy_r"]
            row.update(graph_metrics(c))
            pn = run_path(t, "nucdyn", 2)
            if pn.exists():
                chn, psn, Xn, _ = load_run(pn)
                row["nd_e1_per_copy_r"] = cmp_e.compare(chn, psn, Xn)["per_copy_r"]
                row["nd_e1_whole_r"] = cmp_e.compare(chn, psn, Xn)["whole_r"]
                row["nd_own_per_copy_r"] = cmp_n.compare(chn, psn, Xn)["per_copy_r"]
                row["wall_nucdyn"] = json.loads(Path(str(pn) + ".json").read_text())["wall_seconds"]
            if r["kind"] == "mix":
                for q, mc in enumerate(info["minors"]):
                    row[f"minor{q}_per_copy_r"] = cmp_minor[mc].compare(ch, ps, X2)["per_copy_r"]
        rows.append(row)
        print(name, r["level"], f"{row.get('e1_per_copy_r', np.nan):.3f}", flush=True)
    pd.DataFrame(rows).to_csv(od / "scores.tsv", sep="\t", index=False)


# --------------------------------------------------------------------------- aggregation

def boot_mean(values: dict, n_boot=2000, seed=0):
    """Mean over units (dict unit -> list of values) and 95 % percentile CI resampling units."""
    keys = [k for k, v in values.items() if len(v)]
    if not keys:
        return np.nan, np.nan, np.nan
    per = np.array([np.mean(values[k]) for k in keys])
    cnt = np.array([len(values[k]) for k in keys])
    est = float((per * cnt).sum() / cnt.sum())
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(n_boot):
        q = rng.integers(0, len(keys), len(keys))
        bs.append((per[q] * cnt[q]).sum() / cnt[q].sum())
    return est, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def auc_dir(pos, neg, direction) -> float:
    from metrics import roc_auc
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    pos, neg = pos[np.isfinite(pos)], neg[np.isfinite(neg)]
    # mixed = the "positive" class of the score direction * value
    return roc_auc(direction * neg, direction * pos)


def youden(pos, neg, direction):
    """Threshold on direction * value maximising sensitivity + specificity − 1 (mixed = flagged)."""
    s_mixed = direction * np.asarray(neg, float)
    s_single = direction * np.asarray(pos, float)
    s_mixed, s_single = s_mixed[np.isfinite(s_mixed)], s_single[np.isfinite(s_single)]
    cand = np.unique(np.concatenate([s_mixed, s_single]))
    best = (-1, np.nan, np.nan, np.nan)
    for t in cand:
        sens = float((s_mixed >= t).mean())
        spec = float((s_single < t).mean())
        if sens + spec - 1 > best[0]:
            best = (sens + spec - 1, t, sens, spec)
    j, t, sens, spec = best
    return {"threshold": float(direction * t) if np.isfinite(t) else np.nan, "J": j, "sens": sens, "spec": spec,
            "flag_if": ">=" if direction > 0 else "<="}


def cmd_aggregate(args) -> None:
    import pandas as pd
    df = pd.concat([pd.read_csv(f, sep="\t") for f in args.scores], ignore_index=True)
    df = df[df.get("missing", 0).fillna(0) != 1] if "missing" in df else df
    out = {"n_rows": len(df)}
    levels = ["10k", "30k", "100k", "full"]
    lines = []
    e1 = {}
    for ds, g in df.groupby("dataset"):
        e1[ds] = {}
        pure = g[g.kind == "pure"].drop_duplicates(["dominant", "N"]).set_index(["dominant", "N"])
        donly = g[g.kind == "donly"].drop_duplicates(["dominant", "N", "f"]).set_index(["dominant", "N", "f"])
        mix = g[g.kind == "mix"]
        for lv in levels:
            gl = mix[mix.level == lv]
            if not len(gl):
                continue
            rec = {}
            for m in ("all", 1, 2):
                gm = gl if m == "all" else gl[gl.m == m]
                rows = {}
                for f in FS[1:]:
                    gf = gm[np.isclose(gm.f, f)]
                    vals, dvals, dep, mixe, e2, e2own, ndv = {}, {}, {}, {}, {}, {}, {}
                    for _, r in gf.iterrows():
                        u = r.dominant
                        key = (r.dominant, r.N)
                        p = pure.loc[key] if key in pure.index else None
                        dn = donly.loc[(r.dominant, r.N, r.f)] if (r.dominant, r.N, r.f) in donly.index else None
                        vals.setdefault(u, []).append(r.e1_per_copy_r)
                        if p is not None:
                            dvals.setdefault(u, []).append(r.e1_per_copy_r - p.e1_per_copy_r)
                            if dn is not None:
                                dep.setdefault(u, []).append(dn.e1_per_copy_r - p.e1_per_copy_r)
                        if dn is not None:
                            mixe.setdefault(u, []).append(r.e1_per_copy_r - dn.e1_per_copy_r)
                        if np.isfinite(r.get("nd_e1_per_copy_r", np.nan)):
                            e2.setdefault(u, []).append(r.e1_per_copy_r - r.nd_e1_per_copy_r)
                            ndv.setdefault(u, []).append(r.nd_e1_per_copy_r)
                    rows[flabel(f)] = {"n": int(len(gf)), "E1": boot_mean(vals), "dE1": boot_mean(dvals),
                                       "depth_effect": boot_mean(dep), "mixing_effect": boot_mean(mixe),
                                       "E1_nucdyn": boot_mean(ndv), "E2": boot_mean(e2)}
                fdrop = None
                for f in FS[1:]:
                    v = rows[flabel(f)]["dE1"][0]
                    if np.isfinite(v) and v < -0.05:
                        fdrop = f
                        break
                rec[str(m)] = {"by_f": rows, "f_drop": fdrop}
            pl = g[(g.kind == "pure") & (g.level == lv)].drop_duplicates(["dominant", "N"])
            rec["pure"] = {"E1": boot_mean({u: list(x.e1_per_copy_r) for u, x in pl.groupby("dominant")}),
                           "E1_nucdyn": boot_mean({u: list(x.nd_e1_per_copy_r) for u, x in pl.groupby("dominant")}),
                           "repro": boot_mean({u: list(x.q4_repro) for u, x in pl.groupby("dominant")}),
                           "n_cis": float(pl.n_cis.mean()) if len(pl) else np.nan}
            # E2 over every f < 1 mixture of the level
            e2all = {}
            for _, r in gl.iterrows():
                if np.isfinite(r.get("nd_e1_per_copy_r", np.nan)):
                    e2all.setdefault(r.dominant, []).append(r.e1_per_copy_r - r.nd_e1_per_copy_r)
            rec["E2_all_f"] = boot_mean(e2all)
            e1[ds][lv] = rec
    out["E1"] = e1
    # E3: QC
    qc = {}
    for ds, g in df.groupby("dataset"):
        qc[ds] = {}
        units = pd.concat([g[g.kind == "pure"].drop_duplicates(["dominant", "N", "level"]), g[g.kind == "mix"]])
        units = units[~np.isclose(units.f, 0.7)]
        units = units.assign(single=units.f >= 0.8 - 1e-9)
        for q, dirn in QC_DIR.items():
            if q not in units:
                continue
            per_level = {}
            for lv in levels:
                ul = units[units.level == lv]
                if not len(ul) or ul.single.all() or (~ul.single).all():
                    continue
                a = auc_dir(ul[ul.single][q], ul[~ul.single][q], dirn)
                # bootstrap over dominants
                doms = ul.dominant.unique()
                rng = np.random.default_rng(0)
                bs = []
                for _ in range(1000):
                    pick = rng.choice(doms, len(doms))
                    ub = pd.concat([ul[ul.dominant == x] for x in pick])
                    if ub.single.all() or (~ub.single).all():
                        continue
                    bs.append(auc_dir(ub[ub.single][q], ub[~ub.single][q], dirn))
                yd = youden(ul[ul.single][q], ul[~ul.single][q], dirn)
                rho = ul[[q, "e1_per_copy_r"]].corr(method="spearman").iloc[0, 1]
                per_level[lv] = {"auc": a, "ci": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))] if bs else None,
                                 "n_single": int(ul.single.sum()), "n_mixed": int((~ul.single).sum()), "youden": yd,
                                 "spearman_vs_e1": float(rho)}
            qc[ds][q] = {"levels": per_level,
                         "auc_mean": float(np.mean([v["auc"] for v in per_level.values()])) if per_level else np.nan}
    out["QC"] = qc
    # best metric: mean over datasets of the per-dataset AUC
    means = {}
    for q in QC_DIR:
        v = [qc[ds][q]["auc_mean"] for ds in qc if q in qc[ds] and np.isfinite(qc[ds][q]["auc_mean"])]
        if v:
            means[q] = float(np.mean(v))
    out["QC_mean_auc"] = means
    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / "dominant_dev.json").write_text(json.dumps(out, indent=1, default=float))
    # markdown
    fmt = lambda t: "–" if not np.isfinite(t[0]) else f"{t[0]:+.3f} [{t[1]:+.3f}, {t[2]:+.3f}]"  # noqa: E731
    fm0 = lambda t: "–" if not np.isfinite(t[0]) else f"{t[0]:.3f}"  # noqa: E731
    lines.append("## E1 / E2 by dataset, depth and f (all designs; mean [95 % CI over dominants])\n")
    for ds, rec in e1.items():
        lines.append(f"### {ds}\n")
        lines.append("| level | pure E1 (EMber) | pure E1 (NucDyn) | f | E1 | ΔE1 vs pure | depth effect | mixing effect | E1 NucDyn | E2 EMber − NucDyn | f_drop |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for lv, r in rec.items():
            for f, x in r["all"]["by_f"].items():
                lines.append(f"| {lv} | {fm0(r['pure']['E1'])} | {fm0(r['pure']['E1_nucdyn'])} | {f} | {fm0(x['E1'])} | {fmt(x['dE1'])} | "
                             f"{fmt(x['depth_effect'])} | {fmt(x['mixing_effect'])} | {fm0(x['E1_nucdyn'])} | {fmt(x['E2'])} | "
                             f"{r['all']['f_drop'] if r['all']['f_drop'] else 'none'} |")
        lines.append("")
    lines.append("## E3 QC: ROC-AUC (single-cell-like f >= 0.8 vs mixed f <= 0.6; registered direction)\n")
    for ds, rec in qc.items():
        lines.append(f"### {ds}\n")
        lines.append("| metric | " + " | ".join(levels) + " | mean |")
        lines.append("| --- |" + " --- |" * (len(levels) + 1))
        for q, x in rec.items():
            cells = []
            for lv in levels:
                v = x["levels"].get(lv)
                cells.append("–" if v is None else f"{v['auc']:.2f}" + (f" [{v['ci'][0]:.2f}, {v['ci'][1]:.2f}]" if v["ci"] else ""))
            lines.append(f"| {q} | " + " | ".join(cells) + f" | {x['auc_mean']:.3f} |")
        lines.append("")
    lines.append("Mean AUC over datasets: " + ", ".join(f"{q} {v:.3f}" for q, v in sorted(means.items(), key=lambda t: -t[1])))
    (Path(args.out) / "dominant_dev.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("cells")
    s.add_argument("--dataset", required=True, choices=["nagano", "stevens", "tan"])
    s.add_argument("--set", required=True, choices=["dev", "test"])
    s.add_argument("--manifest")
    s.add_argument("--tables", nargs="*")
    s.add_argument("--data")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_cells)
    s = sub.add_parser("designs")
    s.add_argument("--dir", required=True)
    s.set_defaults(fn=cmd_designs)
    s = sub.add_parser("build")
    s.add_argument("--dir", required=True)
    s.add_argument("--only", nargs="*")
    s.add_argument("--overwrite", action="store_true")
    s.set_defaults(fn=cmd_build)
    s = sub.add_parser("run")
    s.add_argument("--dir", required=True)
    s.add_argument("--dominant", required=True)
    s.add_argument("--device", default="gpu", choices=["cpu", "gpu"])
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser("score")
    s.add_argument("--dir", required=True)
    s.add_argument("--dominant", required=True)
    s.set_defaults(fn=cmd_score)
    s = sub.add_parser("aggregate")
    s.add_argument("--scores", nargs="+", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_aggregate)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
