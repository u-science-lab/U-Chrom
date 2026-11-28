"""skills/compare-groups/scripts/compare_groups.py on synthetic data with known answers."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from tests import REPO

SCRIPT = REPO / "skills/compare-groups/scripts/compare_groups.py"
spec = importlib.util.spec_from_file_location("compare_groups", SCRIPT)
cg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cg)


def _cd(n_a=6, n_b=6, traces=4, scale_a=2.0, rng=np.random.default_rng(0)):
    rows, xyz, cells = [], [], []
    for g, n, sc in (("A", n_a, scale_a), ("B", n_b, 1.0)):
        for c in range(n):
            cid = f"{g}{c}"
            cells.append((cid, g, 100.0 + c))
            for t in range(traces):
                for k in range(10):
                    rows.append(("chr1", k * 10, k * 10 + 10, f"{cid}_t{t}", cid))
                    xyz.append(rng.normal(0, sc, 3))
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    cdf = pd.DataFrame(cells, columns=["cell_id", "cell_type", "nuc_volume_um3"]).set_index("cell_id")
    return ChromData(np.array(xyz), spots, cells=cdf)


def test_cell_is_the_unit_and_direction_is_right():
    res = cg.compare(_cd(), "field:cell_type=A", "field:cell_type=B", stat="rg", confounder=None)
    assert res["a"]["n_cells"] == 6 and res["b"]["n_cells"] == 6
    assert res["a"]["n_traces"] == 24
    assert res["a"]["median"] > 1.5 * res["b"]["median"]
    assert res["effect"]["rank_biserial"] == 1.0          # every A cell above every B cell
    assert res["test"]["p"] < 0.01


def test_small_groups_and_overlap_are_flagged():
    cd = _cd(n_a=3)
    res = cg.compare(cd, "field:cell_type=A", "A0,B0,B1,B2,B3,B4", stat="rg", confounder=None)
    joined = " ".join(res["checks"])
    assert "fewer than 5 cells" in joined and "overlap" in joined


def test_cells_column_stat():
    res = cg.compare(_cd(), "field:cell_type=A", "field:cell_type=B", stat="nuc_volume_um3", confounder=None)
    assert res["unit"] == "cell" and res["a"]["median"] == 102.5


# ------------------------------------------------------------------ windowed tracing
def test_windowed_tracing_validation_and_overlap(tmp_path):
    import json
    import subprocess
    import sys
    import pytest

    cd = _cd(n_a=5, n_b=5, traces=2, scale_a=3.0)
    with pytest.raises(ValueError):
        cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="rg", start=0, end=50)
    with pytest.raises(ValueError):
        cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="rg", chrom="*", start=0, end=50)
    with pytest.raises(ValueError):
        cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="rg", chrom="chr1", start=50, end=50)

    # Window [15, 45) overlaps loci with start in {10, 20, 30, 40} -> 4 spots/trace
    res = cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="n_spots", confounder=None,
                     chrom="chr1", start=15, end=45)
    assert res["a"]["median"] == 4.0 and res["b"]["median"] == 4.0

    # Negative start clamps to 0; end=None defaults to chrom max end
    res_open = cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="n_spots", confounder=None,
                          chrom="chr1", start=-10, end=None)
    assert res_open["a"]["median"] == 10.0

    # Window containing only 1 spot per trace drops <2-spot fragments for rg/span
    res_1 = cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="rg", confounder=None,
                       chrom="chr1", start=0, end=10)
    assert res_1["a"]["n_cells"] == 0 and res_1["b"]["n_cells"] == 0

    # CLI forwarding
    store = tmp_path / "win.chromdata.zarr"
    cd.write(store)
    out = subprocess.check_output([
        sys.executable, str(SCRIPT), str(store),
        "--a", "field:cell_type=A", "--b", "field:cell_type=B",
        "--stat", "n_spots", "--chrom", "chr1", "--start", "15", "--end", "45",
    ], text=True)
    parsed = json.loads(out)
    assert parsed["a"]["median"] == 4.0


# ------------------------------------------------------------------ per-cell contact map stats
def _make_scool_store(tmp_path, *, n_a=5, n_b=5, slope_a=-1.0, slope_b=-1.8, depth_a=2000.0, depth_b=2000.0,
                      sparse_first_diag=False, embed=False, delete_scool=False, as_cdz=False):
    import cooler
    from chromdata import embedded

    bs, nbins = 100_000, 40
    bins = pd.DataFrame({"chrom": "chr1", "start": np.arange(nbins) * bs, "end": np.arange(1, nbins + 1) * bs})
    ii, jj = np.triu_indices(nbins, 1)
    k_diag = jj - ii
    maps = {}
    cell_rows = []
    for grp, n, slp, dep in (("A", n_a, slope_a, depth_a), ("B", n_b, slope_b, depth_b)):
        for c in range(n):
            cid = f"{grp}{c}"
            cell_rows.append((cid, grp))
            if sparse_first_diag and grp == "A" and c == 0:
                # only 2 positive diagonals -> ps_slope should be NaN/dropped
                maps[cid] = pd.DataFrame({"bin1_id": [0, 0], "bin2_id": [1, 2], "count": [5, 5]})
                continue
            w = (k_diag.astype(float)) ** slp
            if dep >= 1000:
                cnt = np.round(w / w.sum() * (dep * (1.0 + 0.05 * c) * 20.0)).astype(int)
            else:
                cnt = np.where(k_diag <= 5, 1, 0)
            m = cnt > 0
            maps[cid] = pd.DataFrame({"bin1_id": ii[m], "bin2_id": jj[m], "count": cnt[m]})
    scool_path = tmp_path / "cells.scool"
    cooler.create_scool(str(scool_path), bins, maps, ordered=True)
    cells_df = pd.DataFrame(cell_rows, columns=["cell_id", "cell_type"]).set_index("cell_id")
    spots = pd.DataFrame(columns=["chrom", "start", "end", "trace_id", "cell_id"])
    cd = ChromData(np.zeros((0, 3)), spots, cells=cells_df)
    cd.link_scool(scool_path, key="per_cell", bin_size=bs)
    store_path = tmp_path / "data.chromdata.zarr"
    cd.write(store_path)
    if embed:
        embedded.embed_links(store_path, verbose=False)
    if delete_scool:
        scool_path.unlink()
    if as_cdz:
        from chromdata.zarrcd import _zip_tree
        cdz_path = tmp_path / "data.cdz"
        _zip_tree(store_path, cdz_path)
        return cdz_path
    return store_path


def test_contact_stats_embedded_without_cooler_or_h5py(tmp_path, monkeypatch):
    import sys
    import pytest

    store = _make_scool_store(tmp_path, embed=True, delete_scool=True)
    cdz_dir = tmp_path / "cdz_sub"
    cdz_dir.mkdir()
    cdz = _make_scool_store(cdz_dir, embed=True, delete_scool=True, as_cdz=True)

    monkeypatch.setitem(sys.modules, "cooler", None)
    monkeypatch.setitem(sys.modules, "h5py", None)

    for path in (store, cdz):
        cd = ChromData.read(path, backed=True)
        res = cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="ps_slope", chrom="chr1")
        assert res["a"]["n_cells"] == 5 and res["b"]["n_cells"] == 5
        assert res["a"]["median"] == pytest.approx(-1.0, abs=0.1)
        assert res["b"]["median"] == pytest.approx(-1.8, abs=0.15)
        assert res["a"]["median"] > res["b"]["median"]
        assert res["a"]["median_cis_contacts"] > 1000
        assert res["test"]["p"] < 0.05

        res_den = cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="contact_density", chrom="chr1")
        assert res_den["a"]["median"] > 0 and res_den["b"]["median"] > 0

        res_cis = cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="cis_contacts", chrom="chr1")
        assert res_cis["a"]["median"] == res["a"]["median_cis_contacts"]


def test_contact_stats_scool_fallback_and_warnings(tmp_path, monkeypatch):
    import sys

    store = _make_scool_store(tmp_path, slope_a=-1.0, slope_b=-1.0, depth_a=200.0, depth_b=200.0,
                              sparse_first_diag=True, embed=False, delete_scool=False)
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "cooler", None)
        cd = ChromData.read(store, backed=True)
        res = cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="ps_slope", chrom="chr1")
        # A0 had <3 positive diagonals -> dropped
        assert res["a"]["n_cells"] == 4 and res["b"]["n_cells"] == 5
        joined = " ".join(res["checks"]).lower()
        assert "sparse single-cell contact maps" in joined

    # Depth confounder warning when ps_slope tracks cis_contacts
    d2 = tmp_path / "conf"
    d2.mkdir()
    import cooler
    bs, nbins = 100_000, 30
    bins = pd.DataFrame({"chrom": "chr1", "start": np.arange(nbins) * bs, "end": np.arange(1, nbins + 1) * bs})
    ii, jj = np.triu_indices(nbins, 1)
    k_diag = jj - ii
    maps = {}
    rows = []
    for idx in range(10):
        cid = f"c{idx}"
        grp = "A" if idx < 5 else "B"
        rows.append((cid, grp))
        slp = -0.6 - 0.15 * idx
        dep = 1000 * (idx + 1)
        w = (k_diag.astype(float)) ** slp
        cnt = np.maximum(1, np.round(w / w.sum() * dep).astype(int))
        maps[cid] = pd.DataFrame({"bin1_id": ii, "bin2_id": jj, "count": cnt})
    sc_path = d2 / "d.scool"
    cooler.create_scool(str(sc_path), bins, maps, ordered=True)
    cd2 = ChromData(np.zeros((0, 3)), pd.DataFrame(columns=["chrom", "start", "end", "trace_id", "cell_id"]),
                    cells=pd.DataFrame(rows, columns=["cell_id", "cell_type"]).set_index("cell_id"))
    cd2.link_scool(sc_path, key="per_cell", bin_size=bs)
    res_conf = cg.compare(cd2, "field:cell_type=A", "field:cell_type=B", stat="ps_slope", chrom="chr1")
    assert any("cis_contacts" in c for c in res_conf["checks"])


def test_contact_stats_multires_resolution_selection(tmp_path, monkeypatch):
    import sys
    import zarr
    from chromdata import embedded

    # Create embedded per_cell map with two resolutions (1000 and 100_000) where span=50_000_000 ->
    # 50_000_000 / 1000 = 50_000 > 25_000, so 100_000 (span/r = 500 <= 25_000) is chosen;
    # for window [0, 10_000_000), 10_000_000 / 1000 = 10_000 <= 25_000, so 1000 is chosen!
    store = _make_scool_store(tmp_path, embed=True, delete_scool=True)
    # Manually add a finer resolution r1000 to the embedded group to verify multi-res selection
    root = zarr.open_group(str(store), path="embedded/contacts/per_cell", mode="r+", zarr_format=3, use_consolidated=False)
    meta = dict(root.attrs["uchrom_contacts"])
    meta["resolutions"] = [1000, 100_000]
    meta["chromsizes"] = {"chr1": 50_000_000}
    meta["chrom_first_bin"]["1000"] = [0]
    r1k = root.create_group("r1000")
    bg = r1k.create_group("bins")
    n1k = 50_000
    bg.create_array("chrom", data=np.zeros(n1k, dtype=np.uint8))
    bg.create_array("start", data=np.arange(n1k, dtype=np.int32) * 1000)
    bg.create_array("end", data=np.arange(1, n1k + 1, dtype=np.int32) * 1000)
    cis = r1k.create_group("cis/chr1")
    # Put 5 pixels per cell in r1000 within [0, 10_000_000)
    nc = int(root["cells"].shape[0])
    pix = np.tile(np.array([[0, 1, 10], [0, 2, 5], [0, 3, 2]], dtype=np.uint32), (nc, 1))
    cis.create_array("pix", data=pix.T)
    cis.create_array("cell_offset", data=np.arange(nc + 1, dtype=np.int64) * 3)
    root.attrs["uchrom_contacts"] = meta
    embedded.consolidate_sections(store)

    monkeypatch.setitem(sys.modules, "cooler", None)
    monkeypatch.setitem(sys.modules, "h5py", None)
    cd = ChromData.read(store, backed=True)
    # Full chr1 (span=50Mb) picks r100_000 (cis_contacts >> 17)
    full = cg.per_cell(cd, "cis_contacts", cg.resolve_group(cd, "all"), chrom="chr1")
    assert (full > 100).all()
    # Window [0, 10Mb) picks r1000 (each cell has 10+5+2 = 17 contacts)
    win = cg.per_cell(cd, "cis_contacts", cg.resolve_group(cd, "all"), chrom="chr1", start=0, end=10_000_000)
    assert (win == 17).all()


# ------------------------------------------------------------------ Format 2.3/2.4: clusters, region, trace_kind
def test_clusters_metrics_and_format24_checks():
    cd = _cd(n_a=6, n_b=6)
    cd.cells["region"] = "fov_1"
    cd.uns["trace_kind"] = "set"

    frag_rows = []
    for i in range(6):
        # Group A: larger cis clusters on chr1
        for k in range(3):
            for f in range(4):
                frag_rows.append((f"A{i}_cl{k}", f"A{i}", "chr1", f * 1000 + 10, f * 1000 + 500))
        # Group B: smaller trans clusters (chr1 + chr2)
        for k in range(2):
            frag_rows.append((f"B{i}_cl{k}", f"B{i}", "chr1", 100, 500))
            frag_rows.append((f"B{i}_cl{k}", f"B{i}", "chr2", 200, 600))
    fdf = pd.DataFrame(frag_rows, columns=["cluster", "cell", "chrom", "start", "end"])
    cd.set_clusters("sprite", fdf, cell="cell")

    r_n = cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="clusters:sprite:n_clusters", confounder=None)
    assert r_n["a"]["median"] == 3.0 and r_n["b"]["median"] == 2.0

    r_sz = cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="clusters:sprite:median_size", confounder=None)
    assert r_sz["a"]["median"] == 4.0 and r_sz["b"]["median"] == 2.0

    r_cf = cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="clusters:sprite:cis_frac", confounder=None)
    assert r_cf["a"]["median"] == 1.0 and r_cf["b"]["median"] == 0.0

    # Windowed clusters metric
    r_win = cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="clusters:sprite:cis_frac",
                       confounder=None, chrom="chr1", start=0, end=2500)
    assert r_win["a"]["median"] == 1.0 and r_win["b"]["median"] == 0.0

    # trace_kind="set" + span warning + single region warning
    r_span = cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="span", confounder=None)
    joined = " ".join(r_span["checks"]).lower()
    assert "set" in joined and "span" in joined
    assert "region" in joined and "no replicate" in joined


def test_review_regressions_dedup_equalize_and_scool_binsize(tmp_path):
    h5py = pytest.importorskip("h5py")

    # 1. Duplicate IDs deduplicated cleanly (with check note) & --equalize 1 reports 2 consistently
    cd = _cd(n_a=5, n_b=5)
    r_dup = cg.compare(cd, "A0,A0,A1,A2,A3,A4", "field:cell_type=B", stat="rg", confounder=None)
    assert r_dup["a"]["n_cells"] == 5
    assert any("duplicate" in c.lower() for c in r_dup["checks"])

    r_eq1 = cg.compare(cd, "field:cell_type=A", "field:cell_type=B", stat="span", confounder=None, equalize=1)
    assert r_eq1["equalized_loci_per_trace"] == 2
    assert any("2 random loci" in c for c in r_eq1["checks"])

    # 2. .scool with trailing partial bin and small single-bin contigs still infers 100 bp nominal bin size
    scool_path = tmp_path / "partial_contigs.scool"
    with h5py.File(scool_path, "w") as f:
        chroms = ["chr1"] + [f"ctg{i}" for i in range(5)]
        f.create_dataset("chroms/name", data=np.array(chroms, dtype="S"))
        f.create_dataset("chroms/length", data=np.array([350] + [50] * 5, dtype=np.int64))
        b_chrom = np.array([0, 0, 0, 0, 1, 2, 3, 4, 5], dtype=np.int64)
        b_start = np.array([0, 100, 200, 300, 0, 0, 0, 0, 0], dtype=np.int64)
        b_end = np.array([100, 200, 300, 350, 50, 50, 50, 50, 50], dtype=np.int64)
        f.create_dataset("bins/chrom", data=b_chrom)
        f.create_dataset("bins/start", data=b_start)
        f.create_dataset("bins/end", data=b_end)
        cg_grp = f.create_group("cells")
        for i, cid in enumerate([f"A{k}" for k in range(5)] + [f"B{k}" for k in range(5)]):
            g = cg_grp.create_group(cid)
            g.create_dataset("pixels/bin1_id", data=np.array([0, 0, 0], dtype=np.int64))
            g.create_dataset("pixels/bin2_id", data=np.array([1, 2, 3], dtype=np.int64))
            g.create_dataset("pixels/count", data=np.array([30.0 + i, 10.0, 2.0], dtype=np.float64))
            off = np.zeros(len(b_chrom) + 1, dtype=np.int64)
            off[1:] = 3
            g.create_dataset("indexes/bin1_offset", data=off)

    cd.uns["linked_scool"] = {"default": {"path": str(scool_path)}}
    df = cg._contact_stats(cd, [f"A{k}" for k in range(5)], smin=100, smax=300)
    assert np.isfinite(df["ps_slope"]).all()
    # With r=100, k in [1..3] includes pixels (0,1)=30+, (0,2)=10, (0,3)=2 out of 3+2+1 = 6 possible pairs
    assert df.loc["A0", "contact_density"] == pytest.approx((30.0 + 10.0 + 2.0) / 6.0)

