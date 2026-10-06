"""Format 2.0: the ``bins`` axis, bin- vs spot-level tracks, intervals and the round trip.

The legacy ``.h5cd`` container and the 1.x → 2.0 upgrade: uchrom's tests/io/test_h5cd_bins.py."""
import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData
from chromdata.intervals import IntervalTable


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
        cd.write(tmp_path / "x.chromdata.zarr")
    cd.spots["end"] = cd.spots["end"] + 1
    cd.rebuild_bins()
    assert cd.bins["start"].tolist() == [1, 11, 1]
    assert np.isnan(cd.bin_tracks["ATAC"]).all()   # the old loci are gone
    cd.write(tmp_path / "x.chromdata.zarr")


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


# ----------------------------------------------------------------- 2.0 round trip

def test_round_trip_without_spots(tmp_path):
    """Data without 3-D spots (scHi-C / RNA only) keeps an empty spot table."""
    spots = pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=int),
                          "end": pd.Series(dtype=int), "trace_id": pd.Series(dtype=str)})
    cells = pd.DataFrame({"n": [1, 2]}, index=pd.Index(["c1", "c2"], name="cell_id"))
    cd = ChromData(np.zeros((0, 3)), spots, cells=cells)
    cd.write(tmp_path / "e.chromdata.zarr")
    back = ChromData.read(tmp_path / "e.chromdata.zarr")
    assert back.n_spots == 0 and back.n_bins == 0 and len(back.cells) == 2
