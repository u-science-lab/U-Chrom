"""Cell spatial position: centroids (``cells`` columns + ``uns['cell_spatial']``),
outlines (``cell_shapes``, GeoParquet) and linked SpatialData stores."""

import json
import sys

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from chromdata import cellspatial as cs


def _cd(n_cells=3):
    rows = [(f"c{c}", f"c{c}_t0", b) for c in range(n_cells) for b in range(4)]
    spots = pd.DataFrame(rows, columns=["cell_id", "trace_id", "b"])
    spots["chrom"] = "chr1"
    spots["start"] = spots["b"] * 100
    spots["end"] = spots["start"] + 100
    spots = spots.drop(columns="b")
    cells = pd.DataFrame({"cell_type": list("aba")[:n_cells]},
                         index=pd.Index([f"c{c}" for c in range(n_cells)], name="cell_id"))
    rng = np.random.default_rng(0)
    return ChromData(rng.normal(size=(len(spots), 3)), spots, cells=cells, uns={"xyz_unit": "um"})


SQUARES = {f"c{c}": np.array([[10 * c, 0], [10 * c + 5, 0], [10 * c + 5, 5], [10 * c, 5]], float)
           for c in range(3)}


# ---------------------------------------------------------------- centroids

def test_set_cell_positions_2d_schema():
    cd = _cd()
    rec = cd.set_cell_positions(np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]), unit="um", frame="tissue")
    assert rec == {"x_col": "centroid_x", "y_col": "centroid_y", "ndim": 2, "unit": "um", "frame": "tissue",
                   "status": "measured"}
    assert cd.uns["cell_spatial"]["default"] == rec
    pos = cd.cell_positions()
    assert list(pos.columns) == ["x", "y"] and list(pos.index) == ["c0", "c1", "c2"]
    assert pos.loc["c2"].tolist() == [5.0, 6.0]
    assert pos.attrs["cell_spatial"]["unit"] == "um"


def test_set_cell_positions_3d_aligned_by_cell_id_with_nan():
    cd = _cd()
    cd.set_cell_positions(np.array([[7.0, 8.0, 9.0], [1.0, 2.0, 3.0]]), cell_ids=["c2", "c0"],
                          frame="fov", region_col="cell_type", in_coords_frame=True)
    assert list(cd.cells.columns[-3:]) == ["centroid_x", "centroid_y", "centroid_z"]
    pos = cd.cell_positions()
    assert pos.loc["c0", ["x", "y", "z"]].tolist() == [1.0, 2.0, 3.0]
    assert pos.loc["c2", ["x", "y", "z"]].tolist() == [7.0, 8.0, 9.0]
    assert pos.loc["c1", ["x", "y", "z"]].isna().all()
    assert pos["region"].tolist() == ["a", "b", "a"]
    assert cd.uns["cell_spatial"]["default"]["in_coords_frame"] is True


def test_positions_from_dataframe_second_key_and_registration():
    cd = _cd()
    df = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]}, index=["c1", "c0"])
    cd.set_cell_positions(df, key="tangram", status="inferred", source="MERFISH", method="Tangram")
    assert "tangram_centroid_x" in cd.cells.columns
    assert cd.cell_positions("tangram").loc["c1"].tolist() == [1.0, 3.0]
    # register columns a loader already wrote
    cd.cells["gx"], cd.cells["gy"] = [1.0, 2.0, 3.0], [4.0, 5.0, 6.0]
    cd.set_cell_positions(columns=["gx", "gy"], key="glob", frame="global")
    assert cd.cell_positions("glob")["y"].tolist() == [4.0, 5.0, 6.0]
    with pytest.raises(KeyError):
        cd.cell_positions("nope")


def test_status_rules():
    cd = _cd()
    with pytest.raises(ValueError, match="source"):
        cd.set_cell_positions(np.zeros((3, 2)), status="inferred")
    with pytest.raises(ValueError, match="status"):
        cd.set_cell_positions(np.zeros((3, 2)), status="guessed")
    with pytest.raises(ValueError, match="shape"):
        cd.set_cell_positions(np.zeros((3, 4)))


