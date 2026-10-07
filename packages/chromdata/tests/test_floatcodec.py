"""Lossless decimal encoding of float64 columns (format 2.2): bitwise round
trips on random and adversarial values (property-style, seeded)."""

import io

import numpy as np
import pytest

from chromdata import floatcodec as fc


def _bits(a):
    return np.ascontiguousarray(a, dtype=np.float64).view(np.int64)


def _roundtrip(v, p):
    packed, m, ev = fc.encode(v, p)
    assert packed.dtype == np.int64
    back = fc.decode(packed, p, m if m.any() else None, ev)
    assert np.array_equal(_bits(back), _bits(v))
    q = packed >> 16
    d = (packed & 0xFFFF) - (1 << 15)
    return q, d, m


def _parquet_roundtrip(v, p):
    import pyarrow as pa
    import pyarrow.parquet as pq

    q, e = fc.encode_arrow(v, p)
    buf = io.BytesIO()
    pq.write_table(pa.table({"v": q, "v#exc": e}), buf, compression="zstd", row_group_size=1000)
    t = pq.read_table(pa.BufferReader(buf.getvalue()))
    back = fc.decode_arrow(t.column("v"), t.column("v#exc"), p)
    assert np.array_equal(_bits(back), _bits(v))


SPECIALS = np.array([0.0, -0.0, np.nan, np.inf, -np.inf, 0.1 + 0.2, 0.3, 1e-320, -1e-320, 5e-324,
                     np.finfo(np.float64).max, -np.finfo(np.float64).max, np.finfo(np.float64).tiny,
                     1e15, -1e15, 2.0 ** 53, 2.0 ** 53 + 2, 123456789.123456789, -7.5, 1e-9, 3e-10,
                     -0.0540429999999999, 89.59939099999997])
NAN_PAYLOAD = np.frombuffer(np.uint64(0x7FF8DEADBEEF0001).tobytes(), np.float64)[0]


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("k", [0, 2, 5, 6, 9])
def test_decimal_text_values_are_exact(seed, k):
    rng = np.random.default_rng(seed)
    ints = rng.integers(-10 ** 8, 10 ** 8, 5000)
    # values as parsed from text with k decimals
    v = np.array([float(f"{i / 10 ** k:.{k}f}") for i in ints])
    p = {"codec": "decimal", "exp": k}
    q, d, m = _roundtrip(v, p)
    assert not m.any() and not d.any()          # exact scaled integers: no correction needed
    assert np.array_equal(q, ints)


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("k", [0, 3, 6, 9])
def test_arbitrary_floats_bitwise(seed, k):
    rng = np.random.default_rng(100 + seed)
    parts = [
        rng.normal(0, 3, 2000),                                   # full-precision noise
        np.round(rng.normal(0, 3, 2000), 5) - np.round(rng.normal(0, 1, 2000), 5),   # arithmetic on decimals
        np.round(rng.normal(0, 3, 2000), 3) * 0.25,
        -np.abs(np.round(rng.normal(0, 1e4, 2000), 4)),           # negative values
        rng.normal(0, 1, 500) * 10.0 ** rng.integers(-300, 300, 500),                # huge / tiny magnitudes
        SPECIALS, np.array([NAN_PAYLOAD, -NAN_PAYLOAD]),
    ]
    v = np.concatenate(parts)
    rng.shuffle(v)
    p = {"codec": "decimal", "exp": k}
    _roundtrip(v, p)
    _parquet_roundtrip(v, p)
    # decoding into a strided view (a column of an (n, 3) array)
    packed, m, ev = fc.encode(v, p)
    out = np.full((len(v), 3), 7.0)
    fc.decode(packed, p, m if m.any() else None, ev, out=out[:, 1])
    assert np.array_equal(_bits(out[:, 1]), _bits(v)) and (out[:, [0, 2]] == 7.0).all()


def test_specials_are_exceptions():
    p = {"codec": "decimal", "exp": 6}
    q, d, m = _roundtrip(SPECIALS, p)
    assert m[np.isnan(SPECIALS) | np.isinf(SPECIALS)].all()
    neg0 = (SPECIALS == 0) & np.signbit(SPECIALS)
    assert m[neg0].all()                         # -0.0 kept exactly
    assert not m[SPECIALS == 0.3].any()          # a plain decimal is not an exception
    _parquet_roundtrip(SPECIALS, p)


def test_large_values_go_to_exceptions():
    v = np.array([1.5, 3e3, 2.2e3, 5e12, -5e12, 1e14])
    p = {"codec": "decimal", "exp": 1}
    q, d, m = _roundtrip(v, p)
    assert m.tolist() == [False, False, False, False, False, True]   # |q| >= 2**47


def test_point_one_plus_point_two():
    v = np.array([0.1 + 0.2, 0.3, 0.1, 0.2] * 10)
    p = {"codec": "decimal", "exp": 1}
    q, d, m = _roundtrip(v, p)
    assert d[0] == 1 and d[1] == 0 and not m.any()   # 0.30000000000000004 = 0.3 + 1 ulp


def test_plan_choices():
    rng = np.random.default_rng(0)
    dec = np.round(rng.normal(0, 50, 100_000), 4)
    assert fc.plan(dec) == {"codec": "decimal", "exp": 4, "dictionary": False}    # distinct values
    rep = np.repeat(np.round(rng.normal(0, 50, 2000), 4), 50)
    rng.shuffle(rep)
    assert fc.plan(rep) == {"codec": "decimal", "exp": 4, "dictionary": True}      # repeated values
    assert fc.plan(np.round(rng.normal(0, 3, 100_000), 5) - np.round(rng.normal(0, 1, 100_000), 5))["exp"] == 5
    assert fc.plan(rng.normal(0, 1, 100_000)) is None            # full precision: nothing fits
    assert fc.plan(np.zeros(0)) is None
    assert fc.plan(np.full(100, np.nan)) is None
    assert fc.plan(np.arange(10, dtype=np.int64)) is None         # not float64


def test_decode_into_buffer():
    v = np.round(np.random.default_rng(1).normal(0, 1, 1000), 3)
    p = {"codec": "decimal", "exp": 3}
    packed, m, ev = fc.encode(v, p)
    out = np.empty(1000)
    res = fc.decode(packed, p, None, None, out=out)
    assert res is out and np.array_equal(_bits(out), _bits(v))
