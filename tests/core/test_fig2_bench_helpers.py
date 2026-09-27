"""Synthetic checks of the Figure 2 benchmark helpers (benchmarks/fig2/_common.py).

The benchmarks themselves run on real data (see benchmarks/fig2/README.md);
these tests only pin the helpers' correctness: the minimal FOF-CT writer
round-trips through ``ChromData.from_fofct``, whole-cell subsetting keeps
cells whole, and replication above the real size gives new unique ids.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def common():
    spec = importlib.util.spec_from_file_location("fig2_common", ROOT / "benchmarks" / "fig2" / "_common.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _toy(n_cells=6, n_bins=10, seed=0):
    from uchrom import ChromData

    rng = np.random.default_rng(seed)
    rows = []
    for c in range(n_cells):
        for chrom in ("chr1", "chr2"):
            for a in (1, 2):
                for k in range(n_bins - c):  # unequal cell sizes
                    rows.append((chrom, k * 1000, (k + 1) * 1000, f"c{c}_{chrom}_a{a}", f"c{c}"))
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    tracks = pd.DataFrame({"H3K27ac": rng.normal(size=len(spots)), "dot_int": rng.random(len(spots))})
    cells = pd.DataFrame({"cell_type": ["A", "B"] * (n_cells // 2), "vol": rng.random(n_cells)},
                         index=pd.Index([f"c{c}" for c in range(n_cells)], name="cell_id"))
    return ChromData(rng.normal(size=(len(spots), 3)), spots, tracks=tracks, cells=cells,
                     cellm={"umap": rng.normal(size=(n_cells, 2))}, uns={"genome_assembly": "mm10"})


def test_write_fofct_roundtrip(common, tmp_path):
    from uchrom import ChromData

    cd = _toy()
    p = tmp_path / "core.csv"
    common.write_fofct(cd, p)
    back = ChromData.from_fofct(p)
    np.testing.assert_allclose(back.coords, cd.coords, rtol=1e-12)
    assert (back.spots["trace_id"].astype(str).values == cd.spots["trace_id"].astype(str).values).all()
    assert (back.spots["cell_id"].astype(str).values == cd.spots["cell_id"].astype(str).values).all()
    # tracks come back as extra spot columns (FOF-CT has no track table)
    np.testing.assert_allclose(back.spots["H3K27ac"].to_numpy(), cd.tracks["H3K27ac"].to_numpy(), rtol=1e-12)
    assert back.uns["genome_assembly"] == "mm10"


def test_subset_by_cells_keeps_cells_whole(common):
    cd = _toy()
    sub, info = common.subset_by_cells(cd, 50)
    assert not info["replicated"] and info["n_spots"] >= 50
    full = cd.spots.groupby("cell_id", observed=True).size()
    part = sub.spots.groupby("cell_id", observed=True).size()
    assert (part == full.loc[part.index]).all()


def test_replicate_store_partitioned(common, tmp_path):
    """replicate_store.py on a 2.1 store = whole relabelled copies + the
    lowest-code cells, read back value-identical, index consistent."""
    import subprocess
    import sys

    from uchrom import ChromData

    cd = _toy()
    src = tmp_path / "src.chromdata.zarr"
    cd.write(src, row_group_rows=7)
    n_target = 2 * cd.n_spots + 40
    dst = tmp_path / "big.chromdata.zarr"
    subprocess.run([sys.executable, str(ROOT / "benchmarks" / "fig2" / "replicate_store.py"), str(src),
                    str(dst), "--n", str(n_target)], check=True, capture_output=True,
                   env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"})
    big = ChromData.read(dst, backed=True)
    assert (big.partitioned or big.has_coords_table) and big.n_spots >= n_target
    mem = ChromData.read(src)
    # expected: copies r=0,1 of every cell, plus copy 2 of the cells with the lowest codes
    cells = list(mem.spots["cell_id"].cat.categories)
    lens = mem.spots.groupby("cell_id", observed=True).size().reindex(cells).to_numpy()
    k = int(np.searchsorted(np.cumsum(lens), 40, side="left") + 1)
    parts = [mem, common._relabel(mem, "r1"),
             common._relabel(mem[np.isin(mem.spots["cell_id"].astype(str), cells[:k])], "r2")]
    exp = pd.concat([p.to_dataframe() for p in parts], ignore_index=True)
    got = big.to_dataframe()
    key = ["cell_id", "trace_id", "start"]
    for df in (exp, got):
        for c in ("cell_id", "trace_id", "chrom"):
            df[c] = df[c].astype(str)
    pd.testing.assert_frame_equal(got.sort_values(key).reset_index(drop=True),
                                  exp.sort_values(key).reset_index(drop=True), check_like=True)
    # index-based access agrees with a scan
    full = big.to_memory()
    for c in ("c1_r1", "c0_r2", "c3"):
        pd.testing.assert_frame_equal(big.get_cell(c).to_dataframe(), full.get_cell(c).to_dataframe())
    for ch in ("chr1", "chr2"):
        pd.testing.assert_frame_equal(big.get_chrom(ch).to_dataframe(), full.get_chrom(ch).to_dataframe())
    assert sum(x.n_spots for x in big.iter_traces(5)) == big.n_spots


def test_subset_by_cells_replicates_with_new_ids(common):
    cd = _toy()
    big, info = common.subset_by_cells(cd, 3 * cd.n_spots + 10)
    assert info["replicated"] and big.n_spots >= 3 * cd.n_spots + 10
    assert big.spots["cell_id"].nunique() == len(big.cells) == big.cellm["umap"].shape[0]
    assert big.cells.index.is_unique and big.traces.index.is_unique if len(big.traces) else True
    assert big.tracks.shape[0] == big.n_spots
