"""uchrom.datasets: the registry of original sources, the data directory, fetch with md5 checks (offline:
file:// URLs)."""

import hashlib
import io
import tarfile

import numpy as np
import pandas as pd
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


def test_fetch_builds_the_head_of_a_field_of_view(monkeypatch, tmp_path):
    rows = "cellID,x\n" + "".join(f"{c},{k}\n" for c in (1, 1, 2, 2, 3) for k in range(1))
    tar = tmp_path / "fovs.tar.gz"
    with tarfile.open(tar, "w:gz") as tf:
        data = rows.encode()
        info = tarfile.TarInfo("rep1/pos0.csv")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    side = tmp_path / "loci.csv"
    side.write_text("locus\n")
    files = [("fov/cells.csv", tar.as_uri()), ("fov/loci.csv", side.as_uri())]
    monkeypatch.setitem(_sources.DATASETS, "toy_fov", {
        "build": ("seqfish_fov_head", {"tarball": tar.as_uri(), "member": "rep1/pos0.csv", "rows": 4,
                                       "sidecars": [("loci.csv", side.as_uri())]}),
        "files": files, "size_mb": 0, "description": "toy"})
    root = tmp_path / "data"
    assert ds.fetch("toy_fov", root=root, verbose=False) == root / "fov"
    cells = pd.read_csv(root / "fov" / "cells.csv")
    assert cells["cellID"].tolist() == [1, 1]              # 4 rows read; cell 2 may be cut off: dropped
    assert (root / "fov" / "loci.csv").read_text() == "locus\n"


def test_load_builds_once_caches_and_rebuilds_on_a_new_loader_version(monkeypatch, tmp_path):
    from chromdata import ChromData
    from uchrom.datasets import _loaders

    calls = []

    def build(root, out):
        calls.append(out)
        spots = pd.DataFrame({"chrom": ["chr1", "chr1"], "start": [0, 100], "end": [100, 200], "trace_id": ["t", "t"]})
        return ChromData(np.arange(6, dtype=float).reshape(2, 3), spots, uns={"genome_assembly": "toy"})

    loader = _loaders.Loader(name="toy_cd", build=build, store="toy/toy.chromdata.zarr", description="toy")
    monkeypatch.setitem(_loaders.LOADERS, "toy_cd", loader)
    cd = ds.load("toy_cd", root=tmp_path)
    assert cd.n_spots == 2 and (tmp_path / "toy" / "toy.chromdata.zarr").exists()
    assert cd.uns["dataset"] == {"name": "toy_cd", "loader_version": 1, "sources": []}
    ds.load("toy_cd", root=tmp_path)
    assert len(calls) == 1                                      # read from the cache
    assert ds.load("toy_cd", root=tmp_path, backed=True).backed
    monkeypatch.setitem(_loaders.LOADERS, "toy_cd", _loaders.Loader(**{**loader.__dict__, "version": 2}))
    ds.load("toy_cd", root=tmp_path)
    assert len(calls) == 2                                      # a new loader version rebuilds
    assert ds.list_datasets().loc["toy_cd", "load"]


def test_load_names_what_it_knows(monkeypatch):
    def no_atlas(name, **kw):
        raise KeyError(name)

    monkeypatch.setattr(ds, "atlas", no_atlas)
    with pytest.raises(KeyError, match="kim2020_scihic"):
        ds.load("no_such_dataset")
