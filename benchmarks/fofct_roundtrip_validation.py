"""Real-data check of the FOF-CT writer: ``from_fofct`` → ``to_fofct`` →
``from_fofct`` must give the same ChromData.

Datasets (catalogued in ``example-data/README.md``):

* Takei 2021 mESC DNA seqFISH+ (4DN ``4DNFIHF3JCBY`` core + ``4DNFIFINA2U9``
  cell + ``4DNFIJ52NVDV`` RNA tables);
* Liu 2025 mouse MOp DNA-MERFISH (4DN ``4DNFID46OABK`` core, 1.68 GB, +
  ``4DNFICX8IVEK`` cell table), under ``liu2025_mop/``.

For each: read time of the source, write time and size of the written
tables, read time of the written tables, and the checks (``to_dataframe()``
with dtypes, cells, RNA points, headers).  Each dataset runs in its own
process (peak RSS reported).

    python benchmarks/fofct_roundtrip_validation.py --data example-data --work /tmp/fofct
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _pkg in ("uchrom", "chromdata", "uchrom-browser"):   # this checkout's packages, not installed copies
    sys.path.insert(0, str(ROOT / "packages" / _pkg))

DATASETS = {
    "takei2021": ("4DNFIHF3JCBY.csv", "4DNFIFINA2U9.csv", "4DNFIJ52NVDV.csv"),
    "liu2025_mop": ("liu2025_mop/4DNFID46OABK.csv", "liu2025_mop/4DNFICX8IVEK.csv", None),
}


def child(name, data, work):
    warnings.simplefilter("ignore")
    import pandas as pd
    from uchrom import ChromData

    core, cell, rna = DATASETS[name]
    data, work = Path(data), Path(work)
    kw = {"cell_table": data / cell}
    if rna:
        kw["rna_table"] = data / rna
    t0 = time.perf_counter()
    a = ChromData.from_fofct(data / core, **kw)
    t_read = time.perf_counter() - t0
    out = {"core": work / f"{name}_core.csv", "cell_table": work / f"{name}_cell.csv"}
    if rna:
        out["rna_table"] = work / f"{name}_rna.csv"
    t0 = time.perf_counter()
    a.to_fofct(out["core"], **{k: v for k, v in out.items() if k != "core"})
    t_write = time.perf_counter() - t0
    t0 = time.perf_counter()
    b = ChromData.from_fofct(out["core"], **{k: v for k, v in out.items() if k != "core"})
    t_reread = time.perf_counter() - t0
    checks = []
    pd.testing.assert_frame_equal(a.to_dataframe(), b.to_dataframe(), check_exact=True)
    checks.append("to_dataframe (coords, ids, loci, extra columns, dtypes) identical")
    pd.testing.assert_frame_equal(a.cells, b.cells, check_exact=True)
    checks.append(f"cells identical ({a.cells.shape[0]} x {a.cells.shape[1]})")
    if rna:
        pd.testing.assert_frame_equal(a.points["rna"], b.points["rna"], check_exact=True)
        checks.append(f"RNA points identical ({len(a.points['rna'])})")
    assert a.uns["fofct_header"] == b.uns["fofct_header"]
    for key in a.uns.get("fofct_companions", {}):
        assert a.uns["fofct_companions"][key]["header"] == b.uns["fofct_companions"][key]["header"]
    checks.append("headers identical")
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    src_bytes = sum((data / f).stat().st_size for f in (core, cell, rna) if f)
    dst_bytes = sum(Path(p).stat().st_size for p in out.values())
    print("__RESULT__" + json.dumps({
        "dataset": name, "n_spots": int(a.n_spots), "n_cells_table": int(len(a.cells)),
        "read_s": t_read, "write_s": t_write, "reread_s": t_reread,
        "source_bytes": src_bytes, "written_bytes": dst_bytes, "checks": checks,
        "peak_rss_gb": r / 2**30 if sys.platform == "darwin" else r / 2**20}), flush=True)
    for p in out.values():
        Path(p).unlink()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "example-data")
    ap.add_argument("--work", type=Path, default=Path("/tmp/fofct_roundtrip"))
    ap.add_argument("--only")
    ap.add_argument("--child", nargs=3, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        return child(*args.child)
    args.work.mkdir(parents=True, exist_ok=True)
    for name in (args.only.split(",") if args.only else DATASETS):
        if not (args.data / DATASETS[name][0]).exists():
            print(f"{name}: source missing, skipped")
            continue
        proc = subprocess.run([sys.executable, __file__, "--child", name, str(args.data), str(args.work)],
                              capture_output=True, text=True)
        if "__RESULT__" not in proc.stdout:
            raise RuntimeError(proc.stderr[-3000:])
        r = json.loads(proc.stdout.rsplit("__RESULT__", 1)[1])
        print(json.dumps(r, indent=1), flush=True)


if __name__ == "__main__":
    main()
