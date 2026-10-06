"""Converting the legacy HDF5 container (``.h5cd`` 1.x / 2.0) to ``.chromdata.zarr`` / ``.cdz``
(``uchrom.io.upgrade_h5cd`` / ``convert_chromdata`` / ``python -m uchrom.io.upgrade``)."""
import numpy as np
import pandas as pd
import pytest

from tests._v1 import write_v1
from chromdata import ChromData
from chromdata.testing import example_chromdata as _cd
from chromdata.zarrcd import write_zarr
from uchrom.io._h5cd_legacy import read_h5cd, write_h5cd


def _write_1x(path):
    spots = pd.DataFrame({"chrom": ["chr2", "chr1", "chr1", "chr2", "chr1", "chr1"],
                          "start": [0, 10, 0, 0, 10, 0], "end": [10, 20, 10, 10, 20, 10],
                          "trace_id": ["1", "1", "1", "0", "0", "0"],
                          "cell_id": ["b", "b", "b", "a", "a", "a"], "spot_id": np.arange(6)})
    tracks = pd.DataFrame({"IF": [1.0, 2.0, 3.0, 4.0, 5.0, np.nan], "ATAC": [9.0, 7.0, 5.0, 9.0, 7.0, 5.0]})
    coords = np.arange(18, dtype=float).reshape(6, 3)
    write_v1(path, coords, spots, tracks=tracks,
             cells=pd.DataFrame({"t": ["x", "y"]}, index=pd.Index(["a", "b"], name="cell_id")),
             layers={"raw": coords + 1}, uns={"genome_assembly": "mm10"},
             results={"tads": pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [20]})})


def test_convert_h5cd_1x_and_2x(tmp_path, capsys):
    from uchrom.io import convert_chromdata, file_format_version, upgrade_h5cd
    from uchrom.io.upgrade import main

    src = tmp_path / "old.h5cd"
    _write_1x(src)
    ref = read_h5cd(src)
    info = upgrade_h5cd(src)                                       # default target
    dst = tmp_path / "old.chromdata.zarr"
    assert info["dst"] == str(dst) and info["to_container"] == "zarr" and info["from_version"] == "1.4"
    assert file_format_version(dst) == "2.3" and file_format_version(src) == "1.4"
    new = ChromData.read(dst, original_order=True)
    pd.testing.assert_frame_equal(new.to_dataframe(), ref.to_dataframe())
    pd.testing.assert_frame_equal(new.tracks_spot_view(), ref.tracks_spot_view())
    np.testing.assert_array_equal(new.layers["raw"], ref.layers["raw"])
    assert new.results == ref.results and new.track_names() == {"bin": ["ATAC"], "spot": ["IF"]}
    with pytest.raises(FileExistsError):
        upgrade_h5cd(src)
    # h5cd 2.0 → cdz, and the CLI
    write_h5cd(ref, tmp_path / "two.h5cd")
    assert file_format_version(tmp_path / "two.h5cd") == "2.0"
    convert_chromdata(tmp_path / "two.h5cd", tmp_path / "two.cdz")
    assert file_format_version(tmp_path / "two.cdz") == "2.3"
    pd.testing.assert_frame_equal(ChromData.read(tmp_path / "two.cdz", original_order=True).to_dataframe(),
                                  read_h5cd(tmp_path / "two.h5cd").to_dataframe())
    assert main([str(src), str(tmp_path / "two.h5cd"), "--out-dir", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "-> " in out and "zarr" in out
    assert {p.name for p in (tmp_path / "out").iterdir()} == {"old.chromdata.zarr", "two.chromdata.zarr"}
    assert main([str(src), "--out-dir", str(tmp_path / "o2"), "--format", "cdz"]) == 0
    assert (tmp_path / "o2" / "old.cdz").exists()
    with pytest.raises(ValueError, match="chromdata.zarr or .cdz"):
        upgrade_h5cd(src, tmp_path / "again.h5cd")                  # .h5cd is not a target
    assert not (tmp_path / "again.h5cd").exists()


# ----------------------------------------------------------------- an older zarr layout (2.1) -> 2.2

def _decimal_cd(n_cells=6, seed=0):
    """``_cd`` with coordinates / tracks that look measured (a few decimals,
    plus arithmetic noise, NaN, -0.0, a huge value) and spot columns that
    are functions of the bin, the cell or the trace."""
    cd = _cd(n_cells=n_cells, seed=seed)
    rng = np.random.default_rng(seed + 1)
    n = cd.n_spots
    co = np.round(rng.normal(100, 20, size=(n, 3)), 6)
    co[:, 2] = np.round(co[:, 2], 3) * 0.25          # arithmetic on decimals: ulp corrections
    co[[2, 7]] = np.nan
    co[5, 0] = -0.0
    co[6, 1] = 1e300
    cd.coords = co
    st = cd.spot_tracks
    st["IF"] = np.round(rng.normal(0, 2, n), 5) - np.round(rng.normal(0, 1, n), 5)
    st["plain"] = rng.normal(size=n)                      # full precision: stays float64
    cd.spot_tracks = st
    cd.layers["raw"] = np.round(co + 0.5, 4)
    s = cd.spots
    bid = s["bin_id"].to_numpy()
    s["name"] = np.array([f"{c}-{a}" for c, a in zip(cd.bins["chrom"], cd.bins["start"])], dtype=object)[bid]
    s["sample"] = "mouse_1"                                           # constant string
    s["fov"] = s["cell_id"].cat.codes.to_numpy().astype(np.int64) * 7 + 3   # a function of the cell
    s["allele"] = pd.Categorical(np.where(s["trace_id"].cat.codes.to_numpy() % 2, "a1", "a2"))  # of the trace
    s["order"] = (bid * 0.5).astype(np.float64)                        # float, of the bin
    cd.spots = s[[c for c in s.columns if c != "bin_id"] + ["bin_id"]]
    return cd


def _bits(a):
    return np.ascontiguousarray(a, dtype=np.float64).view(np.int64)


def test_upgrade_21_to_22_keeps_original_order(tmp_path):
    from uchrom.io.upgrade import file_format_version, upgrade_h5cd

    cd = _decimal_cd()
    write_zarr(cd, tmp_path / "old.chromdata.zarr", _layout="2.1")
    info = upgrade_h5cd(tmp_path / "old.chromdata.zarr", tmp_path / "new.chromdata.zarr")
    assert info["from_version"] == "2.1" and file_format_version(tmp_path / "new.chromdata.zarr") == "2.3"
    back = ChromData.read(tmp_path / "new.chromdata.zarr", original_order=True)
    pd.testing.assert_frame_equal(back.spots, cd.spots)
    np.testing.assert_array_equal(_bits(back.coords), _bits(cd.coords))
    pd.testing.assert_frame_equal(back.spot_tracks, cd.spot_tracks)


# ----------------------------------------------------------------- the legacy writer and cell outlines

def _spatial_cd(n_cells=3):
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


def test_legacy_h5cd_writer_warns_that_shapes_are_dropped(tmp_path):
    from uchrom.io._h5cd_legacy import write_h5cd

    cd = _spatial_cd()
    cd.set_cell_shapes(SQUARES)
    with pytest.warns(UserWarning, match="cell_shapes"):
        write_h5cd(cd, tmp_path / "x.h5cd")

