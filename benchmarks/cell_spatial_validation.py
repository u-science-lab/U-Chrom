"""Real-data check of the cell-position schema (``uns['cell_spatial']``,
``cd.cell_positions()``): the loaders populate it from the source tables and
the values survive the ``.chromdata.zarr`` round trip.

Datasets (catalogued in ``example-data/README.md``):

* Takei 2025 cerebellum rep 1 (3 FOVs, ``takei2025_cerebellum/raw/*.csv`` +
  the clustering CSV): ``read_seqfish_multiomics(..., out=)`` (streaming);
  centroids in voxels (103 nm xy, 250 nm z) in the FOV frame;
* Takei 2021 mESC (4DN ``4DNFIHF3JCBY`` core + ``4DNFIFINA2U9`` cell table,
  ``Cent_ROI_x / Cent_ROI_y``, 2-D);
* Liu 2025 mouse MOp (4DN ``4DNFID46OABK`` core + ``4DNFICX8IVEK`` cell table,
  ``cell_center_x_global / _y_global``, global frame), streaming.

For each: cells in the cell table, cells with a position, the largest
difference to the source table (must be 0), the round trip through the store,
and — where the positions share the frame of the spots — the distance between
each cell's position (physical units) and the mean of its spots.  Each dataset
runs in its own process (peak RSS reported).  None of these data sets ships
cell outlines (segmentation polygons / masks), so outlines are not validated
on real data.

    python benchmarks/cell_spatial_validation.py --data example-data --work /tmp/cellpos
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
sys.path.insert(0, str(ROOT))


def _rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e6 if sys.platform == "darwin" else r / 1e3


def _spot_means(cd):
    import numpy as np
    import pandas as pd

    s = ChromDataRead(cd)
    df = pd.DataFrame(np.asarray(s.coords), columns=["x", "y", "z"])
    df["cell_id"] = s.spots["cell_id"].astype(str).to_numpy()
    return df.groupby("cell_id")[["x", "y", "z"]].mean()


def ChromDataRead(cd):
    return cd.to_memory(columns="coords") if getattr(cd, "backed", False) else cd


def _frame_check(pos, means, cols):
    import numpy as np

    j = pos.join(means, rsuffix="_spots", how="inner").dropna(subset=cols)
    d = np.sqrt(sum((j[c] - j[c + "_spots"]) ** 2 for c in cols))
    return {"n_cells": int(len(j)), "axes": cols, "median_distance": float(np.median(d)),
            "p95_distance": float(np.quantile(d, 0.95)),
            "median_abs_by_axis": {c: float(np.median(np.abs(j[c] - j[c + "_spots"]))) for c in cols}}


def takei2025(data: Path, work: Path) -> dict:
    import numpy as np
    import pandas as pd

    from uchrom import ChromData
    from uchrom.io.seqfish_multiomics import read_seqfish_multiomics

    d = data / "takei2025_cerebellum"
    csvs = sorted((d / "raw").glob("cerebellum_rep1_pos*.csv"))
    out = work / "takei2025_cerebellum_rep1.chromdata.zarr"
    t0 = time.perf_counter()
    cd = read_seqfish_multiomics([str(c) for c in csvs], locus_annotation=d / "LC1-100k-09022022-mm10-25kb-meta.csv",
                                 cell_clustering=d / "cerebellum_mRNA_cluster_nuc_vol_filtered.csv", out=out)
    t_import = time.perf_counter() - t0
    src = pd.read_csv(d / "cerebellum_mRNA_cluster_nuc_vol_filtered.csv")
    src.index = (src["rep"].astype(str) + "_" + src["fov"].astype(str) + "_" + src["cellID"].astype(str))
    pos = cd.cell_positions()
    rec = pos.attrs["cell_spatial"]
    have = pos.dropna(subset=["x", "y", "z"])
    j = have.join(src[["x", "y", "z"]], rsuffix="_src", how="left")
    diff = float(np.nanmax(np.abs(j[["x", "y", "z"]].to_numpy() - j[["x_src", "y_src", "z_src"]].to_numpy())))
    rt = ChromData.read(out, backed=True).cell_positions()
    phys = cd.cell_positions(physical=True)
    means = _spot_means(cd)
    fovs = pd.Series(pos["region"]).value_counts().sort_index().to_dict() if "region" in pos else {}
    return {
        "dataset": "Takei 2025 cerebellum rep 1 (seqFISH+ loader, streaming)",
        "import_s": round(t_import, 1), "n_cells_in_cells_table": int(len(cd.cells)),
        "n_cells_with_position": int(len(have)), "n_cells_in_source_csv_rep1": int((src["rep"] == 1).sum()),
        "cells_per_fov": {str(k): int(v) for k, v in fovs.items()},
        "record": rec, "max_abs_diff_to_source": diff,
        "unmatched_in_source": int(j["x_src"].isna().sum()),
        "round_trip_equal": bool(rt[["x", "y", "z"]].equals(pos[["x", "y", "z"]])),
        "position_vs_spot_mean_um": _frame_check(phys, means, ["x", "y", "z"]),
        "spots_frame_note": "physical = voxel × (0.103, 0.103, 0.25) µm; spots are x_um / y_um / z_um of the "
                            "same FOV",
        "peak_rss_mb": round(_rss_mb(), 1),
    }


def fofct(name: str, data: Path, work: Path) -> dict:
    import numpy as np
    import pandas as pd

    from uchrom import ChromData
    from chromdata.cdata import _read_fofct_table

    core, cell, xs, ys, stream = {
        "takei2021": ("4DNFIHF3JCBY.csv", "4DNFIFINA2U9.csv", "cent_ROI_x", "cent_ROI_y", False),
        "liu2025_mop": ("liu2025_mop/4DNFID46OABK.csv", "liu2025_mop/4DNFICX8IVEK.csv",
                        "cell_center_x_global", "cell_center_y_global", True),
    }[name]
    t0 = time.perf_counter()
    out = work / f"{name}.chromdata.zarr"
    if stream:
        cd = ChromData.from_fofct(data / core, cell_table=data / cell, cell_value_prefix=None, out=out)
    else:
        cd = ChromData.from_fofct(data / core, cell_table=data / cell)
        cd.write(out)
    t_import = time.perf_counter() - t0
    src, _ = _read_fofct_table(data / cell)
    src.index = src["Cell_ID"].astype(str)
    pos = cd.cell_positions()
    rec = pos.attrs["cell_spatial"]
    have = pos.dropna(subset=["x", "y"])
    j = have.join(src[[xs, ys]], how="left")
    diff = float(np.nanmax(np.abs(j[["x", "y"]].to_numpy() - j[[xs, ys]].to_numpy(dtype=float))))
    rt = ChromData.read(out, backed=True).cell_positions()
    res = {
        "dataset": {"takei2021": "Takei 2021 mESC (4DN FOF-CT)", "liu2025_mop": "Liu 2025 MOp (4DN FOF-CT)"}[name],
        "import_s": round(t_import, 1), "n_cells_in_cells_table": int(len(cd.cells)),
        "n_cells_with_position": int(len(have)), "n_rows_in_source_cell_table": int(len(src)),
        "n_cells_with_spots": int(cd.n_cells),
        "n_cells_with_spots_and_position": int(have.index.isin(set(cd.spots["cell_id"].astype(str).unique())).sum())
        if not getattr(cd, "backed", False) else None,
        "record": rec, "max_abs_diff_to_source": diff,
        "round_trip_equal": bool(rt[["x", "y"]].equals(pos[["x", "y"]])),
        "peak_rss_mb": round(_rss_mb(), 1),
    }
    means = _spot_means(cd)
    res["position_vs_spot_mean_xy"] = _frame_check(pos, means, ["x", "y"])
    if res["n_cells_with_spots_and_position"] is None:
        res["n_cells_with_spots_and_position"] = res["position_vs_spot_mean_xy"]["n_cells"]
    return res


def child(name: str, data: str, work: str) -> None:
    warnings.simplefilter("ignore")
    data, work = Path(data), Path(work)
    work.mkdir(parents=True, exist_ok=True)
    res = takei2025(data, work) if name == "takei2025" else fofct(name, data, work)
    print("RESULT " + json.dumps(res, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "example-data"))
    ap.add_argument("--work", default="/tmp/uchrom_cellpos")
    ap.add_argument("--only", nargs="*", default=["takei2025", "takei2021", "liu2025_mop"])
    ap.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "cell_spatial_validation.json"))
    ap.add_argument("--child")
    a = ap.parse_args()
    if a.child:
        return child(a.child, a.data, a.work)
    results = {}
    for name in a.only:                                        # one heavy job at a time
        p = subprocess.run([sys.executable, __file__, "--child", name, "--data", a.data, "--work", a.work],
                           capture_output=True, text=True)
        line = [ln for ln in p.stdout.splitlines() if ln.startswith("RESULT ")]
        if p.returncode or not line:
            print(p.stdout[-3000:], p.stderr[-3000:])
            raise SystemExit(f"{name} failed")
        results[name] = json.loads(line[-1][len("RESULT "):])
        print(name, json.dumps(results[name], indent=1))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(out.read_text()) if out.exists() else {}
    old.update(results)
    out.write_text(json.dumps(old, indent=1) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
