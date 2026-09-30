"""Stage ladder and restraint sets of the consensus reconstruction.

For every stage: the beads (valid bins), their adjacent-bin distance ``D_s``, and
the restraint table (bead pairs, target, bounds, weights, origin).  Everything
here is numpy / pandas; the dynamics run in the native engine.
"""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from ._contacts import balance_coo, balance_weights, cis_expected, fit_decay
from ._params import ConsensusParams

KINDS = ("backbone", "dense", "band", "long_cis", "trans", "carried")


def stage_ladder(final: int, p: ConsensusParams) -> List[int]:
    """Stage resolutions, coarse → fine, ending at ``final``."""
    if p.stage_resolutions is not None:
        r = [int(x) for x in p.stage_resolutions]
        if r[-1] != final:
            r = r + [final] if final < r[-1] else r
        if any(a <= b for a, b in zip(r, r[1:])):
            raise ValueError(f"stage_resolutions must decrease, got {r}")
        if any(x % final for x in r):
            raise ValueError(f"every stage resolution must be a multiple of the final resolution {final}: {r}")
        return r
    out = [int(final)]
    while out[-1] * p.stage_factor <= p.coarsest:
        out.append(out[-1] * p.stage_factor)
    return out[::-1]


@dataclass
class StagePixels:
    """Balanced contacts of one stage (upper triangle, i < j, observed pixels)."""

    res: int
    kind: str                       # "genome" (cis + trans, whole chromosomes) | "cis" (band only)
    bins: pd.DataFrame              # chrom, start, end (all bins of the modelled chromosomes)
    chrom_code: np.ndarray          # per bin
    valid: np.ndarray               # per bin
    i: np.ndarray
    j: np.ndarray
    n: np.ndarray                   # raw reads
    b: np.ndarray                   # balanced frequency
    expected: np.ndarray            # cis, by separation (bins)
    exp_trans: float
    exp_raw: np.ndarray             # expected raw reads per pair, cis, by separation
    exp_raw_trans: float
    max_sep: int                    # largest separation read (cis)
    balance: List[dict] = field(default_factory=list)
    seconds: float = 0.0


def _chrom_codes(bins: pd.DataFrame, chroms: Sequence[str]) -> np.ndarray:
    idx = {c: k for k, c in enumerate(chroms)}
    return np.array([idx[c] for c in bins["chrom"].astype(str)], dtype=np.int64)


def load_stage(source, res: int, chroms: Sequence[str], kind: str, max_sep: int, p: ConsensusParams) -> StagePixels:
    """Read and balance the contacts of one stage."""
    t0 = time.time()
    if kind == "genome":
        u, bins = source.genome(res, chroms)
        bins = bins.reset_index(drop=True)
        cc = _chrom_codes(bins, chroms)
        w, info = balance_weights(u, p.balance, p.min_coverage)
        c = u.tocoo()
        k = c.row < c.col
        i, j, n = c.row[k].astype(np.int64), c.col[k].astype(np.int64), c.data[k].astype(np.float64)
        infos = [dict(info, scope="genome")]
        sizes = np.bincount(cc, minlength=len(chroms))
        max_sep = int(sizes.max()) if len(sizes) else 0
    else:
        parts, bl, infos, ws = [], [], [], []
        off = 0
        for c_name in chroms:
            ii, jj, nn, b = source.cis(res, c_name, max_sep)
            w_c, info = balance_coo(ii, jj, nn, len(b), p.balance, p.min_coverage)
            infos.append(dict(info, scope=c_name))
            k = ii < jj
            parts.append((ii[k] + off, jj[k] + off, nn[k]))
            bl.append(b)
            ws.append(w_c)
            off += len(b)
        bins = pd.concat(bl, ignore_index=True)
        cc = _chrom_codes(bins, chroms)
        w = np.concatenate(ws)
        i = np.concatenate([x[0] for x in parts]).astype(np.int64)
        j = np.concatenate([x[1] for x in parts]).astype(np.int64)
        n = np.concatenate([x[2] for x in parts]).astype(np.float64)
    valid = np.isfinite(w)
    keep = valid[i] & valid[j] & (n > 0)
    i, j, n = i[keep], j[keep], n[keep]
    b = w[i] * w[j] * n
    cis = cc[i] == cc[j]
    sep = np.where(cis, j - i, 0)
    valid_by_chrom = [valid[cc == k] for k in range(len(chroms))]
    exp = cis_expected(sep[cis], b[cis], valid_by_chrom, max_sep)
    exp_raw = cis_expected(sep[cis], n[cis], valid_by_chrom, max_sep)
    if (~cis).any():
        nv = np.bincount(cc[valid], minlength=len(chroms)).astype(float)
        n_trans_pairs = (nv.sum() ** 2 - (nv ** 2).sum()) / 2
        exp_trans = float(b[~cis].sum() / max(n_trans_pairs, 1))
        exp_raw_trans = float(n[~cis].sum() / max(n_trans_pairs, 1))
    else:
        exp_trans = exp_raw_trans = float("nan")
    return StagePixels(res=int(res), kind=kind, bins=bins, chrom_code=cc, valid=valid, i=i, j=j, n=n, b=b,
                       expected=exp, exp_trans=exp_trans,
                       exp_raw=exp_raw, exp_raw_trans=exp_raw_trans, max_sep=int(max_sep), balance=infos,
                       seconds=time.time() - t0)


