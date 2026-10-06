"""``ResultsStore`` / ``ResultRecord``: provenance, validation, round trip."""
import copy
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData, ResultRecord, ResultsStore
from chromdata.zarrcd import ZARR_FORMAT_VERSION


def _write(cd, path):
    cd.write(path)


def _read(path):
    return ChromData.read(path)


def _store_version(path) -> str:
    """The format version a store records (``zarr.json`` of the directory or of the zip)."""
    import json
    import zipfile

    raw = (zipfile.ZipFile(path).read("zarr.json") if str(path).endswith(".cdz")
           else (path / "zarr.json").read_bytes())
    attrs = json.loads(raw).get("attributes", {})
    return str(attrs.get("uchrom", {}).get("format_version", attrs.get("uchrom_format_version")))


def _cd(results=None):
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 4,
        "start": [0, 10, 20, 30],
        "end": [10, 20, 30, 40],
        "trace_id": [0, 0, 0, 0],
    })
    return ChromData(np.arange(12, dtype=float).reshape(4, 3), spots, results=results)


@dataclass
class _Params:
    window: float = 1e5
    thresholds: np.ndarray = None


# ------------------------------------------------------------ in memory

def test_store_is_a_mapping_of_values():
    cd = _cd({"a": np.ones(3)})
    assert isinstance(cd.results, ResultsStore)
    np.testing.assert_array_equal(cd.results["a"], np.ones(3))
    assert "a" in cd.results and list(cd.results) == ["a"] and len(cd.results) == 1
    assert cd.results.get("missing") is None
    rec = cd.results.record("a")
    assert rec.kind == "array" and rec.function is None and rec.params == {}
    del cd.results["a"]
    assert len(cd.results) == 0


def test_plain_dict_assignment_is_coerced():
    cd = _cd()
    cd.results = {"t": pd.DataFrame({"x": [1]})}
    assert isinstance(cd.results, ResultsStore)
    assert cd.results.record("t").kind == "table"


def test_set_records_provenance_from_dataclass_params():
    cd = _cd()
    df = pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [20]})
    rec = cd.results.set(
        "tads.x", df, kind="intervals", function="pkg.fn",
        params=_Params(thresholds=np.array([1.0, 2.0])),
        inputs={"chrom": ["chr1"], "n": np.int64(3)},
    )
    assert cd.results["tads.x"] is df
    assert cd.results.record("tads.x") is rec
    assert rec.params == {"window": 1e5, "thresholds": [1.0, 2.0]}
    assert rec.inputs == {"chrom": ["chr1"], "n": 3}
    assert rec.function == "pkg.fn" and rec.kind == "intervals"
    assert rec.uchrom_version and rec.created_utc.endswith("+00:00")
    assert set(rec.provenance) == {"kind", "function", "params", "inputs",
                                   "uchrom_version", "created_utc"}


@pytest.mark.parametrize("value, kind", [
    (pd.DataFrame({"a": [1]}), "table"),
    (pd.Series([1.0]), "table"),
    (np.zeros(2), "array"),
    ({"k": np.zeros(2)}, "mapping"),
    (3, "scalar"), ("s", "scalar"), (None, "scalar"), ([1, 2], "scalar"),
])
def test_kind_inference(value, kind):
    store = ResultsStore({"v": value})
    assert store.record("v").kind == kind


def test_unsupported_value_raises_at_assignment():
    cd = _cd()
    with pytest.raises(TypeError, match=r"results\['bad'\]"):
        cd.results["bad"] = object()
    with pytest.raises(TypeError, match=r"results\['o'\]\['bad'\]"):
        cd.results["o"] = {"bad": {1, 2}}
    with pytest.raises(TypeError, match="object-dtype"):
        cd.results["arr"] = np.array([{"a": 1}], dtype=object)
    with pytest.raises(ValueError, match="'/'"):
        cd.results["a/b"] = 1
    assert len(cd.results) == 0


def test_record_validation():
    with pytest.raises(ValueError, match="unknown result kind"):
        ResultRecord(kind="blob", value=1)
    with pytest.raises(TypeError, match="intervals"):
        ResultRecord(kind="intervals", value=np.zeros(2))


def test_copy_and_deepcopy_keep_records():
    cd = _cd()
    cd.results.set("t", pd.DataFrame({"x": [1]}), function="f", params={"p": 1})
    cc = cd.copy()
    assert cc.results.record("t").function == "f"
    assert cc.results["t"] is not cd.results["t"]
    dc = copy.deepcopy(cd.results)
    assert dc == cd.results


# ------------------------------------------------------------ on disk

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


@pytest.mark.parametrize("suffix", [".chromdata.zarr", ".cdz"])
def test_every_kind_round_trips_with_provenance(tmp_path, suffix):
    cd = _cd()
    for key, (value, kind) in _all_kinds().items():
        cd.results.set(key, value, kind=kind, function=f"f.{key}",
                       params={"k": key, "arr": np.arange(2)}, inputs={"chrom": ["chr1"]})
    path = tmp_path / f"r{suffix}"
    _write(cd, path)
    assert _store_version(path) == ZARR_FORMAT_VERSION
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


@pytest.mark.parametrize("suffix", [".chromdata.zarr", ".cdz"])
def test_empty_table_keeps_schema(tmp_path, suffix):
    empty = pd.DataFrame({
        "chrom": pd.Series(dtype=object), "start": pd.Series(dtype="int64"),
        "fdr": pd.Series(dtype="float64"),
    })
    cd = _cd({"empty": empty})
    _write(cd, tmp_path / f"e{suffix}")
    out = _read(tmp_path / f"e{suffix}").results["empty"]
    pd.testing.assert_frame_equal(out, empty)
