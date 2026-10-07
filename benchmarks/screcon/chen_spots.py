"""Per-spot EMber + spot QC on Chen et al. 2026 spatial Hi-C (PREREG §13.3).

Subcommands
-----------
``split``     the run's deduplicated pairs (readID = barcode pair) -> per-spot GEO tables of the linked spots
              with >= 10,000 cis contacts (``tables/``), ``spots.tsv`` with every linked spot's counts::

                  python benchmarks/screcon/chen_spots.py split --pairs OAK/RUN/RUN.dedup.pairs.gz \\
                      [--spots MAP.tsv.gz] --out CHEN/<run>

              The barcode pair -> spot map is built by ``apps/atlas/recipes/build_chen2026_spot_maps.py`` into the
              data directory; without ``--spots`` it is taken from
              ``$UCHROM_DATA/spatial_hic_chen2026/spot_maps/chen2026_*_<run>_spots.tsv.gz``.

``mixtures``  secondary, descriptive: 200 single assessable spots and 200 50:50 mixtures of two random
              assessable spots, all at 10,000 cis (``default_rng(20261015)``) -> ``tables/single_*`` / ``mix_*``::

                  python benchmarks/screcon/chen_spots.py mixtures --dir CHEN/<run>

``run``       EMber haploid (tag robust-frozen), 200 kb, 2 models, seed 2 on the tables of one array task::

                  python benchmarks/screcon/chen_spots.py run --dir CHEN/<run> --task 1 --ntasks 8 --device gpu

``score``     Q2, Q3, Q5-Q7 and structural features of the tables of one task -> ``scores/<task>.tsv``.

``report``    pass / fail with the frozen rule (Q3 < the unphased-calibration threshold of the spot's level),
              tables and spatial maps::

                  python benchmarks/screcon/chen_spots.py report --dirs CHEN/CRR1829219 CHEN/CRR1829220 \\
                      --thresholds data/spotqc_unphased.json --out RESULTS/chen2026

Depth levels: < 10 k cis = not assessable; 10 k for 10-30 k, 30 k for 30-100 k, 100 k for >= 100 k.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dominant as dm  # noqa: E402

MIN_CIS = 10_000
N_SECONDARY = 200
SECONDARY_N = 10_000
CHROMS = [f"chr{i}" for i in range(1, 20)] + ["chrX"]


def level_of(n_cis: int) -> str:
    if n_cis < MIN_CIS:
        return "na"
    return "10k" if n_cis < 30_000 else ("30k" if n_cis < 100_000 else "100k")


def data_dir() -> Path:
    """The data directory (as ``uchrom.datasets.data_dir``: ``$UCHROM_DATA``, else ``~/.cache/uchrom``)."""
    env = os.environ.get("UCHROM_DATA")
    return Path(env).expanduser() if env else Path.home() / ".cache" / "uchrom"


def spot_map_path(pairs: str) -> Path:
    """The recipe's spot map of the run named in the pairs file (``<run>.dedup.pairs.gz``)."""
    run = Path(pairs).name.split(".")[0]
    hits = sorted((data_dir() / "spatial_hic_chen2026" / "spot_maps").glob(f"chen2026_*_{run}_spots.tsv.gz"))
    if len(hits) != 1:
        raise SystemExit(f"no spot map for {run} under {data_dir()}/spatial_hic_chen2026/spot_maps "
                         "(build it: python apps/atlas/recipes/build_chen2026_spot_maps.py)")
    return hits[0]


def write_geo(path: Path, ca, pa, cb, pb) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", compresslevel=3) as fh:
        fh.write("#chr_A\tpos_A\tchr_B\tpos_B\n")
        fh.write("".join(f"{a}\t{p}\t{b}\t{q}\n" for a, p, b, q in zip(ca, pa, cb, pb)))


