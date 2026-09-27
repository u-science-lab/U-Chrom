"""Format 2.0: the ``bins`` axis, bin- vs spot-level tracks, intervals,
round trip and the 1.x → 2.0 upgrade."""
import h5py
import numpy as np
import pandas as pd
import pytest

from tests._v1 import write_v1
from uchrom import ChromData
from uchrom.core.intervals import IntervalTable


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


# ----------------------------------------------------------------- schema

def test_bins_derived_from_spot_loci():
    cd = ChromData(_coords(), _spots())
    assert cd.n_bins == 3 and cd.bins.index.name == "bin_id"
    assert list(cd.bins.index) == [0, 1, 2]
    assert cd.bins.to_dict("list") == {"chrom": ["chr1", "chr1", "chr2"],
                                       "start": [0, 10, 0], "end": [10, 20, 10]}
    assert cd.bins["chrom"].dtype == "category" and cd.bins["start"].dtype == np.int64
    assert list(cd.spots["bin_id"]) == [2, 1, 0, 2, 1, 0]
    # chrom/start/end stay available on spots, derived from bins
    assert list(cd.spots["start"]) == [0, 10, 0, 0, 10, 0]
    assert cd.spots["chrom"].dtype == "category"
    assert list(cd.spots.columns)[-1] == "bin_id"


def test_explicit_bins_and_bin_id():
    bins = pd.DataFrame({"chrom": ["chr1", "chr1", "chr2", "chr3"], "start": [0, 10, 0, 0],
                         "end": [10, 20, 10, 5], "name": ["p1", "p2", "p3", "unused"]})
    spots = pd.DataFrame({"bin_id": [2, 1, 0], "trace_id": [0, 0, 0]})
    cd = ChromData(_coords(3), spots, bins=bins)
    assert list(cd.spots.columns[:3]) == ["chrom", "start", "end"]
    assert list(cd.spots["chrom"].astype(str)) == ["chr2", "chr1", "chr1"]
    assert cd.n_bins == 4 and "name" in cd.bins.columns
    # loci given instead of bin_id are looked up
    cd2 = ChromData(_coords(3), cd.spots.drop(columns="bin_id"), bins=bins)
    assert list(cd2.spots["bin_id"]) == [2, 1, 0]


@pytest.mark.parametrize("bins, spots, msg", [
    (pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [10]}),
     pd.DataFrame({"chrom": ["chr9"], "start": [0], "end": [10], "trace_id": [0]}), "not in bins"),
    (pd.DataFrame({"chrom": ["chr1", "chr1"], "start": [0, 0], "end": [10, 10]}),
     pd.DataFrame({"bin_id": [0], "trace_id": [0]}), "duplicate loci"),
    (pd.DataFrame({"chrom": ["chr1"], "start": [5], "end": [5]}),
     pd.DataFrame({"bin_id": [0], "trace_id": [0]}), "end > start"),
    (pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [10]}),
     pd.DataFrame({"bin_id": [3], "trace_id": [0]}), "out of range"),
    (pd.DataFrame({"start": [0], "end": [10]}),
     pd.DataFrame({"bin_id": [0], "trace_id": [0]}), "missing required"),
])
def test_schema_validation(bins, spots, msg):
    with pytest.raises(ValueError, match=msg):
        ChromData(_coords(1), spots, bins=bins)


def test_bin_id_without_bins_needs_loci():
    with pytest.raises(ValueError, match="no bins"):
        ChromData(_coords(1), pd.DataFrame({"bin_id": [0], "trace_id": [0]}))
    # a stale bin_id next to loci (spots concatenated from two objects) is re-derived
    sp = pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [10], "trace_id": [0], "bin_id": [7]})
    assert list(ChromData(_coords(1), sp).spots["bin_id"]) == [0]


