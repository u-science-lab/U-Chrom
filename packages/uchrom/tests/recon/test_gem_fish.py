"""GEM-FISH on the in-repo K562 chr21 Hi-C slice (Ray 2019), tiny iteration budget."""
from pathlib import Path

import numpy as np
import pytest
from tests import FIXTURES

COOL = FIXTURES / "K562_chr21_30kb.cool"
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
        pytest.skip("fixture K562_chr21_30kb.cool missing")


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


def test_gem_fish_user_tads_with_gaps():
    """User TADs that skip bins: one spot per bin inside a TAD, no crash."""
    import pandas as pd
    from uchrom.recon.fish import reconstruct_gem_fish

    tads = pd.DataFrame({"start": [18_000_000, 18_600_000, 19_500_000],
                         "end": [18_300_000, 19_200_000, 19_800_000]})
    cd = reconstruct_gem_fish(str(COOL), "chr21", tads=tads, params=_params())
    st = cd.spots_with_loci()["start"].to_numpy()
    assert len(st) == 10 + 20 + 10
    assert st.min() == 18_000_000 and st.max() == 19_770_000
    assert not ((st >= 18_300_000) & (st < 18_600_000)).any()
    assert np.isfinite(cd.coords).all()


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


def test_gem_fish_from_a_chromdata_with_a_linked_map():
    """The ChromData form (linked map + key, fish=) gives the path form's model and stores its TADs."""
    import pandas as pd
    from chromdata import ChromData

    from uchrom.recon.fish import reconstruct_gem_fish

    hic = ChromData(np.zeros((0, 3)), pd.DataFrame({"chrom": pd.Series(dtype=str), "start": pd.Series(dtype=np.int64),
                                                    "end": pd.Series(dtype=np.int64),
                                                    "trace_id": pd.Series(dtype=str)}),
                    uns={"genome_assembly": "hg19"})
    hic.link_cool(str(COOL), key="bulk")
    tads = pd.DataFrame({"start": [18_000_000, 18_300_000], "end": [18_300_000, 18_900_000]})
    new = reconstruct_gem_fish(hic, contacts="bulk", tads=tads, params=_params())   # one chromosome: chrom inferred
    old = reconstruct_gem_fish(hic_path=str(COOL), chrom="chr21", tads=tads, params=_params())
    assert np.array_equal(new.coords, old.coords)
    assert new.uns["genome_assembly"] == "hg19" and new.uns["gem_fish"]["contacts"] == "bulk"
    assert new.uns["gem_fish"]["fish"] is False and new.uns["gem_fish"]["chrom"] == "chr21"
    t = new.results["gem_fish.tads"]
    assert t[["start", "end"]].values.tolist() == [[18_000_000, 18_300_000], [18_300_000, 18_900_000]]
    assert (t["end_bin"] - t["start_bin"]).tolist() == [10, 20]
    quiet = reconstruct_gem_fish(hic, tads=tads, params=_params(), key_added=None)
    assert "gem_fish" not in quiet.uns and "gem_fish.tads" not in quiet.results
    with pytest.raises(TypeError, match="not both"):
        reconstruct_gem_fish(hic, fish=hic, fish_cd=hic, params=_params())
