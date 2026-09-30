"""Synthetic whole-genome truth + forward model for the consensus tests (correctness only).

Truth: one confined random walk per chromosome (step 1 = adjacent-bin distance), each in its
own territory sphere; population Hi-C expected counts ``depth * min(1, d)^-alpha`` (a
power-law contact kernel, alpha = 4) times per-bin biases, Poisson reads.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.sparse as sp


def truth_genome(lengths=(240, 160, 120), res=50_000, seed=0, territory=4.0, spacing=7.0):
    rng = np.random.default_rng(seed)
    X, rows = [], []
    ang = np.linspace(0, 2 * np.pi, len(lengths), endpoint=False)
    for c, L in enumerate(lengths):
        ctr = np.array([spacing * np.cos(ang[c]), spacing * np.sin(ang[c]), 0.3 * c])
        R = territory * (L / 200) ** (1 / 3)
        x = np.zeros((L, 3))
        x[0] = ctr
        for i in range(1, L):
            for _ in range(100):
                v = rng.normal(size=3)
                q = x[i - 1] + v / np.linalg.norm(v)
                if np.linalg.norm(q - ctr) < R:
                    break
            x[i] = q
        X.append(x)
        st = np.arange(L) * res
        rows.append(pd.DataFrame({"chrom": f"chr{c + 1}", "start": st, "end": st + res}))
    return np.concatenate(X), pd.concat(rows, ignore_index=True)


def forward_counts(X, depth=400.0, alpha=4.0, bias_sd=0.2, seed=1):
    rng = np.random.default_rng(seed)
    n = len(X)
    D = np.linalg.norm(X[:, None] - X[None], axis=2)
    f = np.minimum(1.0, np.maximum(D, 1e-9) ** -alpha)
    bias = np.exp(rng.normal(0, bias_sd, n))
    lam = depth * f * bias[:, None] * bias[None]
    iu = np.triu_indices(n, 0)
    cnt = rng.poisson(lam[iu])
    k = cnt > 0
    return sp.coo_matrix((cnt[k].astype(float), (iu[0][k], iu[1][k])), shape=(n, n)).tocsr()


def similarity_rmsd(truth, model):
    """RMSD after similarity superposition (scale, rotation, reflection), / Rg(truth)."""
    from uchrom.recon.bulk.consensus import kabsch

    fit, r = kabsch(truth, model, reflection=True, scale=True)
    rg = np.sqrt(((truth - truth.mean(0)) ** 2).sum(1).mean())
    return r / rg


def dist_r(a, b, mask=None):
    iu = np.triu_indices(len(a), 1)
    da = np.linalg.norm(a[iu[0]] - a[iu[1]], axis=1)
    db = np.linalg.norm(b[iu[0]] - b[iu[1]], axis=1)
    if mask is not None:
        k = mask[iu]
        da, db = da[k], db[k]
    return float(np.corrcoef(da, db)[0, 1])
