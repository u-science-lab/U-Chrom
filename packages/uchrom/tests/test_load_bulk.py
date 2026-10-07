"""Bulk Hi-C loaders (uchrom.datasets._load_bulk), offline: the map is a fixture cooler placed where fetch()
would build it."""

import shutil

import pytest

import uchrom.datasets as ds
from tests import FIXTURES

cooler = pytest.importorskip("cooler")


def test_rao2014_imr90_chr21_links_its_map(tmp_path):
    cool = tmp_path / "rao2014_imr90" / "IMR90_chr21_5kb_hg19.cool"     # what fetch() builds (here: a stand-in)
    cool.parent.mkdir()
    shutil.copy(FIXTURES / "K562_chr21_30kb.cool", cool)
    cd = ds.load("rao2014_imr90_chr21", root=tmp_path)
    assert cd.n_spots == 0 and cd.uns["dataset"]["name"] == "rao2014_imr90_chr21"
    rec = cd.uns["linked_cool"]["bulk"]
    assert rec["path"] == "IMR90_chr21_5kb_hg19.cool"                  # relative to the store's folder
    clr = cooler.Cooler(str(cool))
    assert rec["bin_size"] == clr.binsize and rec["n_contacts"] == int(clr.info["sum"]) and rec["chroms"] == ["chr21"]
    assert cd.linked_cool_path("bulk") == str(cool) and cd.validate_links() == []
    assert (tmp_path / "rao2014_imr90" / "rao2014_imr90_chr21.chromdata.zarr").is_dir()
    assert ds.list_datasets().loc["rao2014_imr90_chr21", "load"]

    from uchrom.fea import contact_matrix

    bins, M = contact_matrix(cd, chrom="chr21", balance=False)          # the methods start from it
    assert M.shape == (len(bins), len(bins)) and M.sum() > 0
