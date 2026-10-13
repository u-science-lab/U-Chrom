"""Smoke test of c_access.py's lazy AnnData backends on a toy object: every level returns the selected spots."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

repo, tmp = Path(sys.argv[1]), Path(sys.argv[2])
sys.argv = ["c_access.py"]
spec = importlib.util.spec_from_file_location("c_access", repo / "benchmarks/fig2/c_access.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
from uchrom import ChromData  # noqa: E402

rng = np.random.default_rng(0)
rows = [(ch, k * 1000, (k + 1) * 1000, f"c{c}_{ch}_a{a}", f"c{c}")
        for c in range(5) for ch in ("chr1", "chr2") for a in (1, 2) for k in range(8)]
spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
cd = ChromData(rng.normal(size=(len(spots), 3)), spots, spot_tracks=pd.DataFrame({"x1": rng.random(len(spots))}))
for cls in (m.AnnDataLazy, m.AnnDataLazyH5ad):
    p = tmp / f"toy{cls.ext}"
    cls.write(cd, p)
    be = cls()
    be.open(p)
    ids = be.ids()
    for lv, col in (("trace", "trace_id"), ("cell", "cell_id"), ("chrom", "chrom")):
        sub = be.get(lv, ids[lv][1])
        want = spots[col] == ids[lv][1]
        assert len(sub) == want.sum() and np.allclose(sub.obsm["spatial"], cd.coords[want.to_numpy()]), lv
    print(cls.__name__, "ok")
