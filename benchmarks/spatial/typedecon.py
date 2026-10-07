"""Cell-type deconvolution of spot contact maps (PREREG §14): spots = mixtures of type profiles.

Model ("TD")
------------
Spot s holds N_s cis contacts on the bin pairs p of one resolution, y_s ~ Multinomial(N_s, pi_s) with

    pi_sp = sum_t a_st P_tp,      sum_p P_tp = 1,

a_s = the spot's contact share of each type (from RNA: the given composition A_s, optionally times a
learned per-type contact yield c_t and renormalised, optionally refined per spot), P_t = the contact
profile of type t (its normalised pseudo-bulk map, distance decay included).  Equivalent to Poisson
counts lambda_sp = N_s pi_sp with N_s fixed (KL-NMF with the spot factor known).

EM (exact, monotone in the penalised likelihood):

* E: r_stp = a_st P_tp / pi_sp;  expected type counts n_tp = sum_s y_sp r_stp, n_st = sum_p y_sp r_stp.
* M: P_tp  ∝  n_tp + kappa_t m_tp   (Dirichlet prior: mean m_t, strength kappa_t = shrink x sum_s N_s a_st)
     yield (``learn_yield``): c_t <- sum_s n_st / sum_s N_s A_st / (sum_u A_su c_u)  (MM, geometric mean 1)
     composition (``refine`` = rho < inf): a_st ∝ n_st + rho a0_st.

Prior mean m_t: ``pooled`` = the all-spot pooled profile; ``pooled_ps`` = the pooled profile rescaled per
separation to type t's current distance decay (shrinks the type-specific pattern, not its P(s)).

Spatially varying profiles (``groups``): after the global fit, each spot group g gets its own P_tg by
the same EM on its spots, with prior mean = the global P_t and strength ``group_shrink`` x its expected
contacts.

Baselines: :func:`dominant_pool` (every spot to its dominant type, pooled), :func:`nnls_profiles`
(least squares y_s ≈ N_s a_s P, P >= 0).  The random-composition control is TD with permuted rows of A
(``tissue.permuted_composition``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import scipy.sparse as sp


@dataclass
class TDParams:
    n_iter: int = 300
    tol: float = 1e-8              # stop when the relative log-likelihood change is below this
    shrink: float = 0.0            # kappa_t / expected contacts of type t
    prior_mean: str = "pooled"     # "pooled" | "pooled_ps"
    learn_yield: bool = False
    refine: float = np.inf         # rho of the composition prior; inf = composition fixed
    group_shrink: float = 1.0
    eps: float = 1e-300

    def to_dict(self) -> dict:
        d = asdict(self)
        d["refine"] = None if not np.isfinite(self.refine) else float(self.refine)
        return d


def _sep_index(pair_sep: np.ndarray) -> tuple[np.ndarray, int]:
    s = np.asarray(pair_sep, np.int64)
    return s, int(s.max()) + 1


def _ps_rescale(pooled: np.ndarray, P: np.ndarray, pair_sep) -> np.ndarray:
    """pooled profile rescaled per separation to each row of P's decay, normalised."""
    s, ns = _sep_index(pair_sep)
    dp = np.bincount(s, weights=pooled, minlength=ns)
    out = np.empty_like(P)
    for t in range(P.shape[0]):
        dt = np.bincount(s, weights=P[t], minlength=ns)
        f = np.where(dp > 0, dt / np.maximum(dp, 1e-300), 0.0)
        out[t] = pooled * f[s]
    return out / np.maximum(out.sum(1, keepdims=True), 1e-300)


class _Sparse:
    """Row / column indices of the non-zeros of Y (CSR) for the E-step."""

    def __init__(self, Y: sp.csr_matrix):
        Y = sp.csr_matrix(Y, dtype=np.float64)
        Y.sum_duplicates()
        self.Y = Y
        self.rows = np.repeat(np.arange(Y.shape[0]), np.diff(Y.indptr))
        self.cols = Y.indices
        self.y = Y.data
        self.N = np.asarray(Y.sum(1)).ravel()

    def pi(self, a: np.ndarray, P: np.ndarray, chunk: int = 2_000_000) -> np.ndarray:
        out = np.empty(len(self.y))
        for k in range(0, len(self.y), chunk):
            r, c = self.rows[k:k + chunk], self.cols[k:k + chunk]
            out[k:k + chunk] = np.einsum("nt,tn->n", a[r], P[:, c])
        return out

    def ratio(self, q: np.ndarray) -> sp.csr_matrix:
        return sp.csr_matrix((q, self.Y.indices, self.Y.indptr), shape=self.Y.shape)


def _normalise_rows(m: np.ndarray) -> np.ndarray:
    return m / np.maximum(m.sum(1, keepdims=True), 1e-300)


