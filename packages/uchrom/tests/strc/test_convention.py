"""Calling convention of the ``strc`` callers: chrom=None merging,
key_added / copy, provenance records, and the deprecated 1.x forms."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests._synth import chain_traces, domain_traces
from uchrom import ChromData
from tests import REPO

COOL = REPO / "example-data" / "K562_chr21_30kb.cool"


def _two_chroms(make, **kw):
    """Same generator on chr1 and chr2 (different seeds, disjoint trace ids)."""
    a = make(seed=0, **kw)
    b = make(seed=1, **kw)
    sb = b.spots.copy()
    sb["chrom"] = "chr2"
    sb["trace_id"] = sb["trace_id"].astype(int) + 10_000
    sa = a.spots.copy()
    sa["trace_id"] = sa["trace_id"].astype(int)
    sa["chrom"] = sa["chrom"].astype(str)
    spots = pd.concat([sa, sb], ignore_index=True)
    return ChromData(np.concatenate([a.coords, b.coords]), spots)


def _callers():
    from uchrom.strc.comp import CompartmentCallerParams, call_compartments_axes_pc
    from uchrom.strc.loop import call_loops_axiswise_f
    from uchrom.strc.tad import FISHnetParams, TADCallerParams, call_domains_fishnet, call_tads_by_pval

    return {
        "tads": (call_tads_by_pval, "tads.arcfish", "tads",
                 dict(params=TADCallerParams(window_bp=1.5e5), device="cpu"),
                 lambda **kw: domain_traces(n_traces=60, **kw), {}),
        "loops": (call_loops_axiswise_f, "loops.axiswise_f", "loops",
                  dict(device="cpu"),
                  lambda **kw: chain_traces(n_traces=120, n_bins=40, loop=(8, 30), **kw), {}),
        "compartments": (call_compartments_axes_pc, "compartments.axes_pc", "compartments",
                         dict(device="cpu", params=CompartmentCallerParams()),
                         lambda **kw: chain_traces(n_traces=80, n_bins=30, **kw), {}),
        "fishnet": (call_domains_fishnet, "tads.fishnet", "fishnet_domains",
                    dict(params=FISHnetParams(n_louvain_runs=2, max_thresholds=12), max_traces=2),
                    lambda **kw: domain_traces(n_traces=3, **kw), {}),
    }


@pytest.fixture(scope="module")
def two_chrom_data():
    return {name: _two_chroms(spec[4]) for name, spec in _callers().items()}


@pytest.mark.parametrize("name", ["tads", "loops", "compartments", "fishnet"])
def test_chrom_none_merges_per_chrom_outputs(name, two_chrom_data):
    fn, key, _, kw, _, _ = _callers()[name]
    cd = two_chrom_data[name].copy()
    merged = fn(cd, **kw)
    per = [fn(cd, chrom=c, key_added=None, **kw) for c in ("chr1", "chr2")]
    expected = pd.concat([p for p in per if not p.empty], ignore_index=True)
    pd.testing.assert_frame_equal(merged.reset_index(drop=True), expected, check_frame_type=False)
    chrom_col = "chrom1" if name == "loops" else "chrom"
    if len(merged):
        assert set(merged[chrom_col]) <= {"chr1", "chr2"}

    rec = cd.results.record(key)
    assert cd.results[key] is merged
    assert rec.function.startswith("uchrom.strc.")
    assert rec.kind == ("table" if name == "compartments" else "intervals")
    assert rec.inputs["chrom"] == ["chr1", "chr2"]
    assert rec.params  # asdict(params)
    assert list(cd.results) == ([key, f"{key}.ensemble"] if name == "fishnet" else [key])


def test_copy_true_returns_new_chromdata(two_chrom_data):
    from uchrom.strc.tad import TADCallerParams, call_tads_by_pval

    cd = two_chrom_data["tads"].copy()
    out = call_tads_by_pval(cd, chrom="chr1", params=TADCallerParams(window_bp=1.5e5),
                            device="cpu", copy=True)
    assert isinstance(out, ChromData)
    assert "tads.arcfish" in out.results and "tads.arcfish" not in cd.results
    with pytest.raises(ValueError, match="copy=True"):
        call_tads_by_pval(cd, chrom="chr1", key_added=None, copy=True)


def test_key_added_none_does_not_store(two_chrom_data):
    from uchrom.strc.loop import call_loops_axiswise_f

    cd = two_chrom_data["loops"].copy()
    out = call_loops_axiswise_f(cd, chrom="chr1", device="cpu", key_added=None)
    assert isinstance(out, pd.DataFrame) and len(cd.results) == 0


def test_trace_selection_equals_subset(two_chrom_data):
    from uchrom.strc.comp import call_compartments_axes_pc

    cd = two_chrom_data["compartments"]
    keep = [str(t) for t in range(40)]
    sel = call_compartments_axes_pc(cd.copy(), chrom="chr1", trace_ids=keep, device="cpu")
    sub = cd[cd.spots["trace_id"].astype(str).isin(keep).to_numpy()]
    ref = call_compartments_axes_pc(sub, chrom="chr1", device="cpu", key_added=None)
    pd.testing.assert_frame_equal(sel, ref)


@pytest.mark.parametrize("name", ["tads", "loops", "compartments", "fishnet"])
def test_legacy_forms_warn_and_keep_old_keys(name, two_chrom_data):
    fn, new_key, old_key, kw, _, _ = _callers()[name]
    cd = two_chrom_data[name].copy()
    with pytest.warns(DeprecationWarning, match="positional|chrom=..."):
        legacy = fn(cd, "chr1", **kw)
    assert old_key in cd.results and new_key not in cd.results
    new = fn(cd, chrom="chr1", **kw)
    pd.testing.assert_frame_equal(legacy, new, check_frame_type=False)

    cd2 = two_chrom_data[name].copy()
    with pytest.warns(DeprecationWarning, match="store="):
        fn(cd2, chrom="chr1", store=False, **kw)
    assert len(cd2.results) == 0
    with pytest.warns(DeprecationWarning, match="result_key="):
        fn(cd2, chrom="chr1", result_key="mine", **kw)
    assert "mine" in cd2.results


def test_legacy_fishnet_ensemble_layout(two_chrom_data):
    from uchrom.strc.tad import FISHnetParams, call_domains_fishnet

    cd = two_chrom_data["fishnet"].copy()
    params = FISHnetParams(n_louvain_runs=2, max_thresholds=12)
    with pytest.warns(DeprecationWarning):
        call_domains_fishnet(cd, "chr1", params=params, max_traces=2)
    ens = cd.results["fishnet_ensemble"]
    assert ens["chrom"] == "chr1" and ens["n_traces"] == 2 and ens["mask"].ndim == 2
    call_domains_fishnet(cd, chrom="chr1", params=params, max_traces=2)
    new = cd.results["tads.fishnet.ensemble"]["chr1"]
    np.testing.assert_array_equal(new["mask"], ens["mask"])
    assert new["bin_ids"].shape == (ens["mask"].shape[0], 2)


def test_results_round_trip_after_calling(tmp_path, two_chrom_data):
    from uchrom.strc.tad import FISHnetParams, call_domains_fishnet

    cd = two_chrom_data["fishnet"].copy()
    call_domains_fishnet(cd, params=FISHnetParams(n_louvain_runs=2, max_thresholds=12),
                         max_traces=2)
    cd.write(tmp_path / "f.chromdata.zarr")
    back = ChromData.read(tmp_path / "f.chromdata.zarr").results
    for key in cd.results:
        assert back.record(key).provenance == cd.results.record(key).provenance
    pd.testing.assert_frame_equal(
        back["tads.fishnet"].astype({"trace_id": str}),
        cd.results["tads.fishnet"].astype({"trace_id": str}),
        check_frame_type=False,
    )
    for c in ("chr1", "chr2"):
        for k in ("mask", "bin_ids"):
            np.testing.assert_array_equal(back["tads.fishnet.ensemble"][c][k],
                                          cd.results["tads.fishnet.ensemble"][c][k])


def test_multi_wrappers_are_deprecated_but_equivalent(two_chrom_data):
    from uchrom.strc import call_tads_multi
    from uchrom.strc.tad import TADCallerParams, call_tads_by_pval

    cd = two_chrom_data["tads"].copy()
    p = TADCallerParams(window_bp=1.5e5)
    with pytest.warns(DeprecationWarning, match="call_tads_multi"):
        old = call_tads_multi(cd, params=p, device="cpu")
    assert "tads" in cd.results
    new = call_tads_by_pval(cd, params=p, device="cpu")
    pd.testing.assert_frame_equal(old, new, check_frame_type=False)


def test_structural_features_find_new_keys(two_chrom_data):
    from uchrom.strc import add_structural_features
    from uchrom.strc.tad import TADCallerParams, call_tads_by_pval

    cd = two_chrom_data["tads"].copy()
    call_tads_by_pval(cd, params=TADCallerParams(window_bp=1.5e5), device="cpu")
    table = add_structural_features(cd)
    assert "inside_tad" in table.columns
    assert cd.uns["feature_registry"][-1]["source_results"] == ["tads.arcfish"]


def test_tl_aliases_dispatch(two_chrom_data):
    import uchrom as uc
    from uchrom.strc.tad import TADCallerParams

    cd = two_chrom_data["tads"].copy()
    out = uc.tl.call_tads(cd, method="arcfish", chrom="chr1",
                          params=TADCallerParams(window_bp=1.5e5), device="cpu")
    assert cd.results["tads.arcfish"] is out
    with pytest.raises(ValueError, match="unknown TAD method"):
        uc.tl.call_tads(cd, method="nope")
    uc.tl.call_compartments(cd, chrom="chr1", device="cpu")
    assert "compartments.axes_pc" in cd.results
    assert callable(uc.pp.impute)


@pytest.mark.skipif(not COOL.exists(), reason="K562 cool not present")
def test_call_tads_di_matches_kernel_on_linked_cool():
    import cooler
    import torch

    from uchrom.strc.tad import DICallerParams, call_tads_di, get_domains

    cd = domain_traces(n_traces=2)
    cd.link_cool(COOL, key="k562")
    p = DICallerParams(window=10, smoothing_param=0.03, min_size_frac=0.02)
    tads = call_tads_di(cd, contacts="k562", chrom="chr21", params=p, device="cpu")

    clr = cooler.Cooler(str(COOL))
    mat = np.nan_to_num(clr.matrix(balance="weight" in clr.bins().columns).fetch("chr21"))
    ref = get_domains(torch.as_tensor(mat, dtype=torch.float64), window=10,
                      smoothing_param=0.03, min_size_frac=0.02, device="cpu")
    assert list(zip(tads["start_bin"], tads["end_bin"])) == [(int(s), int(e)) for s, e in ref if e > s]
    rec = cd.results.record("tads.di")
    assert rec.inputs["contacts"] == "k562" and rec.inputs["resolution"] == 30_000
    assert rec.params == {"window": 10, "smoothing_param": 0.03, "min_size_frac": 0.02}
