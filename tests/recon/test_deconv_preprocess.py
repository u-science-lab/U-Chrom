"""IGM Hi-C preprocessing (uchrom.recon.bulk.deconv.preprocess) on small synthetic matrices.

Synthetic data check correctness only (balancing, block statistics, f_max fit, filters);
the real-data checks (Juicer KR vectors, Rao 2014 IMR90 plumbing) are in
``benchmarks/bulk/kr_check.py`` and ``benchmarks/bulk/README.md``.
"""

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

from uchrom.recon.bulk.deconv.preprocess import (
    IGMPreprocessParams, ProbabilityMatrix, _BlockEntries, aggregate_bins, canonical_upper, coarse_index,
    coverage_mask, fit_fmax, ice_balance, kr_balance, preprocess_igm, symmetrize_upper, topmean_summary)


def toy_hic(n_per_chrom=(60, 40), res=20_000, seed=0, inter_level=0.02):
    """Polymer-like counts: c_ij ~ Poisson(bias_i bias_j * (|i-j|+1)^-1 * 400) intra, flat inter."""
    rng = np.random.default_rng(seed)
    chrom, start = [], []
    for k, n in enumerate(n_per_chrom):
        chrom += [f"chr{k + 1}"] * n
        start += list(np.arange(n) * res)
    chrom = np.array(chrom)
    start = np.array(start)
    N = len(chrom)
    bias = rng.lognormal(0, 0.3, N)
    idx = np.arange(N)
    sep = np.abs(idx[:, None] - idx[None])
    same = chrom[:, None] == chrom[None]
    lam = np.where(same, 400.0 / (sep + 1.0), 400.0 * inter_level) * bias[:, None] * bias[None]
    C = rng.poisson(np.triu(lam)).astype(float)
    bins = pd.DataFrame({"chrom": chrom, "start": start, "end": start + res})
    return sp.csr_matrix(C), bins


def test_canonical_upper_storage():
    m = sp.csr_matrix(np.array([[1.0, 2, 0], [2, 3, 4], [0, 4, 5]]))
    u = canonical_upper(m)
    assert sp.tril(u, -1).nnz == 0 and u[0, 1] == 2 and u[1, 2] == 4
    assert canonical_upper(sp.tril(m)).toarray().tolist() == u.toarray().tolist()
    assert np.allclose(symmetrize_upper(u).toarray(), m.toarray())


@pytest.mark.parametrize("seed", [0, 1])
def test_kr_unit_rowsums_and_agrees_with_ice(seed):
    C, bins = toy_hic(seed=seed)
    w, info = kr_balance(C)
    A = symmetrize_upper(canonical_upper(C)).toarray()
    B = w[:, None] * A * w[None]
    assert info["converged"]
    assert np.allclose(B.sum(1), 1.0, atol=1e-5)
    w2, info2 = ice_balance(C, tol=1e-12, max_iter=5000)
    # symmetric balancing is unique up to scale: same weights after normalisation
    r = w / w2
    assert np.nanstd(r) / np.nanmean(r) < 1e-4


def test_kr_masks_and_empty_rows():
    C, bins = toy_hic()
    C = C.tolil()
    C[5, :] = 0
    C[:, 5] = 0
    mask = np.zeros(C.shape[0], bool)
    mask[7] = True
    w, info = kr_balance(C.tocsr(), mask)
    assert np.isnan(w[5]) and np.isnan(w[7]) and info["n_kept"] == C.shape[0] - 2
    keep = np.isfinite(w)
    A = symmetrize_upper(canonical_upper(C.tocsr())).toarray()[np.ix_(keep, keep)]
    assert np.allclose((w[keep][:, None] * A * w[keep][None]).sum(1), 1.0, atol=1e-5)


def test_coverage_mask():
    C, bins = toy_hic()
    C = C.tolil()
    C[3, :] = C[3, :] * 0
    C[:, 3] = C[:, 3] * 0
    C[10, :] = C[10, :] * 0.01            # ~1 % of a typical row
    C[:, 10] = C[:, 10] * 0.01
    m = coverage_mask(C.tocsr(), 0.03)
    assert m[3] and m[10] and m.sum() == 2
    seq = np.ones(C.shape[0])
    seq[4] = 0.02
    assert np.flatnonzero(coverage_mask(C.tocsr(), 0.03, sequence_coverage=seq)).tolist() == [4]