def fit_td(Y, A, *, params: TDParams | None = None, pair_sep=None, P0=None, prior=None,
           verbose: bool = False) -> dict:
    """Fit type profiles to spot counts ``Y`` (S x pairs) given compositions ``A`` (S x T).

    Returns ``P`` (T x pairs, rows sum to 1), ``a`` (effective contact shares used), ``yield``,
    ``loglik`` trace, ``n_type`` (expected contacts per type), ``params``.
    ``prior`` (T x pairs) overrides the prior mean (used for spatial groups).
    """
    p = params or TDParams()
    S = _Sparse(Y)
    A = _normalise_rows(np.asarray(A, float))
    T = A.shape[1]
    keep = S.N > 0
    pooled = np.asarray(S.Y.sum(0)).ravel()
    pooled = pooled / max(pooled.sum(), 1e-300)
    if p.prior_mean == "pooled_ps" and pair_sep is None:
        raise ValueError("prior_mean='pooled_ps' needs pair_sep")
    P = np.tile(pooled, (T, 1)) if P0 is None else _normalise_rows(np.array(P0, float))
    # tiny type-specific perturbation is not needed: the composition breaks the symmetry
    c = np.ones(T)
    a0 = A.copy()
    a = A.copy()
    ll_trace = []
    for it in range(p.n_iter):
        pi = S.pi(a, P)
        ll = float(np.sum(S.y * np.log(np.maximum(pi, p.eps))))
        ll_trace.append(ll)
        q = S.y / np.maximum(pi, p.eps)
        Q = S.ratio(q)
        QtA = np.asarray(Q.T @ a).T                 # (T, pairs): sum_s a_st q_sp
        n_tp = P * QtA                               # expected type counts per pair
        n_st = a * np.asarray(Q @ P.T)               # (S, T) expected type counts per spot
        # M-step: profiles
        expected = (S.N[:, None] * a).sum(0)         # expected contacts per type
        if p.shrink > 0:
            if prior is not None:
                m = prior
            elif p.prior_mean == "pooled_ps":
                m = _ps_rescale(pooled, P, pair_sep)
            else:
                m = np.tile(pooled, (T, 1))
            n_tp = n_tp + (p.shrink * expected)[:, None] * m
        P = _normalise_rows(n_tp)
        # M-step: yield / composition
        if p.learn_yield:
            denom = (S.N[keep, None] * A[keep] / (A[keep] @ c)[:, None]).sum(0)
            c = n_st[keep].sum(0) / np.maximum(denom, 1e-300)
            c = c / np.exp(np.mean(np.log(np.maximum(c, 1e-300))))
            a0 = _normalise_rows(A * c)
            if not np.isfinite(p.refine):
                a = a0
        if np.isfinite(p.refine):
            a = _normalise_rows(n_st + p.refine * a0)
        if verbose and it % 20 == 0:
            print(f"  it {it:4d} loglik {ll:.6e}")
        if it > 0 and abs(ll_trace[-1] - ll_trace[-2]) <= p.tol * abs(ll_trace[-2]):
            break
    return {"P": P, "a": a, "yield": c, "loglik": np.array(ll_trace), "n_iter": len(ll_trace),
            "n_type": (S.N[:, None] * a).sum(0), "params": p.to_dict()}


def fit_td_groups(Y, A, groups, *, params: TDParams | None = None, pair_sep=None) -> dict:
    """Global fit, then one profile set per spot group with the global profiles as prior mean."""
    p = params or TDParams()
    glob = fit_td(Y, A, params=p, pair_sep=pair_sep)
    groups = np.asarray(groups)
    out = {"global": glob, "groups": {}}
    for g in np.unique(groups):
        idx = np.flatnonzero(groups == g)
        pg = TDParams(**{**p.__dict__, "shrink": p.group_shrink, "learn_yield": False, "refine": np.inf})
        a_g = glob["a"][idx]
        fit = fit_td(Y[idx], a_g, params=pg, pair_sep=pair_sep, P0=glob["P"], prior=glob["P"])
        out["groups"][int(g) if np.issubdtype(type(g), np.integer) else g] = fit
    return out


# --------------------------------------------------------------------------- baselines

def dominant_pool(Y, A) -> dict:
    """Every spot to its dominant type; P_t = pooled counts of its spots (NaN row: never dominant)."""
    Y = sp.csr_matrix(Y)
    A = np.asarray(A, float)
    dom = A.argmax(1)
    T = A.shape[1]
    P = np.full((T, Y.shape[1]), np.nan)
    n = np.zeros(T)
    for t in range(T):
        idx = np.flatnonzero(dom == t)
        if len(idx):
            v = np.asarray(Y[idx].sum(0)).ravel()
            n[t] = v.sum()
            if v.sum() > 0:
                P[t] = v / v.sum()
    return {"P": P, "n_type": n, "n_spots": np.bincount(dom, minlength=T)}


def nnls_profiles(Y, A, n_iter: int = 500) -> dict:
    """min ||Y - W P||_F^2, P >= 0, W = N_s a_s (accelerated projected gradient); rows renormalised."""
    Y = sp.csr_matrix(Y, dtype=np.float64)
    A = _normalise_rows(np.asarray(A, float))
    N = np.asarray(Y.sum(1)).ravel()
    W = N[:, None] * A
    G = W.T @ W
    B = np.asarray(Y.T @ W).T                       # (T, pairs)
    L = float(np.linalg.eigvalsh(G).max())
    Ginv = np.linalg.pinv(G)
    P = np.maximum(Ginv @ B, 0)                     # unconstrained LS, clipped: start
    Z, Pold, tk = P.copy(), P.copy(), 1.0
    for _ in range(n_iter):
        P = np.maximum(Z - (G @ Z - B) / L, 0)
        tn = (1 + np.sqrt(1 + 4 * tk * tk)) / 2
        Z = P + ((tk - 1) / tn) * (P - Pold)
        Pold, tk = P, tn
    s = P.sum(1, keepdims=True)
    return {"P": np.where(s > 0, P / np.maximum(s, 1e-300), np.nan)}


def oracle_pool(type_counts: np.ndarray) -> dict:
    """True-origin pooling: (T, pairs) counts of the contacts that came from each type."""
    s = type_counts.sum(1, keepdims=True)
    return {"P": np.where(s > 0, type_counts / np.maximum(s, 1e-300), np.nan)}
