"""Lossless decimal encoding of float64 columns (``.chromdata.zarr`` 2.2).

Measured values usually come from text with a few decimals (``1.23456``)
or from simple arithmetic on such values (a z-score, a pixel size times a
position), so a float64 column is mostly *nearly* a scaled integer: for
the right exponent ``k``, ``q = round(v * 10**k)`` gives back ``v`` as
``q / 10**k`` — exactly, since IEEE division is correctly rounded and
``q`` and ``10**k`` are exact doubles — or within a few units in the last
place (ulp) for the arithmetic results.

A column encoded with :func:`encode` is stored as two columns:

* ``<name>``      int64 ``q * 2**16 + (d + 2**15)``, where ``d`` is the ulp
  difference ``bits(v) - bits(q / 10**k)`` (``-2**15 <= d < 2**15``; 0
  for most rows).  ``(q, d)`` is a function of ``v``, so the column has as
  many distinct values as the floats and Parquet dictionary-encodes it as
  well, but its values are small integers that compress (the raw float
  bits do not);
* ``<name>#exc``  float64, null except for the rows that do not fit
  (NaN / ±inf, -0.0, ``|q| >= 2**47``, or an ulp difference out of
  range) — those keep their exact float64 value.

:func:`decode` rebuilds ``q / 10**k``, adds ``d`` to the bit patterns and
puts the exceptions back: the result is **bitwise identical** to the input
(every NaN payload included).  The writer checks this on every chunk it
writes.

:func:`plan` picks ``k`` on a sample (the writer passes the first rows in
stored order) and keeps the plain float64 column when the encoding would
not pay: fewer than 99 % of the sampled values fit, or the sample does not
store (as a Parquet column chunk) at least 2 % smaller.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

#: suffix of the exception column of an encoded column
EXC_SUFFIX = "#exc"
CODEC = "decimal"
MAX_EXP = 9
_D = 1 << 15              # ulp differences in [-2**15, 2**15)
_SHIFT = 16
_QMAX = 2 ** 47           # q * 2**16 must stay inside int64
_SAMPLE = 1 << 16


def _sample(v: np.ndarray, n: int = _SAMPLE) -> np.ndarray:
    if len(v) <= n:
        return v
    runs = max(1, n // 1024)
    starts = np.linspace(0, len(v) - 1024, runs).astype(np.int64)
    return np.concatenate([v[s:s + 1024] for s in starts])


def plan(values, *, max_exp: int = MAX_EXP, min_fit: float = 0.99,
         min_gain: float = 0.02) -> Optional[Dict[str, Any]]:
    """Encoding plan of a float64 column, or ``None`` to store it as is.

    Returns ``{"codec": "decimal", "exp": k, "dictionary": bool}``
    (``dictionary``: whether the packed column is dictionary-encoded).
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
        inside = np.abs(r) < _QMAX              # (inf / NaN compare False)
        r = np.where(inside, r, 0.0)
        d = bits - (r / s).view(np.int64)
        good = inside & (d >= -_D) & (d < _D)
        fit = float(good.mean())
        if fit > best[1] + 1e-12:
            best = (k, fit)
        if fit == 1.0 and not d.any():
            break
    k, fit = best
    if k is None or fit < min_fit:
        return None
    p = {"codec": CODEC, "exp": int(k)}
    # does it pay?  The stored sizes, as Parquet column chunks (zstd) —
    # raw compressed bytes mispredict it.  Repeated values favour a
    # dictionary for the packed integers, distinct ones plain pages.
    packed, exc = encode_arrow(x, p, check=False)
    n_exc = len(exc) - exc.null_count
    with_dict = _parquet_size(packed, dictionary=True)
    plain = _parquet_size(packed, dictionary=False)
    p["dictionary"] = bool(with_dict < plain)
    if min(with_dict, plain) + 8 * n_exc > (1.0 - min_gain) * _parquet_size(x, dictionary=False):
        return None
    return p


def _parquet_size(array, *, dictionary: bool) -> int:
    import io

    import pyarrow as pa
    import pyarrow.parquet as pq

    t = pa.table({"c": pa.array(array) if isinstance(array, np.ndarray) else array})
    buf = io.BytesIO()
    pq.write_table(t, buf, compression="zstd", compression_level=3, use_dictionary=dictionary,
                   write_statistics=False)
    return len(buf.getvalue())