def test_physical_units_from_voxel_size():
    cd = _cd()
    cd.set_cell_positions(np.array([[10.0, 20.0, 4.0]] * 3), unit="voxel", voxel_size=[0.1, 0.1, 0.25],
                          voxel_unit="um")
    raw = cd.cell_positions()
    phys = cd.cell_positions(physical=True)
    assert raw.loc["c0"].tolist() == [10.0, 20.0, 4.0]
    np.testing.assert_allclose(phys.loc["c0"].to_numpy(), [1.0, 2.0, 1.0])
    assert phys.attrs["cell_spatial"]["unit"] == "um" and phys.attrs["cell_spatial"]["stored_unit"] == "voxel"


def test_backward_compatible_names():
    # 1.x record (spatial_x / spatial_y, coordinate_system, inferred)
    cd = _cd()
    cd.cells["spatial_x"], cd.cells["spatial_y"] = [1.0, 2.0, 3.0], [4.0, 5.0, 6.0]
    cd.uns["cell_spatial"] = {"default": {"x_col": "spatial_x", "y_col": "spatial_y",
                                          "coordinate_system": "micron", "inferred": True, "source": "s"}}
    pos = cd.cell_positions()
    assert pos["x"].tolist() == [1.0, 2.0, 3.0]
    assert pos.attrs["cell_spatial"]["status"] == "inferred" and pos.attrs["cell_spatial"]["frame"] == "micron"
    assert cd.validate_links(check_files=False) == []
    # no record: the pre-2.3 seqFISH+ loader columns
    cd = _cd()
    cd.cells["x_centroid"], cd.cells["y_centroid"], cd.cells["z_centroid"] = 1.0, 2.0, 3.0
    pos = cd.cell_positions()
    assert pos.loc["c1"].tolist() == [1.0, 2.0, 3.0] and pos.attrs["cell_spatial"]["unrecorded"] is True
    with pytest.raises(KeyError):
        _cd().cell_positions()


def test_deprecated_setter_writes_schema():
    cd = _cd()
    with pytest.warns(DeprecationWarning):
        cd.set_cell_spatial_coordinates(np.ones((3, 2)), coordinate_system="fov_um", source="seg")
    rec = cd.uns["cell_spatial"]["default"]
    assert rec["x_col"] == "centroid_x" and rec["frame"] == "fov_um" and rec["status"] == "inferred"


# ---------------------------------------------------------------- outlines

def test_wkb_encoding_without_shapely():
    w = cs.polygon_wkb(SQUARES["c0"])
    assert cs.wkb_type(w) == "Polygon"
    ring = cs.polygon_rings(w)[0]
    assert ring.shape == (5, 2) and np.array_equal(ring[0], ring[-1])
    w3 = cs.polygon_wkb(np.c_[SQUARES["c0"], np.ones(4)])
    assert cs.wkb_type(w3) == "Polygon Z" and cs.polygon_rings(w3)[0].shape == (5, 3)
    assert cs.parse_ome_polygon(cs.format_ome_polygon(w)).tolist() == SQUARES["c0"].tolist()
    with pytest.raises(ValueError):
        cs.polygon_wkb(np.zeros((2, 2)))


@pytest.mark.parametrize("suffix", [".chromdata.zarr", ".cdz"])
def test_cell_shapes_round_trip(tmp_path, suffix):
    import pyarrow.parquet as pq

    cd = _cd()
    cd.set_cell_positions(np.array([[2.5, 2.5], [12.5, 2.5], [22.5, 2.5]]), unit="um", frame="fov",
                          shapes=None)
    rec = cd.set_cell_shapes(SQUARES, unit="um", frame="fov")
    cd.set_cell_positions(columns=["centroid_x", "centroid_y"], unit="um", frame="fov", shapes="cell")
    assert rec["geometry_types"] == ["Polygon"] and rec["n"] == 3
    path = tmp_path / f"x{suffix}"
    cd.write(path)
    r = ChromData.read(path)
    pd.testing.assert_frame_equal(r.cell_shapes["cell"], cd.cell_shapes["cell"])
    assert r.uns["cell_shapes"]["cell"] == rec
    assert r.cell_positions().equals(cd.cell_positions())
    assert r.validate_links() == []
    # backed: eager, subset with the cells
    b = ChromData.read(path, backed=True)
    one = b.get_cell("c1")
    assert one.cell_shapes["cell"]["cell_id"].tolist() == ["c1"]
    assert one.cell_positions().index.tolist() == ["c1"]
    if suffix == ".chromdata.zarr":
        f = path / "tables" / "cell_shapes" / "cell.parquet"
        geo = json.loads(pq.read_schema(f).metadata[b"geo"])
        assert geo["primary_column"] == "geometry" and geo["columns"]["geometry"]["encoding"] == "WKB"
        meta = json.loads((path / "zarr.json").read_text())["attributes"]["uchrom"]
        assert meta["format_version"] == "2.3"


