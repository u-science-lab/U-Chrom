"""The legacy HDF5 container (``.h5cd``, ``uchrom.io._h5cd_legacy``) with the format 2.0 locus axis,
its version checks and compression options, and the 1.x → 2.0 upgrade (``uchrom.io.upgrade``)."""
import h5py
import numpy as np
import pandas as pd
import pytest

from tests._v1 import write_v1
from chromdata import ChromData
from uchrom.io._h5cd_legacy import read_h5cd, write_h5cd


def _spots():
    return pd.DataFrame({
        "chrom": ["chr2", "chr1", "chr1", "chr2", "chr1", "chr1"],
        "start": [0, 10, 0, 0, 10, 0],
        "end": [10, 20, 10, 10, 20, 10],
        "trace_id": [0, 0, 0, 1, 1, 1],
        "cell_id": ["a", "a", "a", "b", "b", "b"],
        "spot_id": np.arange(6),
    })


def _coords(n=6):
    return np.arange(3 * n, dtype=float).reshape(n, 3)


def _tracks_1x():
    return pd.DataFrame({
        "IF": [1.0, 2.0, 3.0, 4.0, 5.0, np.nan],       # varies within a bin → spot
        "ATAC": [9.0, 7.0, 5.0, 9.0, 7.0, 5.0],        # constant per bin → bin
        "gc": [np.nan, 0.4, 0.5, np.nan, 0.4, 0.5],    # constant incl. NaN → bin
    })


def _full_cd():
    cells = pd.DataFrame({"cell_type": ["x", "y"]}, index=pd.Index(["a", "b"], name="cell_id"))
    traces = pd.DataFrame({"allele": [1, 2]}, index=pd.Index([0, 1], name="trace_id"))
    cd = ChromData(
        _coords(), _spots(), cells=cells, cellm={"umap": np.ones((2, 2))},
        spot_tracks=_tracks_1x()[["IF"]], binm={"loading": np.arange(6.0).reshape(3, 2)},
        traces=traces, layers={"raw": _coords() + 1},
        uns={"genome_assembly": "mm10", "nested": {"k": 1}},
        points={"rna": pd.DataFrame({"x": [1.0], "y": [2.0], "z": [3.0], "cell_id": ["a"]})},
    )
    cd.bin_tracks = pd.DataFrame({"ATAC": [5.0, 7.0, 9.0], "label": ["p", "q", "r"]})
    cd.bins["name"] = ["b0", "b1", "b2"]
    cd.intervals["tads"] = pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [20], "s": [0.5]})
    cd.results.set("tads", cd.intervals["tads"], kind="intervals", function="f")
    cd.results["pc"] = np.arange(3.0)
    return cd


def _assert_same(a: ChromData, b: ChromData):
    pd.testing.assert_frame_equal(a.bins, b.bins)
    pd.testing.assert_frame_equal(a.spots, b.spots)
    np.testing.assert_array_equal(a.coords, b.coords)
    pd.testing.assert_frame_equal(a.bin_tracks, b.bin_tracks)
    pd.testing.assert_frame_equal(a.spot_tracks, b.spot_tracks)
    pd.testing.assert_frame_equal(a.tracks_spot_view(), b.tracks_spot_view())
    pd.testing.assert_frame_equal(a.to_dataframe(), b.to_dataframe())
    for key in a.binm:
        np.testing.assert_array_equal(a.binm[key], b.binm[key])
    for key in a.layers:
        np.testing.assert_array_equal(a.layers[key], b.layers[key])
    pd.testing.assert_frame_equal(a.cells, b.cells)
    pd.testing.assert_frame_equal(a.traces, b.traces)
    assert set(a.intervals) == set(b.intervals)
    for key in a.intervals:
        pd.testing.assert_frame_equal(pd.DataFrame(a.intervals[key]), pd.DataFrame(b.intervals[key]))
        assert a.intervals[key].kind == b.intervals[key].kind
    assert a.results == b.results
    pd.testing.assert_frame_equal(a.points["rna"], b.points["rna"])


def test_legacy_h5cd_2_round_trip(tmp_path):
    cd = _full_cd()
    path = tmp_path / "v2.h5cd"
    write_h5cd(cd, path)
    with h5py.File(path, "r") as f:
        assert f.attrs["uchrom_format_version"] == "2.0"
        assert set(f["spots"].keys()) >= {"bin_id", "trace_id", "cell_id"}
        assert not {"chrom", "start", "end"} & set(f["spots"].keys())
        assert f["spots/bin_id"].dtype == np.int32
        assert f["spots/trace_id"].attrs["_type"] == "categorical"
        assert f["tracks"].attrs["_n_rows"] == 3 and f["spot_tracks"].attrs["_n_rows"] == 6
        assert f["intervals/tads"].attrs["_kind"] == "domain"
        assert f["results/tads"].attrs["_value_ref"] == "intervals/tads"
    back = read_h5cd(path)
    _assert_same(cd, back)
    assert back.spots["trace_id"].cat.categories.dtype.kind == "i"   # ints survive
    assert back.uns["nested"]["k"] == 1


