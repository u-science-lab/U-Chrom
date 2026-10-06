"""Results in the legacy HDF5 container (``.h5cd``, ``uchrom.io._h5cd_legacy``: conversion and the format
benchmarks only): every kind round trips with its provenance, invalid values raise, and 1.x files read."""


import h5py
import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData
from uchrom.io import file_format_version
from uchrom.io._h5cd_legacy import FORMAT_VERSION, _read_results, read_h5cd, write_h5cd

SUFFIXES = pytest.mark.parametrize("suffix", [".h5cd"])


def _cd(results=None):
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 4,
        "start": [0, 10, 20, 30],
        "end": [10, 20, 30, 40],
        "trace_id": [0, 0, 0, 0],
    })
    return ChromData(np.arange(12, dtype=float).reshape(4, 3), spots, results=results)


def _write(cd, path):
    write_h5cd(cd, path)


def _read(path):
    return read_h5cd(path)


def _roundtrip(tmp_path, results, suffix=".h5cd"):
    path = tmp_path / f"r{suffix}"
    _write(_cd(results), path)
    return read_h5cd(path).results


@SUFFIXES
def test_all_supported_types_roundtrip(tmp_path, suffix):
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
    out = _roundtrip(tmp_path, results, suffix)

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


@SUFFIXES
def test_unsupported_value_raises_instead_of_dropping(tmp_path, suffix):
    with pytest.raises(TypeError, match=r"results\['bad'\]"):
        _write(_cd({"bad": object()}), tmp_path / f"x{suffix}")


@SUFFIXES
def test_nested_unsupported_value_reports_path(tmp_path, suffix):
    with pytest.raises(TypeError, match=r"results\['outer'\]\['bad'\]"):
        _write(_cd({"outer": {"bad": {1, 2}}}), tmp_path / f"x{suffix}")


@SUFFIXES
def test_object_array_raises(tmp_path, suffix):
    with pytest.raises(TypeError, match="object-dtype"):
        _write(_cd({"arr": np.array([{"a": 1}], dtype=object)}), tmp_path / f"x{suffix}")


@SUFFIXES
def test_slash_in_key_raises(tmp_path, suffix):
    with pytest.raises(ValueError, match="'/'"):
        _write(_cd({"a/b": np.zeros(2)}), tmp_path / f"x{suffix}")


def test_legacy_untyped_results_still_read(tmp_path):
    """Pre-1.2 files: untyped groups are DataFrames, datasets are arrays."""
    from tests._v1 import write_v1

    path = tmp_path / "legacy.h5cd"
    cd = _cd({"tads": pd.DataFrame({"start": [0, 10]}), "pc1": np.ones(4)})
    write_v1(path, cd.coords, cd.to_dataframe().drop(columns=["x", "y", "z"]),
             results={"tads": cd.results["tads"], "pc1": cd.results["pc1"]}, version="1.1")
    with h5py.File(path, "r+") as f:
        for obj in (f["results"], f["results/tads"]):
            del obj.attrs["_type"]
        for key in ("tads", "pc1"):
            for attr in [a for a in f["results"][key].attrs if a.startswith("_") and a != "_columns"
                         and a != "_n_rows"]:
                del f["results"][key].attrs[attr]
    out = read_h5cd(path).results
    assert list(out["tads"]["start"]) == [0, 10]
    np.testing.assert_array_equal(out["pc1"], np.ones(4))


def _all_kinds():
    tads = pd.DataFrame({"chrom": ["chr1", "chr2"], "start": [0, 5], "end": [20, 9],
                         "level": [1, 1], "fdr": [0.01, np.nan]})
    return {
        "table": (pd.DataFrame({"a": [1.5, 2.5], "b": ["x", "y"]}), "table"),
        "series": (pd.Series([0.1, 0.2], index=["p", "q"], name="s"), "table"),
        "intervals": (tads, "intervals"),
        "array": (np.arange(6, dtype=np.int32).reshape(2, 3), "array"),
        "mapping": ({"chr1": {"mask": np.eye(2, dtype=np.int64), "n": 3}}, "mapping"),
        "scalar": (0.25, "scalar"),
        "tuple": ((1, 2), "scalar"),
        "none": (None, "scalar"),
    }


