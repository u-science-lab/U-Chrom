"""
Tests for multiprocessing acceleration of SnapFISH-IMPUTE (n_jobs).

Parallelism must NOT change the algorithm: results with n_jobs>1 must be
identical to the serial (n_jobs=1) path, since the same deterministic kernels
(`to_target_single_chr`, `recover_3d_coor_single_chr`) are merely distributed
across workers.
"""

import os
import numpy as np
import pytest


def _real_cd():
    from uchrom.core import ChromData
    from uchrom.datasets import example_path
    data = str(example_path("mesc_sox2", "mESC_Sox2_5cells_wnan.h5cd"))
    if not os.path.exists(data):
        pytest.skip(f"real test data not found: {data}")
    return ChromData.read(data)


def test_snapfish_n_jobs_matches_serial():
    """n_jobs=2 must give identical coordinates to n_jobs=1."""
    pytest.importorskip("skimage")
    from uchrom.im.impute import impute_snapfish

    cd = _real_cd()
    # Equality of the parallel/serial paths holds at any iteration count;
    # a small max_iter keeps the test fast.
    serial = impute_snapfish(cd, max_iter=8, n_jobs=1, verbose=False)
    parallel = impute_snapfish(cd, max_iter=8, n_jobs=2, verbose=False)

    assert serial.coords.shape == parallel.coords.shape
    np.testing.assert_allclose(
        serial.coords, parallel.coords, rtol=1e-6, atol=1e-6, equal_nan=True
    )


def test_impute_coordinates_passes_n_jobs():
    """The public API forwards n_jobs to the snapfish backend."""
    pytest.importorskip("skimage")
    from uchrom.im.impute import impute_coordinates

    cd = _real_cd()
    out = impute_coordinates(cd, method="snapfish", n_jobs=2, max_iter=8, verbose=False)
    assert out.coords.shape[0] == len(out.spots)


def test_snapfish_n_jobs_default_is_serial():
    """Default call (no n_jobs) still works and matches n_jobs=1."""
    pytest.importorskip("skimage")
    from uchrom.im.impute import impute_snapfish

    cd = _real_cd()
    default = impute_snapfish(cd, max_iter=8, verbose=False)
    serial = impute_snapfish(cd, max_iter=8, n_jobs=1, verbose=False)
    np.testing.assert_allclose(
        default.coords, serial.coords, rtol=1e-9, atol=1e-9, equal_nan=True
    )
