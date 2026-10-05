"""Development driver of EMber-mix (PREREG §12; development pools only): run variants on pools, score.

    python benchmarks/screcon/mix_dev.py --pools P1.txt.gz P2.txt.gz \\
        --variants '{"patch": {}, "uni": {"mix_seed": "uniform"}}' --runs RUNS --device gpu \\
        [--baselines naive igm oracle] [--refs-dir DIR]

Each variant is a JSON of engine parameters over ``run_mix.MIX_DEFAULTS``; keys starting with ``_`` are
options of ``run_mix.py`` (``_oracle_prior``, ``_n_models``, ``_seed``).  Writes
``RUNS/<pool>.<variant>.npz`` and ``RUNS/<pool>.score.json`` and prints one line per (pool, method);
``--table`` appends the lines (tab separated) to a file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def fmt(x) -> str:
    return "  -  " if x is None else f"{x:.3f}"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pools", nargs="+", required=True)
    ap.add_argument("--variants", default="{}")
    ap.add_argument("--baselines", nargs="*", default=[])
    ap.add_argument("--runs", required=True)
    ap.add_argument("--device", default="gpu")
    ap.add_argument("--res", default="1e6")
    ap.add_argument("--refs-dir", help="real pools: directory with <pool>.oracle.npz references")
    ap.add_argument("--table", help="append result rows (tsv) here")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    variants = json.loads(args.variants)
    runs = Path(args.runs)
    runs.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    for pool in args.pools:
        base = pool[:-7]
        meta = json.loads(Path(base + ".json").read_text())
        k = int(meta["k"])
        name = Path(base).name
        labels, models = [], []
        for b in args.baselines:
            out = runs / f"{name}.{b}.npz"
            if b == "oracle":
                cells = [f"{base}_cell{j}.txt.gz" for j in range(k)]
                if not Path(cells[0]).exists():
                    cells = meta.get("tables")
                cmd = [py, str(HERE / "run_mix.py"), "--method", "oracle", "--contacts", pool, "--cell-tables", *cells]
            else:
                cmd = [py, str(HERE / "run_mix.py"), "--method", b, "--contacts", pool]
            cmd += ["--k", str(k), "--res", args.res, "--device", args.device, "--seed", "1", "--out", str(out)]
            if args.force or not out.exists():
                with open(str(out) + ".log", "w") as log:
                    subprocess.run(cmd, check=True, stderr=log, stdout=subprocess.DEVNULL)
            labels.append(b)
            models.append(str(out))
        for v, prm in variants.items():
            out = runs / f"{name}.{v}.npz"
            opts = {kk: vv for kk, vv in prm.items() if kk.startswith("_")}
            eng = {kk: vv for kk, vv in prm.items() if not kk.startswith("_")}
            cmd = [py, str(HERE / "run_mix.py"), "--method", "mix", "--contacts", pool, "--k", str(k), "--res", args.res,
                   "--device", args.device, "--seed", str(opts.get("_seed", 1)), "--n-models", str(opts.get("_n_models", 2)),
                   "--params", json.dumps(eng), "--out", str(out)]
            if "_oracle_prior" in opts:
                cmd += ["--oracle-prior", str(opts["_oracle_prior"])]
            if "_prior" in opts:
                cmd += ["--prior", opts["_prior"].format(runs=str(runs), pool=name)]
            if "_oracle_subset" in opts:
                cmd += ["--oracle-subset", opts["_oracle_subset"]]
            if args.force or not out.exists():
                with open(str(out) + ".log", "w") as log:
                    subprocess.run(cmd, check=True, stderr=log, stdout=subprocess.DEVNULL)
            labels.append(v)
            models.append(str(out))
        sc = runs / f"{name}.score.json"
        cmd = [py, str(HERE / "mix_score.py"), "--pool", pool, "--models", *models, "--labels", *labels, "--out", str(sc)]
        if args.refs_dir:
            cmd += ["--refs", str(Path(args.refs_dir) / f"{name}.oracle.npz")]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        res = json.loads(sc.read_text())
        for lab, r in res["methods"].items():
            if "missing" in r:
                continue
            m1 = r.get("M1") or {}
            ll = ll0 = None
            lj = Path(models[labels.index(lab)] + ".json")
            if lj.exists():
                st = json.loads(lj.read_text()).get("stages") or []
                em = [u for s_ in st for u in s_.get("robust", [])]
                ll = em[-1]["loglik"] if em else None
                ll0 = em[-1].get("ll_marginal") if em else None
            line = (f"{name:22s} {lab:14s} M2 {r['M2']:.3f} cis {r['M2_cis']:.3f} | M1 {fmt(m1.get('all'))} "
                    f"trans {fmt(m1.get('trans'))} >20Mb {fmt(m1.get('cis_gt20mb'))} 2-20 {fmt(m1.get('cis_2_20mb'))} "
                    f"<2 {fmt(m1.get('cis_lt2mb'))} | ll {fmt(ll)} ll0 {fmt(ll0)} | {r.get('wall_seconds') or 0:.0f} s")
            print(line, flush=True)
            if args.table:
                with open(args.table, "a") as fh:
                    fh.write("\t".join(map(str, [name, lab, r["M2"], r["M2_cis"], m1.get("all"), m1.get("trans"),
                                                  m1.get("cis_gt20mb"), m1.get("cis_2_20mb"), m1.get("cis_lt2mb"), ll, ll0,
                                                  r.get("wall_seconds")])) + "\n")


if __name__ == "__main__":
    main()
