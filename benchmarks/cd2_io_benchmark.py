"""ChromData 2.0 — .h5cd size, write / full-read time and peak RSS, 1.x vs 2.0.

Every measurement runs in a fresh Python process (so peak RSS is that of
one read or write); the median of ``--repeat`` runs is reported.  The
1.x baseline uses another ``uchrom`` tree (``origin/main``)::

    git archive origin/main uchrom | tar -x -C /tmp/old_main
    python benchmarks/cd2_io_benchmark.py WORKDIR --old-tree /tmp/old_main \\
        --files $UCHROM_DATA/takei2025_fov0/takei2025_fov0.h5cd ...

Inputs are 1.x ``.h5cd`` files (copied into WORKDIR first; the
originals are never touched).  Variants: 1.x (old tree), 2.0 without
compression, 2.0 + lzf, 2.0 + gzip level 4 on integer / string data (the
default) and 2.0 + gzip level 4 on floats too (``compress_floats=True``).
On this tree the 2.0 variants go through ``uchrom.io._h5cd_legacy`` (``.h5cd``
is no longer a ChromData format).
"""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VARIANTS = {"2.0 none": (None, None, False), "2.0 lzf": ("lzf", None, False),
            "2.0 gzip-4 (default)": ("gzip", 4, False),
            "2.0 gzip-4 + floats": ("gzip", 4, True)}

CHILD = r"""
import json, resource, sys, time, warnings
warnings.simplefilter("ignore")
try:        # this tree: .h5cd is no longer a ChromData format, only the legacy module reads / writes it
    from uchrom.io._h5cd_legacy import read_h5cd as read, write_h5cd
    write = lambda cd, dst, **kw: write_h5cd(cd, dst, **kw)
except ImportError:  # the 1.x tree (--old-tree)
    from uchrom import ChromData
    read, write = ChromData.read, lambda cd, dst, **kw: cd.write(dst, **kw)
op, src, dst, comp, level, floats = sys.argv[1:7]
t0 = time.perf_counter()
cd = read(src)
t_read = time.perf_counter() - t0
t_write = None
if op == "write":
    kw = {} if comp == "v1" else {"compression": None if comp == "none" else comp,
                                  "compression_opts": None if level == "none" else int(level),
                                  "compress_floats": floats == "1"}
    t0 = time.perf_counter()
    write(cd, dst, **kw)
    t_write = time.perf_counter() - t0
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
rss = rss if sys.platform == "darwin" else rss * 1024
print(json.dumps({"read": t_read, "write": t_write, "rss_gb": rss / 1e9,
                  "n_spots": int(cd.n_spots)}))
"""


def child(pythonpath, *args):
    env = dict(os.environ, PYTHONPATH=str(pythonpath))
    out = subprocess.run([sys.executable, "-c", CHILD, *map(str, args)], env=env,
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--old-tree", required=True)
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--repeat", type=int, default=3)
    a = ap.parse_args()
    work = Path(a.workdir)
    work.mkdir(parents=True, exist_ok=True)
    rows = []
    for f in map(Path, a.files):
        v1 = work / f"{f.stem}.bench.v1.h5cd"
        shutil.copyfile(f, v1)
        # 1.x: write (old tree, from its own read) and full read
        w = [child(a.old_tree, "write", v1, work / "tmp.v1.h5cd", "v1", "none", "0")
             for _ in range(a.repeat)]
        r = [child(a.old_tree, "read", v1, "-", "-", "-", "-") for _ in range(a.repeat)]
        rows.append(_row(f.stem, "1.x (origin/main)", v1, w, r))
        for name, (comp, level, floats) in VARIANTS.items():
            dst = work / f"{f.stem}.bench.{name.split()[1]}{'_f' if floats else ''}.h5cd"
            w = [child(REPO, "write", v1, dst, comp or "none", level or "none", int(floats))
                 for _ in range(a.repeat)]
            r = [child(REPO, "read", dst, "-", "-", "-", "-") for _ in range(a.repeat)]
            rows.append(_row(f.stem, name, dst, w, r))
    print(f"{'dataset':<26}{'format':<22}{'n_spots':>9}{'size MB':>9}{'write s':>9}"
          f"{'read s':>8}{'peak RSS GB (read)':>20}")
    for r in rows:
        print(f"{r['dataset']:<26}{r['format']:<22}{r['n_spots']:>9}{r['size_mb']:>9.1f}"
              f"{r['write_s']:>9.2f}{r['read_s']:>8.2f}{r['rss_gb']:>20.2f}")
    (work / "io_benchmark.json").write_text(json.dumps(rows, indent=1))


def _row(dataset, fmt, path, writes, reads):
    med = statistics.median
    return {"dataset": dataset, "format": fmt, "n_spots": reads[0]["n_spots"],
            "size_mb": path.stat().st_size / 1e6,
            "write_s": med([w["write"] for w in writes]),
            "read_s": med([r["read"] for r in reads]),
            "rss_gb": med([r["rss_gb"] for r in reads])}


if __name__ == "__main__":
    main()
