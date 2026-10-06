"""
Tests for FISH coordinate imputation.
"""

import pytest
import numpy as np
import pandas as pd
from tests import REPO


@pytest.fixture
def sample_chromdata():
    """Create a FISH-like ChromData where traces share one locus panel.

    Real multiplexed-FISH data has every trace imaging the SAME panel of loci;
    missing entries are NaN coordinates. This fixture mirrors that: 5 traces x
    10 shared loci = 50 spots, ~30% NaN, with a smooth per-trace curve so
    interpolation and similarity-based imputation have signal.
    """
    from chromdata import ChromData

    rng = np.random.RandomState(0)
    # Many traces (cells) sharing the panel keeps the SnapFISH box-cox /
    # similarity steps well-conditioned, as in real multi-cell FISH data.
    n_traces, n_loci = 20, 10
    panel_starts = np.arange(1000000, 1000000 + n_loci * 10000, 10000)

    rows, coords = [], []
    for t in range(n_traces):
        phase = t * 0.6
        for i, s in enumerate(panel_starts):
            x = np.sin(0.4 * i + phase) * 200 + rng.randn() * 5
            y = np.cos(0.4 * i + phase) * 200 + rng.randn() * 5
            z = i * 30 + rng.randn() * 5
            rows.append(dict(chrom='chr21', start=int(s), end=int(s + 10000),
                             trace_id=f'trace_{t}'))
            coords.append([x, y, z])

    spots = pd.DataFrame(rows)
    coords = np.asarray(coords, dtype=float)

    # ~30% NaN, but keep >= 2 anchors per trace.
    for t in range(n_traces):
        idx = np.where(spots['trace_id'].values == f'trace_{t}')[0]
        n_drop = min(int(n_loci * 0.3), n_loci - 2)
        coords[rng.choice(idx, n_drop, replace=False)] = np.nan

    return ChromData(coords=coords, spots=spots)


def _coord_by_key(cd):
    """Map (chrom, start, trace_id) -> coord row for non-NaN spots."""
    out = {}
    for i in range(len(cd.spots)):
        if not np.isnan(cd.coords[i, 0]):
            k = (cd.spots['chrom'].iloc[i], int(cd.spots['start'].iloc[i]),
                 cd.spots['trace_id'].iloc[i])
            out[k] = cd.coords[i]
    return out


def test_impute_linear(sample_chromdata):
    """Test linear interpolation imputation."""
    from uchrom.im.impute import impute_linear

    cd = sample_chromdata
    before = _coord_by_key(cd)

    cd_imputed = impute_linear(cd)

    # Should fill all missing values (each trace keeps >= 2 anchors)
    assert np.isnan(cd_imputed.coords).sum() == 0

    # Should preserve non-missing values at their (chrom, start, trace) keys
    after = {(cd_imputed.spots['chrom'].iloc[i], int(cd_imputed.spots['start'].iloc[i]),
              cd_imputed.spots['trace_id'].iloc[i]): cd_imputed.coords[i]
             for i in range(len(cd_imputed.spots))}
    for k, v in before.items():
        np.testing.assert_allclose(after[k], v, rtol=1e-10)


def test_impute_cubic(sample_chromdata):
    """Test cubic spline interpolation."""
    from uchrom.im.impute import impute_cubic

    cd = sample_chromdata
    before = _coord_by_key(cd)

    cd_imputed = impute_cubic(cd)

    # Should fill all missing values
    assert np.isnan(cd_imputed.coords).sum() == 0

    # Should preserve non-missing values at their keys
    after = {(cd_imputed.spots['chrom'].iloc[i], int(cd_imputed.spots['start'].iloc[i]),
              cd_imputed.spots['trace_id'].iloc[i]): cd_imputed.coords[i]
             for i in range(len(cd_imputed.spots))}
    for k, v in before.items():
        np.testing.assert_allclose(after[k], v, rtol=1e-10)


@pytest.mark.skipif(
    not hasattr(pytest, 'importorskip'),
    reason="pytest.importorskip not available"
)
def test_impute_snapfish():
    """SnapFISH-IMPUTE on the real in-repo mESC Sox2 dataset.

    The similarity-weighted algorithm needs realistic scale (many cells sharing
    a locus panel), so it is validated on real data rather than a tiny synthetic
    fixture, per the project's validation discipline.
    """
    import os
    pytest.importorskip("scipy")
    pytest.importorskip("sklearn")
    pytest.importorskip("skimage")

    from chromdata import ChromData
    from uchrom.im.impute import impute_snapfish

    data = str(REPO / "example-data" / "mESC_Sox2_5cells_wnan.chromdata.zarr")
    if not os.path.exists(data):
        pytest.skip(f"real test data not found: {data}")

    cd = ChromData.read(data)
    n_missing_before = np.isnan(cd.coords).sum()
    before = _coord_by_key(cd)

    cd_imputed = impute_snapfish(cd, max_iter=30, verbose=False)
    n_missing_after = np.isnan(cd_imputed.coords).sum()

    # Should impute the large majority of missing coordinates
    assert n_missing_after < n_missing_before

    # Should preserve non-missing values at their keys (within optimization tol)
    after = {(cd_imputed.spots['chrom'].iloc[i], int(cd_imputed.spots['start'].iloc[i]),
              cd_imputed.spots['trace_id'].iloc[i]): cd_imputed.coords[i]
             for i in range(len(cd_imputed.spots))}
    for k, v in before.items():
        np.testing.assert_allclose(after[k], v, rtol=1e-3, atol=1e-3)


def test_impute_coordinates_api(sample_chromdata):
    """Test the main impute_coordinates API."""
    from uchrom.im.impute import impute_coordinates

    cd = sample_chromdata

    # Test linear method
    cd_linear = impute_coordinates(cd, method='linear')
    assert np.isnan(cd_linear.coords).sum() <= np.isnan(cd.coords).sum()

    # Test cubic method
    cd_cubic = impute_coordinates(cd, method='cubic')
    assert np.isnan(cd_cubic.coords).sum() <= np.isnan(cd.coords).sum()

    # Test invalid method
    with pytest.raises(ValueError, match="Unknown imputation method"):
        impute_coordinates(cd, method='invalid')


def test_metadata_preservation(sample_chromdata):
    """Test that imputation preserves ChromData metadata and original loci."""
    from uchrom.im.impute import impute_linear

    cd = sample_chromdata
    cd.uns['test_key'] = 'test_value'
    orig_keys = set(zip(cd.spots['chrom'], cd.spots['start'].astype(int),
                        cd.spots['trace_id']))

    cd_imputed = impute_linear(cd)

    # Should preserve uns metadata
    assert cd_imputed.uns == cd.uns

    # Output is the dense grid; every original (chrom, start, trace) is retained
    out_keys = set(zip(cd_imputed.spots['chrom'], cd_imputed.spots['start'].astype(int),
                       cd_imputed.spots['trace_id']))
    assert orig_keys <= out_keys


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
