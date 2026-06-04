"""
Tests for FISH coordinate imputation.
"""

import pytest
import numpy as np
import pandas as pd


@pytest.fixture
def sample_chromdata():
    """Create a simple ChromData with some missing coordinates."""
    from uchrom.core import ChromData

    # Create test data: 50 spots, 30% missing
    n_spots = 50
    n_missing = int(n_spots * 0.3)

    # Generate synthetic coordinates
    coords = np.random.randn(n_spots, 3) * 100 + 1000

    # Introduce missing values randomly
    missing_indices = np.random.choice(n_spots, n_missing, replace=False)
    coords[missing_indices] = np.nan

    # Create spots DataFrame
    spots = pd.DataFrame({
        'chrom': ['chr21'] * n_spots,
        'start': np.arange(1000000, 1000000 + n_spots * 10000, 10000),
        'end': np.arange(1010000, 1010000 + n_spots * 10000, 10000),
        'trace_id': [f'trace_{i//10}' for i in range(n_spots)],
    })

    cd = ChromData(coords=coords, spots=spots)
    return cd


def test_impute_linear(sample_chromdata):
    """Test linear interpolation imputation."""
    from uchrom.im.impute import impute_linear

    cd = sample_chromdata
    n_missing_before = np.isnan(cd.coords).sum()

    cd_imputed = impute_linear(cd)
    n_missing_after = np.isnan(cd_imputed.coords).sum()

    # Should reduce missing values
    assert n_missing_after <= n_missing_before

    # Should preserve non-missing values
    mask = ~np.isnan(cd.coords)
    np.testing.assert_allclose(
        cd.coords[mask],
        cd_imputed.coords[mask],
        rtol=1e-10
    )


def test_impute_cubic(sample_chromdata):
    """Test cubic spline interpolation."""
    from uchrom.im.impute import impute_cubic

    cd = sample_chromdata
    n_missing_before = np.isnan(cd.coords).sum()

    cd_imputed = impute_cubic(cd)
    n_missing_after = np.isnan(cd_imputed.coords).sum()

    # Should reduce missing values
    assert n_missing_after <= n_missing_before

    # Should preserve non-missing values
    mask = ~np.isnan(cd.coords)
    np.testing.assert_allclose(
        cd.coords[mask],
        cd_imputed.coords[mask],
        rtol=1e-10
    )


@pytest.mark.skipif(
    not hasattr(pytest, 'importorskip'),
    reason="pytest.importorskip not available"
)
def test_impute_snapfish(sample_chromdata):
    """Test SnapFISH-IMPUTE algorithm (requires extra dependencies)."""
    pytest.importorskip("scipy")
    pytest.importorskip("sklearn")
    pytest.importorskip("skimage")

    from uchrom.im.impute import impute_snapfish

    cd = sample_chromdata
    n_missing_before = np.isnan(cd.coords).sum()

    cd_imputed = impute_snapfish(cd, max_iter=10, verbose=False)
    n_missing_after = np.isnan(cd_imputed.coords).sum()

    # Should reduce missing values
    assert n_missing_after <= n_missing_before

    # Should preserve non-missing values (within tolerance for optimization)
    mask = ~np.isnan(cd.coords)
    np.testing.assert_allclose(
        cd.coords[mask],
        cd_imputed.coords[mask],
        rtol=1e-3  # Allow small changes due to optimization
    )


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
    """Test that imputation preserves ChromData metadata."""
    from uchrom.im.impute import impute_linear

    cd = sample_chromdata
    cd.uns['test_key'] = 'test_value'

    cd_imputed = impute_linear(cd)

    # Should preserve metadata
    assert cd_imputed.uns == cd.uns

    # Should preserve spots DataFrame
    pd.testing.assert_frame_equal(cd.spots, cd_imputed.spots)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
