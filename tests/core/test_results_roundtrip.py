"""``cd.results`` must survive ``write`` / ``read`` without silent loss."""

import h5py
import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData


def _cd(results):
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 4,
        "start": [0, 10, 20, 30],
        "end": [10, 20, 30, 40],
        "trace_id": [0, 0, 0, 0],
    })
    return ChromData(np.arange(12, dtype=float).reshape(4, 3), spots, results=results)


def _roundtrip(tmp_path, results):
    path = tmp_path / "r.h5cd"
    _cd(results).write(path)
    return ChromData.read(path).results


def test_all_supported_types_roundtrip(tmp_path):
    tads = pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [20]})
    series = pd.Series([0.1, 0.2, 0.3], index=["a", "b", "c"], name="score")
    results = {
        "tads": tads,
        "pc1": np.array([0.5, -0.5, 0.1, -0.1]),
        "score": series,
        "ensemble": {                       # fishnet-style nested dict
            "chrom": "chr1",
            "mask": np.array([True, False, True]),
            "n_traces": np.int64(7),
            "nested": {"threshold": 0.05, "table": tads},
        },
        "n_iter": 12,
        "alpha": float("nan"),
        "converged": True,
        "label": "run-1",
        "missing": None,
        "window": [3, 5, 7],
        "shape": (2, 3),
    }
    out = _roundtrip(tmp_path, results)

    assert set(out) == set(results)
    pd.testing.assert_frame_equal(out["tads"], tads)
    np.testing.assert_array_equal(out["pc1"], results["pc1"])
    pd.testing.assert_series_equal(out["score"], series)

    ens = out["ensemble"]
    assert ens["chrom"] == "chr1"
    np.testing.assert_array_equal(ens["mask"], [True, False, True])
    assert ens["n_traces"] == 7
    assert ens["nested"]["threshold"] == 0.05
    pd.testing.assert_frame_equal(ens["nested"]["table"], tads)

    assert out["n_iter"] == 12 and isinstance(out["n_iter"], int)
    assert np.isnan(out["alpha"])
    assert out["converged"] is True
    assert out["label"] == "run-1"
    assert out["missing"] is None
    assert out["window"] == [3, 5, 7]
    assert out["shape"] == (2, 3)


def test_unsupported_value_raises_instead_of_dropping(tmp_path):
    with pytest.raises(TypeError, match=r"results\['bad'\]"):
        _cd({"bad": object()}).write(tmp_path / "x.h5cd")


def test_nested_unsupported_value_reports_path(tmp_path):
    with pytest.raises(TypeError, match=r"results\['outer'\]\['bad'\]"):
        _cd({"outer": {"bad": {1, 2}}}).write(tmp_path / "x.h5cd")


def test_object_array_raises(tmp_path):
    with pytest.raises(TypeError, match="object-dtype"):
        _cd({"arr": np.array([{"a": 1}], dtype=object)}).write(tmp_path / "x.h5cd")


def test_slash_in_key_raises(tmp_path):
    with pytest.raises(ValueError, match="'/'"):
        _cd({"a/b": np.zeros(2)}).write(tmp_path / "x.h5cd")


def test_legacy_untyped_results_still_read(tmp_path):
    """Pre-1.2 files: untyped groups are DataFrames, datasets are arrays."""
    path = tmp_path / "legacy.h5cd"
    _cd({"tads": pd.DataFrame({"start": [0, 10]}), "pc1": np.ones(4)}).write(path)
    with h5py.File(path, "r+") as f:
        f.attrs["uchrom_format_version"] = "1.1"
        for obj in (f["results"], f["results/tads"]):
            del obj.attrs["_type"]
    out = ChromData.read(path).results
    assert list(out["tads"]["start"]) == [0, 10]
    np.testing.assert_array_equal(out["pc1"], np.ones(4))
