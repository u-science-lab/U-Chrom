"""Local-support likelihood ratio of every contact (prototype of a data-driven prior for ``robust``).

False contacts are uniform over locus pairs, so the number of other contacts near a false contact
(Chebyshev window ``W`` at both ends, same chromosome pair) is distributed as the number near a
*random location* at the same separation; true contacts are spatially correlated (neighbouring
loci of two loci in contact are close too).  Per separation stratum (cis: log2 bins of the
separation in units of W; trans: one stratum) the ratio

    LR(n) = P_obs(n | stratum) / P_random(n | stratum)        (n capped at ``nmax``)

estimates P(n | true) / P(n | false) up to the false fraction of the stratum (it is a
conservative, ε-free version: LR -> 1 where the stratum is all noise or all signal).  Uses only
the contact table, no structure.  Clipped to [lr_min, lr_max].
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree


def _canon(ca, pa, cb, pb):
    ca, cb = np.asarray(ca).astype(str), np.asarray(cb).astype(str)
    pa, pb = np.asarray(pa, np.int64), np.asarray(pb, np.int64)
    swap = (ca > cb) | ((ca == cb) & (pa > pb))
    ca, cb = np.where(swap, cb, ca), np.where(swap, ca, cb)
    pa, pb = np.where(swap, pb, pa), np.where(swap, pa, pb)
    return ca, pa, cb, pb


def support_counts(ca, pa, cb, pb, W: float, *, n_random: int = 5, seed: int = 0):
    """-> (n_obs, stratum_obs, n_random_points, stratum_random): support counts at the contacts and
    at random locations of the same chromosome pair and separation."""
    rng = np.random.default_rng(seed)
    ca, pa, cb, pb = _canon(ca, pa, cb, pb)
    same = ca == cb
    key = np.char.add(np.char.add(ca, "|"), cb)
    allc, allp = np.r_[ca, cb], np.r_[pa, pb]
    lim = {c: (allp[allc == c].min(), allp[allc == c].max()) for c in np.unique(allc)}
    lo_a = np.array([lim[c][0] for c in ca]); hi_a = np.array([lim[c][1] for c in ca])
    lo_b = np.array([lim[c][0] for c in cb]); hi_b = np.array([lim[c][1] for c in cb])
    sep = np.where(same, pb - pa, -1)
    n_obs = np.zeros(len(pa), np.int64)
    trees = {}
    for k in np.unique(key):
        s = np.flatnonzero(key == k)
        trees[k] = cKDTree(np.c_[pa[s], pb[s]].astype(float))
        n_obs[s] = trees[k].query_ball_point(np.c_[pa[s], pb[s]].astype(float), W, p=np.inf, return_length=True) - 1
    rn, rs = [], []
    for _ in range(n_random):
        ra = lo_a + (rng.random(len(pa)) * (hi_a - lo_a + 1)).astype(np.int64)
        rb = np.where(same, ra + sep, lo_b + (rng.random(len(pa)) * (hi_b - lo_b + 1)).astype(np.int64))
        ok = ~same | (rb <= hi_a)
        for k in np.unique(key[ok]):
            s = np.flatnonzero(ok & (key == k))
            rn.append(trees[k].query_ball_point(np.c_[ra[s], rb[s]].astype(float), W, p=np.inf, return_length=True))
            rs.append(sep[s])
    rn = np.concatenate(rn) if rn else np.zeros(0, np.int64)
    rs = np.concatenate(rs) if rs else np.zeros(0, np.int64)

    def stratum(x):
        return np.where(x < 0, -1, np.floor(np.log2(np.maximum(x, W) / W))).astype(int)

    return n_obs, stratum(sep), rn, stratum(rs)


def _fit_stratum(o, r, nmax=30, iters=100):
    """Mixture of the counts at contacts: false ~ empirical counts at random locations, true ~
    negative binomial (EM, NB by weighted ML).  -> (eps, P_true(n), P_false(n)) on 0..nmax."""
    from scipy import optimize, stats
    o = np.minimum(o, nmax)
    r = np.minimum(r, nmax)
    pf = np.bincount(r, minlength=nmax + 1) + 0.1
    pf /= pf.sum()
    h = np.bincount(o, minlength=nmax + 1).astype(float)
    nn = np.arange(nmax + 1)

    def nb(mu, size):
        p = size / (size + mu)
        v = stats.nbinom.pmf(nn, size, p)
        v[-1] += stats.nbinom.sf(nmax, size, p)
        return v + 1e-12

    eps, mu, size = 0.3, max(float(h @ nn / h.sum()), float(r.mean()) + 1.0) * 1.5, 1.0
    for _ in range(iters):
        pt = nb(mu, size)
        post = (1 - eps) * pt / ((1 - eps) * pt + eps * pf)
        new_eps = 1 - float((h * post).sum() / h.sum())
        w = h * post
        res = optimize.minimize(lambda x: -(w * np.log(nb(np.exp(x[0]), np.exp(x[1])))).sum(),
                                [np.log(mu), np.log(size)], method="Nelder-Mead",
                                options={"xatol": 1e-4, "fatol": 1e-6})
        mu, size = np.exp(res.x)
        done = abs(new_eps - eps) < 1e-5
        eps = new_eps
        if done:
            break
    return eps, nb(mu, size), pf


def support_mixture(ca, pa, cb, pb, W: float, *, n_random: int = 5, nmax: int = 30, min_random: int = 50,
                    lr_min: float = 1e-3, lr_max: float = 1e3, seed: int = 0):
    """Calibrated local-support evidence per contact.  Per separation stratum the support counts
    are fitted as a mixture (false: counts at random locations, exactly what a uniform false
    contact sees; true: negative binomial).  -> dict with ``lr`` = P(n | true) / P(n | false)
    (clipped), ``pi`` = P(true | n, stratum), ``eps`` per stratum, ``n``."""
    n, so, rn, sr = support_counts(ca, pa, cb, pb, W, n_random=n_random, seed=seed)
    lr = np.ones(len(n))
    pi = np.ones(len(n))
    eps = {}
    for s in np.unique(so):
        m = so == s
        if (sr == s).sum() < min_random:
            continue
        e, pt, pf = _fit_stratum(n[m], rn[sr == s], nmax=nmax)
        k = np.minimum(n[m], nmax)
        lr[m] = np.clip(pt[k] / pf[k], lr_min, lr_max)
        pi[m] = (1 - e) * pt[k] / ((1 - e) * pt[k] + e * pf[k])
        eps[int(s)] = (float(e), int(m.sum()))
    return {"n": n, "lr": lr, "pi": pi, "eps": eps}


def support_lr(ca, pa, cb, pb, W: float, *, n_random: int = 5, nmax: int = 8, lr_min: float = 0.05,
               lr_max: float = 20.0, seed: int = 0):
    """-> (n_support, lr) per contact."""
    rng = np.random.default_rng(seed)
    ca, pa, cb, pb = _canon(ca, pa, cb, pb)
    same = ca == cb
    key = np.char.add(np.char.add(ca, "|"), cb)
    allc, allp = np.r_[ca, cb], np.r_[pa, pb]
    lim = {c: (allp[allc == c].min(), allp[allc == c].max()) for c in np.unique(allc)}
    lo_a = np.array([lim[c][0] for c in ca]); hi_a = np.array([lim[c][1] for c in ca])
    lo_b = np.array([lim[c][0] for c in cb]); hi_b = np.array([lim[c][1] for c in cb])
    sep = np.where(same, pb - pa, -1)
    n_obs = np.zeros(len(pa), np.int64)
    trees = {}
    for k in np.unique(key):
        s = np.flatnonzero(key == k)
        trees[k] = cKDTree(np.c_[pa[s], pb[s]].astype(float))
        n_obs[s] = trees[k].query_ball_point(np.c_[pa[s], pb[s]].astype(float), W, p=np.inf, return_length=True) - 1
    # random locations: same chromosome pair and separation (cis), uniform position
    rk, rs, rn = [], [], []
    for _ in range(n_random):
        ra = lo_a + (rng.random(len(pa)) * (hi_a - lo_a + 1)).astype(np.int64)
        rb = np.where(same, ra + sep, lo_b + (rng.random(len(pa)) * (hi_b - lo_b + 1)).astype(np.int64))
        ok = ~same | (rb <= hi_a)
        for k in np.unique(key[ok]):
            s = np.flatnonzero(ok & (key == k))
            rn.append(trees[k].query_ball_point(np.c_[ra[s], rb[s]].astype(float), W, p=np.inf, return_length=True))
            rs.append(sep[s])
    rn = np.concatenate(rn) if rn else np.zeros(0, np.int64)
    rs = np.concatenate(rs) if rs else np.zeros(0, np.int64)

    def stratum(x):
        return np.where(x < 0, -1, np.floor(np.log2(np.maximum(x, W) / W))).astype(int)

    so, sr = stratum(sep), stratum(rs)
    lr = np.ones(len(pa))
    for s in np.unique(so):
        o = np.minimum(n_obs[so == s], nmax)
        r = np.minimum(rn[sr == s], nmax)
        if len(r) < 20:
            continue
        po = np.bincount(o, minlength=nmax + 1) + 0.5
        pr = np.bincount(r, minlength=nmax + 1) + 0.5
        lr[so == s] = (po / po.sum() / (pr / pr.sum()))[o]
    return n_obs, np.clip(lr, lr_min, lr_max)