def test_cell_shapes_subset_and_copy():
    cd = _cd()
    cd.set_cell_shapes(SQUARES)
    sub = cd.get_cell("c2")
    assert sub.cell_shapes["cell"]["cell_id"].tolist() == ["c2"]
    cp = cd.copy()
    cp.cell_shapes["cell"].loc[0, "cell_id"] = "zz"
    assert cd.cell_shapes["cell"]["cell_id"].iloc[0] == "c0"
    assert "cell_shapes" in repr(cd)


def test_cell_shapes_geometry_objects():
    shapely = pytest.importorskip("shapely")
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Polygon

    cd = _cd()
    gdf = gpd.GeoDataFrame(geometry=[Polygon(v) for v in SQUARES.values()], index=list(SQUARES))
    cd.set_cell_shapes(gdf, key="nucleus")
    back = cd.cell_shapes_geodataframe("nucleus")
    assert list(back.index) == list(SQUARES) and np.allclose(back.area, 25.0)
    assert shapely.equals(back.geometry.iloc[1], Polygon(SQUARES["c1"]))


def test_geoparquet_readable_by_geopandas(tmp_path):
    gpd = pytest.importorskip("geopandas")
    cd = _cd()
    cd.set_cell_shapes(SQUARES)
    cd.write(tmp_path / "x.chromdata.zarr")
    g = gpd.read_parquet(tmp_path / "x.chromdata.zarr" / "tables" / "cell_shapes" / "cell.parquet")
    assert g["cell_id"].tolist() == list(SQUARES) and np.allclose(g.area, 25.0)


def test_missing_shapely_gives_clear_error(monkeypatch):
    cd = _cd()
    cd.set_cell_shapes(SQUARES)                                  # storage needs no shapely
    monkeypatch.setitem(sys.modules, "shapely", None)
    monkeypatch.setitem(sys.modules, "geopandas", None)
    with pytest.raises(ImportError, match="pip install"):
        cd.cell_shapes_geodataframe()


def test_legacy_h5cd_writer_warns_that_shapes_are_dropped(tmp_path):
    from uchrom.io._h5cd_legacy import write_h5cd

    cd = _cd()
    cd.set_cell_shapes(SQUARES)
    with pytest.warns(UserWarning, match="cell_shapes"):
        write_h5cd(cd, tmp_path / "x.h5cd")


def test_streaming_writer_keeps_shapes(tmp_path):
    cd = _cd()
    cd.set_cell_shapes(SQUARES)
    with ChromData.writer(tmp_path / "s.chromdata.zarr") as w:
        w.append(cd)
    r = ChromData.read(tmp_path / "s.chromdata.zarr")
    pd.testing.assert_frame_equal(r.cell_shapes["cell"], cd.cell_shapes["cell"])


def test_store_without_cell_spatial_parts_reads(tmp_path):
    """Older stores (no cell_shapes table, no records) read with empty parts."""
    from chromdata.zarrcd import write_zarr

    cd = _cd()
    write_zarr(cd, tmp_path / "old.chromdata.zarr", _layout="2.1")
    r = ChromData.read(tmp_path / "old.chromdata.zarr")
    assert r.cell_shapes == {} and "cell_spatial" not in r.uns
    with pytest.raises(KeyError):
        r.cell_positions()


def test_validate_links_cell_spatial_issues():
    cd = _cd()
    cd.uns["cell_spatial"] = {"a": {"x_col": "nope", "y_col": "centroid_y", "status": "inferred"}}
    cd.cell_shapes["cell"] = cs.to_wkb(SQUARES)
    issues = cd.validate_links(check_files=False)
    assert any("columns missing" in i for i in issues)
    assert any("no source" in i for i in issues)
    assert any("no uns['cell_shapes'] record" in i for i in issues)


# ---------------------------------------------------------------- FOF-CT

