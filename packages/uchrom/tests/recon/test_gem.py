"""GEM single-cell reconstruction (Taichi, CPU; the optional ``gem`` extra) on a slice of real scHi-C.

Uses chr19 of ``example-data/cell1.pairs`` (Stevens 2017) at 1 Mb so each
run takes ~1 s.  Checks the output is a valid ChromData and that the
polymer backbone is respected (adjacent particles closer than random
pairs) — a cheap sanity bound, not a structural-accuracy benchmark.
"""
from pathlib import Path

import numpy as np
import pytest
from tests import REPO

ti = pytest.importorskip("taichi")

PAIRS = REPO / "example-data" / "cell1.pairs"


def _backbone_ratio(X):
    rng = np.random.default_rng(0)
    nb = np.median(np.linalg.norm(X[1:] - X[:-1], axis=1))
    i, j = rng.integers(0, len(X), (2, 1000))
    rand = np.median(np.linalg.norm(X[i] - X[j], axis=1))
    return nb / rand


@pytest.fixture(autouse=True)
def _need_data():
    if not PAIRS.exists():
        pytest.skip("example-data/cell1.pairs missing")


def test_gem_chr19_cpu(tmp_path):
    from uchrom import ChromData
    from uchrom.recon.sc.gem.gem import main

    out = tmp_path / "gem.chromdata.zarr"
    main(str(PAIRS), str(out), arch="cpu", genome_ranges=["chr19"],
         size_steps=[1], steps=300)
    cd = ChromData.read(out)
    assert cd.n_spots > 30
    assert np.isfinite(cd.coords).all()
    assert _backbone_ratio(cd.coords) < 0.8
