"""uchrom.im.impute.evaluate_imputation (hold-out test) and the ``imputed`` spot column."""

import numpy as np
import pandas as pd
import pytest

from uchrom.im.impute import evaluate_imputation, impute_coordinates


def _traces(n_traces=12, n_loci=15, seed=0):
    from chromdata import ChromData

    rng = np.random.default_rng(seed)
    rows, coords = [], []
    for t in range(n_traces):
        for i in range(n_loci):
            rows.append({"chrom": "chr2", "start": 10_000 * i, "end": 10_000 * (i + 1), "trace_id": t + 1})
            coords.append([100 * np.sin(0.3 * i + t), 100 * np.cos(0.3 * i + t), 20 * i + rng.normal(0, 1)])
    return ChromData(np.asarray(coords), pd.DataFrame(rows), uns={"xyz_unit": "nm"})


def test_imputed_column_marks_the_filled_loci():
    cd = _traces(3, 6)
    missing = np.zeros(cd.n_spots, bool)
    missing[[2, 9]] = True
    coords = cd.coords.copy()
    coords[missing] = np.nan
    cd.coords = coords
    drop = cd[np.flatnonzero(np.arange(cd.n_spots) != 14)]           # one absent row too
    out = impute_coordinates(drop, method="linear")
    assert out.spots["imputed"].sum() == 3
    flagged = out.spots_with_loci()[out.spots["imputed"].to_numpy()]
    got = sorted(zip(flagged["trace_id"].astype(int), flagged["start"]))
    assert got == [(1, 20_000), (2, 30_000), (3, 20_000)]
    assert not np.isnan(out.coords).any()


def test_holdout_summary_errors_and_storage():
    cd = _traces()
    res = evaluate_imputation(cd, ["linear", "cubic"], frac=0.2, seed=3)
    assert res.n_observed == 12 * 15 and res.n_hidden == 36
    assert list(res.summary.columns) == ["linear", "cubic"]
    assert "median error (nm)" in res.summary.index and "seconds" in res.summary.index
    assert res.errors.shape == (36, 2) and list(res.errors.index.names) == ["trace_id", "chrom", "start"]
    assert res.summary.loc["not imputed"].tolist() == [0, 0]
    assert res.neighbour_bp == 30_000                                   # three bins of 10 kb
    assert res.summary.loc["median error (nm)", "linear"] < 30          # smooth chains: close to the truth
    rec = cd.results.record("imputation.holdout")
    assert rec.params["frac"] == 0.2 and rec.function == "uchrom.im.impute.evaluate_imputation"


def test_holdout_does_not_depend_on_the_row_order():
    cd = _traces()
    shuffled = cd[np.random.default_rng(1).permutation(cd.n_spots)]
    a = evaluate_imputation(cd, ["linear"], seed=5, key_added=None)
    b = evaluate_imputation(shuffled, ["linear"], seed=5, key_added=None)
    pd.testing.assert_frame_equal(a.summary.drop(index="seconds"), b.summary.drop(index="seconds"))
    pd.testing.assert_frame_equal(a.errors, b.errors)


def test_holdout_selects_traces_and_checks_frac():
    cd = _traces()
    res = evaluate_imputation(cd, ["linear"], trace_ids=[1, 2, 3], frac=0.1, key_added=None)
    assert set(res.errors.index.get_level_values("trace_id")) <= {"1", "2", "3"}
    assert res.n_observed == 45 and res.n_hidden == 4
    with pytest.raises(ValueError, match="frac"):
        evaluate_imputation(cd, ["linear"], frac=1.5)
