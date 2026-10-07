"""uchrom.fea.band: banded reads of a cooler, the cis expected, observed / expected."""

import numpy as np
import pandas as pd
import pytest

cooler = pytest.importorskip("cooler")


def _toy(tmp_path, n=40, res=1000, seed=0):
    rng = np.random.default_rng(seed)
    bins = pd.concat([pd.DataFrame({"chrom": c, "start": np.arange(m) * res, "end": np.arange(1, m + 1) * res})
                      for c, m in (("chr1", n), ("chr2", n // 2))], ignore_index=True)
    i, j = np.triu_indices(len(bins))
    lam = 50.0 / (1 + (j - i)) ** 1.0
    cnt = rng.poisson(lam)
    keep = cnt > 0
    path = tmp_path / "toy.cool"
    cooler.create_cooler(str(path), bins, pd.DataFrame({"bin1_id": i[keep], "bin2_id": j[keep], "count": cnt[keep]}),
                         ordered=True)
    clr = cooler.Cooler(str(path))
    cooler.balance_cooler(clr, store=True, cis_only=True, ignore_diags=0, min_nnz=0, mad_max=0)
    return clr


def test_read_band_matches_the_dense_matrix(tmp_path):
    from uchrom.fea.band import read_band

    clr = _toy(tmp_path)
    dense = clr.matrix(balance=True).fetch("chr1")
    band = read_band(clr, chrom="chr1", max_dist=5_000, chunk=37)            # small chunks: crosses boundaries
    assert band.n == 40 and band.max_diag == 5 and (band.diag <= 5).all() and (band.j >= band.i).all()
    got = band.dense()
    k = np.abs(np.subtract.outer(np.arange(40), np.arange(40))) <= 5
    np.testing.assert_allclose(np.nan_to_num(got[k]), np.nan_to_num(dense[k]))
    assert (got[~k] == 0).all()
    full = read_band(clr, chrom="chr2")                                      # whole chromosome, other offset
    np.testing.assert_allclose(np.nan_to_num(full.dense()), np.nan_to_num(clr.matrix(balance=True).fetch("chr2")))


def test_expected_and_observed_over_expected(tmp_path):
    from uchrom.fea.band import band_observed_over_expected, expected_cis, read_band

    clr = _toy(tmp_path)
    dense = clr.matrix(balance=True).fetch("chr1")
    exp = expected_cis(clr, chroms=["chr1"], max_dist=10_000)
    assert list(exp["diag"]) == list(range(11))
    for d in (0, 3, 10):
        diag = np.diagonal(dense, d)
        ok = np.isfinite(diag)
        assert exp.loc[d, "n_valid"] == ok.sum()
        assert exp.loc[d, "balanced_avg"] == pytest.approx(diag[ok].mean())
    band = read_band(clr, chrom="chr1", max_dist=10_000)
    oe = band_observed_over_expected(band, exp)
    sel = band.diag == 3
    np.testing.assert_allclose(oe[sel], band.values()[sel] / exp.loc[3, "balanced_avg"])
    both = expected_cis(clr)                                                  # every chromosome, whole range
    assert set(both["chrom"]) == {"chr1", "chr2"} and both.groupby("chrom").size().to_dict() == {"chr1": 40, "chr2": 20}
