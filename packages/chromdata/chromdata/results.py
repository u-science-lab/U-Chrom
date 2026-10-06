"""Typed, provenance-tracked analysis results — ``cd.results``.

``cd.results`` is a :class:`ResultsStore`: a ``MutableMapping`` from a
result key (``"tads.arcfish"``, ``"loops.axiswise_f"``, …) to a
:class:`ResultRecord`.  Mapping access returns the *value*, so code
written against the 1.x plain ``dict`` keeps working::

    cd.results["tads.arcfish"]            # -> DataFrame (the value)
    cd.results.record("tads.arcfish")     # -> ResultRecord (value + provenance)
    cd.results["my_table"] = df           # plain assignment: record without provenance

Analysis functions store their output with :meth:`ResultsStore.set`,
passing the producing function, its parameters and its inputs.

Serialisation contract
----------------------
Every record kind has a writer and a reader in :mod:`chromdata.cdata`.
Assigning a value that cannot be written raises :class:`TypeError`
**at assignment time** (not later, in ``write()``):

========== ==========================================================
kind       value
========== ==========================================================
table      ``pandas.DataFrame`` or ``pandas.Series``
intervals  ``pandas.DataFrame`` of genomic intervals (TADs, loops, …)
array      ``numpy.ndarray`` (not object dtype)
mapping    ``dict`` whose leaves are any of the value types here
scalar     JSON-compatible scalar or list / tuple (str, int, float,
           bool, None)
========== ==========================================================
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, MutableMapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import numpy as np
import pandas as pd

RESULT_KINDS = ("table", "intervals", "array", "mapping", "scalar")


def _uchrom_version() -> str:
    from ._version import producer_version
    return producer_version()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def infer_kind(value: Any) -> str:
    """Record kind for ``value`` (``intervals`` is never inferred)."""
    if isinstance(value, (pd.DataFrame, pd.Series)):
        return "table"
    if isinstance(value, np.ndarray):
        return "array"
    if isinstance(value, Mapping):
        return "mapping"
    return "scalar"


def validate_value(value: Any, where: str = "value") -> None:
    """Raise ``TypeError`` if ``value`` cannot be written to a ChromData store."""
    if isinstance(value, (pd.DataFrame, pd.Series)):
        return
    if isinstance(value, np.ndarray):
        if value.dtype == object:
            raise TypeError(
                f"{where}: object-dtype arrays cannot be stored in a ChromData store; "
                f"convert to a numeric/string dtype or a list first."
            )
        return
    if isinstance(value, Mapping):
        for k, v in value.items():
            k = str(k)
            if "/" in k or k in ("", "."):
                raise ValueError(f"{where}: nested keys must be non-empty and contain no '/': {k!r}")
            validate_value(v, f"{where}[{k!r}]")
        return
    try:
        json.dumps(jsonable(value), allow_nan=True)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"{where}: cannot store a value of type {type(value).__name__} in "
            f"cd.results. Supported: DataFrame, Series, ndarray, dict, and "
            f"JSON-compatible scalars / lists."
        ) from exc


def jsonable(value: Any) -> Any:
    """Normalise numpy scalars / nested containers for ``json.dumps``."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    return value


