"""uchrom.datasets: the registry of original sources, the data directory, fetch with md5 checks (offline:
file:// URLs)."""

import hashlib

import pytest

import uchrom.datasets as ds
from uchrom.datasets import _sources


def test_every_source_names_its_files_and_urls():
    for name, entry in _sources.DATASETS.items():
        if name in ("tan2021_cortex", "hires2023", "unic2025"):     # lists read from GEO / a cell table
            continue
        paths = ds.files(name)
        assert paths, name
        for rel, url in ds._files(entry):
            assert url.startswith(("https://", "http://")), (name, url)
            assert not rel.startswith("/"), (name, rel)
        assert entry.get("description"), name


def test_data_dir_follows_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("UCHROM_DATA", str(tmp_path))
    assert ds.data_dir() == tmp_path
    assert ds.path("takei") == tmp_path / "4DNFIHF3JCBY.csv"
    monkeypatch.delenv("UCHROM_DATA")
    assert ds.data_dir().name == "uchrom"


def test_fetch_downloads_once_and_checks_md5(monkeypatch, tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("chr1\t0\t100\n")
    good = hashlib.md5(src.read_bytes()).hexdigest()
    monkeypatch.setitem(_sources.DATASETS, "toy", {"files": [("toy/a.txt", src.as_uri())], "md5": {"toy/a.txt": good},
                                                   "size_mb": 0, "description": "toy"})
    root = tmp_path / "data"
    assert ds.fetch("toy", root=root, verbose=False) == root / "toy" / "a.txt"
    src.write_text("changed")                                  # already there: not fetched again
    assert (root / "toy" / "a.txt").read_text() == "chr1\t0\t100\n"
    monkeypatch.setitem(_sources.DATASETS, "bad", {"files": [("bad/a.txt", src.as_uri())], "md5": {"bad/a.txt": good},
                                                   "size_mb": 0, "description": "bad"})
    with pytest.raises(IOError, match="md5"):
        ds.fetch("bad", root=root, verbose=False)


def test_unknown_dataset_names_the_known_ones():
    with pytest.raises(KeyError, match="takei"):
        ds.files("no_such_dataset")