def random_per_bin(i: np.ndarray, j: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    """Mask of a uniform random subset: every bin keeps (about) ``k`` of its pairs."""
    return top_per_bin(i, j, rng.random(len(i)), k)


def top_per_bin(i: np.ndarray, j: np.ndarray, score: np.ndarray, k: int) -> np.ndarray:
    """Mask of pairs that are among the ``k`` highest-scoring pairs of bin i or of bin j."""
    if len(i) == 0 or k <= 0:
        return np.zeros(len(i), bool)
    order = np.argsort(-score, kind="stable")
    rank = np.empty(len(i), np.int64)
    ends = np.concatenate([i[order], j[order]])
    idx = np.concatenate([order, order])
    df = pd.DataFrame({"bin": ends, "pair": idx, "o": np.concatenate([np.arange(len(i))] * 2)})
    df = df.sort_values(["bin", "o"], kind="stable")
    df["r"] = df.groupby("bin").cumcount()
    best = df.groupby("pair")["r"].min()
    rank[best.index.to_numpy()] = best.to_numpy()
    return rank < k


@dataclass
class StageModel:
    """Beads and restraints of one stage (bead indices)."""

    res: int
    kind: str
    bins: pd.DataFrame
    bead_bin: np.ndarray            # bin index of every bead
    bead_chrom: np.ndarray          # chromosome code
    bead_pos: np.ndarray            # bin midpoint (bp)
    D: float                        # adjacent-bin distance
    radius: float
    rest: pd.DataFrame              # i, j, target, lo, hi, w_conf, w, n, oe, kind
    force_const: float
    band_bins: int
    f_nn: float
    info: dict = field(default_factory=dict)

    @property
    def n_beads(self) -> int:
        return len(self.bead_bin)

    def counts(self) -> Dict[str, int]:
        vc = self.rest["kind"].value_counts()
        return {k: int(vc.get(k, 0)) for k in KINDS}


def _rep_beads(prev: StageModel, cur_bins: pd.DataFrame, bead_bin: np.ndarray, bead_chrom: np.ndarray,
               bead_pos: np.ndarray) -> np.ndarray:
    """For every previous-stage bead the current bead nearest to its bin midpoint inside
    that bin (-1 if none)."""
    out = np.full(prev.n_beads, -1, np.int64)
    pb = prev.bins
    ps = pb["start"].to_numpy()[prev.bead_bin]
    pe = pb["end"].to_numpy()[prev.bead_bin]
    pm = (ps + pe) // 2
    for c in np.unique(prev.bead_chrom):
        pk = np.flatnonzero(prev.bead_chrom == c)
        ck = np.flatnonzero(bead_chrom == c)
        if not len(ck):
            continue
        pos = bead_pos[ck]
        k = np.searchsorted(pos, pm[pk])
        lo = np.clip(k - 1, 0, len(ck) - 1)
        hi = np.clip(k, 0, len(ck) - 1)
        pick = np.where(np.abs(pos[hi] - pm[pk]) < np.abs(pos[lo] - pm[pk]), hi, lo)
        inside = (pos[pick] >= ps[pk]) & (pos[pick] < pe[pk])
        out[pk[inside]] = ck[pick[inside]]
    return out


def build_stage(px: StagePixels, stage: int, final_res: int, prev_res: Optional[int], prev: Optional[StageModel],
                alpha: float, nu: float, p: ConsensusParams) -> StageModel:
    """Beads + restraints of one stage."""
    res = px.res
    D = (res / final_res) ** nu
    bead_bin = np.flatnonzero(px.valid)
    if not len(bead_bin):
        raise ValueError(f"stage {stage} ({res} bp): no valid bins")
    bead_of = np.full(len(px.bins), -1, np.int64)
    bead_of[bead_bin] = np.arange(len(bead_bin))
    bead_chrom = px.chrom_code[bead_bin]
    st = px.bins["start"].to_numpy()[bead_bin]
    en = px.bins["end"].to_numpy()[bead_bin]
    bead_pos = (st + en) // 2
    band = int(max(p.band_min_bins, np.ceil(p.band_factor * (prev_res / res)))) if prev_res else None
    f_nn = float(px.expected[1]) if len(px.expected) > 1 and np.isfinite(px.expected[1]) and px.expected[1] > 0 else \
        float(np.median(px.b[(px.chrom_code[px.i] == px.chrom_code[px.j]) & (px.j - px.i == 1)]))

    i, j, n, b = px.i, px.j, px.n, px.b
    cis = px.chrom_code[i] == px.chrom_code[j]
    sep = np.where(cis, j - i, -1)
    exp = np.where(cis, px.expected[np.clip(sep, 0, len(px.expected) - 1)], px.exp_trans)
    with np.errstate(invalid="ignore", divide="ignore"):
        oe = b / exp
    # a pair is *measurable* when the expected reads of its separation (or of trans pairs)
    # reach min_expected: selecting on the expectation, not on the observed count, avoids
    # keeping only the pairs that happened to get reads
    lam = np.where(cis, px.exp_raw[np.clip(sep, 0, len(px.exp_raw) - 1)], px.exp_raw_trans)
    meas = np.nan_to_num(lam) >= p.min_expected
    obs = n >= p.min_count
    rng = np.random.default_rng([p.seed, stage, 0xC0])
    use = np.zeros(len(i), bool)
    kind = np.full(len(i), "", dtype=object)
    dense = px.kind == "genome" and len(bead_bin) <= p.dense_max_bins
    trans_ok = p.use_trans and px.kind == "genome" and (dense or res >= p.trans_max_resolution)

    def add(mask, name):
        new = mask & ~use
        use[new] = True
        kind[new] = name

    if dense:
        add(cis & (sep >= 2) & meas & obs, "dense")
        if trans_ok:
            add(~cis & meas & obs, "dense")
        band = None
    else:
        band = band if band is not None else int(max(p.band_min_bins, 12))
        add(cis & (sep >= 2) & (sep <= band) & meas & obs, "band")
        far = cis & (sep > band)
        if px.kind == "cis":
            far &= sep <= p.long_cis_max_bins
        # enriched pairs (loops, compartment contacts): O/E >= oe_min with enough reads
        ci = np.flatnonzero(far & (oe >= p.oe_min) & (n >= p.long_min_count))
        add(np.isin(np.arange(len(i)), ci[top_per_bin(i[ci], j[ci], oe[ci], p.max_long_per_bin)]), "long_cis")
        # plus an unbiased sample of the measurable long-range pairs (distance scale)
        ci = np.flatnonzero(far & meas & obs & ~use)
        add(np.isin(np.arange(len(i)), ci[random_per_bin(i[ci], j[ci], p.long_sample_per_bin, rng)]), "long_cis")
        if trans_ok:
            ci = np.flatnonzero(~cis & (oe >= p.oe_min_trans) & (n >= p.long_min_count))
            add(np.isin(np.arange(len(i)), ci[top_per_bin(i[ci], j[ci], oe[ci], p.max_trans_per_bin)]), "trans")
            ci = np.flatnonzero(~cis & meas & obs & ~use)
            add(np.isin(np.arange(len(i)), ci[random_per_bin(i[ci], j[ci], p.trans_sample_per_bin, rng)]), "trans")
    k = np.flatnonzero(use)
    target = D * np.power(np.maximum(b[k] / f_nn, 1e-300), -1.0 / alpha)
    target = np.maximum(target, p.target_min * D)
    w_conf = n[k] / (n[k] + p.weight_n0)
    w_conf = np.where(cis[k], w_conf, w_conf * p.trans_weight)
    own = pd.DataFrame({"i": bead_of[i[k]], "j": bead_of[j[k]], "target": target, "lo": p.lower * target,
                        "hi": p.upper * target, "w_conf": w_conf, "n": n[k], "oe": oe[k], "kind": kind[k]})
    # backbone
    same = bead_chrom[1:] == bead_chrom[:-1]
    bi = np.flatnonzero(same)
    gap = (bead_bin[bi + 1] - bead_bin[bi]).astype(float)
    tb = D * gap ** nu
    bb = pd.DataFrame({"i": bi, "j": bi + 1, "target": tb, "lo": p.backbone_lower * tb, "hi": p.backbone_upper * tb,
                       "w_conf": p.backbone_weight, "n": np.nan, "oe": np.nan, "kind": "backbone"})
    parts = [bb, own]
    # carried
    n_carried_dropped = 0
    if prev is not None and p.carry and len(prev.rest):
        rep = _rep_beads(prev, px.bins, bead_bin, bead_chrom, bead_pos)
        r = prev.rest[prev.rest["kind"] != "backbone"]
        a, c = rep[r["i"].to_numpy()], rep[r["j"].to_numpy()]
        ok = (a >= 0) & (c >= 0) & (a != c)
        n_carried_dropped = int((~ok).sum())
        r = r[ok].copy()
        a, c = a[ok], c[ok]
        lo_, hi_ = np.minimum(a, c), np.maximum(a, c)
        # pairs of the band are measured at this stage; elsewhere the coarser estimate is
        # carried unless this stage restrains the same bead pair itself
        trans_c = bead_chrom[lo_] != bead_chrom[hi_]
        far = trans_c | (np.abs(bead_bin[hi_] - bead_bin[lo_]) > (band if band is not None else 1))
        key = lo_ * len(bead_bin) + hi_
        own_key = own["i"].to_numpy() * len(bead_bin) + own["j"].to_numpy()
        far &= ~np.isin(key, own_key)
        r = r[far]
        r["i"], r["j"] = lo_[far], hi_[far]
        r["w_conf"] = r["w_conf"] * p.carry_weight
        r["kind"] = "carried"
        parts.append(r[["i", "j", "target", "lo", "hi", "w_conf", "n", "oe", "kind"]])
    rest = pd.concat(parts, ignore_index=True)
    rest["i"] = rest["i"].astype(np.int64)
    rest["j"] = rest["j"].astype(np.int64)
    rel = (D / rest["hi"].to_numpy()) ** 2 if p.relative_error else 1.0
    rest["w"] = rest["w_conf"].to_numpy() * rel
    K = p.force_scale * len(bead_bin) / max(float(rest["w"].sum()), 1e-12)
    info = {"n_bins": int(len(px.bins)), "n_beads": int(len(bead_bin)), "dense": bool(dense), "band_bins": band,
            "f_nn": f_nn, "exp_trans": px.exp_trans, "exp_raw_nn": float(px.exp_raw[1]) if len(px.exp_raw) > 1 else None,
            "exp_raw_trans": px.exp_raw_trans, "carried_dropped": n_carried_dropped,
            "balance": px.balance, "seconds_load": px.seconds, "pixels": int(len(px.i))}
    return StageModel(res=res, kind=px.kind, bins=px.bins, bead_bin=bead_bin, bead_chrom=bead_chrom,
                      bead_pos=bead_pos.astype(np.int64), D=D, radius=0.5 * D, rest=rest, force_const=float(K),
                      band_bins=band, f_nn=f_nn, info=info)


def resolve_alpha_nu(p: ConsensusParams, pixels: Sequence[StagePixels], final_res: int) -> tuple:
    """alpha, nu and the decay fit (gamma) they come from."""
    fit_src = [x for x in pixels if x.kind == "genome"] or list(pixels)
    src = min(fit_src, key=lambda x: x.res)
    # the ladder connects separations from the final bin to the first stage's bin
    max_bp = min(p.ps_fit_max_bp, max(x.res for x in pixels))
    gamma, fit = fit_decay(src.expected, src.res, max_bp)
    if not np.isfinite(gamma):
        src = min(pixels, key=lambda x: x.res)
        gamma, fit = fit_decay(src.expected, src.res, max_bp)
    fit["stage_resolution"] = int(src.res)
    lo, hi = p.nu_bounds
    if p.alpha == "fit":
        if not np.isfinite(gamma):
            raise ValueError("alpha='fit': the contact decay could not be fitted")
        nu = p.nu_polymer if p.nu == "fit" else float(p.nu)
        alpha = gamma / nu
    else:
        alpha = float(p.alpha)
        if p.nu == "fit":
            if np.isfinite(gamma):
                nu = float(np.clip(gamma / alpha, lo, hi))
            else:
                warnings.warn("contact decay not fitted; nu = nu_polymer", RuntimeWarning, stacklevel=3)
                nu = p.nu_polymer
        else:
            nu = float(p.nu)
    return float(alpha), float(nu), {"gamma": gamma, **fit}


def engine_stage(sm: StageModel, stage: int, p: ConsensusParams) -> dict:
    """The dict ``uchrom_nucdyn.calc_consensus`` takes."""
    form = p.restraint_form
    if form == "lorentzian" and stage == 0 and not p.lorentzian_first_stage:
        form = "saturating"
    first = stage == 0
    return {
        "particle_size": float(sm.res),
        "radius": float(sm.radius),
        "chrom": sm.bead_chrom.astype(np.uint32),
        "pos": sm.bead_pos.astype(np.int64),
        "rest_i": sm.rest["i"].to_numpy(np.uint32),
        "rest_j": sm.rest["j"].to_numpy(np.uint32),
        "rest_lo": sm.rest["lo"].to_numpy(np.float64),
        "rest_hi": sm.rest["hi"].to_numpy(np.float64),
        "rest_w": sm.rest["w"].to_numpy(np.float64),
        "form": form,
        "force_const": float(sm.force_const),
        "temp_start": float(p.temp_start if first else p.refine_temp_start),
        "temp_end": float(p.temp_end),
        "temp_steps": int(p.temp_steps if first else p.refine_temp_steps),
        "dyn_steps": int(p.dyn_steps if first else p.refine_dyn_steps),
    }
