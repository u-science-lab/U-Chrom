"""Exact streaming distance maps (``uchrom.fea.distance_map``) against the
dense in-memory reference (``mean_distance_matrix``)."""
import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData
from uchrom.fea import distance_map, mean_distance_matrix


def _tracing(n_cells=7, n_bins=12, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for c in rng.permutation(n_cells):
        for chrom in ("chr2", "chr1"):
            for a in range(2):                              # two homologs
                obs = np.sort(rng.choice(n_bins, rng.integers(2, n_bins), replace=False))
                obs = rng.permutation(np.r_[obs, rng.choice(obs, 2)])   # duplicated loci
                for b in obs:
                    rows.append((chrom, int(b) * 1000, int(b) * 1000 + 1000, f"c{c}_{chrom}_{a}", f"c{c}"))
    spots = pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id", "cell_id"])
    coords = rng.normal(size=(len(spots), 3)) * 3
    coords[rng.choice(len(spots), 5, replace=False), rng.integers(0, 3, 5)] = np.nan
    return ChromData(coords, spots)


def _dense(cd, chrom, reduce):
    # the dense reference pivots the stored order (last duplicate wins)
    df = cd.to_dataframe()
    with np.errstate(all="ignore"), pd.option_context("mode.chained_assignment", None):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return mean_distance_matrix(df, chrom=chrom, reduce=reduce)


@pytest.mark.parametrize("stat", ["median", "mean"])
def test_distance_map_equals_dense_reference(tmp_path, stat):
    cd = _tracing()
    path = tmp_path / "t.chromdata.zarr"
    cd.write(path, row_group_rows=16)
    mem = ChromData.read(path)
    bk = ChromData.read(path, backed=True)
    for chrom in ("chr1", "chr2"):
        ref, bins, n_traces = _dense(mem, chrom, stat)
        variants = [distance_map(mem, chrom, stat, streaming=False),
                    distance_map(cd, chrom, stat, streaming=False),         # unsorted object
                    distance_map(bk, chrom, stat, batch=3, memory_budget=2_000),   # many bands
                    distance_map(bk, chrom, stat)]
        for res in variants:
            assert res.n_traces == n_traces
            assert list(zip(res.bins["start"], res.bins["end"])) == bins
            np.testing.assert_array_equal(res.matrix, ref)            # bitwise, NaN == NaN
            assert (res.count == res.count.T).all()
        if stat == "median":
            assert variants[2].n_bands > 1 and variants[2].n_passes == variants[2].n_bands + 1
            assert variants[0].n_bands == 1


def test_distance_map_all_bins_and_errors(tmp_path):
    cd = _tracing(n_cells=3)
    res = distance_map(cd, "chr1", observed=False)
    assert res.matrix.shape == (int((cd.bins["chrom"] == "chr1").sum()),) * 2
    with pytest.raises(ValueError, match="stat"):
        distance_map(cd, "chr1", "max")
    with pytest.raises(ValueError, match="No spots"):
        distance_map(cd, "chrZ")