def cmd_split(args) -> None:
    spots = pd.read_csv(args.spots or spot_map_path(args.pairs), sep="\t", low_memory=False)
    code = {b: i for i, b in enumerate(spots.barcode_pair)}
    cidx = {c: i for i, c in enumerate(CHROMS)}
    parts = []
    t0 = time.time()
    n_lines = 0
    for ch in pd.read_csv(args.pairs, sep="\t", comment="#", header=None, usecols=[0, 1, 2, 3, 4],
                          names=["bc", "c1", "p1", "c2", "p2"], chunksize=5_000_000,
                          dtype={"bc": str, "c1": str, "p1": np.int64, "c2": str, "p2": np.int64}):
        n_lines += len(ch)
        s = ch.bc.map(code)
        a, b = ch.c1.map(cidx), ch.c2.map(cidx)
        ok = s.notna() & a.notna() & b.notna()
        parts.append((s[ok].to_numpy(np.int32), a[ok].to_numpy(np.int8), ch.p1[ok].to_numpy(np.int64),
                      b[ok].to_numpy(np.int8), ch.p2[ok].to_numpy(np.int64)))
        print(f"{n_lines:,} lines, {time.time() - t0:.0f} s", flush=True)
    s, a, pa, b, pb = (np.concatenate([p[k] for p in parts]) for k in range(5))
    del parts
    cis = (a == b) & (np.abs(pa - pb) >= dm.CIS_MIN)
    n = len(spots)
    spots["n_cis"] = np.bincount(s[cis], minlength=n)
    spots["n_trans"] = np.bincount(s[a != b], minlength=n)
    spots["n_short"] = np.bincount(s[(a == b) & ~cis], minlength=n)
    spots["level"] = [level_of(x) for x in spots.n_cis]
    out = Path(args.out)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    order = np.argsort(s, kind="stable")
    s, a, pa, b, pb = s[order], a[order], pa[order], b[order], pb[order]
    bounds = np.searchsorted(s, np.arange(n + 1))
    names = np.array(CHROMS)
    rows = []
    for i in np.flatnonzero(spots.n_cis.to_numpy() >= MIN_CIS):
        lo, hi = bounds[i], bounds[i + 1]
        name = f"spot_{i:05d}"
        write_geo(out / "tables" / f"{name}.txt.gz", names[a[lo:hi]], pa[lo:hi], names[b[lo:hi]], pb[lo:hi])
        rows.append({"name": name, "kind": "spot", "spot": spots.spot.iloc[i], "n_cis": int(spots.n_cis.iloc[i]),
                     "level": spots.level.iloc[i]})
    spots.to_csv(out / "spots.tsv", sep="\t", index=False)
    pd.DataFrame(rows).to_csv(out / "manifest.tsv", sep="\t", index=False)
    (out / "split.json").write_text(json.dumps({"pairs": args.pairs, "lines": n_lines, "rows_linked": int(len(s)),
                                                "spots": n, "assessable": len(rows), "seconds": time.time() - t0}))
    print(f"{len(rows)} assessable of {n} linked spots", flush=True)


