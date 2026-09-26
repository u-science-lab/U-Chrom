"""Lossless decimal encoding of float64 columns (format 2.2): bitwise round
trips on random and adversarial values (property-style, seeded)."""

import io

import numpy as np
import pytest

from uchrom.core import floatcodec as fc


def _bits(a):
    return np.ascontiguousarray(a, dtype=np.float64).view(np.int64)


def _roundtrip(v, p):
    q, d, m, ev = fc.encode(v, p)
    back = fc.decode(q, p, d, m if m.any() else None, ev)
    assert np.array_equal(_bits(back), _bits(v))
    return q, d, m


def _parquet_roundtrip(v, p):
    import pyarrow as pa
    import pyarrow.parquet as pq

    q, u, e = fc.encode_arrow(v, p)
    buf = io.BytesIO()
    pq.write_table(pa.table({"v": q, "v#ulp": u, "v#exc": e}), buf, compression="zstd")
    t = pq.read_table(pa.BufferReader(buf.getvalue()))
    back = fc.decode_arrow(t.column("v"), t.column("v#ulp"), t.column("v#exc"), p)
    assert np.array_equal(_bits(back), _bits(v))


SPECIALS = np.array([0.0, -0.0, np.nan, np.inf, -np.inf, 0.1 + 0.2, 0.3, 1e-320, -1e-320, 5e-324,
                     np.finfo(np.float64).max, -np.finfo(np.float64).max, np.finfo(np.float64).tiny,
                     1e15, -1e15, 2.0 ** 53, 2.0 ** 53 + 2, 123456789.123456789, -7.5, 1e-9, 3e-10])


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("k", [0, 2, 5, 6, 9])
def test_decimal_text_values_are_exact(seed, k):
    rng = np.random.default_rng(seed)
    ints = rng.integers(-10 ** 8, 10 ** 8, 5000)
    # values as parsed from text with k decimals
    v = np.array([float(f"{i / 10 ** k:.{k}f}") for i in ints])
    p = {"codec": "decimal", "exp": k, "int": "int64"}
    q, d, m = _roundtrip(v, p)
    assert not m.any() and not d.any()          # exact scaled integers: no correction needed
    assert np.array_equal(q, ints)


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("k", [3, 6, 9])
@pytest.mark.parametrize("int_type", ["int32", "int64"])
def test_arbitrary_floats_bitwise(seed, k, int_type):
    rng = np.random.default_rng(100 + seed)
    parts = [
        rng.normal(0, 3, 2000),                                   # full-precision noise
        np.round(rng.normal(0, 3, 2000), 5) - np.round(rng.normal(0, 1, 2000), 5),   # arithmetic on decimals
        rng.normal(0, 1, 500) * 10.0 ** rng.integers(-300, 300, 500),                # huge / tiny magnitudes
        SPECIALS,
        np.array([np.float64(np.frombuffer(np.uint64(0x7FF8DEADBEEF0001).tobytes(), np.float64)[0])]),  # NaN payload
    ]
    v = np.concatenate(parts)
    rng.shuffle(v)
    p = {"codec": "decimal", "exp": k, "int": int_type}
    _roundtrip(v, p)
    _parquet_roundtrip(v, p)


def test_specials_are_exceptions():
    p = {"codec": "decimal", "exp": 6, "int": "int32"}
    q, d, m = _roundtrip(SPECIALS, p)
    assert m[np.isnan(SPECIALS) | np.isinf(SPECIALS)].all()
    neg0 = (SPECIALS == 0) & np.signbit(SPECIALS)
    assert m[neg0].all()                         # -0.0 kept exactly
    assert not m[SPECIALS == 0.3].any()          # a plain decimal is not an exception
    _parquet_roundtrip(SPECIALS, p)


def test_int32_overflow_goes_to_exceptions():
    v = np.array([1.5, 3e3, 2.2e3, 5e9, -5e9])
    p = {"codec": "decimal", "exp": 1, "int": "int32"}
    q, d, m = _roundtrip(v, p)
    assert q.dtype == np.int32 and m.tolist() == [False, False, False, True, True]


def test_point_one_plus_point_two():
    v = np.array([0.1 + 0.2, 0.3, 0.1, 0.2] * 10)
    p = {"codec": "decimal", "exp": 1, "int": "int32"}
    q, d, m = _roundtrip(v, p)
    assert d[0] != 0 and d[1] == 0 and not m.any()   # 0.30000000000000004 = 0.3 + 1 ulp


def test_plan_choices():
    rng = np.random.default_rng(0)
    dec = np.round(rng.normal(0, 50, 100_000), 4)
    p = fc.plan(dec)
    assert p == {"codec": "decimal", "exp": 4, "int": "int32"}
    assert fc.plan(rng.normal(0, 1, 100_000)) is None            # full precision: no gain
    assert fc.plan(np.zeros(0)) is None
    assert fc.plan(np.full(100, np.nan)) is None
    assert fc.plan(np.arange(10, dtype=np.int64)) is None         # not float64
    big = np.round(rng.normal(0, 1e6, 100_000), 4)
    assert fc.plan(big)["int"] == "int64"


def test_decode_into_buffer():
    v = np.round(np.random.default_rng(1).normal(0, 1, 1000), 3)
    p = {"codec": "decimal", "exp": 3, "int": "int32"}
    q, d, m, ev = fc.encode(v, p)
    out = np.empty(1000)
    res = fc.decode(q, p, d, None, None, out=out)
    assert res is out and np.array_equal(_bits(out), _bits(v))
