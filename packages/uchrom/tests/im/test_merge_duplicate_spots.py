"""uchrom.im.merge_duplicate_spots: one spot per (trace, locus)."""

import numpy as np
import pandas as pd
import pytest

from uchrom.im import merge_duplicate_spots


def _cd():
    from chromdata import ChromData

    spots = pd.DataFrame({"chrom": "chr1", "start": [0, 10, 10, 20, 0, 0, 10],
                          "end": [10, 20, 20, 30, 10, 10, 20],
                          "trace_id": ["a", "a", "a", "a", "b", "b", "b"], "cell_id": ["c", "c", "c", "c", "c", "c", "c"],
                          "spot_id": [1, 2, 3, 4, 5, 6, 7]})
    coords = np.array([[0, 0, 0], [1, 1, 1], [3, 3, 3], [5, 5, 5], [0, 0, 0], [2, 4, np.nan], [9, 9, 9]], float)
    cd = ChromData(coords, spots, spot_tracks=pd.DataFrame({"intensity": [1.0, 2, 4, 1, 1, 3, 1],
                                                            "kind": list("pqrstuv")}),
                   layers={"raw": coords * 10}, uns={"xyz_unit": "nm"})
    return cd


def test_mean_merges_duplicates_and_keeps_the_rest():
    cd = _cd()
    out = merge_duplicate_spots(cd)
    assert out.n_spots == 5 and cd.n_spots == 7                       # input untouched
    assert out.spots["n_merged"].tolist() == [1, 2, 1, 2, 1]
    assert out.spots["spot_id"].tolist() == [1, 2, 4, 5, 7]           # first spot of each group, in order
    np.testing.assert_array_equal(out.coords[1], [2, 2, 2])
    np.testing.assert_array_equal(out.coords[3], [1, 2, 0])           # NaN skipped
    np.testing.assert_array_equal(out.layers["raw"][1], [20, 20, 20])
    assert out.spot_tracks["intensity"].tolist() == [1.0, 3.0, 1.0, 2.0, 1.0]
    assert out.spot_tracks["kind"].tolist() == list("pqstv")          # non-numeric: the first value
    assert out.n_bins == cd.n_bins and out.uns == cd.uns


@pytest.mark.parametrize("how, row1", [("first", [1, 1, 1]), ("last", [3, 3, 3]), ("median", [2, 2, 2])])
def test_other_reductions(how, row1):
    out = merge_duplicate_spots(_cd(), how=how)
    np.testing.assert_array_equal(out.coords[1], row1)


def test_without_duplicates_and_bad_how():
    cd = _cd()
    single = cd[[0, 1, 3, 4, 6]]
    out = merge_duplicate_spots(single)
    np.testing.assert_array_equal(out.coords, single.coords)
    assert (out.spots["n_merged"] == 1).all()
    with pytest.raises(ValueError, match="how"):
        merge_duplicate_spots(cd, how="mode")


def test_merged_distance_map_equals_the_mean_of_duplicates():
    from uchrom.fea import distance_map

    out = merge_duplicate_spots(_cd())
    dm = distance_map(out, "chr1")
    # trace a: locus 0 (0,0,0), locus 10 the mean of two spots (2,2,2); trace b: locus 0 the mean of
    # (0,0,0) and (2,4,NaN) -> (1,2,0), locus 10 (9,9,9)
    d_a = np.linalg.norm([2, 2, 2])
    d_b = np.linalg.norm([8, 7, 9])
    assert dm.matrix[0, 1] == pytest.approx(np.median([d_a, d_b]))