def test_edited_spot_loci_are_detected_and_rebuild_bins_fixes_them(tmp_path):
    cd = ChromData(_coords(), _spots())
    cd.bin_tracks = pd.DataFrame({"ATAC": [1.0, 2.0, 3.0]})
    cd.spots["start"] = cd.spots["start"] + 1
    with pytest.raises(ValueError, match="rebuild_bins"):
        cd.write(tmp_path / "x.h5cd")
    cd.spots["end"] = cd.spots["end"] + 1
    cd.rebuild_bins()
    assert cd.bins["start"].tolist() == [1, 11, 1]
    assert np.isnan(cd.bin_tracks["ATAC"]).all()   # the old loci are gone
    cd.write(tmp_path / "x.h5cd")


def test_spots_with_loci_and_to_dataframe():
    cd = ChromData(_coords(), _spots())
    swl = cd.spots_with_loci()
    pd.testing.assert_frame_equal(swl, cd.spots)
    assert swl is not cd.spots
    df = cd.to_dataframe()
    assert list(df.columns[:6]) == ["chrom", "start", "end", "x", "y", "z"]
    assert "bin_id" not in df.columns and "bin_id" in cd.to_dataframe(include_bin_id=True)
    back = ChromData.from_dataframe(cd.to_dataframe(include_bin_id=True))
    assert back.n_bins == 3


# ----------------------------------------------------------------- tracks

def test_spot_aligned_tracks_are_split_and_view_is_lossless():
    with pytest.warns(DeprecationWarning, match="spot_tracks="):
        cd = ChromData(_coords(), _spots(), tracks=_tracks_1x())
    assert list(cd.bin_tracks.columns) == ["ATAC", "gc"] and len(cd.bin_tracks) == 3
    assert list(cd.spot_tracks.columns) == ["IF"] and len(cd.spot_tracks) == 6
    assert cd.bin_tracks["ATAC"].tolist() == [5.0, 7.0, 9.0]
    pd.testing.assert_frame_equal(cd.tracks_spot_view(), _tracks_1x())   # order kept
    with pytest.warns(DeprecationWarning, match="cd.tracks is the deprecated"):
        view = cd.tracks
    pd.testing.assert_frame_equal(pd.DataFrame(view), _tracks_1x())
    assert cd.track_names() == {"bin": ["ATAC", "gc"], "spot": ["IF"]}


def test_tracks_shim_write_through_and_setters():
    cd = ChromData(_coords(), _spots(), spot_tracks=_tracks_1x()[["IF"]])
    cd.bin_tracks = pd.DataFrame({"ATAC": [5.0, 7.0, 9.0]})
    with pytest.warns(DeprecationWarning):
        cd.tracks["new"] = [1, 2, 3, 4, 5, 6]          # 1.x in-place idiom
    assert "new" in cd.spot_tracks.columns
    with pytest.warns(DeprecationWarning):
        cd.tracks["ATAC"] = [0.0, 1.0, 2.0, 0.0, 1.0, 2.0]   # still constant per bin
    assert cd.bin_tracks["ATAC"].tolist() == [2.0, 1.0, 0.0]
    with pytest.raises(ValueError, match="n_bins"):
        cd.bin_tracks = pd.DataFrame({"x": [1.0, 2.0]})
    with pytest.raises(ValueError, match="n_spots"):
        cd.spot_tracks = pd.DataFrame({"x": [1.0]})
    cd.tracks = pd.DataFrame({"B": [1.0, 2.0, 3.0]}, index=pd.RangeIndex(3, name="bin_id"))
    assert "B" in cd.bin_tracks.columns
    cd.tracks = None
    assert cd.track_names() == {"bin": [], "spot": []}


def test_binm_and_subsetting_keep_the_locus_axis():
    cd = ChromData(_coords(), _spots(), spot_tracks=_tracks_1x()[["IF"]],
                   binm={"pc": np.ones((3, 2))})
    cd.bin_tracks = pd.DataFrame({"ATAC": [5.0, 7.0, 9.0]})
    sub = cd.get_chrom("chr1")
    assert sub.n_spots == 4 and sub.n_bins == 3             # bins are shared, not subset
    assert sub.bin_tracks is cd.bin_tracks and sub.binm["pc"].shape == (3, 2)
    assert sub.spot_tracks["IF"].tolist()[:2] == [2.0, 3.0]
    assert sub.tracks_spot_view()["ATAC"].tolist() == [7.0, 5.0, 7.0, 5.0]
    with pytest.raises(ValueError, match="binm"):
        ChromData(_coords(), _spots(), binm={"bad": np.ones((2, 2))})