@pytest.mark.parametrize("suffix", [".h5cd"])
def test_every_kind_round_trips_with_provenance(tmp_path, suffix):
    cd = _cd()
    for key, (value, kind) in _all_kinds().items():
        cd.results.set(key, value, kind=kind, function=f"f.{key}",
                       params={"k": key, "arr": np.arange(2)}, inputs={"chrom": ["chr1"]})
    path = tmp_path / f"r{suffix}"
    _write(cd, path)
    assert file_format_version(path) == FORMAT_VERSION
    out = _read(path).results

    assert set(out) == set(cd.results)
    for key in cd.results:
        a, b = cd.results.record(key), out.record(key)
        assert b.provenance == a.provenance, key
    pd.testing.assert_frame_equal(out["table"], cd.results["table"])
    pd.testing.assert_series_equal(out["series"], cd.results["series"])
    pd.testing.assert_frame_equal(out["intervals"], cd.results["intervals"])
    np.testing.assert_array_equal(out["array"], cd.results["array"])
    assert out["array"].dtype == np.int32
    np.testing.assert_array_equal(out["mapping"]["chr1"]["mask"], np.eye(2))
    assert out["mapping"]["chr1"]["n"] == 3
    assert out["scalar"] == 0.25 and out["tuple"] == (1, 2) and out["none"] is None
    assert out.record("table").params == {"k": "table", "arr": [0, 1]}


@pytest.mark.parametrize("suffix", [".h5cd"])
def test_empty_table_keeps_schema(tmp_path, suffix):
    empty = pd.DataFrame({
        "chrom": pd.Series(dtype=object), "start": pd.Series(dtype="int64"),
        "fdr": pd.Series(dtype="float64"),
    })
    cd = _cd({"empty": empty})
    _write(cd, tmp_path / f"e{suffix}")
    out = _read(tmp_path / f"e{suffix}").results["empty"]
    pd.testing.assert_frame_equal(out, empty)


def test_old_reader_sees_values_unchanged(tmp_path):
    """1.4 only adds attrs: the value-level reader used by 1.2/1.3 still works."""
    cd = _cd()
    cd.results.set("t", pd.DataFrame({"x": [1, 2]}), function="f")
    cd.results.set("m", {"a": np.ones(2)}, function="f")
    write_h5cd(cd, tmp_path / "v.h5cd")
    with h5py.File(tmp_path / "v.h5cd", "r") as f:
        plain = _read_results(f, "results")
    pd.testing.assert_frame_equal(plain["t"], cd.results["t"])
    np.testing.assert_array_equal(plain["m"]["a"], np.ones(2))


def test_pre_provenance_file_reads_as_records_without_provenance(tmp_path):
    """A 1.3 file (no ``_kind`` attrs) reads into a store with inferred kinds."""
    from tests._v1 import write_v1

    path = tmp_path / "v13.h5cd"
    cd = _cd()
    cd.results.set("tads", pd.DataFrame({"start": [0]}), function="f")
    cd.results.set("pc1", np.ones(4), function="f")
    write_v1(path, cd.coords, cd.to_dataframe().drop(columns=["x", "y", "z"]),
             results=cd.results, version="1.3")
    with h5py.File(path, "r+") as f:
        for key in ("tads", "pc1"):
            for attr in ("_kind", "_function", "_params", "_inputs",
                         "_uchrom_version", "_created_utc"):
                del f["results"][key].attrs[attr]
    out = read_h5cd(path).results
    assert out.record("tads").kind == "table" and out.record("tads").function is None
    assert out.record("pc1").kind == "array"
    np.testing.assert_array_equal(out["pc1"], np.ones(4))