def reference_topmean(P, f2c, nC, top=10, inclusive=True):
    """Straight port of the block statistic (alabtools cmtools TopmeanSummaryMatrix semantics),
    dense, loop over blocks; P = full symmetric probability matrix with zero diagonal."""
    out = np.zeros((nC, nC))
    for I in range(nC):
        for J in range(I, nC):
            a, b = np.flatnonzero(f2c == I), np.flatnonzero(f2c == J)
            data = np.sort(P[np.ix_(a, b)].ravel())
            n = len(data)
            q1 = data[min(int(n * 0.25 + 0.5), n - 1)]
            q3 = data[min(int(n * 0.75 + 0.5), n - 1)]
            fence = q3 + 1.5 * (q3 - q1)
            cut = n // top or n
            if fence == 0:
                fence, cut = 10.0, n
            s, c = 0.0, 0
            for x in data[::-1]:
                if (x <= fence) if inclusive else (x < fence):
                    s += x
                    c += 1
                if c == cut:
                    break
            out[I, J] = s / cut
    return out


@pytest.mark.parametrize("inclusive", [True, False])
@pytest.mark.parametrize("fmax", [5.0, 50.0, 400.0])
def test_topmean_matches_reference(fmax, inclusive):
    C, bins = toy_hic(n_per_chrom=(37, 23), seed=3)
    f2c, cb = coarse_index(bins, 200_000)
    nC = len(cb)
    n_per = np.bincount(f2c, minlength=nC)
    blocks = _BlockEntries(canonical_upper(C), f2c, nC, n_per)
    got = np.zeros((nC, nC))
    got[blocks.bI, blocks.bJ] = topmean_summary(blocks, fmax, fence_inclusive=inclusive)
    A = symmetrize_upper(canonical_upper(C)).toarray()
    np.fill_diagonal(A, 0)
    ref = reference_topmean(np.minimum(A / fmax, 1.0), f2c, nC, inclusive=inclusive)
    assert np.allclose(got, ref, atol=1e-12)


def test_fit_fmax_hits_target():
    C, bins = toy_hic(n_per_chrom=(120, 80))
    w, _ = kr_balance(C)
    g = sp.diags(w) @ canonical_upper(C) @ sp.diags(w)
    f2c, cb = coarse_index(bins, 100_000)
    blocks = _BlockEntries(sp.csr_matrix(g), f2c, len(cb), np.bincount(f2c))
    for target in (3.0, 8.0):
        f, avg, trace = fit_fmax(blocks, target=target, tol=0.01, theta=0.001)
        assert abs(avg - target) / target <= 0.01


def test_preprocess_end_to_end_and_roundtrip(tmp_path):
    C, bins = toy_hic(n_per_chrom=(120, 80))
    P = IGMPreprocessParams(coarse_resolution=100_000, target_contacts=6.0)
    out = preprocess_igm(C, bins, params=P)
    M = out.probabilities.toarray()
    assert np.allclose(M, M.T) and M.min() >= 0 and M.max() <= 1
    assert np.allclose(np.diag(M), 1.0)
    ch = out.bins.chrom.to_numpy()
    for I in range(len(ch) - 1):
        if ch[I] == ch[I + 1]:
            assert M[I, I + 1] == 1.0
    assert out.provenance["max_inter_probability"] <= 0.2
    r = out.provenance["rounds"][-1]
    assert abs(r["average_contacts"] - 6.0) / 6.0 <= 0.01
    assert len(out.bins) == 40 and out.bins.n_fine.sum() == 200
    out.save(tmp_path / "p.npz")
    back = ProbabilityMatrix.load(tmp_path / "p.npz")
    assert np.allclose(back.probabilities.toarray(), M) and back.bins.chrom.tolist() == ch.tolist()
    i, j, p = out.upper_coo()
    assert (i <= j).all()


def test_spurious_inter_bins_removed():
    C, bins = toy_hic(n_per_chrom=(120, 80), inter_level=0.005)
    C = C.tolil()
    C[25:30, 150:155] = 300.0              # a whole 100 kb x 100 kb inter block (translocation-like)
    P = IGMPreprocessParams(coarse_resolution=100_000, target_contacts=6.0)
    out = preprocess_igm(C.tocsr(), bins, params=P)
    assert out.provenance["n_fine_removed_inter"] >= 2
    assert out.fine_mask[25:30].any() and out.fine_mask[150:155].any()
    assert out.provenance["max_inter_probability"] <= 0.2
    assert len(out.provenance["rounds"]) >= 2


def test_coarse_bins_dataframe_and_aggregate():
    C, bins = toy_hic(n_per_chrom=(40,))
    cb = pd.DataFrame({"chrom": ["chr1", "chr1"], "start": [100_000, 400_000], "end": [300_000, 500_000]})
    f2c, got = coarse_index(bins, cb)
    mid = (bins.start + bins.end) // 2
    assert (f2c[(mid >= 100_000) & (mid < 300_000)] == 0).all()
    assert (f2c[(mid >= 400_000) & (mid < 500_000)] == 1).all()
    assert (f2c[mid < 100_000] == -1).all()
    m, b = aggregate_bins(C, bins, 4)
    assert len(b) == 10 and np.isclose(m.sum(), canonical_upper(C).sum())
