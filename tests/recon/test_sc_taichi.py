"""Single-cell reconstruction (Taichi, CPU) on a slice of real scHi-C.

Uses chr19 of ``example-data/stevens2017_mesc/cell1.pairs`` (Stevens 2017) at 1 Mb so each
run takes ~1 s.  Checks the output is a valid ChromData and that the
polymer backbone is respected (adjacent particles closer than random
pairs) — a cheap sanity bound, not a structural-accuracy benchmark.
"""
import numpy as np
import pytest

ti = pytest.importorskip("taichi")

from uchrom.datasets import example_path

PAIRS = example_path("stevens2017_mesc", "cell1.pairs")


def _backbone_ratio(X):
    rng = np.random.default_rng(0)
    nb = np.median(np.linalg.norm(X[1:] - X[:-1], axis=1))
    i, j = rng.integers(0, len(X), (2, 1000))
    rand = np.median(np.linalg.norm(X[i] - X[j], axis=1))
    return nb / rand


@pytest.fixture(autouse=True)
def _need_data():
    if not PAIRS.exists():
        pytest.skip("example-data/stevens2017_mesc/cell1.pairs missing")


def test_nucdyn_chr19_cpu(tmp_path):
    from uchrom import ChromData
    from uchrom.recon.sc.nucdyn.nucdyn import main

    out = tmp_path / "nd.chromdata.zarr"
    main(str(PAIRS), str(out), arch="cpu", genome_ranges=["chr19"],
         size_steps=[1, 0.5], dyns=100)
    cd = ChromData.read(out)
    assert cd.n_spots > 50
    assert set(cd.spots["chrom"]) == {"chr19"}
    assert np.isfinite(cd.coords).all()
    assert _backbone_ratio(cd.coords) < 0.8


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
