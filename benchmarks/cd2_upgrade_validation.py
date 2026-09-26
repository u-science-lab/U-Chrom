"""ChromData 2.0 step 3 — upgrade real 1.x files to format 2.0 and compare.

Two passes, one per ``uchrom`` tree::

    git archive origin/main uchrom | tar -x -C /tmp/old_main
    PYTHONPATH=/tmp/old_main python benchmarks/cd2_upgrade_validation.py old WORKDIR
    PYTHONPATH=.             python benchmarks/cd2_upgrade_validation.py new WORKDIR

``old`` copies every 1.x example file into ``WORKDIR`` (the originals are
never touched), builds 1.x files from the FOF-CT CSVs with the old
``from_fofct``, reads each with the 1.x reader and saves ``to_dataframe()``,
``coords`` and the spot-aligned ``tracks`` (+ read / write timings).

``new`` upgrades each copy with ``upgrade_h5cd`` and checks that
``to_dataframe()``, ``coords`` and ``tracks_spot_view()`` equal the 1.x
values — for the in-memory upgrade (reading the 1.x file) and for the
2.0 file on disk — and reports n_bins, n_spots, file sizes and times.
It also checks that ``from_fofct`` gives the same table in both versions.

Data (see ``example-data/README.md``; set ``UCHROM_EXAMPLE_DATA``):
``sim_cell1/sim_cell1.h5cd``, ``takei2025_fov0/takei2025_fov0.h5cd``,
``schicar_mop/schicar_mop.h5cd``, ``mesc_sox2/mESC_Sox2_5cells_*.h5cd`` and
the Takei 2021 FOF-CT core table ``takei2021_mesc/4DNFIHF3JCBY.csv`` with its
in-repo cell (``4DNFIFINA2U9.csv``) and RNA (``4DNFIJ52NVDV.csv``) tables.
"""
import json
import os
import pickle
import shutil
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
# Same root as uchrom.datasets.example_data_dir(); resolved here without importing
# uchrom because the 'old' pass runs against an older uchrom tree.
DATA = Path(os.environ.get("UCHROM_EXAMPLE_DATA", REPO / "example-data"))
MODE, WORK = sys.argv[1], Path(sys.argv[2])
WORK.mkdir(parents=True, exist_ok=True)
warnings.simplefilter("ignore")

H5CD = {
    "sim_cell1": DATA / "sim_cell1" / "sim_cell1.h5cd",
    "takei2025_fov0": DATA / "takei2025_fov0" / "takei2025_fov0.h5cd",
    "schicar_mop": DATA / "schicar_mop" / "schicar_mop.h5cd",
    "mESC_Sox2_wnan": DATA / "mesc_sox2" / "mESC_Sox2_5cells_wnan.h5cd",
    "mESC_Sox2_linear": DATA / "mesc_sox2" / "mESC_Sox2_5cells_imputed_linear.h5cd",
    "mESC_Sox2_snapfish": DATA / "mesc_sox2" / "mESC_Sox2_5cells_imputed_snapfish.h5cd",
}
FOFCT = {
    "takei2021_fofct": dict(core=DATA / "takei2021_mesc" / "4DNFIHF3JCBY.csv",
                            cell_table=DATA / "takei2021_mesc" / "4DNFIFINA2U9.csv",
                            rna_table=DATA / "takei2021_mesc" / "4DNFIJ52NVDV.csv"),
}


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t0


def snapshot(cd, tracks):
    return {"df": cd.to_dataframe(), "coords": np.asarray(cd.coords),
            "tracks": None if tracks is None or len(tracks.columns) == 0 else pd.DataFrame(tracks)}


def run_old():
    from uchrom import ChromData

    meta = {}
    for name, src in H5CD.items():
        if not src.exists():
            print("missing", src)
            continue
        dst = WORK / f"{name}.v1.h5cd"
        shutil.copyfile(src, dst)
        cd, t_read = timed(lambda: ChromData.read(dst))
        _, t_write = timed(lambda: cd.write(WORK / f"{name}.v1rewrite.h5cd"))
        (WORK / f"{name}.old.pkl").write_bytes(pickle.dumps(snapshot(cd, cd.tracks)))
        meta[name] = {"t_read_v1": t_read, "t_write_v1": t_write}
        print(name, cd.n_spots, "spots", f"read {t_read:.2f}s")
    for name, paths in FOFCT.items():
        if not paths["core"].exists():
            print("missing", paths["core"])
            continue
        cd, t_build = timed(lambda: ChromData.from_fofct(
            paths["core"], cell_table=paths["cell_table"], rna_table=paths["rna_table"]))
        dst = WORK / f"{name}.v1.h5cd"
        _, t_write = timed(lambda: cd.write(dst))
        back, t_read = timed(lambda: ChromData.read(dst))
        (WORK / f"{name}.old.pkl").write_bytes(pickle.dumps(snapshot(back, back.tracks)))
        (WORK / f"{name}.old_fofct.pkl").write_bytes(pickle.dumps(snapshot(cd, cd.tracks)))
        meta[name] = {"t_read_v1": t_read, "t_write_v1": t_write, "t_from_fofct_v1": t_build}
        print(name, cd.n_spots, "spots", f"write {t_write:.2f}s read {t_read:.2f}s")
    (WORK / "old_meta.json").write_text(json.dumps(meta, indent=1))