# ----------------------------------------------------------------- intervals

def test_interval_tables_are_typed_and_validated():
    cd = ChromData(_coords(), _spots())
    cd.intervals["tads"] = pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [20]})
    cd.intervals["loops"] = pd.DataFrame({"chrom1": ["chr1"], "start1": [0], "end1": [10],
                                          "chrom2": ["chr1"], "start2": [10], "end2": [20]})
    seg = cd.intervals.add("ab", pd.DataFrame({"chrom": ["chr1", "chr2"], "start": [0, 0],
                                              "end": [10, 10], "label": ["A", "B"]}))
    assert isinstance(cd.intervals["tads"], IntervalTable)
    assert [cd.intervals[k].kind for k in ("tads", "loops", "ab")] == ["domain", "pair", "segment"]
    with pytest.raises(ValueError, match="missing column"):
        cd.intervals.add("x", pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [5]}), kind="segment")
    with pytest.raises(ValueError, match="end >= start"):
        cd.intervals["x"] = pd.DataFrame({"chrom": ["chr1"], "start": [9], "end": [5]})
    with pytest.raises(TypeError):
        cd.intervals["x"] = [1, 2]
    assert seg.to_bins(cd.bins, column="label").tolist() == ["A", None, "B"]
    assert cd.intervals["tads"].to_bins(cd.bins, how="bool").tolist() == [True, True, False]
    assert cd.intervals["loops"].to_bins(cd.bins, how="count").tolist() == [1, 1, 0]
    assert cd.intervals["loops"].to_bins(cd.bins).tolist() == [0, 0, -1]


def test_callers_expose_intervals_and_bin_tracks(tmp_path):
    from tests._synth import chain_traces, domain_traces
    from uchrom.strc.comp import call_compartments_axes_pc
    from uchrom.strc.tad import TADCallerParams, call_tads_by_pval

    cd = domain_traces(n_traces=60)
    tads = call_tads_by_pval(cd, params=TADCallerParams(window_bp=1.5e5), device="cpu")
    assert cd.intervals["tads.arcfish"] is tads is cd.results["tads.arcfish"]
    assert tads.kind == "domain" and tads.source_result == "tads.arcfish"

    cc = chain_traces(n_traces=60, n_bins=30)
    comp = call_compartments_axes_pc(cc, device="cpu")
    seg = cc.intervals["compartments.axes_pc"]
    assert seg.kind == "segment" and seg["n_bins"].sum() == len(comp) == cc.n_bins
    np.testing.assert_allclose(cc.bin_tracks["compartments.axes_pc.pc2"], comp["pc2"])

    cd.write(tmp_path / "t.h5cd")
    back = ChromData.read(tmp_path / "t.h5cd")
    assert back.results["tads.arcfish"] is back.intervals["tads.arcfish"]
    assert back.intervals["tads.arcfish"].kind == "domain"
    pd.testing.assert_frame_equal(pd.DataFrame(back.intervals["tads.arcfish"]), pd.DataFrame(tads))
    assert back.results.record("tads.arcfish").provenance == cd.results.record("tads.arcfish").provenance


# ----------------------------------------------------------------- 2.0 round trip

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


def test_format_2_round_trip(tmp_path):
    cd = _full_cd()
    path = tmp_path / "v2.h5cd"
    cd.write(path)
    with h5py.File(path, "r") as f:
        assert f.attrs["uchrom_format_version"] == "2.0"
        assert set(f["spots"].keys()) >= {"bin_id", "trace_id", "cell_id"}
        assert not {"chrom", "start", "end"} & set(f["spots"].keys())
        assert f["spots/bin_id"].dtype == np.int32
        assert f["spots/trace_id"].attrs["_type"] == "categorical"
        assert f["tracks"].attrs["_n_rows"] == 3 and f["spot_tracks"].attrs["_n_rows"] == 6
        assert f["intervals/tads"].attrs["_kind"] == "domain"
        assert f["results/tads"].attrs["_value_ref"] == "intervals/tads"
    back = ChromData.read(path)
    _assert_same(cd, back)
    assert back.spots["trace_id"].cat.categories.dtype.kind == "i"   # ints survive
    assert back.uns["nested"]["k"] == 1