def test_legacy_h5cd_version_dispatch(tmp_path):
    path = tmp_path / "v.h5cd"
    write_h5cd(ChromData(_coords(), _spots()), path)
    with h5py.File(path, "r+") as f:
        f.attrs["uchrom_format_version"] = "2.9"
    with pytest.warns(UserWarning, match="Forward-compatible"):
        read_h5cd(path)
    with h5py.File(path, "r+") as f:
        f.attrs["uchrom_format_version"] = "3.0"
    with pytest.raises(ValueError, match="incompatible"):
        read_h5cd(path)


def _write_1x(path):
    spots = _spots()
    for col in ("chrom", "trace_id", "cell_id"):     # as a 1.x ChromData held them
        spots[col] = spots[col].astype("category")
    cells = pd.DataFrame({"cell_type": ["x", "y"]}, index=pd.Index(["a", "b"], name="cell_id"))
    write_v1(path, _coords(), spots, tracks=_tracks_1x(), cells=cells,
             layers={"raw": _coords() + 1}, cellm={"umap": np.ones((2, 2))},
             results={"tads": pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [20]})},
             uns={"genome_assembly": "mm10"},
             points={"rna": pd.DataFrame({"x": [1.0], "y": [2.0], "z": [3.0]})})
    # what 1.x code returns for this file: categoricals as strings
    df = spots.assign(x=_coords()[:, 0], y=_coords()[:, 1], z=_coords()[:, 2])
    for col in ("chrom", "trace_id", "cell_id"):
        df[col] = df[col].astype(str).astype("category")
    return df[["chrom", "start", "end", "x", "y", "z", "trace_id", "cell_id", "spot_id"]]


def test_1x_file_is_upgraded_on_read(tmp_path, caplog):
    path = tmp_path / "old.h5cd"
    expected = _write_1x(path)
    import logging
    with caplog.at_level(logging.INFO, logger="uchrom"):
        cd = read_h5cd(path)
    assert "format 1.x upgrade" in caplog.text
    pd.testing.assert_frame_equal(cd.to_dataframe(), expected)
    pd.testing.assert_frame_equal(cd.tracks_spot_view(), _tracks_1x())
    assert cd.track_names() == {"bin": ["ATAC", "gc"], "spot": ["IF"]}
    assert cd.n_bins == 3 and cd.results.record("tads").function is None
    np.testing.assert_array_equal(cd.layers["raw"], _coords() + 1)
    assert cd.uns["genome_assembly"] == "mm10" and len(cd.points["rna"]) == 1


def test_upgrade_h5cd_and_cli(tmp_path, capsys):
    from uchrom.io import file_format_version, upgrade_h5cd
    from uchrom.io.upgrade import main

    src = tmp_path / "old.h5cd"
    expected = _write_1x(src)
    new_path = tmp_path / "new.chromdata.zarr"
    info = upgrade_h5cd(src, new_path)
    assert info["from_version"] == "1.4" and info["to_version"] == "2.3"
    assert info["n_bins"] == 3 and info["spot_tracks"] == ["IF"]
    assert file_format_version(src) == "1.4"                       # source untouched
    new = ChromData.read(new_path, original_order=True)
    pd.testing.assert_frame_equal(new.to_dataframe(), expected, check_categorical=False)
    pd.testing.assert_frame_equal(new.tracks_spot_view(), _tracks_1x())

    with pytest.raises(ValueError, match="differ"):
        upgrade_h5cd(src, src)
    with pytest.raises(FileExistsError):
        upgrade_h5cd(src, new_path)
    with pytest.raises(ValueError, match="chromdata.zarr or .cdz"):
        upgrade_h5cd(src, tmp_path / "again.h5cd")               # no .h5cd target any more
    assert main([str(src), "--out-dir", str(tmp_path / "out")]) == 0
    assert "(1.4, h5cd) ->" in capsys.readouterr().out
    assert file_format_version(tmp_path / "out" / "old.chromdata.zarr") == "2.3"


def test_legacy_h5cd_compression_options(tmp_path):
    n = 5000
    spots = pd.DataFrame({"chrom": ["chr1"] * n, "start": np.arange(n) * 10,
                          "end": np.arange(n) * 10 + 10, "trace_id": np.arange(n) // 50,
                          "label": np.array(["é-x", "b"] * (n // 2))})     # non-ASCII survives
    cd = ChromData(np.random.default_rng(0).normal(size=(n, 3)), spots)
    paths = {}
    for name, kw in {"default": {}, "floats": {"compress_floats": True},
                     "lzf": {"compression": "lzf"}, "none": {"compression": None}}.items():
        paths[name] = tmp_path / f"{name}.h5cd"
        write_h5cd(cd, paths[name], **kw)
        pd.testing.assert_frame_equal(read_h5cd(paths[name]).to_dataframe(), cd.to_dataframe())
    with h5py.File(paths["default"], "r") as f:
        assert f["spots/bin_id"].compression == "gzip" and f["spots/bin_id"].chunks[0] == n
        assert f["coords"].compression is None               # floats off by default
        assert f["spots/label"].compression == "gzip"
    with h5py.File(paths["floats"], "r") as f:
        assert f["coords"].compression == "gzip"
    with h5py.File(paths["lzf"], "r") as f:
        assert f["spots/bin_id"].compression == "lzf"
    with h5py.File(paths["none"], "r") as f:
        assert f["spots/bin_id"].compression is None
    with pytest.raises(ValueError, match="compression"):
        write_h5cd(cd, tmp_path / "x.h5cd", compression="zstd")
