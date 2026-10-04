"""Deep low-phasing diploid development (PREREG §10): derived contact tables for diagnostics and for
prototyping candidate fixes before they go into the engine.

``derive`` writes a hickit ``.pairs`` (phases only; hickit's ``phase_prob`` columns dropped) from a phased
table with any of:

* ``--downsample N``     N random rows (``--seed``)
* ``--min-cis-sep BP``   drop cis contacts closer than BP
* ``--commit TAU``       hard phasing with EMber's 2-D neighbourhood prior (``uchrom_nucdyn.neighbour_phase_prior``,
                         same-homolog rule within 10 Mb): a contact with an unphased end whose most probable
                         copy pair has probability >= TAU gets those haplotypes; ``--rest drop`` removes the
                         other ambiguous contacts (hickit ``-S``), ``--rest keep`` keeps them unphased
* ``--iso-nei K --iso-radius R``  keep a contact only if >= K other contacts of the same chromosome pair have
                         both ends within R (Chebyshev; hickit ``-r R -c K``)

Prints a JSON line with the counts.

    python benchmarks/screcon/deep_diploid.py derive --contacts cell.pairs.gz --commit 0.75 --rest drop --out X.pairs.gz
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diploid import Phased, read_phased, write_phased  # noqa: E402


def isolated_mask(c: Phased, k: int, radius: int) -> np.ndarray:
    """True for contacts with >= k other contacts of the same chromosome pair within ``radius`` at both ends."""
    keep = np.zeros(len(c), bool)
    key = np.char.add(np.char.add(c.chrom_a.astype(str), "|"), c.chrom_b.astype(str))
    for g in np.unique(key):
        idx = np.flatnonzero(key == g)
        pa, pb = c.pos_a[idx], c.pos_b[idx]
        o = np.argsort(pa, kind="stable")
        pa, pb, idx = pa[o], pb[o], idx[o]
        lo = np.searchsorted(pa, pa - radius, "left")
        hi = np.searchsorted(pa, pa + radius, "right")
        for i in range(len(idx)):
            n = int((np.abs(pb[lo[i]:hi[i]] - pb[i]) <= radius).sum()) - 1
            keep[idx[i]] = n >= k
    return keep


def cmd_derive(args) -> None:
    c = read_phased(args.contacts)
    n0 = len(c)
    rng = np.random.default_rng(args.seed)
    keep = np.ones(len(c), bool)
    if args.downsample and args.downsample < len(c):
        sel = np.zeros(len(c), bool)
        sel[rng.choice(len(c), args.downsample, replace=False)] = True
        keep &= sel
    if args.min_cis_sep:
        keep &= ~((c.chrom_a == c.chrom_b) & (np.abs(c.pos_b - c.pos_a) < args.min_cis_sep))
    c = c.subset(keep)
    stats = {"input": n0, "after_subset": len(c)}
    if args.iso_nei:
        m = isolated_mask(c, args.iso_nei, args.iso_radius)
        c = c.subset(m)
        stats["after_isolation"] = len(c)
    if args.commit:
        import uchrom_nucdyn as un
        pr = un.neighbour_phase_prior(c.chrom_a, c.pos_a, c.chrom_b, c.pos_b, c.hap_a, c.hap_b, ploidy="auto")
        amb = (c.hap_a < 0) | (c.hap_b < 0)
        best = pr.argmax(1)
        ok = amb & (pr.max(1) >= args.commit)
        ha, hb = c.hap_a.copy(), c.hap_b.copy()
        ha[ok], hb[ok] = (best[ok] >> 1).astype(np.int8), (best[ok] & 1).astype(np.int8)
        c = Phased(c.chrom_a, c.pos_a, ha, c.chrom_b, c.pos_b, hb, c.header, None)
        stats.update({"ambiguous": int(amb.sum()), "committed": int(ok.sum())})
        if args.rest == "drop":
            c = c.subset(~amb | ok)
            stats["after_drop"] = len(c)
    write_phased(args.out, c)
    stats["written"] = len(c)
    print(json.dumps(stats), flush=True)


def cmd_table(args) -> None:
    """Development table: one row per cell x variant (``runs/highres/dev/<cell>/<variant>/``)."""
    import pandas as pd
    rows = []
    for cdir in sorted(Path(args.root).iterdir()):
        if not cdir.is_dir():
            continue
        for v in sorted(p for p in cdir.iterdir() if p.is_dir() and p.name != "split"):
            r = {"cell": cdir.name.split("_", 1)[1], "variant": v.name}
            for res in (100000, 20000, 10000, 5000):
                f = v / f"score_res{res}.json"
                if f.exists():
                    s = json.loads(f.read_text())
                    k = res // 1000
                    ab = s.get("a_vs_b") or {}
                    r[f"seeds_{k}k"] = ab.get("per_copy_r")
                    r[f"seeds_whole_{k}k"] = ab.get("whole_r")
                    for b, x in (ab.get("band_r") or {}).items():
                        r[f"seeds_{b}_{k}k"] = x
                    r[f"vs_hickit_{k}k"] = (s.get("a_vs_ref") or {}).get("per_copy_r")
            for ev, lab in (("eval_pairs", "ho"), ("eval_pairs_cis", "ho2mb")):
                f = v / f"heldout_{ev}.json"
                if f.exists():
                    m = next(iter(json.loads(f.read_text())["methods"].values()))
                    r[f"{lab}_cis_auc"] = m["median"]["cis"]["roc_auc"]
                    r[f"{lab}_trans_auc"] = m["median"]["trans"]["roc_auc"]
            t = v / "table.pairs.gz.json"
            if t.exists():
                r["contacts"] = json.loads(t.read_text())["written"]
            for res in (100000, 20000):
                j = v / f"res{res}_s1.npz.json"
                if j.exists():
                    m = json.loads(j.read_text())
                    r[f"wall_{res // 1000}k"] = m["wall_seconds"]
                    st = m["stages"]
                    st = json.loads(st) if isinstance(st, str) else st
                    eps = [e["eps"] for s_ in st for e in s_.get("robust", [])]
                    r[f"eps_last_{res // 1000}k"] = eps[-1] if eps else None
            rows.append(r)
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 60)
    cols = [c for c in ["cell", "variant", "contacts", "seeds_100k", "seeds_whole_100k", "seeds_20k", "seeds_whole_20k",
                        "seeds_lt2mb_20k", "seeds_2-20mb_20k", "seeds_gt20mb_20k", "vs_hickit_100k", "vs_hickit_20k",
                        "ho_cis_auc", "ho_trans_auc", "ho2mb_cis_auc", "eps_last_100k", "eps_last_20k", "wall_20k"]
            if c in t.columns]
    print(t[cols].round(3).to_string(index=False))
    if args.out:
        t.to_csv(args.out, sep="\t", index=False)


def cmd_dipc_table(args) -> None:
    """Criterion C3 table: Dip-C development cells, every label scored by deep_dipc.sbatch
    (``runs/highres/dipc/cell<k>/scores/<label>_*.json``), means over cells; differences vs ``ember_nbr``."""
    import pandas as pd
    rows = []
    for cdir in sorted(Path(args.root).glob("cell*")):
        labels = sorted({p.name.rsplit("_", 1)[0] for p in (cdir / "scores").glob("*_full.json")})
        for lab in labels:
            S = cdir / "scores"
            r = {"cell": cdir.name, "label": lab}
            f = json.loads((S / f"{lab}_full.json").read_text())["methods"]
            for ref in ("dipc", "hickit"):
                v = [m["vs"][ref] for m in f.values() if ref in m["vs"]]
                r[f"r_chain_{ref}"] = float(np.mean([x["dist_r_median"] for x in v])) if v else None
                r[f"r_whole_{ref}"] = float(np.mean([x["whole_r"] for x in v])) if v else None
            r["precision"] = float(np.mean([m["precision"].get("rmsd_to_mean_per_unit") or np.nan for m in f.values()]))
            if (S / f"{lab}_mask.json").exists():
                m = next(iter(json.loads((S / f"{lab}_mask.json").read_text())["methods"].values()))
                r["phase_acc"] = m.get("phase_holdback", {}).get("acc_all")
            auc = []
            for k in (1, 2, 3):
                p = S / f"{lab}_heldout_fold{k}.json"
                if p.exists():
                    m = next(iter(json.loads(p.read_text())["methods"].values()))
                    auc.append(m["median"]["cis"]["roc_auc"])
            r["heldout_cis_auc"] = float(np.mean(auc)) if auc else None
            if (S / f"{lab}_seeds.json").exists():
                r["seeds_r"] = json.loads((S / f"{lab}_seeds.json").read_text())["a_vs_b"]["per_copy_r"]
            rows.append(r)
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(t.round(4).to_string(index=False))
    m = t.drop(columns="cell").groupby("label").mean(numeric_only=True)
    print("\nmean over cells")
    print(m.round(4).to_string())
    if "ember_nbr" in m.index:
        print("\ndifference vs ember_nbr (frozen)")
        print((m - m.loc["ember_nbr"]).round(4).to_string())
    if args.out:
        t.to_csv(args.out, sep="\t", index=False)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("derive")
    d.add_argument("--contacts", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--seed", type=int, default=1)
    d.add_argument("--downsample", type=int, default=0)
    d.add_argument("--min-cis-sep", type=int, default=0)
    d.add_argument("--commit", type=float, default=0.0)
    d.add_argument("--rest", choices=["keep", "drop"], default="drop")
    d.add_argument("--iso-nei", type=int, default=0)
    d.add_argument("--iso-radius", type=int, default=10_000_000)
    d.set_defaults(fn=cmd_derive)
    t = sub.add_parser("table")
    t.add_argument("--root", required=True)
    t.add_argument("--out")
    t.set_defaults(fn=cmd_table)
    t2 = sub.add_parser("dipc-table")
    t2.add_argument("--root", required=True)
    t2.add_argument("--out")
    t2.set_defaults(fn=cmd_dipc_table)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