def test_round_trip_without_spots(tmp_path):
    """Data without 3-D spots (scHi-C / RNA only) keeps an empty spot table."""
    spots = pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=int),
                          "end": pd.Series(dtype=int), "trace_id": pd.Series(dtype=str)})
    cells = pd.DataFrame({"n": [1, 2]}, index=pd.Index(["c1", "c2"], name="cell_id"))
    cd = ChromData(np.zeros((0, 3)), spots, cells=cells)
    cd.write(tmp_path / "e.h5cd")
    back = ChromData.read(tmp_path / "e.h5cd")
    assert back.n_spots == 0 and back.n_bins == 0 and len(back.cells) == 2


def test_version_dispatch(tmp_path):
    path = tmp_path / "v.h5cd"
    ChromData(_coords(), _spots()).write(path)
    with h5py.File(path, "r+") as f:
        f.attrs["uchrom_format_version"] = "2.9"
    with pytest.warns(UserWarning, match="Forward-compatible"):
        ChromData.read(path)
    with h5py.File(path, "r+") as f:
        f.attrs["uchrom_format_version"] = "3.0"
    with pytest.raises(ValueError, match="incompatible"):
        ChromData.read(path)


# ----------------------------------------------------------------- 1.x → 2.0

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
        cd = ChromData.read(path)
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
    info = upgrade_h5cd(src, tmp_path / "new.h5cd")
    assert info["from_version"] == "1.4" and info["to_version"] == "2.0"
    assert info["n_bins"] == 3 and info["spot_tracks"] == ["IF"]
    assert file_format_version(src) == "1.4"                       # source untouched
    assert file_format_version(tmp_path / "new.h5cd") == "2.0"
    new = ChromData.read(tmp_path / "new.h5cd")
    pd.testing.assert_frame_equal(new.to_dataframe(), expected)
    pd.testing.assert_frame_equal(new.tracks_spot_view(), _tracks_1x())
    _assert_same(ChromData.read(src), new)

    with pytest.raises(ValueError, match="differ"):
        upgrade_h5cd(src, src)
    with pytest.raises(FileExistsError):
        upgrade_h5cd(src, tmp_path / "new.h5cd")
    assert main([str(src), "--out-dir", str(tmp_path / "out"), "--format", "h5cd"]) == 0
    assert "(1.4, h5cd) ->" in capsys.readouterr().out
    assert file_format_version(tmp_path / "out" / "old.h5cd") == "2.0"
    # the default target is the zarr container (tests/core/test_zarr_format.py)
    assert main([str(src), "--out-dir", str(tmp_path / "out")]) == 0
    assert file_format_version(tmp_path / "out" / "old.chromdata.zarr") == "2.2"


def test_write_compression_options(tmp_path):
    n = 5000
    spots = pd.DataFrame({"chrom": ["chr1"] * n, "start": np.arange(n) * 10,
                          "end": np.arange(n) * 10 + 10, "trace_id": np.arange(n) // 50,
                          "label": np.array(["é-x", "b"] * (n // 2))})     # non-ASCII survives
    cd = ChromData(np.random.default_rng(0).normal(size=(n, 3)), spots)
    paths = {}
    for name, kw in {"default": {}, "floats": {"compress_floats": True},
                     "lzf": {"compression": "lzf"}, "none": {"compression": None}}.items():
        paths[name] = tmp_path / f"{name}.h5cd"
        cd.write(paths[name], **kw)
        pd.testing.assert_frame_equal(ChromData.read(paths[name]).to_dataframe(), cd.to_dataframe())
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
        cd.write(tmp_path / "x.h5cd", compression="zstd")
