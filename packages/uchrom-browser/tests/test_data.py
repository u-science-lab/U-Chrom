"""Framework-free tests for the web browser's data layer."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData
from uchrom_browser.data import (
    DatasetStore,
    GeometryFilter,
    decode_geometry,
    natural_chrom_key,
)
from tests import FIXTURES

SOX2 = FIXTURES / "mESC_Sox2_5cells_wnan.chromdata.zarr"


def _toy():
    """Two traces on chr2 / chr10 plus one on chr1, with a NaN spot in t_a."""
    rows = []
    coords = []
    for trace, chrom, n in [("t_b", "chr10", 3), ("t_a", "chr2", 5), ("t_c", "chr1", 2)]:
        for i in range(n):
            rows.append({"chrom": chrom, "start": 1000 * i, "end": 1000 * (i + 1),
                         "trace_id": trace, "cell_id": f"cell_{trace}"})
            coords.append([i, len(rows), 0.0])
    coords = np.array(coords, dtype=float)
    coords[3 + 2] = np.nan  # t_a, third spot → splits t_a into 2 + 2
    cd = ChromData(coords, pd.DataFrame(rows), uns={"xyz_unit": "um"})
    store = DatasetStore()
    return store, store.add(cd, name="toy")


def test_natural_chrom_order():
    names = ["chrX", "chr10", "chr2", "chrM", "chr1", "scaffold_7", "chrY"]
    assert sorted(names, key=natural_chrom_key) == [
        "chr1", "chr2", "chr10", "chrX", "chrY", "chrM", "scaffold_7"]


def test_summary_and_traces():
    _, ds = _toy()
    s = ds.summary()
    assert s["n_spots"] == 10 and s["n_traces"] == 3 and s["xyz_unit"] == "um"
    assert [c["name"] for c in s["chroms"]] == ["chr1", "chr2", "chr10"]
    assert s["chroms"][1] == {"name": "chr2", "start": 0, "end": 5000,
                              "n_spots": 5, "n_traces": 1}
    assert s["trace_mode"] is False  # one trace per chromosome
    assert s["trace_kind"] == "fibre"
    ds.cd.uns["trace_kind"] = "set"                  # traces of reads / localisations: drawn as points
    assert ds.summary()["trace_kind"] == "set"

    t = ds.traces()
    assert t["total"] == 3
    assert [r["trace_id"] for r in t["traces"]] == ["t_c", "t_a", "t_b"]
    assert t["traces"][1] == {"trace_id": "t_a", "chrom": "chr2", "cell_id": "cell_t_a",
                              "n_spots": 5, "start": 0, "end": 5000}
    assert ds.traces(chrom="chr10")["total"] == 1
    assert ds.traces(offset=2, limit=5)["traces"][0]["trace_id"] == "t_b"


def test_geometry_segments_split_on_nan_and_trace():
    _, ds = _toy()
    g = decode_geometry(ds.geometry(GeometryFilter()))
    h = g["header"]
    # t_c (2) | t_a (2 + 2 after dropping the NaN spot) | t_b (3)
    assert [(s["trace_id"], s["n_points"]) for s in h["segments"]] == [
        ("t_c", 2), ("t_a", 2), ("t_a", 2), ("t_b", 3)]
    assert h["n_points"] == 9 and h["total_points"] == 9 and not h["truncated"]
    assert list(g["offsets"]) == [0, 2, 4, 6, 9]
    assert np.isfinite(g["positions"]).all()
    assert list(g["starts"][2:6]) == [0, 1000, 3000, 4000]  # bin 2000 dropped
    assert h["segments"][2] == {"trace_id": "t_a", "chrom": "chr2", "cell_id": "cell_t_a",
                                "n_points": 2, "start": 3000, "end": 5000}
    assert h["chrom_extent"]["chr10"] == [0, 3000]
    assert h["bbox"]["min"][0] == 0.0


def test_geometry_filters_combine():
    _, ds = _toy()

    def seg_traces(**kw):
        h = decode_geometry(ds.geometry(GeometryFilter(**kw)))["header"]
        return [(s["trace_id"], s["n_points"]) for s in h["segments"]]

    assert seg_traces(chroms=["chr10"]) == [("t_b", 3)]
    assert seg_traces(trace_ids=["t_a", "t_c"]) == [("t_c", 2), ("t_a", 2), ("t_a", 2)]
    # region overlaps bins [1000,2000) and [3000,4000) of chr2 → NaN bin in between
    assert seg_traces(region={"chrom": "chr2", "start": 1500, "end": 3500}) == [
        ("t_a", 1), ("t_a", 1)]
    assert seg_traces(chroms=["chr1"], trace_ids=["t_a"]) == []
    empty = decode_geometry(ds.geometry(GeometryFilter(chroms=["chrZ"])))
    assert empty["header"]["n_points"] == 0 and empty["header"]["bbox"] is None
    assert list(empty["offsets"]) == [0]


def test_geometry_truncation_keeps_whole_segments():
    _, ds = _toy()
    h = decode_geometry(ds.geometry(GeometryFilter(max_points=5)))["header"]
    assert h["truncated"] and h["total_points"] == 9
    assert [s["n_points"] for s in h["segments"]] == [2, 2]  # third segment would hit 6
    one = decode_geometry(ds.geometry(GeometryFilter(max_points=1)))
    assert one["header"]["n_points"] == 1 and list(one["offsets"]) == [0, 1]


def test_invalid_filters():
    with pytest.raises(ValueError):
        GeometryFilter(region={"chrom": "chr1", "start": 5})
    with pytest.raises(ValueError):
        GeometryFilter(region={"chrom": "chr1", "start": 5, "end": 5})
    with pytest.raises(ValueError):
        GeometryFilter(max_points=0)


def test_store_load_csv_and_missing(tmp_path):
    store = DatasetStore()
    df = pd.DataFrame({"chrom": ["chr1"] * 3, "start": [0, 10, 20], "end": [10, 20, 30],
                       "x": [0.0, 1, 2], "y": [0.0, 0, 0], "z": [0.0, 0, 1]})
    csv = tmp_path / "recon.csv"
    df.to_csv(csv)
    ds = store.load(csv)
    assert ds.name == "recon" and ds.summary()["n_spots"] == 3
    assert [d.id for d in store.list()] == [ds.id]
    store.remove(ds.id)
    assert store.list() == []
    with pytest.raises(FileNotFoundError):
        store.load(tmp_path / "nope.chromdata.zarr")


@pytest.mark.skipif(not SOX2.exists(), reason="in-repo Sox2 FISH fixture missing")
def test_real_fish_data_with_missing_spots():
    """mESC Sox2 DNA FISH (5 cells, 41 loci, 49 missing spots)."""
    store = DatasetStore()
    ds = store.load(SOX2)
    s = ds.summary()
    assert s["n_spots"] == 205 and s["n_traces"] == 5 and s["trace_mode"] is True

    g = decode_geometry(ds.geometry(GeometryFilter()))
    h = g["header"]
    finite = np.isfinite(ds.cd.coords).all(axis=1)
    assert h["n_points"] == int(finite.sum()) == 156
    assert {s["trace_id"] for s in h["segments"]} == set(ds.cd.spots["trace_id"].astype(str))
    # every segment is a gap-free, start-ordered run of one trace
    for i, seg in enumerate(h["segments"]):
        lo, hi = g["offsets"][i], g["offsets"][i + 1]
        starts = g["starts"][lo:hi]
        assert (np.diff(starts.astype(np.int64)) > 0).all()
        sel = ds.cd.spots["trace_id"].astype(str) == seg["trace_id"]
        expected = ds.cd.coords[sel.to_numpy()]
        expected = expected[np.isin(ds.cd.spots["start"][sel], starts)]
        np.testing.assert_allclose(g["positions"][lo:hi], expected, rtol=1e-6)
    # positions match the float32 cast of the source coordinates
    assert g["positions"].dtype == np.float32


def test_cells_table_and_filter():
    _, ds = _toy()
    c = ds.cells()
    assert c["total"] == 3
    assert [r["cell_id"] for r in c["cells"]] == ["cell_t_a", "cell_t_b", "cell_t_c"]
    assert c["cells"][0] == {"cell_id": "cell_t_a", "n_spots": 5, "n_traces": 1, "n_chroms": 1}
    h = decode_geometry(ds.geometry(GeometryFilter(cell_ids=["cell_t_b"])))["header"]
    assert [(s["trace_id"], s["cell_id"]) for s in h["segments"]] == [("t_b", "cell_t_b")]


def test_cells_natural_order_and_missing_column():
    from uchrom_browser.data import natural_key
    assert sorted(["c10", "c2", "c1", "b"], key=natural_key) == ["b", "c1", "c2", "c10"]
    store = DatasetStore()
    spots = pd.DataFrame({"chrom": ["chr1"] * 2, "start": [0, 10], "end": [10, 20],
                          "trace_id": ["t"] * 2})
    ds = store.add(ChromData(np.zeros((2, 3)), spots), name="nocell")
    assert ds.cells() == {"total": 0, "cells": []}
    h = decode_geometry(ds.geometry(GeometryFilter(cell_ids=["x"])))["header"]
    assert h["n_points"] == 0


def _cells(offset: float, n_cells: int = 6, n: int = 200, seed: int = 0) -> ChromData:
    """Random-walk 'structures' of ``n_cells`` cells, cell k shifted by ``k * offset`` along x."""
    rng = np.random.default_rng(seed)
    coords, rows = [], []
    for k in range(n_cells):
        walk = np.cumsum(rng.normal(size=(n, 3)), axis=0)
        coords.append(walk - walk.mean(0) + [k * offset, 0, 0])
        rows += [("chr1", i * 1000, (i + 1) * 1000, f"c{k}_t", f"c{k}") for i in range(n)]
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    return ChromData(np.concatenate(coords), spots)


@pytest.mark.parametrize("backed", [False, True])
def test_cells_overlap_tells_stacked_models_from_placed_cells(tmp_path, backed):
    for offset, want in ((0.0, True), (200.0, False)):
        cd = _cells(offset)
        if backed:
            path = tmp_path / f"c{int(offset)}.chromdata.zarr"
            cd.write(path)
            ds = DatasetStore().load(path)
        else:
            ds = DatasetStore().add(cd, name="cells")
        assert ds.cells_overlap() is want
        assert ds.summary()["cells_overlap"] is want


def test_positions_in_the_3d_frame_are_told_apart():
    cd = _cells(200.0)                                        # cells placed 200 apart along x
    centre = pd.DataFrame(np.asarray(cd.coords), columns=list("xyz")).groupby(cd.spots["cell_id"].astype(str).to_numpy()).mean()
    for shift, want in ((0.0, True), (5000.0, False)):     # positions at the cells' centres, or elsewhere
        c = cd.copy()
        cells = pd.DataFrame(index=pd.Index(centre.index, name="cell_id"))
        cells["px"], cells["py"] = centre["x"].to_numpy() + shift, centre["y"].to_numpy()
        c.cells = cells
        c.set_cell_positions(columns=["px", "py"], unit="micron")
        ds = DatasetStore().add(c, name="placed")
        assert [s["in_coords_frame"] for s in ds.spatial()] == [want]


def test_traces_in_crops_of_their_own_count_as_overlapping():
    # ORCA-like: x, y local to each trace's crop, z spread over the stack
    cd = _cells(0.0)
    xyz = np.asarray(cd.coords).copy()
    cells = cd.spots["cell_id"].astype(str).to_numpy()
    for k, c in enumerate(sorted(set(cells))):
        xyz[cells == c, 2] += 10.0 * k
    ds = DatasetStore().add(ChromData(xyz, cd.spots), name="crops")
    assert ds.cells_overlap() is True


def test_stats_window_and_per_cell_median(tmp_path, monkeypatch):
    """Windowed stats filter by [start, end), drop 1-spot window fragments in Rg,
    report per_cell_median, and forward windows through _stats_sample."""
    import uchrom_browser.data as data_mod

    rows = []
    coords = []
    # Cell c0 has 2 traces (Rg in [1000, 3000) is 1.0 and 1.0) + 1 trace clipped to a 1-spot fragment
    for tid, xs in [("c0_a", [0, 0, 2, 0]), ("c0_b", [0, 0, 2, 0])]:
        for k, x in enumerate(xs):
            rows.append({"chrom": "chr1", "start": k * 1000, "end": (k + 1) * 1000, "trace_id": tid, "cell_id": "c0"})
            coords.append([float(x), 0.0, 0.0])
    # A trace that only has 1 spot inside [1000, 3000) (spot at [2000, 3000)): degenerate in window
    rows.extend([
        {"chrom": "chr1", "start": 0, "end": 1000, "trace_id": "c0_frag", "cell_id": "c0"},
        {"chrom": "chr1", "start": 2000, "end": 3000, "trace_id": "c0_frag", "cell_id": "c0"},
    ])
    coords.extend([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
    # Cell c1 has 1 trace whose spread in [1000, 3000) is Rg = 10.0 (centroid=10, dists=10)
    for k, x in enumerate([0.0, 0.0, 20.0, 0.0]):
        rows.append({"chrom": "chr1", "start": k * 1000, "end": (k + 1) * 1000, "trace_id": "c1_a", "cell_id": "c1"})
        coords.append([x, 0.0, 0.0])

    cd = ChromData(np.array(coords, float), pd.DataFrame(rows), uns={"xyz_unit": "um"})
    ds = DatasetStore().add(cd, name="win")

    # Whole-chrom stats_rg keeps all 4 traces (c0_a=sqrt(3)/2, c0_b=sqrt(3)/2, c0_frag=5.0 -> med=sqrt(3)/2; c1_a=sqrt(75) -> ~8.66)
    full_rg = ds.stats_rg("chr1")
    assert len(full_rg["rg"]) == 4
    expected_full = 0.5 * (float(np.sqrt(3) / 2) + float(np.sqrt(75)))
    assert full_rg["per_cell_median"] == pytest.approx(expected_full)

    # Window [1000, 3000): c0_frag only has 1 spot inside window -> excluded from windowed stats_rg
    win_rg = ds.stats_rg("chr1", start=1000, end=3000)
    assert set(win_rg["trace_ids"]) == {"c0_a", "c0_b", "c1_a"}
    assert win_rg["n_spots"] == [2, 2, 2]
    assert win_rg["per_cell_median"] == pytest.approx(5.5)

    # Windowed scaling only measures pairs inside [1000, 3000) -> max sep is 1000 bp
    win_sc = ds.stats_scaling("chr1", start=1000, end=3000, n_bins=4)
    assert max(win_sc["sep_bp"]) <= 1100.0
    assert sum(win_sc["n_pairs"]) == 3  # 1 pair each in c0_a, c0_b, c1_a (c0_frag has only 1 spot in window)

    # Validation errors
    with pytest.raises(ValueError):
        ds.stats_rg(chrom=None, start=1000, end=3000)
    with pytest.raises(ValueError):
        ds.stats_rg(chrom="*", start=1000, end=3000)
    with pytest.raises(ValueError):
        ds.stats_scaling(chrom="chr1", start=3000, end=3000)

    # Large backed store (_index_segments() True): must forward start/end & disclose note without reading _segments()
    path = tmp_path / "large.chromdata.zarr"
    cd.write(path)
    monkeypatch.setattr(data_mod, "LARGE_SPOTS", 1)
    monkeypatch.setattr(data_mod, "STATS_MAX_SPOTS", 1)
    bds = DatasetStore().load(path)
    monkeypatch.setattr(bds, "_segments", lambda: (_ for _ in ()).throw(AssertionError("_segments must not run")))
    sampled_rg = bds.stats_rg("chr1", start=1000, end=3000)
    assert set(sampled_rg["trace_ids"]) <= {"c0_a", "c0_b", "c1_a"}
    assert "random sample" in (sampled_rg["note"] or "")
    sampled_sc = bds.stats_scaling("chr1", start=1000, end=3000, n_bins=4)
    assert max(sampled_sc["sep_bp"]) <= 1100.0
    assert "random sample" in (sampled_sc["note"] or "")


def test_stats_ps_power_law_and_edge_cases(tmp_path):
    """Analytical C(k) ~ (n - k) * k^-1 recovers slope -1.0 and handles sparse/degenerate edge cases."""
    cooler = pytest.importorskip("cooler")

    bs, n = 10_000, 40
    bins = pd.DataFrame({"chrom": "chr1", "start": np.arange(n) * bs, "end": np.arange(1, n + 1) * bs})
    i, j = np.triu_indices(n, 0)
    k = j - i
    cnt = np.where(k == 0, 50_000, np.round(10_000.0 / np.maximum(k, 1))).astype(int)
    cooler.create_cooler(str(tmp_path / "decay.cool"), bins, pd.DataFrame({"bin1_id": i, "bin2_id": j, "count": cnt}), ordered=True)

    # Also test a k=0-only cooler and 1-bin chrom cooler
    bins_1 = pd.DataFrame({"chrom": ["chr1", "chrShort"], "start": [0, 0], "end": [10_000, 10_000]})
    cooler.create_cooler(str(tmp_path / "k0.cool"), bins_1, pd.DataFrame({"bin1_id": [0], "bin2_id": [0], "count": [42]}), ordered=True)

    spots = pd.DataFrame({c: pd.Series(dtype=t) for c, t in [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str)]})
    cd = ChromData(np.zeros((0, 3)), spots)
    cd.link_cool("decay.cool", key="decay")
    cd.link_cool("k0.cool", key="k0")
    cd.write(tmp_path / "ps.chromdata.zarr")
    ds = DatasetStore().load(tmp_path / "ps.chromdata.zarr")

    # Request n_bins >= n - 1 so early diagonals have |K_b| == 1 (exact single-diagonal identity check)
    ps = ds.stats_ps(key="decay", chrom="chr1", n_bins=n)
    assert ps["slope"] == pytest.approx(-1.0, abs=0.02)
    t_cis = float(cnt.sum())
    assert ps["total_cis_contacts"] == pytest.approx(t_cis)
    c1 = float(cnt[k == 1].sum())
    assert ps["p"][0] == pytest.approx((c1 / (n - 1)) / t_cis)

    # Fit sub-range smin/smax + large n_bins > k_max
    sub = ds.stats_ps(key="decay", chrom="chr1", n_bins=100, smin=20_000, smax=200_000)
    assert sub["fit_range_bp"] == [20_000, 200_000]
    assert sub["slope"] == pytest.approx(-1.0, abs=0.02)

    # k=0 only / < 2 bins -> empty arrays, None slope
    empty_ps = ds.stats_ps(key="k0", chrom="chr1")
    assert empty_ps["sep_bp"] == [] and empty_ps["slope"] is None
    with pytest.raises(LookupError):
        DatasetStore().add(ChromData(np.zeros((0, 3)), spots), name="nomap").stats_ps()
    with pytest.raises(ValueError):
        ds.stats_ps(key="decay", chrom="chr1", smin=50_000, smax=10_000)
    with pytest.raises(ValueError):
        ds.stats_ps(key="decay", chrom="chr1", n_bins=0)
