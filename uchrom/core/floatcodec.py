"""Lossless decimal encoding of float64 columns (``.chromdata.zarr`` 2.2).

Measured values usually come from text with a few decimals (``1.23456``)
or from simple arithmetic on such values (a z-score, a pixel size times a
position), so a float64 column is mostly *nearly* a scaled integer: for
the right exponent ``k``, ``q = round(v * 10**k)`` gives back ``v`` as
``q / 10**k`` — exactly, since IEEE division is correctly rounded and
``q`` and ``10**k`` are exact doubles — or within a few units in the last
place (ulp) for the arithmetic results.

A column encoded with :func:`encode` is stored as three columns:

* ``<name>``      int32 / int64 ``q``;
* ``<name>#ulp``  int16: ``bits(v) - bits(q / 10**k)`` (0 for most rows);
* ``<name>#exc``  float64, null except for the rows that do not fit
  (NaN / ±inf, -0.0, ``|q| >= 2**53``, an int32 overflow, or an ulp
  difference beyond int16) — those keep their exact float64 value.

:func:`decode` rebuilds ``q / 10**k``, adds the ulp differences to the
bit patterns and puts the exceptions back: the result is **bitwise
identical** to the input (every NaN payload included).  The writer checks
this on every chunk it writes.

:func:`plan` picks ``k`` on a sample and keeps the plain float64 column
when the encoding would not pay (fewer than 99 % of the sampled values
fit, or the sample does not compress at least 5 % smaller).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

#: suffixes of the helper columns of an encoded column
ULP_SUFFIX = "#ulp"
EXC_SUFFIX = "#exc"
CODEC = "decimal"
MAX_EXP = 9
_I16 = 32767
_EXACT = 2 ** 53
_SAMPLE = 1 << 16


def _sample(v: np.ndarray, n: int = _SAMPLE) -> np.ndarray:
    if len(v) <= n:
        return v
    # evenly spaced runs of 1,024 rows (neighbouring rows are what the
    # compressor sees)
    runs = max(1, n // 1024)
    starts = np.linspace(0, len(v) - 1024, runs).astype(np.int64)
    return np.concatenate([v[s:s + 1024] for s in starts])


def _zstd_size(data: bytes) -> int:
    import pyarrow as pa
    return len(pa.compress(data, codec="zstd", asbytes=True))


def plan(values, *, max_exp: int = MAX_EXP, min_fit: float = 0.99,
         min_gain: float = 0.05) -> Optional[Dict[str, Any]]:
    """Encoding plan of a float64 column, or ``None`` to store it as is.

    Returns ``{"codec": "decimal", "exp": k, "int": "int32" | "int64"}``.
    """
    v = np.asarray(values)
    if v.dtype != np.float64 or v.ndim != 1 or len(v) == 0:
        return None
    x = _sample(v)
    x = x[np.isfinite(x)]
    if not len(x):
        return None
    bits = x.view(np.int64)
    best: Tuple[Optional[int], float] = (None, -1.0)
    for k in range(max_exp + 1):
        s = 10.0 ** k
        with np.errstate(over="ignore", invalid="ignore"):
            r = np.round(x * s)
        inside = np.abs(r) < _EXACT              # (inf / NaN compare False)
        r = np.where(inside, r, 0.0)
        d = bits - (r / s).view(np.int64)
        good = inside & (np.abs(d) <= _I16)
        fit = float(good.mean())
        if fit > best[1] + 1e-12:
            best = (k, fit)
        if fit == 1.0 and not d.any():
            break
    k, fit = best
    if k is None or fit < min_fit:
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        q = np.round(x * 10.0 ** k)
    q = q[np.abs(q) < _EXACT]
    qmax = float(np.abs(q).max()) if len(q) else 0.0
    int_type = "int32" if qmax * 4 < 2 ** 31 else "int64"
    p = {"codec": CODEC, "exp": int(k), "int": int_type}
    enc_q, ulp, exc, _ = encode(x, p)
    plain = _zstd_size(x.tobytes())
    packed = _zstd_size(enc_q.tobytes()) + _zstd_size(ulp.tobytes()) + 8 * int(exc.sum())
    if packed > (1.0 - min_gain) * plain:
        return None
    return p


def encode(values, p: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """``(q, ulp, exception mask, exception values)`` of a float64 column."""
    v = np.ascontiguousarray(values, dtype=np.float64)
    s = 10.0 ** int(p["exp"])
    fin = np.isfinite(v)
    with np.errstate(over="ignore", invalid="ignore"):
        r = np.round(np.where(fin, v, 0.0) * s)
    big = np.abs(r) >= _EXACT
    if big.any():
        r[big] = 0.0
    q = r.astype(np.int64)
    d = v.view(np.int64) - (q.astype(np.float64) / s).view(np.int64)
    exc = ~fin | big | (np.abs(d) > _I16) | ((v == 0) & np.signbit(v))
    if p["int"] == "int32":
        exc |= (q < -(2 ** 31 - 1)) | (q > 2 ** 31 - 1)
    if exc.any():
        q[exc] = 0
        d[exc] = 0
    return q.astype(np.dtype(p["int"])), d.astype(np.int16), exc, v[exc]


def decode(q, p: Dict[str, Any], ulp=None, exc_mask=None, exc_values=None,
           out: Optional[np.ndarray] = None) -> np.ndarray:
    """Float64 values of an encoded column (bitwise the encoded input).

    ``q`` / ``ulp``: numpy arrays; ``exc_mask`` a boolean array (or
    ``None`` when there are no exceptions) with ``exc_values`` the values
    of its ``True`` rows; ``out`` an optional float64 buffer to fill."""
    s = 10.0 ** int(p["exp"])
    q = np.asarray(q)
    if out is None:
        out = np.empty(len(q), dtype=np.float64)
    np.divide(q, s, out=out, dtype=np.float64, casting="unsafe")
    if ulp is not None:
        o = out.view(np.int64)
        np.add(o, ulp, out=o, casting="unsafe")
    if exc_mask is not None:
        out[exc_mask] = exc_values
    return out


def encode_arrow(values, p: Dict[str, Any], *, check: bool = True):
    """The three Arrow arrays ``(q, ulp, exc)`` of a float64 column;
    ``check`` decodes them again and raises if a value would change."""
    import pyarrow as pa

    v = np.ascontiguousarray(values, dtype=np.float64)
    q, d, m, ev = encode(v, p)
    if check:
        back = decode(q, p, d, m if m.any() else None, ev)
        if not np.array_equal(back.view(np.int64), v.view(np.int64)):  # pragma: no cover - a bug
            raise AssertionError("decimal float encoding is not lossless for this column")
    if m.any():
        full = np.zeros(len(v), dtype=np.float64)
        full[m] = ev
        exc = pa.array(full, mask=~m)
    else:
        exc = pa.nulls(len(v), type=pa.float64())
    return pa.array(q), pa.array(d), exc


def decode_arrow(q, ulp, exc, p: Dict[str, Any], out: Optional[np.ndarray] = None) -> np.ndarray:
    """:func:`decode` of Arrow (chunked) arrays."""
    qn = _numpy(q)
    un = _numpy(ulp) if ulp is not None else None
    mask = values = None
    if exc is not None and exc.null_count < len(exc):
        import pyarrow.compute as pc
        valid = _numpy(pc.is_valid(exc))
        mask = valid
        values = _numpy(pc.fill_null(exc, 0.0))[valid]
    return decode(qn, p, un, mask, values, out=out)


def _numpy(a) -> np.ndarray:
    import pyarrow as pa

    if isinstance(a, pa.ChunkedArray):
        if a.num_chunks == 1:
            a = a.chunk(0)
        else:
            a = a.combine_chunks()
    return a.to_numpy(zero_copy_only=False)


def physical_columns(name: str) -> Tuple[str, str, str]:
    return name, name + ULP_SUFFIX, name + EXC_SUFFIX


__all__ = ["CODEC", "EXC_SUFFIX", "ULP_SUFFIX", "decode", "decode_arrow", "encode", "encode_arrow",
           "physical_columns", "plan"]
