"""Streaming ArcFISH preprocessing and callers (``streaming=True`` / backed
stores) against the in-memory torch path (``device="cpu"``)."""
import numpy as np
import pandas as pd
import pytest

from tests._synth import chain_traces, domain_traces
from uchrom import ChromData
from uchrom.fea import axis_variance_cube, axis_weight, filter_normalize
from uchrom.fea.arc_stream import axis_cube_streaming


def _messy(cd, seed=0):
    """Missing spots, a partly-NaN spot and duplicated loci, in a random row order."""
    rng = np.random.default_rng(seed)
    keep = rng.random(cd.n_spots) > 0.15
    sub = cd[np.flatnonzero(keep)]
    coords = sub.coords.copy()
    coords[rng.choice(len(coords), 4, replace=False), 1] = np.nan
    spots = sub.spots.drop(columns=["bin_id"]).copy()
    dup = rng.choice(len(spots), 30, replace=False)
    spots = pd.concat([spots, spots.iloc[dup]], ignore_index=True)
    coords = np.vstack([coords, coords[dup] + rng.normal(0, 0.05, (len(dup), 3))])
    perm = rng.permutation(len(spots))
    spots = spots.iloc[perm].reset_index(drop=True)
    spots["trace_id"] = spots["trace_id"].astype(str)
    return ChromData(coords[perm], spots)


def _sorted(cd):
    """The stored order, which the in-memory reference must see: both paths
    keep the first spot of a repeated (trace, locus) in that order."""
    return next(cd.iter_traces(10 ** 9))


@pytest.mark.parametrize("gen", ["domains", "loop"])
def test_axis_cube_streaming_matches_torch(tmp_path, gen):
    base = domain_traces(n_traces=60) if gen == "domains" else chain_traces(n_traces=80, n_bins=30, loop=(6, 22))
    cd = _messy(base)
    path = tmp_path / "t.chromdata.zarr"
    cd.write(path, row_group_rows=64)
    bk = ChromData.read(path, backed=True)
    mem = _sorted(cd)
    ref = filter_normalize(axis_variance_cube(mem, "chr1", device="cpu"))
    w_ref = axis_weight(mem, "chr1", device="cpu")
    for kw in ({}, {"memory_budget": 20_000, "batch": 7}):
        got = axis_cube_streaming(bk, "chr1", **kw)
        assert got["bin_ids"] == ref["bin_ids"] and got["n_traces"] == ref["n_traces"]
        np.testing.assert_array_equal(got["count"], ref["count"])
        np.testing.assert_array_equal(got["raw_var"], ref["raw_var"])          # exact medians
        for key in ("var", "expected", "norm_var"):
            np.testing.assert_allclose(got[key], ref[key], rtol=1e-9, atol=0, err_msg=key)
        np.testing.assert_allclose(got["axis_weight"], w_ref, rtol=1e-12)
    assert axis_cube_streaming(bk, "chr1", memory_budget=20_000)["n_bands"] > 1


def test_streaming_callers_match_in_memory(tmp_path):
    from uchrom.strc.loop import call_loops_axiswise_f
    from uchrom.strc.tad import TADCallerParams, call_tads_by_pval

    cd = chain_traces(n_traces=200, n_bins=40, loop=(8, 30))
    cd.write(tmp_path / "l.chromdata.zarr")
    bk = ChromData.read(tmp_path / "l.chromdata.zarr", backed=True)
    mem = ChromData.read(tmp_path / "l.chromdata.zarr")
    ref = call_loops_axiswise_f(mem, chrom="chr1", device="cpu", key_added=None)
    got = call_loops_axiswise_f(bk, chrom="chr1", key_added="loops.stream", memory_budget="64KB")
    assert len(ref) >= 1 and "loops.stream" in bk.results
    pd.testing.assert_frame_equal(got[["chrom1", "start1", "end1", "start2", "end2", "cluster_size",
                                       "summit_i", "summit_j"]],
                                  ref[["chrom1", "start1", "end1", "start2", "end2", "cluster_size",
                                       "summit_i", "summit_j"]])
    np.testing.assert_allclose(got["pval"], ref["pval"], rtol=1e-6)
    np.testing.assert_allclose(got["contact_freq"], ref["contact_freq"])
    # the in-memory object streams too when asked
    got2 = call_loops_axiswise_f(mem, chrom="chr1", key_added=None, streaming=True)
    pd.testing.assert_frame_equal(got2[["start1", "start2"]], ref[["start1", "start2"]])

    cd = domain_traces(n_traces=150, bounds=(0, 15, 30, 45))
    cd.write(tmp_path / "d.chromdata.zarr")
    bk = ChromData.read(tmp_path / "d.chromdata.zarr", backed=True)
    mem = ChromData.read(tmp_path / "d.chromdata.zarr")
    p = TADCallerParams(window_bp=1.5e5)
    ref = call_tads_by_pval(mem, chrom="chr1", params=p, device="cpu", key_added=None)
    got = call_tads_by_pval(bk, chrom="chr1", params=p, key_added=None, memory_budget="64KB")
    assert len(ref) > 0
    pd.testing.assert_frame_equal(got[["chrom", "start", "end", "level", "start1", "start2"]],
                                  ref[["chrom", "start", "end", "level", "start1", "start2"]])
    np.testing.assert_allclose(got[["stat1", "stat2"]].to_numpy(float), ref[["stat1", "stat2"]].to_numpy(float),
                               rtol=1e-6, equal_nan=True)