def test_fofct_mapping_table_and_centroids_round_trip(tmp_path):
    cd = _cd()
    cd.set_cell_positions(np.array([[2.5, 2.5, 1.0], [12.5, 2.5, 1.0], [22.5, 2.5, 1.0]]), unit="micron")
    cd.set_cell_shapes(SQUARES, unit="micron")
    files = cd.to_fofct(tmp_path / "core.csv", cell_table=tmp_path / "cell.csv",
                        mapping_table=tmp_path / "map.csv")
    text = files["mapping"].read_text()
    assert "##ROI_Boundaries_Format=" in text and "Table_namespace=4dn_FOF-CT_mapping" in text
    r = ChromData.from_fofct(files["core"], cell_table=files["cells"], mapping_table=files["mapping"])
    pd.testing.assert_frame_equal(r.cell_shapes["cell"], cd.cell_shapes["cell"])
    assert r.uns["cell_shapes"]["cell"]["frame"] == "global"
    rec = r.uns["cell_spatial"]["default"]
    assert rec["x_col"] == "centroid_x" and rec["z_col"] == "centroid_z" and rec["shapes"] == "cell"
    pd.testing.assert_frame_equal(r.cell_positions()[["x", "y", "z"]], cd.cell_positions()[["x", "y", "z"]])
    # the streaming import gives the same parts
    s = ChromData.from_fofct(files["core"], cell_table=files["cells"], mapping_table=files["mapping"],
                             out=tmp_path / "s.chromdata.zarr")
    pd.testing.assert_frame_equal(s.cell_shapes["cell"], cd.cell_shapes["cell"])
    assert s.uns["cell_spatial"]["default"]["shapes"] == "cell"


def test_fofct_global_centroid_columns(tmp_path):
    """Liu et al. 2025 cell tables name their centroids cell_center_x_global / _y_global."""
    cd = _cd()
    cd.to_fofct(tmp_path / "core.csv")
    (tmp_path / "cell.csv").write_text(
        "##FOF-CT_version=v0.1\n##Table_namespace=4dn_FOF-CT_cell\n##XYZ_unit=micron\n"
        "##columns=(Cell_ID,cell_center_x_global,cell_center_y_global)\n"
        "c0,100.5,200.5\nc1,110.5,210.5\nc2,120.5,220.5\n")
    r = ChromData.from_fofct(tmp_path / "core.csv", cell_table=tmp_path / "cell.csv", cell_value_prefix=None)
    rec = r.uns["cell_spatial"]["default"]
    assert rec["frame"] == "global" and rec["unit"] == "micron"
    assert r.cell_positions().loc["c1", ["x", "y"]].tolist() == [110.5, 210.5]


def test_fofct_mapping_table_skips_meshes(tmp_path):
    cd = _cd()
    cd.to_fofct(tmp_path / "core.csv")
    (tmp_path / "map.csv").write_text(
        "##FOF-CT_version=v0.1\n##Table_namespace=4dn_FOF-CT_mapping\n"
        "##ROI_Boundaries_Format=OME polygon\n##columns=(Cell_ID,ROI_Boundaries)\n"
        'c0,"0,0 1,0 1,1"\nc1,"v 0.1 0.2 0.3 1.0"\n')
    with pytest.warns(UserWarning, match="skipped"):
        r = ChromData.from_fofct(tmp_path / "core.csv", mapping_table=tmp_path / "map.csv")
    assert r.cell_shapes["cell"]["cell_id"].tolist() == ["c0"]


# ---------------------------------------------------------------- SpatialData

def _sdata(tmp_path, ids=("c0", "c1", "c2"), name="cells.sdata.zarr"):
    sd = pytest.importorskip("spatialdata")
    gpd = pytest.importorskip("geopandas")
    import anndata as ad
    from shapely.geometry import Polygon
    from spatialdata.models import ShapesModel, TableModel

    ids = list(ids)
    shapes = ShapesModel.parse(gpd.GeoDataFrame(geometry=[Polygon(SQUARES.get(i, SQUARES["c0"])) for i in ids],
                                                index=ids))
    obs = pd.DataFrame({"region": pd.Categorical(["cell_boundaries"] * len(ids)), "instance_id": ids},
                       index=[str(i) for i in range(len(ids))])
    table = TableModel.parse(ad.AnnData(X=np.ones((len(ids), 2)), obs=obs), region="cell_boundaries",
                             region_key="region", instance_key="instance_id")
    sdata = sd.SpatialData(shapes={"cell_boundaries": shapes}, tables={"table": table})
    sdata.write(tmp_path / name)
    return tmp_path / name