def params_jsonable(value: Any) -> Any:
    """Like :func:`jsonable` but lenient — for params / inputs metadata.

    Dataclasses become dicts, arrays become lists, paths become strings
    and anything else unknown becomes its ``str``.  The result always
    serialises with ``json.dumps``.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: params_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, np.ndarray):
        return [params_jsonable(v) for v in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): params_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, pd.Index)):
        return [params_jsonable(v) for v in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


@dataclasses.dataclass
class ResultRecord:
    """One analysis output plus its provenance.

    Attributes
    ----------
    kind : str
        ``"table" | "intervals" | "array" | "mapping" | "scalar"``.
    value : Any
        The result itself (what ``cd.results[key]`` returns).
    params : dict
        The tuning parameters (``asdict(params)`` of the caller's
        ``*Params`` dataclass).  JSON-compatible.
    function : str or None
        Fully qualified name of the producing function, e.g.
        ``"uchrom.strc.tad.call_tads_by_pval"``.  ``None`` for values
        assigned directly.
    uchrom_version : str
        Package version that produced the value.
    inputs : dict
        What the function read, e.g. ``{"chrom": ["chr1"], "n_traces": 900}``.
    created_utc : str
        ISO-8601 UTC timestamp.
    """

    kind: str
    value: Any
    params: Dict[str, Any] = dataclasses.field(default_factory=dict)
    function: Optional[str] = None
    uchrom_version: str = dataclasses.field(default_factory=_uchrom_version)
    inputs: Dict[str, Any] = dataclasses.field(default_factory=dict)
    created_utc: str = dataclasses.field(default_factory=_utc_now)

    def __post_init__(self):
        if self.kind not in RESULT_KINDS:
            raise ValueError(f"unknown result kind {self.kind!r}; expected one of {RESULT_KINDS}")
        if self.kind == "intervals" and not isinstance(self.value, pd.DataFrame):
            raise TypeError("kind='intervals' requires a DataFrame value")
        validate_value(self.value, "ResultRecord.value")
        self.params = params_jsonable(dict(self.params or {}))
        self.inputs = params_jsonable(dict(self.inputs or {}))

    @property
    def provenance(self) -> dict:
        """Everything except the value, as a JSON-compatible dict."""
        return {
            "kind": self.kind,
            "function": self.function,
            "params": self.params,
            "inputs": self.inputs,
            "uchrom_version": self.uchrom_version,
            "created_utc": self.created_utc,
        }


class ResultsStore(MutableMapping):
    """``MutableMapping[str, value]`` backed by :class:`ResultRecord` s.

    Plain item assignment (``store[key] = value``) creates a record with
    an inferred kind and no provenance; analysis functions use
    :meth:`set`.  Assigning a :class:`ResultRecord` stores it as is.
    """

    def __init__(self, data: Optional[Mapping[str, Any]] = None):
        self._records: Dict[str, ResultRecord] = {}
        if data is not None:
            items = data._records.items() if isinstance(data, ResultsStore) else data.items()
            for key, value in items:
                self[key] = value

    @classmethod
    def coerce(cls, data: Any) -> "ResultsStore":
        """Return ``data`` if it is already a store, else wrap it."""
        if isinstance(data, ResultsStore):
            return data
        if data is None:
            return cls()
        if not isinstance(data, Mapping):
            raise TypeError(f"results must be a mapping, got {type(data).__name__}")
        return cls(data)

    # -- mapping protocol ------------------------------------------------

    @staticmethod
    def _check_key(key: Any) -> str:
        key = str(key)
        if "/" in key or key in ("", "."):
            raise ValueError(f"result keys must be non-empty and contain no '/': {key!r}")
        return key

    def __getitem__(self, key: str) -> Any:
        return self._records[str(key)].value

    def __setitem__(self, key: str, value: Any) -> None:
        key = self._check_key(key)
        if isinstance(value, ResultRecord):
            record = value
        else:
            validate_value(value, f"results[{key!r}]")
            record = ResultRecord(kind=infer_kind(value), value=value)
        self._records[key] = record

    def __delitem__(self, key: str) -> None:
        del self._records[str(key)]

    def __iter__(self) -> Iterator[str]:
        return iter(self._records)

    def __len__(self) -> int:
        return len(self._records)

    def __contains__(self, key: object) -> bool:
        return str(key) in self._records

    def __repr__(self) -> str:
        inner = ", ".join(f"{k!r}: <{r.kind}>" for k, r in self._records.items())
        return f"ResultsStore({{{inner}}})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ResultsStore):
            return self._records.keys() == other._records.keys() and all(
                _values_equal(self[k], other[k]) for k in self._records
            )
        if isinstance(other, Mapping):
            return set(self.keys()) == set(map(str, other.keys())) and all(
                _values_equal(self[k], other[k]) for k in other
            )
        return NotImplemented

    # -- records ---------------------------------------------------------

    def record(self, key: str) -> ResultRecord:
        """The full :class:`ResultRecord` stored under ``key``."""
        return self._records[str(key)]

    def records(self) -> Dict[str, ResultRecord]:
        """A shallow copy of ``key -> ResultRecord``."""
        return dict(self._records)

    def set(
        self,
        key: str,
        value: Any,
        *,
        kind: Optional[str] = None,
        function: Optional[str] = None,
        params: Any = None,
        inputs: Optional[Mapping[str, Any]] = None,
    ) -> ResultRecord:
        """Store ``value`` with provenance and return the record.

        ``params`` may be a ``*Params`` dataclass or a dict.
        """
        key = self._check_key(key)
        if dataclasses.is_dataclass(params) and not isinstance(params, type):
            params = params_jsonable(params)
        validate_value(value, f"results[{key!r}]")
        record = ResultRecord(
            kind=kind or infer_kind(value),
            value=value,
            params=dict(params or {}),
            function=function,
            inputs=dict(inputs or {}),
        )
        self._records[key] = record
        return record

    def to_dict(self) -> Dict[str, Any]:
        """Plain ``key -> value`` dict (the 1.x representation)."""
        return {k: r.value for k, r in self._records.items()}


def _values_equal(a: Any, b: Any) -> bool:
    if isinstance(a, (pd.DataFrame, pd.Series)):
        return isinstance(b, type(a)) and a.equals(b)
    if isinstance(a, np.ndarray):
        return isinstance(b, np.ndarray) and np.array_equal(a, b, equal_nan=a.dtype.kind == "f")
    if isinstance(a, Mapping):
        return isinstance(b, Mapping) and set(a) == set(b) and all(_values_equal(a[k], b[k]) for k in a)
    try:
        return bool(a == b)
    except Exception:
        return False


__all__ = [
    "RESULT_KINDS",
    "ResultRecord",
    "ResultsStore",
    "infer_kind",
    "validate_value",
]