def encode(values, p: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(packed int64, exception mask, exception values)`` of a float64 column."""
    v = np.ascontiguousarray(values, dtype=np.float64)
    s = 10.0 ** int(p["exp"])
    fin = np.isfinite(v)
    with np.errstate(over="ignore", invalid="ignore"):
        r = np.round(np.where(fin, v, 0.0) * s)
    big = np.abs(r) >= _QMAX
    if big.any():
        r[big] = 0.0
    q = r.astype(np.int64)
    d = v.view(np.int64) - (q.astype(np.float64) / s).view(np.int64)
    exc = ~fin | big | (d < -_D) | (d >= _D) | ((v == 0) & np.signbit(v))
    if exc.any():
        q[exc] = 0
        d[exc] = 0
    packed = (q << _SHIFT) + (d + _D)
    return packed, exc, v[exc]


def decode(packed, p: Dict[str, Any], exc_mask=None, exc_values=None,
           out: Optional[np.ndarray] = None) -> np.ndarray:
    """Float64 values of an encoded column (bitwise the encoded input).

    ``packed``: int64 numpy array; ``exc_mask`` a boolean array (or ``None``
    when there are no exceptions) with ``exc_values`` the values of its
    ``True`` rows; ``out`` an optional float64 buffer (or view) to fill."""
    s = 10.0 ** int(p["exp"])
    packed = np.asarray(packed, dtype=np.int64)
    contiguous = out is None or out.flags.c_contiguous
    res = out if (out is not None and contiguous) else np.empty(len(packed), dtype=np.float64)
    tmp, _ = _scratch(len(packed)) if len(packed) <= _SCRATCH_MAX else (np.empty(len(packed), np.int64), None)
    np.right_shift(packed, _SHIFT, out=tmp)              # q (arithmetic shift: floor)
    np.divide(tmp, s, out=res, casting="unsafe")
    np.bitwise_and(packed, (1 << _SHIFT) - 1, out=tmp)
    tmp -= _D                                            # d
    o = res.view(np.int64)
    o += tmp
    if exc_mask is not None:
        res[exc_mask] = exc_values
    if out is not None and not contiguous:               # a strided view (a coordinate column)
        out[:] = res
        return out
    return res


_SCRATCH = __import__("threading").local()
_SCRATCH_MAX = 1 << 20


def _scratch(m: int) -> Tuple[np.ndarray, np.ndarray]:
    """Two reusable int64 work arrays of at least ``m`` rows (per thread: no
    allocation, and no page faults, per call)."""
    buf = getattr(_SCRATCH, "buf", None)
    if buf is None or buf.shape[1] < m:
        buf = _SCRATCH.buf = np.empty((2, max(m, 1 << 16)), dtype=np.int64)
    return buf[0, :m], buf[1, :m]


def decode_inplace(buf: np.ndarray, p: Dict[str, Any], start: int = 0, stop: Optional[int] = None) -> None:
    """Decode ``buf[start:stop]`` in place: a float64 array (or strided
    view) whose memory holds the packed int64 values."""
    s = 10.0 ** int(p["exp"])
    seg = buf[start:stop]
    packed = seg.view(np.int64)
    q, d = _scratch(len(seg))
    np.right_shift(packed, _SHIFT, out=q)
    np.bitwise_and(packed, (1 << _SHIFT) - 1, out=d)
    d -= _D
    np.divide(q, s, out=seg, casting="unsafe")
    packed += d


def encode_arrow(values, p: Dict[str, Any], *, check: bool = True):
    """The Arrow arrays ``(packed, exc)`` of a float64 column; ``check``
    decodes them again and raises if a value would change."""
    import pyarrow as pa

    v = np.ascontiguousarray(values, dtype=np.float64)
    packed, m, ev = encode(v, p)
    if check:
        back = decode(packed, p, m if m.any() else None, ev)
        if not np.array_equal(back.view(np.int64), v.view(np.int64)):  # pragma: no cover - a bug
            raise AssertionError("decimal float encoding is not lossless for this column")
    if m.any():
        full = np.zeros(len(v), dtype=np.float64)
        full[m] = ev
        exc = pa.array(full, mask=~m)
    else:
        exc = pa.nulls(len(v), type=pa.float64())
    return pa.array(packed), exc


def decode_arrow(packed, exc, p: Dict[str, Any], out: Optional[np.ndarray] = None) -> np.ndarray:
    """:func:`decode` of Arrow (chunked) arrays (``exc`` may be ``None``),
    chunk by chunk into ``out`` (no concatenation of the chunks)."""
    import pyarrow as pa

    n = len(packed)
    if out is None:
        out = np.empty(n, dtype=np.float64)
    chunks = packed.chunks if isinstance(packed, pa.ChunkedArray) else [packed]
    pos = 0
    for ch in chunks:
        m = len(ch)
        if m:
            decode(ch.to_numpy(zero_copy_only=False), p, out=out[pos:pos + m])
        pos += m
    if exc is not None and exc.null_count < len(exc):
        import pyarrow.compute as pc
        valid = _numpy(pc.is_valid(exc))
        out[valid] = _numpy(pc.fill_null(exc, 0.0))[valid]
    return out


def _numpy(a) -> np.ndarray:
    import pyarrow as pa

    if isinstance(a, pa.ChunkedArray):
        a = a.chunk(0) if a.num_chunks == 1 else a.combine_chunks()
    return a.to_numpy(zero_copy_only=False)


__all__ = ["CODEC", "EXC_SUFFIX", "decode", "decode_arrow", "decode_inplace", "encode", "encode_arrow", "plan"]