def cmd_mixtures(args) -> None:
    d = Path(args.dir)
    man = pd.read_csv(d / "manifest.tsv", sep="\t")
    spot_rows = man[man.kind == "spot"].reset_index(drop=True)
    rng = np.random.default_rng(20261015)
    cache = {}

    def cell(name):
        if name not in cache:
            cache[name] = dm.load_cell(str(d / "tables" / f"{name}.txt.gz"), "chen")
        return cache[name]

    new = []
    singles = rng.choice(len(spot_rows), min(N_SECONDARY, len(spot_rows)), replace=False)
    pairs = [rng.choice(len(spot_rows), 2, replace=False) for _ in range(N_SECONDARY)]
    for q, i in enumerate(singles):
        src = spot_rows.name[i]
        c = cell(src)
        take = dm.Sampler(c, 1000 + q).take(SECONDARY_N)
        name = f"single_{q:03d}"
        c2 = c.subset(take)
        write_geo(d / "tables" / f"{name}.txt.gz", c2.chrom_a, c2.pos_a, c2.chrom_b, c2.pos_b)
        new.append({"name": name, "kind": "single", "spot": src, "n_cis": SECONDARY_N, "level": "10k"})
    for q, (i, j) in enumerate(pairs):
        s1, s2 = spot_rows.name[i], spot_rows.name[j]
        c1, c2 = cell(s1), cell(s2)
        t1 = dm.Sampler(c1, 2000 + q).take(SECONDARY_N // 2)
        t2 = dm.Sampler(c2, 3000 + q).take(SECONDARY_N // 2)
        m = dm.concat([c1.subset(t1), c2.subset(t2)], "chen")
        m = m.subset(np.random.default_rng(7).permutation(len(m.pos_a)))
        name = f"mix_{q:03d}"
        write_geo(d / "tables" / f"{name}.txt.gz", m.chrom_a, m.pos_a, m.chrom_b, m.pos_b)
        new.append({"name": name, "kind": "mix2", "spot": f"{s1}+{s2}", "n_cis": SECONDARY_N, "level": "10k"})
    man = pd.concat([man[man.kind == "spot"], pd.DataFrame(new)], ignore_index=True)
    man.to_csv(d / "manifest.tsv", sep="\t", index=False)
    print(len(new), "secondary tables", flush=True)


def task_rows(d: Path, task: int, ntasks: int) -> pd.DataFrame:
    man = pd.read_csv(d / "manifest.tsv", sep="\t")
    return man.iloc[task - 1::ntasks]


def cmd_run(args) -> None:
    d = Path(args.dir)
    rows = task_rows(d, args.task, args.ntasks)
    done = 0
    t0 = time.time()
    for name in rows.name:
        t = d / "tables" / f"{name}.txt.gz"
        out = d / "runs" / f"{name}.ember.s2.npz"
        if out.exists() and Path(str(out) + ".json").exists():
            continue
        if done >= args.restart_every:
            print(f"restart after {done} runs", flush=True)
            os.execv(sys.executable, [sys.executable] + sys.argv)
        try:
            meta = dm.reconstruct(t, out, "ember", 2, "chen", args.device)
        except RuntimeError as e:
            if "GPU adapter" in str(e):
                print(f"NO_GPU_ADAPTER after {done} runs: {e}", flush=True)
                if done > 0:
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                sys.exit(3)
            raise
        done += 1
        print(f"{name}\t{meta['n_rows']}\t{meta['wall_seconds']:.1f}", flush=True)
    print(f"task {args.task}: {done} runs of {len(rows)} in {time.time() - t0:.0f} s", flush=True)


def structure_features(chrom, X) -> dict:
    """Genome and median chromosome radius of gyration (bead units) and intermingling (fraction of particles
    with a particle of another chromosome within 2 bead units), mean over models."""
    from scipy.spatial import cKDTree
    from metrics import bead_unit
    u = bead_unit(chrom, X)
    rg, rgc, mingle = [], [], []
    codes = pd.factorize(chrom)[0]
    for Xm in X:
        Y = Xm / u
        rg.append(float(np.sqrt(((Y - Y.mean(0)) ** 2).sum(1).mean())))
        rgc.append(float(np.median([np.sqrt(((Y[codes == k] - Y[codes == k].mean(0)) ** 2).sum(1).mean())
                                    for k in np.unique(codes) if (codes == k).sum() >= 10])))
        tree = cKDTree(Y)
        nb = tree.query_ball_point(Y, r=2.0)
        mingle.append(float(np.mean([np.any(codes[n] != codes[i]) for i, n in enumerate(nb)])))
    return {"rg_genome": float(np.mean(rg)), "rg_chrom_median": float(np.mean(rgc)), "intermingling": float(np.mean(mingle))}


def cmd_score(args) -> None:
    d = Path(args.dir)
    rows = task_rows(d, args.task, args.ntasks)
    out = []
    for _, r in rows.iterrows():
        rec = dict(r)
        c = dm.load_cell(str(d / "tables" / f"{r['name']}.txt.gz"), "chen")
        rec["trans_frac"] = float(np.mean(c.chrom_a != c.chrom_b))
        rec.update(dm.graph_metrics(c))
        p = d / "runs" / f"{r['name']}.ember.s2.npz"
        if p.exists() and Path(str(p) + ".json").exists():
            ch, ps, X, w = dm.load_run(p)
            rec["q2_down"] = float(np.mean(~(np.nan_to_num(w, nan=-1.0) >= 0.5))) if w is not None else np.nan
            rec["q3_viol"] = dm.violation_rate(c, ch, ps, X, False)
            rec.update(structure_features(ch, X))
            rec["wall_ember"] = json.loads(Path(str(p) + ".json").read_text())["wall_seconds"]
        out.append(rec)
    (d / "scores").mkdir(exist_ok=True)
    pd.DataFrame(out).to_csv(d / "scores" / f"{args.task:03d}.tsv", sep="\t", index=False)
    print(f"task {args.task}: {len(out)} scored", flush=True)


def cmd_report(args) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    thr = json.loads(Path(args.thresholds).read_text())
    q3t, q7t = thr["thresholds"], thr["q7_thresholds"]
    outd = Path(args.out)
    outd.mkdir(parents=True, exist_ok=True)
    lines, summary = [], {}
    for d in map(Path, args.dirs):
        spots = pd.read_csv(d / "spots.tsv", sep="\t", low_memory=False)
        sc = pd.concat([pd.read_csv(f, sep="\t") for f in sorted((d / "scores").glob("*.tsv"))], ignore_index=True)
        real = sc[sc.kind == "spot"].set_index("spot")
        sec = spots.section.iloc[0]
        run = spots.run.iloc[0]
        spots = spots.join(real.drop(columns=["n_cis", "level"], errors="ignore"), on="spot")
        lvl = spots.level
        spots["q3_thr"] = lvl.map(lambda x: q3t.get(x, np.nan))
        spots["q7_thr"] = lvl.map(lambda x: q7t.get(x, np.nan))
        spots["status"] = np.where(lvl == "na", "not assessable",
                                   np.where(spots.q3_viol.isna(), "no run",
                                            np.where(spots.q3_viol < spots.q3_thr, "pass", "fail")))
        spots["q7_pass"] = np.where(lvl == "na", np.nan, (spots.q7_conflict < spots.q7_thr).astype(float))
        spots.to_csv(outd / f"{run}_spots_qc.tsv.gz", sep="\t", index=False)
        rec = {"section": sec, "run": run, "linked": int(len(spots)), "levels": {}}
        for lv in ("na", "10k", "30k", "100k"):
            s = spots[lvl == lv]
            rec["levels"][lv] = {"n": int(len(s)), "pass": int((s.status == "pass").sum()),
                                 "frac_pass": float((s.status == "pass").mean()) if len(s) else np.nan,
                                 "q7_frac_pass": float(np.nanmean(s.q7_pass)) if len(s) and lv != "na" else np.nan,
                                 "median_q3": float(s.q3_viol.median()) if len(s) and "q3_viol" in s else np.nan}
        rec["pass_all_linked"] = float((spots.status == "pass").mean())
        ass = spots[lvl != "na"]
        rec["pass_assessable"] = float((ass.status == "pass").mean()) if len(ass) else np.nan
        sec2 = sc[sc.kind.isin(["single", "mix2"])]
        rec["secondary"] = {k: {"q3_median": float(g.q3_viol.median()), "q7_median": float(g.q7_conflict.median()),
                                "frac_pass_q3_10k": float((g.q3_viol < q3t["10k"]).mean())} for k, g in sec2.groupby("kind")}
        group = "Region" if "Region" in spots and spots.Region.notna().any() else "anno"
        reg = spots[lvl != "na"].groupby(group).agg(n=("status", "size"), frac_pass=("status", lambda x: float((x == "pass").mean())),
                                                    rg_genome=("rg_genome", "median"), rg_chrom=("rg_chrom_median", "median"),
                                                    intermingling=("intermingling", "median"), trans=("trans_frac", "median"))
        allreg = spots.groupby(group).agg(n_linked=("status", "size"), median_cis=("n_cis", "median"))
        reg = allreg.join(reg, how="left")
        passing = spots[spots.status == "pass"]
        reg_pass = passing.groupby(group)[["rg_genome", "rg_chrom_median", "intermingling", "trans_frac"]].median()
        reg = reg.join(reg_pass.add_suffix("_pass"), how="left")
        reg.to_csv(outd / f"{run}_by_{group}.tsv", sep="\t")
        rec["by_region"] = json.loads(reg.reset_index().to_json(orient="records"))
        summary[run] = rec
        # maps
        cols = [("n_cis", "cis contacts (log10)", lambda v: np.log10(v.clip(lower=1)), "viridis"),
                ("status", "QC status", None, None), ("q3_viol", "Q3 violation rate", None, "magma"),
                ("q7_conflict", "Q7 partner conflict", None, "magma"),
                ("rg_genome", "genome Rg (bead units), passing", None, "cividis"),
                ("rg_chrom_median", "median chromosome Rg, passing", None, "cividis"),
                ("intermingling", "intermingling, passing", None, "cividis"),
                ("trans_frac", "trans fraction, passing", None, "cividis")]
        fig, axes = plt.subplots(2, 4, figsize=(18, 9.5))
        for ax, (col, title, tf, cmap) in zip(axes.ravel(), cols):
            ax.set_aspect("equal")
            ax.invert_yaxis()
            ax.set_xticks([]); ax.set_yticks([])
            ax.set_title(title, fontsize=10)
            x, y = spots.grid_col, spots.grid_row
            if col == "status":
                pal = {"not assessable": "#d9d9d9", "pass": "#1b9e77", "fail": "#d95f02", "no run": "#7570b3"}
                for k, c in pal.items():
                    s = spots.status == k
                    ax.scatter(x[s], y[s], s=4, c=c, marker="s", linewidths=0, label=f"{k} ({int(s.sum())})")
                ax.legend(fontsize=7, loc="lower left", markerscale=3)
                continue
            sel = spots.status == "pass" if title.endswith("passing") else spots[col].notna()
            ax.scatter(x, y, s=4, c="#eeeeee", marker="s", linewidths=0)
            v = spots.loc[sel, col]
            v = tf(v) if tf else v
            sc_ = ax.scatter(x[sel], y[sel], s=4, c=v, cmap=cmap, marker="s", linewidths=0,
                             vmin=np.nanpercentile(v, 2) if len(v) else None, vmax=np.nanpercentile(v, 98) if len(v) else None)
            plt.colorbar(sc_, ax=ax, fraction=0.04)
        fig.suptitle(f"Chen et al. 2026 {sec} ({run}): per-spot EMber + spot QC (PREREG §13.3)")
        fig.tight_layout()
        fig.savefig(outd / f"{run}_maps.png", dpi=110)
        plt.close(fig)
        lines.append(f"{sec} ({run}): linked {len(spots)}; " + "; ".join(
            f"{lv} n={v['n']} pass={v['pass']} ({v['frac_pass']:.2f})" for lv, v in rec["levels"].items())
            + f"; pass among assessable {rec['pass_assessable']:.3f}, among all linked {rec['pass_all_linked']:.3f}")
    (outd / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    print("\n".join(lines))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split")
    s.add_argument("--pairs", required=True)
    s.add_argument("--spots", help="barcode pair -> spot map (default: the data directory)")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_split)
    s = sub.add_parser("mixtures")
    s.add_argument("--dir", required=True)
    s.set_defaults(fn=cmd_mixtures)
    for name, fn in (("run", cmd_run), ("score", cmd_score)):
        s = sub.add_parser(name)
        s.add_argument("--dir", required=True)
        s.add_argument("--task", type=int, required=True)
        s.add_argument("--ntasks", type=int, required=True)
        s.add_argument("--device", default="gpu")
        s.add_argument("--restart-every", type=int, default=15)
        s.set_defaults(fn=fn)
    s = sub.add_parser("report")
    s.add_argument("--dirs", nargs="+", required=True)
    s.add_argument("--thresholds", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_report)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