def test_link_spatialdata_records_cell_map_and_validates(tmp_path):
    path = _sdata(tmp_path)
    cd = _cd()
    rec = cd.link_spatialdata(path)
    assert rec["format"] == "spatialdata" and rec["table"] == "table"
    assert rec["region"] == "cell_boundaries" and rec["region_key"] == "region"
    assert rec["instance_key"] == "instance_id" and rec["spatialdata_version"]
    assert cd.validate_links() == []
    one = cd.load_linked_spatialdata(cells=["c1"])
    assert one.tables["table"].obs["instance_id"].tolist() == ["c1"]
    assert list(one.shapes["cell_boundaries"].index) == ["c1"]
    full = cd.load_linked_spatialdata()
    assert full.tables["table"].n_obs == 3


def test_link_spatialdata_relative_path_survives_round_trip(tmp_path):
    _sdata(tmp_path)
    cd = _cd()
    store = tmp_path / "x.chromdata.zarr"
    cd.link_spatialdata("cells.sdata.zarr", read_attrs=False, table="table", region="cell_boundaries",
                        region_key="region", instance_key="instance_id")
    cd.write(store)
    r = ChromData.read(store)
    assert r.uns["linked_spatialdata"]["default"]["path"] == "cells.sdata.zarr"
    assert r.validate_links() == []                       # resolved next to the store
    assert r.describe_links()["linked_spatialdata"]["default"]["table"] == "table"


def test_link_spatialdata_cell_map_mismatch_and_cell_col(tmp_path):
    path = _sdata(tmp_path, ids=("A", "B", "C"))
    cd = _cd()
    cd.link_spatialdata(path)
    assert any("no ChromData cell matches" in i for i in cd.validate_links())
    cd.cells["sd_id"] = ["A", "B", "C"]
    cd.link_spatialdata(path, cell_col="sd_id")
    assert cd.validate_links() == []
    assert cd.load_linked_spatialdata(cells=["c2"]).tables["table"].obs["instance_id"].tolist() == ["C"]
    cd.cells["sd_id"] = ["A", "B", "Z"]
    assert any("1 of 3" in i for i in cd.validate_links())
    cd.uns["linked_spatialdata"]["default"]["path"] = str(tmp_path / "missing.zarr")
    assert any("does not exist" in i for i in cd.validate_links())


def test_to_spatialdata_round_trip(tmp_path):
    sd = pytest.importorskip("spatialdata")
    pytest.importorskip("geopandas")
    cd = _cd()
    cd.cellm["X_umap"] = np.arange(6.0).reshape(3, 2)
    cd.points["rna"] = pd.DataFrame({"x": [0.1], "y": [0.2], "z": [0.3], "gene": ["Actb"], "cell_id": ["c0"]})
    cd.set_cell_positions(np.array([[2.5, 2.5, 1.0], [12.5, 2.5, 1.0], [22.5, 2.5, 1.0]]), unit="um", frame="fov")
    cd.set_cell_shapes(SQUARES, unit="um", frame="fov")
    sdata = cd.to_spatialdata()
    sdata.write(tmp_path / "out.sdata.zarr")
    r = sd.read_zarr(tmp_path / "out.sdata.zarr")
    spots = r.points["spots"].compute()
    np.testing.assert_allclose(spots[["x", "y", "z"]].to_numpy(), cd.coords)
    assert spots["cell_id"].tolist() == cd.spots["cell_id"].astype(str).tolist()
    cen = r.points["cell_centroids"].compute().set_index("cell_id")
    np.testing.assert_allclose(cen.loc[["c0", "c1", "c2"], ["x", "y", "z"]].to_numpy(),
                               cd.cell_positions()[["x", "y", "z"]].to_numpy())
    assert np.allclose(r.shapes["cell_shapes_cell"].area, 25.0)
    t = r.tables["cells"]
    assert t.uns["spatialdata_attrs"]["region"] == "cell_shapes_cell"
    assert t.obs["cell_type"].tolist() == ["a", "b", "a"] and np.allclose(t.obsm["X_umap"], cd.cellm["X_umap"])
    assert len(r.points["points_rna"].compute()) == 1
    # link the export back
    cd.link_spatialdata(tmp_path / "out.sdata.zarr")
    assert cd.validate_links() == []
