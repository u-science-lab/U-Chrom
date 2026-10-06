"""Downloading: retries for throttling servers, md5 checks, members streamed out of archives."""

from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def download(url: str, dest: Path, description: str = "", size_mb: float = 0, tries: int = 7,
             verbose: bool = True) -> Path:
    """Fetch ``url`` to ``dest`` (via ``dest.part``; skipped when ``dest`` exists).  A refused / throttled
    request (NCBI answers 403 / 429 / 503 when hit too often) is retried after 30 s, 60 s, 120 s, ..."""
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    if verbose:
        print(f"[pull] {description or dest.name} (~{size_mb:g} MB) -> {dest}", flush=True)
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "u-chrom datasets"})
            with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as out:
                while chunk := r.read(1 << 22):
                    out.write(chunk)
            tmp.rename(dest)
            return dest
        except Exception as exc:
            if tmp.exists():
                tmp.unlink()
            retry = (isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 429, 500, 502, 503, 504)) or \
                isinstance(exc, (urllib.error.URLError, ConnectionError, TimeoutError))
            if not retry or k == tries - 1:
                print(f"[fail] {dest.name}: {exc}", file=sys.stderr, flush=True)
                raise
            wait = 30 * 2 ** k
            print(f"[wait] {dest.name}: {exc}; retry in {wait} s", file=sys.stderr, flush=True)
            time.sleep(wait)
    return dest


def extract_member(url: str, member_suffix: str, dest: Path, verbose: bool = True) -> Path:
    """Stream a .tar.gz and write only the member whose path ends with ``member_suffix``."""
    import shutil
    import tarfile

    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if verbose:
        print(f"[pull] {member_suffix} streamed out of {url} -> {dest}", flush=True)
    with urllib.request.urlopen(url) as resp, tarfile.open(fileobj=resp, mode="r|gz") as tf:
        for m in tf:
            if m.isfile() and m.name.endswith(member_suffix):
                tmp = dest.with_suffix(dest.suffix + ".part")
                with tf.extractfile(m) as src, open(tmp, "wb") as out:
                    shutil.copyfileobj(src, out)
                tmp.rename(dest)
                return dest
    raise FileNotFoundError(f"{member_suffix} not found in {url}")


def extract_many(url: str, pattern: str, dest_dir: Path, verbose: bool = True) -> Path:
    """Stream a .tar.gz once; write every file member whose name matches ``pattern`` (regex search) to
    ``dest_dir/<basename>`` and the archive's member list (size, name) to ``dest_dir/_members.txt``."""
    import re
    import shutil
    import tarfile

    listing = dest_dir / "_members.txt"
    if listing.exists():
        return dest_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    rx = re.compile(pattern)
    if verbose:
        print(f"[pull] members matching {pattern!r} streamed out of {url} -> {dest_dir}", flush=True)
    names = []
    with urllib.request.urlopen(url) as resp, tarfile.open(fileobj=resp, mode="r|gz") as tf:
        for m in tf:
            names.append(f"{m.size}\t{m.name}")
            if m.isfile() and rx.search(m.name):
                dest = dest_dir / Path(m.name).name
                tmp = dest.with_suffix(dest.suffix + ".part")
                with tf.extractfile(m) as src, open(tmp, "wb") as out:
                    shutil.copyfileobj(src, out)
                tmp.rename(dest)
    tmp = listing.with_suffix(".part")
    tmp.write_text("\n".join(names) + "\n")
    tmp.rename(listing)
    return dest_dir


def md5(path: Path) -> str:
    import hashlib

    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()