def same(a, b):
    if a is None or b is None:
        return (a is None) == (b is None), 0.0
    if len(a) == 0 and len(b) == 0:
        # empty spot tables (data without 3-D spots): 1.x read the empty
        # loci columns back as object dtype, 2.0 types them (int64); compare
        # the schema only and say so
        diff = {c: (str(a[c].dtype), str(b[c].dtype)) for c in a.columns
                if c in b.columns and a[c].dtype != b[c].dtype}
        if diff:
            print("   empty table, dtype-only differences (1.x, 2.0):", diff)
        return list(a.columns) == list(b.columns), 0.0
    try:
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True),
                                      check_frame_type=False)
        return True, 0.0
    except AssertionError as exc:
        print("   DIFF:", str(exc)[:400])
        return False, float("nan")


def run_new():
    from uchrom import ChromData
    from uchrom.io import upgrade_h5cd

    meta = json.loads((WORK / "old_meta.json").read_text())
    rows = []
    for name in list(H5CD) + list(FOFCT):
        v1 = WORK / f"{name}.v1.h5cd"
        if not v1.exists():
            continue
        old = pickle.loads((WORK / f"{name}.old.pkl").read_bytes())
        v2 = WORK / f"{name}.v2.h5cd"
        info, t_up = timed(lambda: upgrade_h5cd(v1, v2, overwrite=True))
        mem, t_read_v1 = timed(lambda: ChromData.read(v1))      # in-memory upgrade
        disk, t_read_v2 = timed(lambda: ChromData.read(v2))
        _, t_write_v2 = timed(lambda: disk.write(WORK / f"{name}.v2rewrite.h5cd"))
        ok = {}
        for label, cd in (("mem", mem), ("disk", disk)):
            snap = snapshot(cd, cd.tracks_spot_view())
            ok[f"{label}.df"] = same(old["df"], snap["df"])[0]
            ok[f"{label}.coords"] = bool(np.array_equal(old["coords"], snap["coords"], equal_nan=True))
            ok[f"{label}.tracks"] = same(old["tracks"], snap["tracks"])[0]
        if name in FOFCT:
            paths = FOFCT[name]
            fresh = ChromData.from_fofct(paths["core"], cell_table=paths["cell_table"],
                                         rna_table=paths["rna_table"])
            ref = pickle.loads((WORK / f"{name}.old_fofct.pkl").read_bytes())
            ok["from_fofct.df"] = same(ref["df"], fresh.to_dataframe())[0]
        names = disk.track_names()
        rows.append({
            "dataset": name, "n_spots": disk.n_spots, "n_bins": disk.n_bins,
            "n_bin_tracks": len(names["bin"]), "n_spot_tracks": len(names["spot"]),
            "size_v1_MB": v1.stat().st_size / 1e6, "size_v2_MB": v2.stat().st_size / 1e6,
            "t_read_v1_old": meta[name]["t_read_v1"], "t_read_v1_new": t_read_v1,
            "t_read_v2": t_read_v2, "t_write_v1_old": meta[name]["t_write_v1"],
            "t_write_v2": t_write_v2, "t_upgrade": t_up,
            "identical": all(ok.values()), **ok,
        })
        print(name, "identical:", all(ok.values()), {k: v for k, v in ok.items() if not v})
    table = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    cols = ["dataset", "n_spots", "n_bins", "n_bin_tracks", "n_spot_tracks", "size_v1_MB",
            "size_v2_MB", "t_read_v1_old", "t_read_v1_new", "t_read_v2", "t_write_v1_old",
            "t_write_v2", "t_upgrade", "identical"]
    print(table[cols].round(3).to_string(index=False))
    table.to_csv(WORK / "upgrade_validation.csv", index=False)


if __name__ == "__main__":
    run_old() if MODE == "old" else run_new()
