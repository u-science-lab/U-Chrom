"""uchrom.emb.hic follows the authors' scHiCluster code: ``neighbor_ave_cpu``, ``random_walk_cpu`` and
``impute_cpu`` of ``schicluster.schicluster`` (github.com/zhoujt1994/scHiCluster, PyPI 1.3.2, MIT licence,
Copyright (c) Jingtian Zhou), transcribed below as the reference (the file reading of ``impute_cpu`` replaced by
its matrix), on random maps with empty rows; and the feature step of ``hicluster_cpu``."""

import numpy as np
import pytest

from uchrom.emb import schicluster_features
from uchrom.emb.hic import schicluster_impute


# ---------------------------------------------------------------- the authors' code (reference)

def neighbor_ave_cpu(A, pad):
    if pad == 0:
        return A
    ngene, _ = A.shape
    ll = pad * 2 + 1
    B, C, D, E = [np.zeros((ngene + ll, ngene + ll)) for i in range(4)]
    B[(pad + 1):(pad + ngene + 1), (pad + 1):(pad + ngene + 1)] = A[:]
    F = B.cumsum(axis=0).cumsum(axis=1)
    C[ll:, ll:] = F[:-ll, :-ll]
    D[ll:, :] = F[:-ll, :]
    E[:, ll:] = F[:, :-ll]
    return (np.around(F + C - D - E, decimals=8)[ll:, ll:] / float(ll * ll))


def random_walk_cpu(A, rp):
    ngene, _ = A.shape
    A = A - np.diag(np.diag(A))
    A = A + np.diag(np.sum(A, axis=0) == 0)
    P = np.divide(A, np.sum(A, axis=0))
    Q = np.eye(ngene)
    I = np.eye(ngene)  # noqa: E741
    for i in range(30):
        Q_new = (1 - rp) * I + rp * np.dot(Q, P)
        delta = np.linalg.norm(Q - Q_new)
        Q = Q_new.copy()
        if delta < 1e-6:
            break
    return Q


def impute_cpu(upper, pad, rp):
    """``impute_cpu`` on the upper triangle of a cell's counts (the matrix its text file holds)."""
    A = np.log2(upper + upper.T + 1)
    A = neighbor_ave_cpu(A, pad)
    return A[:] if rp == -1 else random_walk_cpu(A, rp)


# ---------------------------------------------------------------- tests

def _maps(n_cells=6, n=25, seed=0):
    rng = np.random.default_rng(seed)
    ups = []
    for k in range(n_cells):
        u = np.triu(rng.poisson(0.4, (n, n)).astype(float))
        u[:, rng.choice(n, 3, replace=False)] = 0           # empty bins (rows and columns)
        u[rng.choice(n, 3, replace=False), :] = 0
        ups.append(u)
    sym = [u + u.T - np.diag(np.diag(u)) for u in ups]       # what a .scool gives: the diagonal once
    return ups, np.stack(sym)


@pytest.mark.parametrize("pad,rp", [(1, 0.5), (2, 0.5), (1, 0.3), (0, 0.5), (1, -1)])
def test_impute_equals_the_authors_code(pad, rp):
    ups, sym = _maps()
    got = schicluster_impute(sym, pad=pad, rp=rp)
    for k, u in enumerate(ups):
        np.testing.assert_allclose(got[k], impute_cpu(u, pad, rp), rtol=1e-12, atol=1e-15)
    # one map at a time gives the batch's maps (each stops at its own step)
    one = schicluster_impute(sym[2], pad=pad, rp=rp)
    np.testing.assert_allclose(one, got[2], rtol=1e-13, atol=1e-15)


def test_features_follow_hicluster_cpu():
    """``hicluster_cpu``'s feature step: Q flattened, set to 1 above the cell's 80th percentile, PCA with
    int(0.2 min(cells, n²)) - 1 components (here the binarised matrices are compared, the PCA by its size)."""
    ups, sym = _maps(n_cells=40, n=12, seed=3)
    Q = np.stack([impute_cpu(u, 1, 0.5).reshape(-1) for u in ups])
    want = Q > np.percentile(Q, 80, axis=1)[:, None]
    got = schicluster_impute(sym, pad=1, rp=0.5).reshape(40, -1)
    np.testing.assert_array_equal(got > np.percentile(got, 80, axis=1)[:, None], want)
    feats, cols = schicluster_features({"chr1": sym})
    assert feats.shape == (40, int(min(40, 144) * 0.2) - 1) and cols[0] == "chr1_PC1"
