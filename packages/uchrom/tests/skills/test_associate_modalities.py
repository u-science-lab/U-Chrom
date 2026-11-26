"""skills/associate-modalities/scripts/associate.py tests for P1 extensions."""

import importlib.util
import json
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData, embedded
from tests import REPO

SCRIPT = REPO / "skills/associate-modalities/scripts/associate.py"
spec = importlib.util.spec_from_file_location("associate", SCRIPT)
assoc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assoc)


def _tracing_cd(n_cells=12, loci=10, rng=np.random.default_rng(7)):
    rows, xyz, cells = [], [], []
    for c in range(n_cells):
        cid = f"c{c}"
        ct = "A" if c < n_cells // 2 else "B"
        scale = 1.0 + 0.3 * c
        cells.append((cid, ct, 100.0 + c, float(c)))
        for t in range(2):
            for k in range(loci):
                rows.append(("chr1", k * 1000, (k + 1) * 1000, f"{cid}_t{t}", cid))
                xyz.append(rng.normal(0, scale, 3))
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    cdf = pd.DataFrame(cells, columns=["cell_id", "cell_type", "nuc_volume_um3", "if.X"]).set_index("cell_id")
    return ChromData(np.array(xyz), spots, cells=cdf)


def test_windowed_tracing_validation_and_cell_level(tmp_path):
    cd = _tracing_cd()
    with pytest.raises(ValueError):
        assoc.cell_level(cd, "if.X", "rg", start=0, end=5000)
    with pytest.raises(ValueError):
        assoc.cell_level(cd, "if.X", "rg", chrom="*", start=0, end=5000)
    with pytest.raises(ValueError):
        assoc.cell_level(cd, "if.X", "rg", chrom="chr1", start=5000, end=1000)

    ns = assoc.per_cell(cd, "n_spots", chrom="chr1", start=1500, end=4500)
    assert (ns == 4.0).all()

    # Window with only 1 spot per trace -> <2-spot fragments dropped -> NaN for rg/span
    pt = assoc.per_trace(cd, chrom="chr1", start=0, end=1000)
    assert pt["rg"].isna().all() and pt["span"].isna().all()

    res = assoc.cell_level(cd, "if.X", "rg", covariates=[], chrom="chr1", start=1000, end=8000)
    assert res["n_cells"] == 12 and res["rho"] > 0.5

    store = tmp_path / "assoc_win.chromdata.zarr"
    cd.write(store)
    out = subprocess.check_output([
        sys.executable, str(SCRIPT), "cell", str(store),
        "--x", "if.X", "--y", "n_spots", "--chrom", "chr1", "--start", "1500", "--end", "4500",
    ], text=True)
    parsed = json.loads(out)
    assert parsed["n_cells"] == 12


def test_contact_stats_embedded_and_scool_fallback(tmp_path, monkeypatch):
    import cooler

    bs, nbins = 100_000, 30
    bins = pd.DataFrame({"chrom": "chr1", "start": np.arange(nbins) * bs, "end": np.arange(1, nbins + 1) * bs})
    ii, jj = np.triu_indices(nbins, 1)
    k_diag = jj - ii
    maps, rows = {}, []
    for idx in range(10):
        cid = f"c{idx}"
        slp = -0.7 - 0.1 * idx
        rows.append((cid, "A" if idx < 5 else "B", float(idx)))
        w = (k_diag.astype(float)) ** slp
        cnt = np.maximum(1, np.round(w / w.sum() * 3000.0).astype(int))
        maps[cid] = pd.DataFrame({"bin1_id": ii, "bin2_id": jj, "count": cnt})

    scool_path = tmp_path / "cells.scool"
    cooler.create_scool(str(scool_path), bins, maps, ordered=True)
    cdf = pd.DataFrame(rows, columns=["cell_id", "cell_type", "if.M"]).set_index("cell_id")
    cd = ChromData(np.zeros((0, 3)), pd.DataFrame(columns=["chrom", "start", "end", "trace_id", "cell_id"]), cells=cdf)
    cd.link_scool(scool_path, key="per_cell", bin_size=bs)
    store = tmp_path / "sc.chromdata.zarr"
    cd.write(store)

    # 1. External scool fallback (cooler=None)
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "cooler", None)
        r_sc = assoc.cell_level(ChromData.read(store, backed=True), "if.M", "ps_slope",
                                covariates=[], chrom="chr1", smin=100_000, smax=2_000_000)
        assert r_sc["n_cells"] == 10 and r_sc["rho"] < -0.7

    # 2. Embedded Zarr & .cdz with external .scool deleted and cooler=None, h5py=None
    from chromdata.zarrcd import _zip_tree
    embedded.embed_links(store, verbose=False)
    cdz = tmp_path / "sc.cdz"
    _zip_tree(store, cdz)
    scool_path.unlink()

    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "cooler", None)
        mp.setitem(sys.modules, "h5py", None)
        for p in (store, cdz):
            cdb = ChromData.read(p, backed=True)
            r_emb = assoc.cell_level(cdb, "if.M", "ps_slope", covariates=[], chrom="chr1")
            assert r_emb["n_cells"] == 10 and r_emb["rho"] < -0.7
            cis = assoc.per_cell(cdb, "cis_contacts", chrom="chr1")
            den = assoc.per_cell(cdb, "contact_density", chrom="chr1")
            assert (cis > 2000).all() and (den > 0).all()


