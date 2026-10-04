"""High-resolution diploid EMber on scMicro-C GM12878 (Wu et al. 2025): a demonstration for Fig. 3.

Not part of the pre-registered tests (``PREREG.md``): EMber with its frozen diploid defaults, nothing tuned.

Subcommands
-----------
``count``   Contacts per cell of hickit phased ``.pairs[.gz]``: rows, unique contacts (both ends
            ordered, exact duplicates removed), fraction of phased ends, cis fraction -> TSV, deepest first.

``score``   Agreement of diploid models (``.npz`` copy chains, ``diploid.py`` convention) at high
            resolution, where full per-chain distance matrices do not fit in memory: Pearson r of the
            distances of random particle pairs (``--pairs`` per copy chain, same pairs for every
            model; median over chains = ``per_copy_r``; ``--pairs`` over the whole genome, homologs
            and trans included = ``whole_r``; ``--pairs`` within-chain pairs per separation band
            < 2 Mb / 2-20 Mb / > 20 Mb, pooled over chains = ``band_r``) between
            * the two seeds of a run (``--a`` / ``--b``: every model of a vs every model of b, median);
            * the models and the authors' hickit structure on the same grid (``--ref``,
              ``diploid_real.py ref``), median over models.
            Particles are matched by (copy chain, position).

    python benchmarks/screcon/highres.py count --out counts.tsv DATA/*.impute.pairs.gz
    python benchmarks/screcon/highres.py score --a RUN/s1.npz --b RUN/s2.npz --ref REF/hickit_5kb.npz --out S.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _columns(path: str) -> list[str]:
    with (gzip.open(path, "rt") if path.endswith(".gz") else open(path)) as fh:
        for line in fh:
            if not line.startswith("#"):
                break
            if line.startswith("#columns:"):
                return line.split()[1:]
    raise ValueError(f"{path}: no #columns: header")


def count_cell(path: str) -> dict:
    import pandas as pd
    cols = _columns(path)
    use = ["chr1", "pos1", "chr2", "pos2", "phase0", "phase1"]
    df = pd.read_csv(path, sep="\t", comment="#", header=None, names=cols, usecols=use, dtype=str)
    a = df["chr1"] + ":" + df["pos1"].str.zfill(10)
    b = df["chr2"] + ":" + df["pos2"].str.zfill(10)
    lo, hi = np.minimum(a.to_numpy(), b.to_numpy()), np.maximum(a.to_numpy(), b.to_numpy())
    uniq = len(set(zip(lo.tolist(), hi.tolist())))
    ph = (df["phase0"] != ".").to_numpy().astype(int) + (df["phase1"] != ".").to_numpy().astype(int)
    cis = (df["chr1"] == df["chr2"]).to_numpy()
    sep = np.abs(df["pos1"].astype(np.int64).to_numpy() - df["pos2"].astype(np.int64).to_numpy())
    chroms = sorted(set(df["chr1"]) | set(df["chr2"]))
    return {"file": Path(path).name, "cell": Path(path).name.split(".")[0], "rows": int(len(df)), "unique": int(uniq),
            "frac_ends_phased": float(ph.sum() / (2 * len(df))), "frac_both_phased": float((ph == 2).mean()),
            "frac_cis": float(cis.mean()), "frac_cis_lt_1kb": float((cis & (sep < 1000)).mean()),
            "n_chroms": len(chroms), "has_chrY": any(c.upper().endswith("Y") for c in chroms),
            "n_chrY_ends": int((df["chr1"].str.upper().str.endswith("Y")).sum()
                               + (df["chr2"].str.upper().str.endswith("Y")).sum())}


def cmd_count(args) -> None:
    import pandas as pd
    rows = []
    for p in args.files:
        r = count_cell(p)
        print(json.dumps(r), flush=True)
        rows.append(r)
    t = pd.DataFrame(rows).sort_values("unique", ascending=False)
    t.to_csv(args.out, sep="\t", index=False)
    print(t.to_string(index=False))


# --------------------------------------------------------------------------- scoring

def _load(path):
    z = np.load(path, allow_pickle=False)
    X = z["coords"]
    if X.ndim == 2:
        X = X[None]
    return z["chrom"].astype(str), z["pos"].astype(np.int64), X.astype(np.float32)


def _match(sets):
    """Common (chain, pos) keys of several (chrom, pos, X) -> list of index arrays + chain labels."""
    keys = None
    for c, p, _ in sets:
        k = np.char.add(np.char.add(c.astype(str), ":"), p.astype(str))
        keys = k if keys is None else np.intersect1d(keys, k)
    out = []
    for c, p, _ in sets:
        k = np.char.add(np.char.add(c.astype(str), ":"), p.astype(str))
        order = np.argsort(k)
        out.append(order[np.searchsorted(k[order], keys)])
    chain = np.array([s.rsplit(":", 1)[0] for s in keys.tolist()])
    pos = np.array([int(s.rsplit(":", 1)[1]) for s in keys.tolist()], np.int64)
    return out, chain, pos


BANDS = (("lt2mb", 0, 2_000_000), ("2-20mb", 2_000_000, 20_000_000), ("gt20mb", 20_000_000, 10 ** 10))


def _band_pairs(chain, pos, n, rng):
    """Within-chain particle pairs by genomic separation: for each band, ``n`` pairs pooled over chains
    (first end uniform, separation uniform within the band and the chain)."""
    order = np.lexsort((pos, chain))
    chain, pos = chain[order], pos[order]
    out = {}
    starts = {c: (np.searchsorted(chain, c, "left"), np.searchsorted(chain, c, "right")) for c in np.unique(chain)}
    for name, lo, hi in BANDS:
        ii, jj = [], []
        for c, (s0, s1) in starts.items():
            if s1 - s0 < 50:
                continue
            k = rng.integers(s0, s1, n // len(starts) * 4)
            sep = rng.uniform(lo, min(hi, pos[s1 - 1] - pos[s0]), len(k)) if pos[s1 - 1] - pos[s0] > lo else None
            if sep is None:
                continue
            target = pos[k] + sep
            j = np.searchsorted(pos[s0:s1], target) + s0
            ok = (j < s1) & (j != k)
            ok[ok] &= (np.abs(pos[j[ok]] - pos[k[ok]]) >= lo) & (np.abs(pos[j[ok]] - pos[k[ok]]) < hi)
            ii.append(k[ok]); jj.append(j[ok])
        i, j = np.concatenate(ii), np.concatenate(jj)
        sel = rng.permutation(len(i))[:n]
        out[name] = (order[i[sel]], order[j[sel]])
    return out


def _pairs(chain, n, rng, min_chain=50):
    per = {}
    for c in np.unique(chain):
        idx = np.flatnonzero(chain == c)
        if len(idx) < min_chain:
            continue
        i, j = rng.integers(0, len(idx), n), rng.integers(0, len(idx), n)
        ok = i != j
        per[c] = (idx[i[ok]], idx[j[ok]])
    i, j = rng.integers(0, len(chain), n), rng.integers(0, len(chain), n)
    ok = i != j
    return per, (i[ok], j[ok])


def _d(X, ij):
    return np.linalg.norm(X[ij[0]] - X[ij[1]], axis=1)


def _r(u, v):
    return float(np.corrcoef(u, v)[0, 1])


def compare(A, B, per, whole, same=False, bands=None) -> dict:
    """Median over model pairs of per-chain (median over chains), whole-genome and per-band r."""
    pc, wr, chains, br = [], [], {}, {}
    for a in range(len(A)):
        for b in range(len(B)):
            if same and b <= a:
                continue
            rs = {c: _r(_d(A[a], ij), _d(B[b], ij)) for c, ij in per.items()}
            for c, v in rs.items():
                chains.setdefault(c, []).append(v)
            pc.append(float(np.median(list(rs.values()))))
            wr.append(_r(_d(A[a], whole), _d(B[b], whole)))
            for name, ij in (bands or {}).items():
                br.setdefault(name, []).append(_r(_d(A[a], ij), _d(B[b], ij)))
    return {"per_copy_r": float(np.median(pc)), "whole_r": float(np.median(wr)), "n_model_pairs": len(pc),
            "band_r": {k: float(np.median(v)) for k, v in br.items()},
            "per_copy_r_by_chain": {c: float(np.median(v)) for c, v in chains.items()}}


def cmd_score(args) -> None:
    rng = np.random.default_rng(args.seed)
    sets = {"a": _load(args.a)}
    if args.b:
        sets["b"] = _load(args.b)
    if args.ref:
        sets["ref"] = _load(args.ref)
    idx, chain, pos = _match(list(sets.values()))
    M = {k: s[2][:, ii] for (k, s), ii in zip(sets.items(), idx)}
    per, whole = _pairs(chain, args.pairs, rng)
    bands = _band_pairs(chain, pos, args.pairs, rng)
    out = {"a": args.a, "b": args.b, "ref": args.ref, "n_matched": int(len(chain)),
           "n_particles": {k: int(s[2].shape[1]) for k, s in sets.items()}, "n_chains": len(per),
           "pairs_per_chain": args.pairs}
    out["a_within"] = compare(M["a"], M["a"], per, whole, same=True, bands=bands) if len(M["a"]) > 1 else None
    if "b" in M:
        out["a_vs_b"] = compare(M["a"], M["b"], per, whole, bands=bands)
    if "ref" in M:
        out["a_vs_ref"] = compare(M["a"], M["ref"], per, whole, bands=bands)
        if "b" in M:
            out["b_vs_ref"] = compare(M["b"], M["ref"], per, whole, bands=bands)
    brief = {k: (v["per_copy_r"], v["whole_r"], *v["band_r"].values()) for k, v in out.items()
             if isinstance(v, dict) and "per_copy_r" in v}
    print(json.dumps({"n_matched": out["n_matched"], **{k: [round(x, 3) for x in v] for k, v in brief.items()}}),
          flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1))


def _run_record(npz: Path) -> dict | None:
    meta = Path(str(npz) + ".json")
    if not meta.exists():
        return None
    m = json.loads(meta.read_text())
    if "stages" not in m:                       # not a run_diploid.py run (e.g. run_hickit.py)
        return {"file": npz.name, "method": m.get("method"), "res": float(m.get("res", np.nan)),
                "n_models": m.get("n_models"), "wall_seconds": m.get("wall_seconds"),
                "seconds_per_model": m.get("seconds_per_model"), "seed": None}
    st = m["stages"]
    st = json.loads(st) if isinstance(st, str) else st
    last = st[-1]
    gpu = None
    g = Path(str(npz) + ".gpumem.csv")
    if g.exists():
        vals = [float(l.split(",")[1]) for l in g.read_text().splitlines() if l.count(",") == 1]
        gpu = {"peak_mib": max(vals), "baseline_mib": vals[0]} if vals else None
    z = np.load(npz, allow_pickle=False)
    n_grid = int(z["coords"].shape[-2])
    return {"file": npz.name, "method": m.get("method"), "protocol": m.get("protocol"), "res": float(m["particle_sizes"][-1]), "seed": m["seed"], "n_models": m["n_models"],
            "n_contacts_input": m["n_contacts"], "frac_ends_phased": m["frac_ends_phased"],
            "contacts_last_stage": last.get("n_contacts"), "restraints_last_stage": last.get("n_restraints"),
            "particles_grid": n_grid, "particles_simulated": last.get("n_particles"),
            "contacts_per_particle": m["n_contacts"] / n_grid,
            "contacts_per_simulated_particle": (last.get("n_contacts") or 0) / max(last.get("n_particles") or 1, 1),
            "wall_seconds": m["wall_seconds"], "engine_seconds": m["engine_seconds"], "read_seconds": m["read_seconds"],
            "peak_rss_mb": m["peak_rss_mb"], "gpu": gpu, "gpu_name": (m.get("gpu") or {}).get("name") if
            isinstance(m.get("gpu"), dict) else m.get("gpu"),
            "stages": [{k: s.get(k) for k in ("particle_size", "n_particles", "n_contacts", "n_restraints",
                                              "seconds_prepare", "seconds_dynamics")} for s in st],
            "engine_version": m.get("engine_version"), "slurm_job_id": m.get("slurm_job_id")}


def cmd_summary(args) -> None:
    root = Path(args.root)
    out = {"root": str(root), "cells": {}}
    counts = {}
    if args.counts and Path(args.counts).exists():
        import pandas as pd
        counts = {r["cell"]: r for r in pd.read_csv(args.counts, sep="\t").to_dict("records")}
    for C in sorted(p for p in root.iterdir() if p.is_dir()):
        cell = {"contacts": counts.get(C.name), "runs": [], "scores": {}, "heldout": {}}
        for sub in ("ladder", "explore", "compare"):
            for npz in sorted((C / sub).glob("*.npz")):
                r = _run_record(npz)
                if r:
                    cell["runs"].append({"set": sub, **r})
        for s in sorted((C / "scores").glob("*.json")):
            d = json.loads(s.read_text())
            if s.stem.startswith("heldout"):
                meth = d["methods"].get("ember", {})
                cell["heldout"][s.stem] = {
                    "eval_stats": d.get("eval_stats"),
                    **{sub: meth.get("median", {}).get(sub) for sub in ("all", "cis", "trans")},
                    "ps_baseline_cis_auc": meth.get("ps_baseline_cis_auc"),
                    "cis_bands": {b: v.get("roc_auc") for b, v in meth.get("median", {}).get("cis_bands", {}).items()},
                    "coverage_pos": meth.get("coverage_pos")}
            else:
                cell["scores"][s.stem] = {k: ({kk: vv for kk, vv in v.items() if kk != "per_copy_r_by_chain"}
                                              if isinstance(v, dict) else v) for k, v in d.items()}
        ho = C / "heldout" / "fold1" / "ember.npz"
        if ho.exists():
            cell["heldout_run"] = _run_record(ho)
        out["cells"][C.name] = cell
    Path(args.out).write_text(json.dumps(out, indent=1, default=float))
    print(args.out)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("count")
    c.add_argument("--out", required=True)
    c.add_argument("files", nargs="+")
    c.set_defaults(fn=cmd_count)
    s = sub.add_parser("score")
    s.add_argument("--a", required=True)
    s.add_argument("--b")
    s.add_argument("--ref")
    s.add_argument("--pairs", type=int, default=200_000)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_score)
    m = sub.add_parser("summary")
    m.add_argument("--root", required=True, help="runs/highres (one directory per cell)")
    m.add_argument("--counts", help="contacts_per_cell.tsv")
    m.add_argument("--out", required=True)
    m.set_defaults(fn=cmd_summary)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
