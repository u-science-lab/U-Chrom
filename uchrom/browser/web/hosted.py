"""Hosted mode of the web browser: the server of a public atlas.

A local server trusts its user: it lists the machine's folders, opens any path and keeps every opened dataset in
one list.  A public one cannot.  In hosted mode (``--hosted``):

- every visitor (a cookie) has **their own** list of datasets, so nobody sees what somebody else opened;
- only stores **inside the atlas** can be opened (``allowed_prefixes``, normally the atlas root URL): no local
  paths, no other URLs (the server would fetch whatever it is told to otherwise);
- the server's folders cannot be listed (``/api/files`` is off);
- the memory a visitor can hold is bounded: at most ``max_datasets`` datasets (the oldest is closed to make room),
  at most ``max_sessions`` visitors at a time (the one idle longest is dropped), idle sessions expire after ``ttl``
  seconds, and a pseudo-bulk map sums at most ``max_pseudobulk_cells`` cells.
"""

from __future__ import annotations

import contextvars
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Sequence

from .data import Dataset, DatasetStore

COOKIE = "uchrom_session"
_current: contextvars.ContextVar[str] = contextvars.ContextVar("uchrom_session", default="")


@dataclass
class HostedConfig:
    allowed_prefixes: Sequence[str] = field(default_factory=list)
    max_datasets: int = 4
    max_sessions: int = 64
    ttl: float = 1800.0
    max_pseudobulk_cells: int = 5000


def new_session_id() -> str:
    return secrets.token_urlsafe(18)


def set_session(session_id: str):
    """Make ``session_id`` the visitor of the current request (returns the token to reset it)."""
    return _current.set(session_id)


def reset_session(token) -> None:
    _current.reset(token)


class SessionStores:
    """The ``DatasetStore`` interface the server uses (``get`` / ``list`` / ``load`` / ``remove``), one store per
    visitor, chosen by the session of the current request."""

    def __init__(self, cfg: HostedConfig, factory: Callable[[], DatasetStore] = DatasetStore,
                 clock: Callable[[], float] = time.time):
        self.cfg, self._factory, self._clock = cfg, factory, clock
        self._sessions: "OrderedDict[str, List[Any]]" = OrderedDict()    # id -> [store, last used]
        self._lock = threading.Lock()

    # -- sessions ------------------------------------------------------------

    def _store(self) -> DatasetStore:
        sid = _current.get()
        if not sid:
            raise PermissionError("no session")
        now = self._clock()
        with self._lock:
            for k in [k for k, (_, t) in self._sessions.items() if now - t > self.cfg.ttl]:
                del self._sessions[k]
            rec = self._sessions.get(sid)
            if rec is None:
                while len(self._sessions) >= self.cfg.max_sessions:
                    self._sessions.popitem(last=False)                  # the one idle longest
                rec = self._sessions[sid] = [self._factory(), now]
            rec[1] = now
            self._sessions.move_to_end(sid)
            return rec[0]

    @property
    def n_sessions(self) -> int:
        return len(self._sessions)

    # -- the DatasetStore interface ----------------------------------------------

    def allowed(self, path: str) -> bool:
        p = str(path).rstrip("/")
        if ".." in p.split("/"):
            return False
        return any(p.startswith(pre.rstrip("/") + "/") for pre in self.cfg.allowed_prefixes)

    def load(self, path) -> Dataset:
        if not self.allowed(path):
            raise PermissionError(f"only datasets of the atlas can be opened here ({', '.join(self.cfg.allowed_prefixes)})")
        store = self._store()
        while len(store.list()) >= self.cfg.max_datasets:               # make room: close the oldest
            store.remove(store.list()[0].id)
        return store.load(path)

    def get(self, dataset_id: str) -> Dataset:
        return self._store().get(dataset_id)

    def list(self):
        return self._store().list()

    def remove(self, dataset_id: str) -> None:
        self._store().remove(dataset_id)

    def add(self, *a, **kw):
        raise PermissionError("datasets cannot be added to a hosted server")