def test_clusters_metrics():
    cd = _tracing_cd(n_cells=8)
    frags = []
    for i in range(8):
        for k in range(i + 1):
            for f in range(3):
                frags.append((f"c{i}_cl{k}", f"c{i}", "chr1", f * 1000, f * 1000 + 400))
        if i % 2 == 0:
            frags.append((f"c{i}_tr", f"c{i}", "chr1", 100, 400))
            frags.append((f"c{i}_tr", f"c{i}", "chr2", 200, 500))
    cd.set_clusters("sprite", pd.DataFrame(frags, columns=["cluster", "cell", "chrom", "start", "end"]), cell="cell")

    nc = assoc.per_cell(cd, "clusters:sprite:n_clusters")
    assert nc["c0"] == 2.0 and nc["c1"] == 2.0 and nc["c7"] == 8.0
    ms = assoc.per_cell(cd, "clusters:sprite:median_size")
    assert ms["c1"] == 3.0
    cf = assoc.per_cell(cd, "clusters:sprite:cis_frac", chrom="chr1", start=0, end=3000)
    assert cf["c1"] == 1.0 and cf["c0"] == 0.5

    res = assoc.cell_level(cd, "if.X", "clusters:sprite:n_clusters", covariates=[], group=None)
    assert res["rho"] > 0.9


def test_spatial_autocorr_and_cli(tmp_path):
    rng = np.random.default_rng(42)
    n_main, n_small = 36, 12
    # 6x6 grid in region A with smooth spatial gradient; 12 cells in region B with noise
    gx, gy = np.meshgrid(np.arange(6, dtype=float), np.arange(6, dtype=float))
    pos_a = np.column_stack([gx.ravel(), gy.ravel()])
    pos_b = rng.uniform(0, 5, size=(n_small, 2))
    pos = np.vstack([pos_a, pos_b])

    ids = [f"cell_{i}" for i in range(n_main + n_small)]
    reg = ["fovA"] * n_main + ["fovB"] * n_small
    grad = np.concatenate([pos_a[:, 0] + pos_a[:, 1], rng.normal(size=n_small)])
    const = np.ones(n_main + n_small)

    cdf = pd.DataFrame({"region": reg, "grad": grad, "const": const}, index=ids)
    cd = ChromData(np.zeros((0, 3)), pd.DataFrame(columns=["chrom", "start", "end", "trace_id", "cell_id"]), cells=cdf)
    cd.set_cell_positions(pos, cell_ids=ids, unit="um", frame="fov", region_col="region")

    r1 = assoc.spatial_autocorr(cd, "grad", k=4, permutations=99, seed=123)
    r2 = assoc.spatial_autocorr(cd, "grad", k=4, permutations=99, seed=123)
    assert r1 == r2
    assert r1["region"] == "fovA" and r1["n_cells"] == n_main
    assert r1["morans_i"] > 0.5
    assert r1["p_upper"] <= 0.02 and r1["p_two_sided"] <= 0.04

    # Constant feature handled cleanly
    rc = assoc.spatial_autocorr(cd, "const", region="fovA", k=4, permutations=49, seed=0)
    assert rc["morans_i"] is None and any("constant" in c.lower() for c in rc["checks"])

    # Small n handled cleanly
    cd_tiny = cd.get_cells(["cell_0", "cell_1", "cell_2"]) if "cell_id" in cd.spots.columns else ChromData(
        np.zeros((0, 3)), pd.DataFrame(columns=["chrom", "start", "end", "trace_id", "cell_id"]),
        cells=cdf.iloc[:3],
    )
    cd_tiny.set_cell_positions(pos[:3], cell_ids=ids[:3], unit="um", frame="fov", region_col="region")
    rt = assoc.spatial_autocorr(cd_tiny, "grad", k=4, permutations=49, seed=0)
    assert rt["morans_i"] is None and len(rt["checks"]) > 0

    # CLI spatial subcommand
    store = tmp_path / "sp.chromdata.zarr"
    cd.write(store)
    out = subprocess.check_output([
        sys.executable, str(SCRIPT), "spatial", str(store),
        "--feature", "grad", "--k", "4", "--permutations", "99", "--seed", "123",
    ], text=True)
    parsed = json.loads(out)
    assert parsed["morans_i"] == pytest.approx(r1["morans_i"])
