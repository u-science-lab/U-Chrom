"""GEM-FISH on the in-repo IMR90 chr21 Hi-C slice, tiny iteration budget."""
import numpy as np
import pytest

from uchrom.datasets import example_path

COOL = example_path("imr90_hic", "IMR90_chr21_30kb.cool")
pytest.importorskip("cooler")


def _params(**kw):
    from uchrom.recon.fish import GEMFISHParams

    base = dict(stage1_iter=30, stage1_ensemble=2, stage2_iter=20,
                stage2_ensemble=2, device="cpu")
    base.update(kw)
    return GEMFISHParams(**base)


@pytest.fixture(autouse=True)
def _need_data():
    if not COOL.exists():
        pytest.skip("example-data/imr90_hic/IMR90_chr21_30kb.cool missing")


def test_gem_fish_hic_only():
    """fish_cd=None is documented as a Hi-C-only degenerate run."""
    from uchrom.recon.fish import reconstruct_gem_fish

    cd = reconstruct_gem_fish(str(COOL), "chr21", params=_params())
    assert cd.coords.shape[1] == 3
    assert np.isfinite(cd.coords).all()
    assert (cd.spots["chrom"] == "chr21").all()
    assert "gem_fish" in cd.uns


def test_gem_fish_with_fish_constraints():
    """Feed FISH traces sampled from a smooth chain over a 1.2 Mb window."""
    from uchrom import ChromData
    from uchrom.recon.fish import reconstruct_gem_fish
    import pandas as pd

    rng = np.random.default_rng(0)
    res, start0, n_bins, n_traces = 30_000, 18_000_000, 40, 20
    rows, coords = [], []
    for t in range(n_traces):
        coords.append(np.cumsum(rng.normal(0, 0.1, (n_bins, 3)), axis=0))
        rows += [("chr21", start0 + k * res, start0 + (k + 1) * res, t)
                 for k in range(n_bins)]
    fish = ChromData(np.concatenate(coords),
                     pd.DataFrame(rows, columns=["chrom", "start", "end", "trace_id"]))
    cd, inter = reconstruct_gem_fish(
        str(COOL), "chr21", fish_cd=fish, params=_params(),
        return_intermediate=True,
    )
    assert np.isfinite(cd.coords).all()
    assert isinstance(inter, dict)


def test_mds_seed_all_missing_returns_finite_cloud():
    """Regression: an all-NaN FISH matrix (no FISH) used to crash eigh."""
    from uchrom.recon.fish._tad_level import _mds_seed

    D = np.full((6, 6), np.nan)
    X = _mds_seed(D, np.ones((6, 6)))
    assert X.shape == (6, 3) and np.isfinite(X).all()


def test_mds_seed_nan_diagonal_partial():
    from scipy.spatial.distance import pdist, squareform
    from uchrom.recon.fish._tad_level import _mds_seed

    P = np.random.default_rng(0).normal(size=(8, 3))
    D = squareform(pdist(P))
    np.fill_diagonal(D, np.nan)
    D[0, 3] = D[3, 0] = np.nan
    X = _mds_seed(D, np.ones((8, 8)))
    assert np.isfinite(X).all()
    assert np.corrcoef(pdist(X), pdist(P))[0, 1] > 0.9
