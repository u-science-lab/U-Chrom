"""Stores on object storage / HTTP: ``s3://bucket/x.chromdata.zarr``, ``https://host/x.chromdata.zarr``.

``ChromData.read(url, backed=True)`` and the web browser open them through fsspec (install the
filesystem of the scheme: ``s3fs`` for ``s3://``, ``aiohttp`` for ``http(s)://``, ``gcsfs`` for
``gs://``).  Only the directory form (``.chromdata.zarr``) is read remotely, and only backed: the
metadata and the small tables are fetched when the store is opened, the spots / contact pixels as
range requests when a view needs them.  Extra arguments of the filesystem (credentials, anonymous
access) go to ``uchrom.settings`` / ``UCHROM_STORAGE_OPTIONS`` (a JSON object), or are read by
fsspec's own config (``~/.config/fsspec``).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Tuple


def is_url(path: Any) -> bool:
    """Whether ``path`` is a remote location (``scheme://``, other than ``file://``)."""
    return isinstance(path, str) and "://" in path and not path.startswith("file://")


def storage_options() -> Dict[str, Any]:
    raw = os.environ.get("UCHROM_STORAGE_OPTIONS")
    return json.loads(raw) if raw else {}


def filesystem(url: str) -> Tuple[Any, str]:
    """(synchronous fsspec filesystem, path inside it) of a URL."""
    import fsspec

    return fsspec.core.url_to_fs(url, **storage_options())


def zarr_store(url: str):
    """Read-only zarr store over a URL (the async filesystem is built or wrapped)."""
    import fsspec
    from zarr.storage import FsspecStore

    fs, root = fsspec.core.url_to_fs(url, asynchronous=True, **storage_options()) if _async_ok(url) else (None, None)
    if fs is None:
        from fsspec.implementations.asyn_wrapper import AsyncFileSystemWrapper

        sfs, root = filesystem(url)
        fs = AsyncFileSystemWrapper(sfs, asynchronous=True)
    return FsspecStore(fs, path=root, read_only=True)


def _async_ok(url: str) -> bool:
    import fsspec

    cls = fsspec.get_filesystem_class(url.split("://", 1)[0])
    return bool(getattr(cls, "async_impl", False))
