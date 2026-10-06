#!/usr/bin/env python
"""Spatial Hi-C spot compartments as mixtures of cell-type compartments (mouse cortex).

Question: is the A/B compartment state of a spatial Hi-C spot explained by the spot's cell-type composition, or is
there a position-dependent residual?  Main data: Guo et al. 2026 spatial Hi-C-RNA, mouse brain sections r1 / r2
(Hi-C and RNA from the same 20-um spots).  References: dissociated single cells with RNA + Hi-C in the same cell
(GAGE-seq, Paired Hi-C, scHiCAR).  Cross-protocol replication: Chen et al. 2026 spatial Hi-C, adult cortex 10 um
(Hi-C and RNA from adjacent sections).

Stages (``--stages``, default all, in this order):

  e1           reference compartment track: E1 of the Guo r1 bulk 1-Mb map (ICE in memory; the .mcool has no
               weights), oriented per chromosome with the published single-spot A/B (used ONLY for the sign).
  scores       linear, distance-centred compartment scores, kept per contact-distance band:
               per spot for Guo r1 / r2 (memory-mapped .npy), pooled per group (class x random half) for the
               references and per (layer x random quarter) for Chen.
  geometry     Guo cortex mask + relative cortical depth from RNA only (pia = tissue edge, white matter = arc of
               oligodendrocyte genes) and spot QC (edge rows, dead barcode columns, low-contact spots).
  composition  NNLS deconvolution of spot RNA (Guo spots; Chen RNA section) on 14 coarse classes, one run per
               reference.
  analysis     every number and the figure data: spatial_composition.npz / .json, written to the paper repository
               (<u-chrom-paper>/manuscripts/nmeth-bc/figures/results/, the Brief Communication's Fig. 2).

Linearity: a spot's score in bin i is s_i = N_i / D_i with N_i = sum_j C_ij v_ij, D_i = sum_j C_ij (cis partners j,
|i - j| >= 2 bins).  N and D are additive over cells, so a pool of spots / a spot made of several cells has the
contact-weighted mixture of their scores; the composition model  s(spot) ~ sum_k pi_k S_k  is linear.

PITFALLS (each is handled explicitly below; see the comments marked PITFALL):
  1. Bin layouts differ between files (the Guo maps list chr1, chr2, chrX, chr3, ...; the references and Chen use
     natural order, Chen has a different bin count).  Every per-bin array is mapped by (chrom, start) onto ONE
     canonical layout (the Guo r1 bulk 1-Mb bins) at scoring time.  Never compare arrays by position alone.
  2. The plain partner score (v_ij = e_j) is confounded by the contact-distance decay P(d): with shorter-range
     contacts a bin's partners are its neighbours, which share its compartment.  The main score is distance-centred,
     v_ij = e_j - mean(e_{i-d}, e_{i+d}) = (e_j - e_{2i-j}) / 2, whose expectation is 0 for ANY P(d).
  3. Guo arrays have QC problems: the first / last barcode row of each array holds 5-8x the median contacts, and r2 has
     a dead barcode column (x = 11, ~560 contacts / spot).  Spots on edge rows, in dead columns or with < 50k contacts
     are excluded.
  4. The published single-spot A/B (both studies) is Higashi-imputed (smoothed over similar spots); it is used only to
     orient E1, never as data.  Chen's Hi-C-side label-transfer scores are derived from the Hi-C itself and are not
     used as composition (circular).
  5. The Guo "mouse brain" sections are coronal sections through the dorsal hippocampus; the references have no
     hippocampal types, so analyses are restricted to the cortex strip (RNA-only mask).

Usage:
    python benchmarks/spatial_composition/spatial_composition.py [--data EXAMPLE_DATA] [--out CACHE] [--figdata DIR]
                                                                [--stages e1,scores,geometry,composition,analysis]
"""
from __future__ import annotations

from uchrom.datasets import data_dir
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------------------------------------------
# constants
# ----------------------------------------------------------------------------------------------------------------
BANDS = [(2, 3), (3, 6), (6, 12), (12, 25), (25, 1_000_000)]   # contact distance bands, in 1-Mb bins
DMAX = 300                                                      # distance histogram length (bins)
MIN_CONTACTS = 50_000                                           # Guo spot QC
CLASSES = ['L23IT', 'L45IT', 'L6IT', 'L5PT', 'NP', 'L6CT', 'Pvalb', 'Sst', 'CGE', 'Astro', 'Oligo', 'OPC', 'Micro',
           'Vasc']
EXN = ['L23IT', 'L45IT', 'L6IT', 'L5PT', 'NP', 'L6CT']          # excitatory neuron classes
GLIA = ['Astro', 'Oligo', 'OPC', 'Micro']
REF_NAMES = ['gage', 'paired', 'schicar']
SECTIONS = {'r1': 'mouse_brain_r1', 'r2': 'mouse_brain_r2'}
CHEN_LAYERS = ['Layer_I', 'Layer_II_III', 'Layer_IV', 'Layer_V', 'Layer_VI']
CHEN_POOLS = CHEN_LAYERS + ['CC']
NDEC = 10
SUP, DEEP = [1, 2, 3, 4], [7, 8, 9]                             # superficial / deep depth deciles for contrasts
# genes that dominate the Guo spot RNA through capture artefacts (Gm42418 alone is 16.5 % of UMIs) or are not
# informative for cell type; removed from the marker set of every deconvolution
ARTEFACT_GENES = {'Cdk8', 'Cmss1', 'Lars2', 'Malat1', 'Mir6236', 'Camk1d', 'Gphn', 'Meg3'}

CLASSMAP = {
    'gage': {'L2/3 IT CTX a': 'L23IT', 'L2/3 IT CTX b': 'L23IT', 'L2/3 IT CTX c': 'L23IT', 'L2/3 IT RSP': 'L23IT',
             'L2 IT RvPP': 'L23IT', 'L4 IT CTX': 'L45IT', 'L4/5 IT CTX': 'L45IT', 'L5 IT CTX': 'L45IT',
             'L5 IT RSP': 'L45IT', 'L6 IT CTX': 'L6IT', 'L5 PT CTX': 'L5PT', 'L5/6 NP CTX': 'NP',
             'L6 CT CTX a': 'L6CT', 'L6 CT CTX b': 'L6CT', 'L6b CTX': 'L6CT', 'Pvalb a': 'Pvalb', 'Pvalb b': 'Pvalb',
             'Sst a': 'Sst', 'Sst b': 'Sst', 'Vip': 'CGE', 'Lamp5': 'CGE', 'Sncg': 'CGE', 'Astro': 'Astro',
             'ODC': 'Oligo', 'OPC': 'OPC', 'Micro': 'Micro', 'VLMC': 'Vasc'},
    'paired': {'ITL23GL': 'L23IT', 'ITL45GL': 'L45IT', 'ITL5GL': 'L45IT', 'ITL6GL': 'L6IT', 'PTGL': 'L5PT',
               'NPGL': 'NP', 'CTGL': 'L6CT', 'PVGA': 'Pvalb', 'SSTGA': 'Sst', 'VIPGA': 'CGE', 'ASC': 'Astro',
               'OGC': 'Oligo', 'OPC': 'OPC', 'MGL': 'Micro', 'VLMC': 'Vasc'},
    'schicar': {'L23IT.1': 'L23IT', 'L23IT.2': 'L23IT', 'L23IT.3': 'L23IT', 'L45IT': 'L45IT', 'L5IT': 'L45IT',
                'L6IT': 'L6IT', 'PT': 'L5PT', 'L56NP': 'NP', 'L6CT': 'L6CT', 'Pvalb': 'Pvalb', 'Sst': 'Sst',
                'Vip': 'CGE', 'Lamp5': 'CGE', 'Astro': 'Astro', 'Oligo': 'Oligo', 'OPC': 'OPC', 'MGL': 'Micro',
                'Endo': 'Vasc', 'Peri': 'Vasc', 'LMC': 'Vasc'},
}


@dataclass
class Inputs:
    """Input locations, all relative to the data directory (uchrom.datasets.data_dir(); sources: apps/atlas/recipes/README.md)."""
    data: Path

    @property
    def guo_store(self):
        return self.data / 'spatial_hicrna/hicrna_mouse_brain.chromdata.zarr'

    @property
    def chen_store(self):
        return self.data / 'spatial_hic_chen2026/cortex_adult_10um.chromdata.zarr'

    def ref_store(self, ref):
        return self.data / {'gage': 'gageseq2024/gageseq_mouse_cortex.chromdata.zarr',
                            'paired': 'droplet_hic2024/paired_hic_mouse_cortex.chromdata.zarr',
                            'schicar': 'schicar_mop/schicar_mop.chromdata.zarr'}[ref]

    @staticmethod
    def ref_label_col(ref):
        # Paired Hi-C: the authors' predicted labels (snm3C atlas names) include SSTGA / ITL45GL, the raw ones do not
        return {'gage': 'cell_type', 'paired': 'cell_type_predicted', 'schicar': 'cell_type'}[ref]


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def read_store(path):
    from chromdata import ChromData
    return ChromData.read(path, backed=True)


def corr(a, b):
    a = np.asarray(a, float) - np.mean(a)
    b = np.asarray(b, float) - np.mean(b)
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum()))


def cov(a, b):
    return float(((a - a.mean()) * (b - b.mean())).mean())


def bin_keys(chrom, start):
    return pd.MultiIndex.from_arrays([np.asarray(chrom).astype(str), np.asarray(start).astype(np.int64)])


# ----------------------------------------------------------------------------------------------------------------
# stage e1
# ----------------------------------------------------------------------------------------------------------------
def e1_from_mcool(mcool, res=1_000_000, ice_iter=50):
    """First eigenvector of the O/E correlation per autosome of an UNBALANCED .mcool (ICE in memory).

    Returns (bins DataFrame, e) with e = NaN on chrX / chrY / chrM and on low-coverage bins."""
    import cooler
    c = cooler.Cooler(f'{mcool}::/resolutions/{res}')
    bins = c.bins()[['chrom', 'start', 'end']][:]
    e = np.full(len(bins), np.nan)
    for ch in c.chromnames:
        if ch in ('chrX', 'chrY', 'chrM'):
            continue
        lo, hi = c.extent(ch)
        m = c.matrix(balance=False).fetch(ch).astype(float)
        n = m.shape[0]
        np.fill_diagonal(m, 0)
        cov_ = m.sum(1)
        good = cov_ > np.percentile(cov_[cov_ > 0], 5) if (cov_ > 0).any() else cov_ > 0
        m[~good] = 0
        m[:, ~good] = 0
        for _ in range(ice_iter):                                  # ICE on the cis matrix of the chromosome
            r = m.sum(1)
            r = r / r[good].mean()
            r[~good] = 1
            m = m / r[:, None] / r[None, :]
        oe = np.zeros_like(m)
        for d in range(n):                                         # observed / expected by diagonal
            dg = np.diagonal(m, d)
            gg = good[: n - d] & good[d:]
            mu = dg[gg].mean() if gg.any() else 0
            if mu > 0:
                idx = np.arange(n - d)
                oe[idx, idx + d] = dg / mu
                oe[idx + d, idx] = dg / mu
        g = np.where(good)[0]
        sub = oe[np.ix_(g, g)]
        np.fill_diagonal(sub, 1.0)
        w, v = np.linalg.eigh(np.nan_to_num(np.corrcoef(sub)))
        e[lo + g] = v[:, -1]
    return bins, e


def stage_e1(inp: Inputs, out: Path):
    import anndata as ad
    cd = read_store(inp.guo_store)
    bins, e = e1_from_mcool(cd.linked_cool_path('bulk.mouse_brain_r1'))
    # orientation only: mean published ssA/B (500 kb, r1) per 1-Mb bin; sign per chromosome
    s = ad.read_h5ad(cd.resolve_link_path(cd.uns['linked_bin_matrices']['ssAB']['path']))
    mean = np.asarray(s.X.mean(0)).ravel()
    b500 = cd.bins.loc[s.var['bin_id'].to_numpy()]
    key = pd.Series(mean, index=bin_keys(b500['chrom'], (b500['start'].to_numpy() // 1_000_000) * 1_000_000))
    key = key.groupby(level=[0, 1]).mean()
    ref = key.reindex(bin_keys(bins['chrom'], bins['start'])).to_numpy()
    for ch, idx in bins.groupby('chrom', observed=True).indices.items():
        ok = np.isfinite(e[idx]) & np.isfinite(ref[idx])
        if ok.sum() > 5 and np.corrcoef(e[idx][ok], ref[idx][ok])[0, 1] < 0:
            e[idx] = -e[idx]
    ok = np.isfinite(e) & np.isfinite(ref)
    r_ssab = float(np.corrcoef(e[ok], ref[ok])[0, 1])
    # z-score per chromosome (s is linear in e, and partners are cis, so this only rescales each chromosome)
    ez = np.full_like(e, np.nan)
    chrom = bins['chrom'].astype(str).to_numpy()
    for ch in np.unique(chrom):
        m = (chrom == ch) & np.isfinite(e)
        if m.sum():
            ez[m] = (e[m] - e[m].mean()) / e[m].std()
    np.savez(out / 'e1.npz', e=ez, e_raw=e, chrom=chrom, start=bins['start'].to_numpy(), r_ssab=r_ssab,
             n_bins=int(ok.sum()))
    log(f'e1: r(E1, published ssA/B mean) = {r_ssab:.3f} over {ok.sum()} bins')


def load_e1(out: Path):
    d = np.load(out / 'e1.npz', allow_pickle=True)
    return d['e'], d['chrom'].astype(str), d['start']


# ----------------------------------------------------------------------------------------------------------------
# stage scores
# ----------------------------------------------------------------------------------------------------------------
def _band_lookup():
    """Band index per distance d < start of the last (open) band; -1 below 2 bins.  d beyond -> last band."""
    lut = np.full(BANDS[-1][0], -1, np.int64)
    for b, (lo, hi) in enumerate(BANDS[:-1]):
        lut[lo:hi] = b
    return lut


def _scool_context(scool, e_can, chrom_can, start_can):
    """Per-file context: e on the file's own bins, file-bin -> canonical-bin map, chromosome extents."""
    with h5py.File(scool, 'r') as f:
        chrom_ids = f['bins/chrom'][:]
        names = f['chroms/name'][:].astype(str)
        start = f['bins/start'][:]
    chrom = names[chrom_ids]
    # PITFALL 1: map by (chrom, start), never by position
    can = pd.Series(np.arange(len(start_can)), index=bin_keys(chrom_can, start_can))
    loc2can = can.reindex(bin_keys(chrom, start)).to_numpy()
    has = np.isfinite(loc2can)
    loc2can = np.where(has, loc2can, -1).astype(np.int64)
    e_loc = np.full(len(start), np.nan)
    e_loc[has] = e_can[loc2can[has]]
    lo = np.zeros(len(start), np.int64)
    hi = np.zeros(len(start), np.int64)
    for cid in np.unique(chrom_ids):
        ix = np.where(chrom_ids == cid)[0]
        lo[ix], hi[ix] = ix[0], ix[-1]
    return dict(chrom_ids=chrom_ids, e=e_loc, loc2can=loc2can, lo=lo, hi=hi, n_can=len(start_can))


def _cell_scores(b1, b2, cnt, ctx, lut):
    """Banded (num_plain, num_centred, den) on canonical bins, distance histogram and trans count of one cell."""
    cid, e, lo, hi = ctx['chrom_ids'], ctx['e'], ctx['lo'], ctx['hi']
    nb, B = len(e), len(BANDS)
    ok_e = np.isfinite(e)
    ef = np.nan_to_num(e)
    cis = cid[b1] == cid[b2]
    trans = float(cnt[~cis].sum())
    b1, b2, cnt = b1[cis], b2[cis], cnt[cis]
    d = b2 - b1                                                   # scool pixels are upper-triangular (d >= 0)
    dh = np.bincount(np.minimum(d, DMAX), weights=cnt, minlength=DMAX + 1)
    band = np.where(d < len(lut), lut[np.minimum(d, len(lut) - 1)], B - 1)
    band = np.where(d >= 2, band, -1)
    m = band >= 0
    b1, b2, cnt, band = b1[m], b2[m], cnt[m], band[m]
    nump = np.zeros(B * nb)
    numc = np.zeros(B * nb)
    den = np.zeros(B * nb)
    for anchor, partner in ((b1, b2), (b2, b1)):
        okp = ok_e[partner]
        # PITFALL 2 -- distance centring: the partner at distance d is compared with the mirror bin on the other
        # side of the anchor (2*anchor - partner, same chromosome).  v = e_j - mean(e_j, e_mirror) = (e_j - e_m)/2;
        # 0 when the mirror is off the chromosome or has no E1 (then mean = e_j).
        mirror = 2 * anchor - partner
        okm = (mirror >= lo[anchor]) & (mirror <= hi[anchor])
        mc = np.clip(mirror, 0, nb - 1)
        okm &= ok_e[mc]
        vc = np.where(okp & okm, (ef[partner] - ef[mc]) / 2, 0.0)
        idx = band * nb + anchor
        nump += np.bincount(idx[okp], weights=cnt[okp] * ef[partner[okp]], minlength=B * nb)
        den += np.bincount(idx[okp], weights=cnt[okp], minlength=B * nb)
        numc += np.bincount(idx, weights=cnt * vc, minlength=B * nb)
    out = []
    l2c = ctx['loc2can']
    keep = l2c >= 0
    for arr in (nump, numc, den):
        a = arr.reshape(B, nb)
        c_ = np.zeros((B, ctx['n_can']))
        c_[:, l2c[keep]] = a[:, keep]
        out.append(c_)
    return out[0], out[1], out[2], dh, trans


def _score_chunk(args):
    """Worker: score a chunk of cells.  mode 'cells' writes rows into memory-mapped arrays; mode 'groups' returns
    pooled sums per group index."""
    scool, names, rows, groups, ctx, mode, mm, n_groups = args
    lut = _band_lookup()
    B, nbc = len(BANDS), ctx['n_can']
    if mode == 'cells':
        A = {k: np.load(p, mmap_mode='r+') for k, p in mm.items()}
    else:
        G = {k: np.zeros((B, n_groups, nbc)) for k in ('nump', 'numc', 'den')}
    dhs = np.zeros((len(names), DMAX + 1), np.float32)
    trs = np.zeros(len(names), np.float32)
    with h5py.File(scool, 'r') as f:
        for k, n in enumerate(names):
            g = f[f'cells/{n}/pixels']
            res = _cell_scores(g['bin1_id'][:], g['bin2_id'][:], g['count'][:].astype(np.float64), ctx, lut)
            dhs[k], trs[k] = res[3], res[4]
            if mode == 'cells':
                for key, arr in zip(('nump', 'numc', 'den'), res[:3]):
                    A[key][:, rows[k], :] = arr
            elif groups[k] >= 0:
                for key, arr in zip(('nump', 'numc', 'den'), res[:3]):
                    G[key][:, groups[k], :] += arr
    if mode == 'cells':
        for a in A.values():
            a.flush()
        return rows, dhs, trs, None
    return rows, dhs, trs, G


def score_scool(scool, names, ctx, out_prefix=None, groups=None, n_groups=0, workers=8):
    """Score the cells ``names`` of a .scool.  With ``out_prefix``: per-cell arrays (B, n, bins) saved as
    <prefix>_{nump,numc,den}.npy (memory-mapped).  With ``groups`` (int per cell, -1 = skip): pooled sums."""
    n, B, nbc = len(names), len(BANDS), ctx['n_can']
    mode = 'cells' if out_prefix is not None else 'groups'
    mm = {}
    if mode == 'cells':
        for k in ('nump', 'numc', 'den'):
            p = f'{out_prefix}_{k}.npy'
            np.lib.format.open_memmap(p, mode='w+', dtype=np.float32, shape=(B, n, nbc)).flush()
            mm[k] = p
    chunks = np.array_split(np.arange(n), max(1, workers * 4))
    jobs = [(str(scool), [names[i] for i in ch], ch, None if groups is None else groups[ch], ctx, mode, mm, n_groups)
            for ch in chunks if len(ch)]
    dh = np.zeros((n, DMAX + 1), np.float32)
    tr = np.zeros(n, np.float32)
    G = {k: np.zeros((B, n_groups, nbc)) for k in ('nump', 'numc', 'den')} if mode == 'groups' else None
    with ProcessPoolExecutor(workers) as ex:
        for rows, dhs, trs, g in ex.map(_score_chunk, jobs):
            dh[rows], tr[rows] = dhs, trs
            if g is not None:
                for k in G:
                    G[k] += g[k]
    return dh, tr, G


def stage_scores(inp: Inputs, out: Path, workers: int, seed: int):
    import cooler
    e, chrom, start = load_e1(out)
    rng = np.random.default_rng(seed)
    # Guo spots: per-spot arrays
    cd = read_store(inp.guo_store)
    for s, sec in SECTIONS.items():
        scool = cd.load_linked_scool(key=f'per_spot.{sec}')['path']
        names = [x.split('/')[-1] for x in cooler.fileops.list_scool_cells(scool)]
        ctx = _scool_context(scool, e, chrom, start)
        t = time.time()
        dh, tr, _ = score_scool(scool, names, ctx, out_prefix=str(out / f'spots_{s}'), workers=workers)
        np.savez(out / f'spots_{s}_meta.npz', names=np.array(names), dh=dh, trans=tr)
        log(f'scores: Guo {s}: {len(names)} spots in {time.time() - t:.0f} s')
    # references: pooled per (class, random half)
    for ref in REF_NAMES:
        rc = read_store(inp.ref_store(ref))
        scool = rc.load_linked_scool(key='per_cell')['path']
        names = [x.split('/')[-1] for x in cooler.fileops.list_scool_cells(scool)]
        lab = rc.cells[inp.ref_label_col(ref)].astype(str).map(CLASSMAP[ref]).reindex(names).to_numpy()
        half = rng.integers(0, 2, len(names))
        kidx = pd.Series(np.arange(len(CLASSES)), index=CLASSES).reindex(lab).to_numpy()
        groups = np.where(np.isfinite(kidx), np.nan_to_num(kidx) * 2 + half, -1).astype(np.int64)
        ctx = _scool_context(scool, e, chrom, start)
        t = time.time()
        dh, tr, G = score_scool(scool, names, ctx, groups=groups, n_groups=2 * len(CLASSES), workers=workers)
        np.savez(out / f'ref_{ref}.npz', **G, ncell=np.bincount(groups[groups >= 0] // 2, minlength=len(CLASSES)),
                 dh_class=np.array([dh[groups // 2 == k].sum(0) if (groups // 2 == k).any() else np.zeros(DMAX + 1)
                                    for k in range(len(CLASSES))]))
        log(f'scores: {ref}: {len(names)} cells ({(groups >= 0).sum()} in classes) in {time.time() - t:.0f} s')
    # Chen: pooled per (region, random quarter); four quarters give three different split-half pairings
    ch = read_store(inp.chen_store)
    scool = ch.load_linked_scool(key='per_spot.Adult16_HiC')['path']
    names = [x.split('/')[-1] for x in cooler.fileops.list_scool_cells(scool)]
    regions = sorted(ch.cells['Region'].dropna().astype(str).unique())
    reg = ch.cells['Region'].astype(str).reindex(names).to_numpy()
    ridx = pd.Series(np.arange(len(regions)), index=regions).reindex(reg).to_numpy()
    quarter = rng.integers(0, 4, len(names))
    groups = np.where(np.isfinite(ridx), np.nan_to_num(ridx) * 4 + quarter, -1).astype(np.int64)
    ctx = _scool_context(scool, e, chrom, start)
    t = time.time()
    dh, tr, G = score_scool(scool, names, ctx, groups=groups, n_groups=4 * len(regions), workers=workers)
    np.savez(out / 'chen.npz', **G, regions=np.array(regions), names=np.array(names), dh=dh, trans=tr,
             n_spots=np.bincount(groups[groups >= 0], minlength=4 * len(regions)))
    log(f'scores: Chen: {len(names)} spots in {time.time() - t:.0f} s')


# ----------------------------------------------------------------------------------------------------------------
# stage geometry
# ----------------------------------------------------------------------------------------------------------------
OLIGO_GENES = ['Mbp', 'Plp1', 'Mobp', 'Mog', 'Cldn11', 'Mal', 'Trf', 'Cnp', 'Mag']


def cortex_geometry(x, y, olig_frac_smoothed, wm_quantile=0.80, min_gap=8, smooth_rows=7):
    """Cortex mask and relative depth on one section's spot grid (RNA only).

    pia = leftmost tissue spot of each grid row (the cortex strip runs along the left edge of the Guo sections);
    white matter = first pair of adjacent 'WM' spots (smoothed oligodendrocyte-gene fraction above the section's
    ``wm_quantile``) at least ``min_gap`` spots in from the pia, median-smoothed over ``smooth_rows`` rows;
    cortex = spots left of the WM boundary; depth = d_pia / (d_pia + d_wm) in [0, 1]."""
    from scipy.spatial import cKDTree
    wm = olig_frac_smoothed > np.quantile(olig_frac_smoothed, wm_quantile)
    df = pd.DataFrame({'x': x, 'y': y, 'wm': wm})
    xpia = df.groupby('y').x.min()
    xwm = {}
    for row, g in df.groupby('y'):
        w = g.set_index('x').wm
        xs = [xx for xx in sorted(w.index) if xx >= xpia[row] + min_gap and w.get(xx, False) and w.get(xx + 1, False)]
        xwm[row] = xs[0] if xs else np.nan
    xwm = pd.Series(xwm).rolling(smooth_rows, center=True, min_periods=3).median()
    cortex = np.array([xx < xwm.get(yy, np.nan) - 1 for xx, yy in zip(x, y)])
    xy = np.c_[x, y]
    dp = cKDTree(np.c_[xpia.values, xpia.index.values]).query(xy)[0]
    W = xwm.dropna()
    dw = cKDTree(np.c_[W.values, W.index.values]).query(xy)[0]
    depth = np.where(cortex, dp / (dp + dw), np.nan)
    return cortex, depth


def stage_geometry(inp: Inputs, out: Path):
    from scipy.spatial import cKDTree
    import anndata as ad
    cd = read_store(inp.guo_store)
    c = cd.cells
    a = ad.read_h5ad(cd.resolve_link_path(cd.uns['linked_anndata']['path']))
    a = a[c.index]
    X = a.X.tocsr()
    tot = np.asarray(X.sum(1)).ravel()
    gi = {g: i for i, g in enumerate(a.var_names)}
    ol = np.asarray(X[:, [gi[g] for g in OLIGO_GENES]].sum(1)).ravel()
    rows = []
    for s, sec in SECTIONS.items():
        m = np.where((c.section == sec).to_numpy())[0]
        x = c.centroid_x.to_numpy()[m].astype(int)
        y = c.centroid_y.to_numpy()[m].astype(int)
        nb = cKDTree(np.c_[x, y]).query_ball_point(np.c_[x, y], r=2.01)
        frac = np.array([ol[m][n].sum() / tot[m][n].sum() for n in nb])
        cortex, depth = cortex_geometry(x, y, frac)
        hc = c.hic_contacts.to_numpy()[m]
        # PITFALL 3 -- array QC: edge rows carry several-fold the median contacts; dead barcode columns (median
        # contacts < 5 % of the section median) and low-contact spots are dropped.
        edge = (y == y.min()) | (y == y.max())
        colmed = pd.Series(hc).groupby(x).median()
        dead_cols = colmed.index[colmed < 0.05 * np.median(hc)].to_numpy()
        dead = np.isin(x, dead_cols)
        qc = (hc >= MIN_CONTACTS) & ~edge & ~dead
        rows.append(pd.DataFrame({'cell_id': c.index[m], 'section': sec, 'x': x, 'y': y,
                                  'img_x': c.image_centroid_x.to_numpy()[m], 'img_y': c.image_centroid_y.to_numpy()[m],
                                  'hic_contacts': hc, 'wm_frac': frac, 'cortex_raw': cortex, 'qc': qc,
                                  'edge_row': edge, 'dead_col': dead, 'cortex': cortex & qc, 'depth': depth}))
        log(f'geometry: {sec}: cortex {cortex.sum()} spots, after QC {(cortex & qc).sum()}; edge-row spots '
            f'{edge.sum()} (median contacts {np.median(hc[edge]):.0f} vs {np.median(hc[~edge]):.0f}); '
            f'dead columns {dead_cols.tolist()}')
    pd.concat(rows).set_index('cell_id').to_parquet(out / 'geometry.parquet')


# ----------------------------------------------------------------------------------------------------------------
# stage composition
# ----------------------------------------------------------------------------------------------------------------
def ref_rna_profiles(inp: Inputs, ref):
    """Class profiles of a reference's RNA: mean per-cell UMI proportions, detection rate, median UMI per cell."""
    import anndata as ad
    cd = read_store(inp.ref_store(ref))
    c = cd.cells
    a = ad.read_h5ad(cd.resolve_link_path(cd.uns['linked_anndata']['path']))
    a = a[c.index]
    cls = c[inp.ref_label_col(ref)].astype(str).map(CLASSMAP[ref])
    keep = cls.notna().to_numpy()
    X = a.X.tocsr()[keep].astype(np.float64)
    cls = cls[keep].to_numpy()
    tot = np.asarray(X.sum(1)).ravel()
    import scipy.sparse as sp
    P = sp.diags(1 / tot) @ X
    K = len(CLASSES)
    mu, frac = np.zeros((K, X.shape[1])), np.zeros((K, X.shape[1]))
    umi, ncell = np.zeros(K), np.zeros(K, int)
    for k, t in enumerate(CLASSES):
        m = cls == t
        ncell[k] = m.sum()
        mu[k] = np.asarray(P[m].mean(0)).ravel()
        frac[k] = np.asarray((X[m] > 0).mean(0)).ravel()
        umi[k] = np.median(tot[m])
    return pd.Index(a.var_names), mu, frac, umi, ncell


def select_markers(mu, frac, n=200, genes_ok=None):
    """Top-n genes per class by log2 fold change over the mean of the other classes (detected in >= 10 % of the
    class's cells)."""
    eps = 1e-6
    sel = set()
    for k in range(mu.shape[0]):
        lfc = np.log2((mu[k] + eps) / (np.delete(mu, k, 0).mean(0) + eps))
        ok = (frac[k] >= 0.1) & (mu[k] > 2e-5)
        if genes_ok is not None:
            ok &= genes_ok
        idx = np.where(ok)[0]
        sel.update(idx[np.argsort(-lfc[idx])[:n]].tolist())
    return np.array(sorted(sel))


def wnnls(A, y, iters=3):
    """Poisson-weighted NNLS by iterative reweighting (weights 1 / sqrt(fit + 1))."""
    from scipy.optimize import nnls
    w = np.ones(len(y))
    for _ in range(iters):
        b, _ = nnls(A * w[:, None], y * w)
        fit = A @ b
        w = 1 / np.sqrt(fit + 1.0)
    return b, fit


def deconvolve(Y, M, bulk):
    """Deconvolve spot counts Y (spots x genes) on class profiles M (genes x classes).  Gene platform factors
    gamma_g = bulk / fit(bulk) (RCTD-like) from the pseudo-bulk of the reference tissue; genes the reference cannot
    explain (gamma outside [0.1, 10] or < 20 counts) are dropped.  Returns UMI masses (spots x classes), kept genes."""
    b, fit = wnnls(M, bulk)
    ratio = bulk / np.maximum(fit, 1e-9)
    gok = (ratio > 0.1) & (ratio < 10) & (bulk >= 20)
    Mg = M[gok] * ratio[gok][:, None]
    Yk = Y[:, gok]
    B = np.zeros((len(Y), M.shape[1]))
    for i in range(len(Y)):
        B[i] = wnnls(Mg, Yk[i])[0]
    return B, gok


def _composition_job(args):
    inp, out, ref, target = args
    import anndata as ad
    genes_r, mu, frac, umi, ncell = ref_rna_profiles(inp, ref)
    if target == 'guo':
        cd = read_store(inp.guo_store)
        c = cd.cells
        geo = pd.read_parquet(out / 'geometry.parquet').reindex(c.index)
        groups = [(sec, (c.section == sec).to_numpy(), (c.section == sec).to_numpy() & geo.cortex.fillna(False).to_numpy())
                  for sec in SECTIONS.values()]
    else:
        cd = read_store(inp.chen_store)
        c = cd.cells[cd.cells.assay == 'rna']
        lay = c.Region.astype(str).str.startswith('Layer').to_numpy()
        groups = [('Adult15_RNA', np.ones(len(c), bool), lay)]
    a = ad.read_h5ad(cd.resolve_link_path(cd.uns['linked_anndata']['path']))
    a = a[c.index]
    gs = pd.Index(a.var_names)
    common = genes_r.intersection(gs[~gs.duplicated()])
    mu_c, frac_c = mu[:, genes_r.get_indexer(common)], frac[:, genes_r.get_indexer(common)]
    bad = np.array([g.startswith(('mt-', 'Gm')) or g in ARTEFACT_GENES for g in common])
    mk = select_markers(mu_c, frac_c, n=200, genes_ok=~bad)
    M = mu_c[:, mk].T
    Xs = a.X.tocsr()[:, gs.get_indexer(common)[mk]].astype(np.float64).toarray()
    tot = np.asarray(a.X.sum(1)).ravel()
    res = []
    for name, m, mref in groups:
        B, gok = deconvolve(Xs[m], M, Xs[mref].sum(0))
        df = pd.DataFrame(B, index=c.index[m], columns=[f'umi_{t}' for t in CLASSES])
        cs = B / umi[None, :]
        for k, t in enumerate(CLASSES):
            df[f'us_{t}'] = B[:, k] / np.maximum(B.sum(1), 1e-12)                       # UMI share (main)
            df[f'cs_{t}'] = cs[:, k] / np.maximum(cs.sum(1), 1e-12)                     # cell share
        df['marker_umi'] = Xs[m][:, gok].sum(1)
        df['umi'] = tot[m]
        res.append(df)
    out_df = pd.concat(res)
    if target == 'chen':
        out_df['Region'] = c.Region.astype(str).reindex(out_df.index).to_numpy()
    out_df.to_parquet(out / f'comp_{target}_{ref}.parquet')
    return ref, target, len(mk), int(gok.sum()), ncell.tolist()


def stage_composition(inp: Inputs, out: Path, workers: int):
    jobs = [(inp, out, ref, target) for ref in REF_NAMES for target in ('guo', 'chen')]
    with ProcessPoolExecutor(min(workers, len(jobs))) as ex:
        for ref, target, nm, nk, ncell in ex.map(_composition_job, jobs):
            log(f'composition: {target} with {ref}: {nm} markers, {nk} kept after platform factors; '
                f'reference cells per class {dict(zip(CLASSES, ncell))}')


# ----------------------------------------------------------------------------------------------------------------
# stage analysis
# ----------------------------------------------------------------------------------------------------------------
class Numbers:
    """Key numbers with a description of how each was computed (written to the JSON)."""

    def __init__(self):
        self.d = {}

    def add(self, key, value, desc):
        if isinstance(value, (np.floating, np.integer)):
            value = value.item()
        if isinstance(value, np.ndarray):
            value = value.tolist()
        if isinstance(value, float):
            value = round(value, 4)
        self.d[key] = {'value': value, 'description': desc}
        return value


def collapse(arrs, w, rows=None, cols=None):
    """Fixed-weight sum over distance bands: (N, D) from banded (B, n, bins) arrays (rows / cols subset)."""
    N = D = None
    for b, wb in enumerate(w):
        nb_ = np.asarray(arrs['num'][b] if rows is None else arrs['num'][b][rows], dtype=np.float64)
        db_ = np.asarray(arrs['den'][b] if rows is None else arrs['den'][b][rows], dtype=np.float64)
        if cols is not None:
            nb_, db_ = nb_[..., cols], db_[..., cols]
        N = wb * nb_ if N is None else N + wb * nb_
        D = wb * db_ if D is None else D + wb * db_
    return N, D


def proj(M, v):
    """Projection of v (centred) on the span of the (centred) rows of M."""
    Q, _ = np.linalg.qr((M - M.mean(1, keepdims=True)).T)
    v = v - v.mean()
    return Q @ (Q.T @ v)


def zscore(v):
    return (v - np.nanmean(v)) / np.nanstd(v)


class Section:
    """Guo section data restricted to the canonical analysis bins."""

    def __init__(self, out, s, w, okb, score, geo):
        meta = np.load(out / f'spots_{s}_meta.npz', allow_pickle=True)
        self.s, self.sec = s, SECTIONS[s]
        self.names = meta['names']
        arrs = {'num': np.load(out / f'spots_{s}_{"numc" if score == "centred" else "nump"}.npy', mmap_mode='r'),
                'den': np.load(out / f'spots_{s}_den.npy', mmap_mode='r')}
        g = geo.reindex(self.names)
        self.g = g
        self.cx = np.where(g.cortex.fillna(False).to_numpy())[0]
        self.wm = np.where(((g.wm_frac > g.wm_frac.quantile(0.93)) & ~g.cortex_raw.astype(bool) & g.qc.astype(bool)).to_numpy())[0]
        cols = np.where(okb)[0]
        N, D = collapse(arrs, w, rows=self.cx, cols=cols)
        self.N, self.D = N, D
        self.sbar = N.sum(0) / D.sum(0)
        Nw, Dw = collapse(arrs, w, rows=self.wm, cols=cols)
        self.wm_pool = Nw.sum(0) / Dw.sum(0)
        self.depth = g.depth.to_numpy()[self.cx]
        self.dec = np.minimum((self.depth * NDEC).astype(int), NDEC - 1)
        self.pools = [np.where(self.dec == i)[0] for i in range(NDEC)]
        self.delta = np.array([N[ix].sum(0) / D[ix].sum(0) - self.sbar for ix in self.pools])
        self.ids = self.names[self.cx]

    def comp(self, out, ref, share='us', rows='cx'):
        c = pd.read_parquet(out / f'comp_guo_{ref}.parquet')
        ids = {'cx': self.ids, 'wm': self.names[self.wm]}[rows]
        return c.reindex(ids)[[f'{share}_{t}' for t in CLASSES]].fillna(0).to_numpy()

    def halves(self, rng, nrep=20):
        """Random split halves of the spots of every depth decile: list over reps of list over deciles of (A, B)."""
        H = []
        for _ in range(nrep):
            hh = []
            for ix in self.pools:
                p_ = rng.permutation(ix)
                hh.append((p_[: len(p_) // 2], p_[len(p_) // 2:]))
            H.append(hh)
        return H


def explained_block(sec: Section, P, S, H, rng, nperm=200):
    """Composition model over depth deciles with one slope; reproducible variance from split halves (each half
    predicted from its own spots' composition).  Returns a dict of statistics, the residual and nulls (class labels
    of the reference profiles permuted)."""
    N, D, sbar = sec.N, sec.D, sec.sbar
    dA = np.array([[N[A].sum(0) / D[A].sum(0) - sbar for A, _ in hh] for hh in H])     # (rep, dec, bins)
    dB = np.array([[N[B].sum(0) / D[B].sum(0) - sbar for _, B in hh] for hh in H])
    PA = np.array([[P[A].mean(0) for A, _ in hh] for hh in H])                         # (rep, dec, K)
    PB = np.array([[P[B].mean(0) for _, B in hh] for hh in H])
    Pd = np.array([P[ix].mean(0) for ix in sec.pools])
    Pm = P.mean(0)

    def stats(S_):
        Sbar = Pm @ S_
        Dl = Pd @ S_ - Sbar
        b = (sec.delta * Dl).sum() / (Dl ** 2).sum()
        RA = dA - b * (PA @ S_ - Sbar)
        RB = dB - b * (PB @ S_ - Sbar)
        cRA = RA - RA.mean(-1, keepdims=True)
        cRB = RB - RB.mean(-1, keepdims=True)
        v_res = (cRA * cRB).mean(-1)                                                  # (rep, dec)
        cA = dA - dA.mean(-1, keepdims=True)
        cB = dB - dB.mean(-1, keepdims=True)
        v_obs = (cA * cB).mean(-1)
        con_o = sec.delta[SUP].mean(0) - sec.delta[DEEP].mean(0)
        con_p = Dl[SUP].mean(0) - Dl[DEEP].mean(0)
        return dict(slope=b, explained=1 - v_res.sum(1).mean() / v_obs.sum(1).mean(), r_all=corr(sec.delta.ravel(), Dl.ravel()),
                    r_contrast=corr(con_o, con_p), v_res=v_res, v_obs=v_obs, Dl=Dl, RA=RA, RB=RB)

    st = stats(S)
    nulls = np.array([[v for k, v in stats(S[rng.permutation(len(S))]).items() if k in ('explained', 'r_all', 'r_contrast')]
                      for _ in range(nperm)])
    st['null_explained'], st['null_r_all'], st['null_r_contrast'] = nulls[:, 0], nulls[:, 1], nulls[:, 2]
    cA = dA[:, SUP].mean(1) - dA[:, DEEP].mean(1)
    cB = dB[:, SUP].mean(1) - dB[:, DEEP].mean(1)
    st['rel_contrast'] = np.mean([corr(a, b) for a, b in zip(cA, cB)])
    st['rel_dec'] = np.array([[corr(dA[r, i], dB[r, i]) for i in range(NDEC)] for r in range(len(H))]).mean(0)
    st['rel_resid_dec'] = np.array([[corr(st['RA'][r, i], st['RB'][r, i]) for i in range(NDEC)] for r in range(len(H))]).mean(0)
    R = sec.delta - st['slope'] * st['Dl']
    st['resid'] = R
    st['resid_contrast'] = R[SUP].mean(0) - R[DEEP].mean(0)
    rcA = st['RA'][:, SUP].mean(1) - st['RA'][:, DEEP].mean(1)
    rcB = st['RB'][:, SUP].mean(1) - st['RB'][:, DEEP].mean(1)
    st['resid_contrast_halves'] = (rcA, rcB)
    return st


def spot_axes(sec: Section, P, S, rng, nperm=500):
    """Per-spot projections on two class-difference axes: Hi-C from the spot's own contacts (h) vs RNA prediction (c).
    h = sum_i D_i delta_i z_i / sum_i D_i z_i^2 (delta = spot score - cortex pool), c = (Delta . z)/(z . z) with
    Delta = sum_k pi_k (S_k - Sbar).  Also the correlation within depth deciles (decile means removed) and nulls from
    permuting spots (within deciles for the partial)."""
    N, D, sbar = sec.N, sec.D, sec.sbar
    delta = np.where(D > 0, N / np.maximum(D, 1e-12), sbar) - sbar
    valid = P.sum(1) > 0
    Sbar = P[valid].mean(0) @ S
    Z = S - Sbar
    ki = {t: i for i, t in enumerate(CLASSES)}
    axes = {'glia_neuron': Z[[ki[t] for t in GLIA]].mean(0) - Z[[ki[t] for t in EXN]].mean(0),
            'L23IT_L6CT': Z[ki['L23IT']] - Z[ki['L6CT']]}
    res = {}
    for name, z in axes.items():
        h = (D * delta * z).sum(1) / (D * z * z).sum(1)
        c = (P @ Z @ z) / (z @ z)
        r = corr(h[valid], c[valid])
        null = np.array([corr(h[valid], rng.permutation(c[valid])) for _ in range(nperm)])
        hr = h - pd.Series(h).groupby(sec.dec).transform('mean').to_numpy()
        cr = c - pd.Series(c).groupby(sec.dec).transform('mean').to_numpy()
        rp = corr(hr[valid], cr[valid])
        nullp = []
        for _ in range(nperm):
            cp = cr.copy()
            for d_ in range(NDEC):
                ix = np.where(valid & (sec.dec == d_))[0]
                cp[ix] = cr[rng.permutation(ix)]
            nullp.append(corr(hr[valid], cp[valid]))
        res[name] = dict(obs=h, pred=c, r=r, null_sd=null.std(), r_within=rp, null_within_sd=np.std(nullp))
    Dl = P @ Z
    vi = np.where(valid)[0]
    rp = np.array([corr(delta[i], Dl[i]) for i in vi])
    rn = np.array([corr(delta[i], Dl[j]) for i, j in zip(vi, rng.permutation(vi))])
    res['pattern'] = dict(mean_r=rp.mean(), mean_null=rn.mean(), frac_above=float((rp > rn).mean()))
    return res


def decile_projection(sec: Section, P, S, rng, nboot=200):
    """Depth-decile projections of the observed and predicted deviations on the L2/3 IT - L6 CT fingerprint axis
    z = S_L23IT - S_L6CT:  o_g = delta_g . z / z.z,  p_g = Delta_g . z / z.z.  Bootstrap over spots within deciles."""
    ki = {t: i for i, t in enumerate(CLASSES)}
    z = S[ki['L23IT']] - S[ki['L6CT']]
    z = z / (z @ z)
    Sbar = P.mean(0) @ S
    N, D, sbar = sec.N, sec.D, sec.sbar
    o = np.array([(N[ix].sum(0) / D[ix].sum(0) - sbar) @ z for ix in sec.pools])
    p = np.array([(P[ix].mean(0) @ S - Sbar) @ z for ix in sec.pools])
    bo, bp = [], []
    for _ in range(nboot):
        sel = [rng.choice(ix, len(ix)) for ix in sec.pools]
        bo.append([(N[ix].sum(0) / D[ix].sum(0) - sbar) @ z for ix in sel])
        bp.append([(P[ix].mean(0) @ S - Sbar) @ z for ix in sel])
    return dict(obs=o, pred=p, obs_se=np.std(bo, 0), pred_se=np.std(bp, 0), slope_axis=float((o @ p) / (p @ p)),
                depth_mean=np.array([sec.depth[ix].mean() for ix in sec.pools]), n=np.array([len(ix) for ix in sec.pools]))


def chen_block(out, w, okb, S, comp, rng, nperm=300):
    """Chen replication.  Hi-C pooled per anatomical layer ('Region'); composition = mean deconvolved composition of
    the RNA section's spots of the same layer; cortex mean weighted by the Hi-C spot counts per layer.  Split halves
    from four random quarters (three pairings)."""
    ch = dict(np.load(out / 'chen.npz', allow_pickle=True))          # load once (npz members re-read on access)
    regions = list(ch['regions'])
    cols = np.where(okb)[0]
    Nw = np.tensordot(w, ch['numc'], axes=(0, 0))[:, cols]           # (groups, bins), band weights applied
    Dw = np.tensordot(w, ch['den'], axes=(0, 0))[:, cols]

    def pool(region, quarters):
        gi = [regions.index(region) * 4 + q for q in quarters]
        return Nw[gi].sum(0), Dw[gi].sum(0)

    ND = {r: pool(r, [0, 1, 2, 3]) for r in regions}
    ctxN = sum(ND[L][0] for L in CHEN_LAYERS)
    ctxD = sum(ND[L][1] for L in CHEN_LAYERS)
    okc = ctxD > 0
    sbar = np.where(okc, ctxN / np.where(okc, ctxD, 1), 0)
    pairs = [([0, 1], [2, 3]), ([0, 2], [1, 3]), ([0, 3], [1, 2])]
    obs, halves = {}, {}
    for L in CHEN_POOLS:
        N, D = ND[L]
        obs[L] = np.where(D > 0, N / np.where(D > 0, D, 1), sbar) - sbar
        hh = []
        for qa, qb in pairs:
            (NA, DA), (NB, DB) = pool(L, qa), pool(L, qb)
            hh.append((np.where(DA > 0, NA / np.where(DA > 0, DA, 1), sbar) - sbar,
                       np.where(DB > 0, NB / np.where(DB > 0, DB, 1), sbar) - sbar))
        halves[L] = hh
    n_hic = {r: int(ch['n_spots'][regions.index(r) * 4: regions.index(r) * 4 + 4].sum()) for r in regions}
    Pm = comp.groupby('Region')[[f'us_{t}' for t in CLASSES]].mean()
    nh = np.array([n_hic[L] for L in CHEN_LAYERS])
    Pctx = (Pm.loc[CHEN_LAYERS].to_numpy() * nh[:, None]).sum(0) / nh.sum()

    def preds(S_):
        return {L: (Pm.loc[L].to_numpy() - Pctx) @ S_ for L in CHEN_POOLS}

    pr = preds(S)
    Ob = np.array([obs[L][okc] for L in CHEN_LAYERS])
    Pr = np.array([pr[L][okc] for L in CHEN_LAYERS])
    b = (Ob * Pr).sum() / (Pr ** 2).sum()
    V_rep = np.mean([sum(cov(halves[L][p][0][okc], halves[L][p][1][okc]) for L in CHEN_LAYERS) for p in range(3)])
    V_res = np.mean([sum(cov(halves[L][p][0][okc] - b * pr[L][okc], halves[L][p][1][okc] - b * pr[L][okc])
                         for L in CHEN_LAYERS) for p in range(3)])
    r_all = corr(Ob.ravel(), Pr.ravel())
    nulls = []
    for _ in range(nperm):
        prp = preds(S[rng.permutation(len(S))])
        nulls.append(corr(Ob.ravel(), np.array([prp[L][okc] for L in CHEN_LAYERS]).ravel()))
    nulls = np.array(nulls)
    per = {}
    for L in CHEN_POOLS:
        sh = np.mean([corr(a[okc], b_[okc]) for a, b_ in halves[L]])
        per[L] = dict(r=corr(obs[L][okc], pr[L][okc]), split_half=sh, ceiling=float(np.sqrt(max(2 * sh / (1 + sh), 0))),
                      n_hic=n_hic[L], n_rna=int((comp.Region == L).sum()))
    con = lambda d: (d['Layer_II_III'] + d['Layer_IV']) / 2 - (d['Layer_V'] + d['Layer_VI']) / 2
    co, cp = con(obs), con(pr)
    cA = con({L: halves[L][0][0] for L in CHEN_LAYERS[1:]})
    cB = con({L: halves[L][0][1] for L in CHEN_LAYERS[1:]})
    bc = (co[okc] * cp[okc]).sum() / (cp[okc] ** 2).sum()
    cr = np.where(okc, co - bc * cp, np.nan)
    return dict(per=per, r_all=r_all, null_r=nulls, p=float((np.sum(nulls >= r_all) + 1) / (nperm + 1)),
                null95=float(np.percentile(nulls, 95)), slope=b, explained=1 - V_res / V_rep,
                r_contrast=corr(co[okc], cp[okc]), rel_contrast=corr(cA[okc], cB[okc]), resid_contrast=cr, okc=okc,
                n_hic=n_hic)


def stage_analysis(inp: Inputs, out: Path, figdir: Path, seed: int):
    e, chrom, start = load_e1(out)
    geo = pd.read_parquet(out / 'geometry.parquet')
    NB = Numbers()
    F = {}                                                       # figure arrays
    NB.add('e1_vs_published_ssab_r', float(np.load(out / 'e1.npz')['r_ssab']),
           'Pearson r of the reference E1 (Guo r1 bulk, 1 Mb, ICE in memory) with the mean published ssA/B of r1 per 1-Mb '
           'bin; the ssA/B is used only for the sign of each chromosome')
    # band weights: equal contribution of each distance band in the Guo r1 cortex pool
    meta1 = np.load(out / 'spots_r1_meta.npz', allow_pickle=True)
    cx1 = np.where(geo.reindex(meta1['names']).cortex.fillna(False).to_numpy())[0]
    den1 = np.load(out / 'spots_r1_den.npy', mmap_mode='r')
    tot_b = np.array([np.asarray(den1[b][cx1], dtype=np.float64).sum() for b in range(len(BANDS))])
    w = tot_b.sum() / tot_b / len(BANDS)
    NB.add('band_weights', w, 'fixed weights of the distance bands 2-3, 3-6, 6-12, 12-25, >=25 Mb so that each band '
           'contributes equally to the summed den of the Guo r1 cortex pool')
    # reference class profiles (centred score, band weights)
    refs = {}
    for ref in REF_NAMES:
        r = np.load(out / f'ref_{ref}.npz')
        K = len(CLASSES)
        Nk = sum(w[b] * r['numc'][b] for b in range(len(w)))          # (2K, bins): class k half h at 2k + h
        Np = sum(w[b] * r['nump'][b] for b in range(len(w)))
        Dk = sum(w[b] * r['den'][b] for b in range(len(w)))
        refs[ref] = dict(N=Nk.reshape(K, 2, -1).sum(1), D=Dk.reshape(K, 2, -1).sum(1), Np=Np.reshape(K, 2, -1).sum(1),
                         NA=Nk[0::2], DA=Dk[0::2], NB=Nk[1::2], DB=Dk[1::2], ncell=r['ncell'])
    okb = np.isfinite(e)
    for rr in refs.values():
        okb &= (rr['D'] > 0).all(0)
    NB.add('n_bins', int(okb.sum()), 'autosomal 1-Mb bins with E1 and long-range contacts in every class of every reference')
    with np.errstate(divide='ignore', invalid='ignore'):       # bins without contacts are dropped by okb
        S = {ref: (refs[ref]['N'] / refs[ref]['D'])[:, okb] for ref in REF_NAMES}
        Sp = {ref: (refs[ref]['Np'] / refs[ref]['D'])[:, okb] for ref in REF_NAMES}
        SAB = {ref: ((refs[ref]['NA'] / refs[ref]['DA'])[:, okb], (refs[ref]['NB'] / refs[ref]['DB'])[:, okb]) for ref in REF_NAMES}
    for ref in REF_NAMES:
        SA, SB = SAB[ref]
        rel = [corr(SA[k] - SA.mean(0), SB[k] - SB.mean(0)) for k in range(len(CLASSES))]
        NB.add(f'ref_{ref}_class_split_half_r', dict(zip(CLASSES, np.round(rel, 3).tolist())),
               'split-half r (random halves of the reference cells) of each class profile minus the class mean')
        NB.add(f'ref_{ref}_ncell', dict(zip(CLASSES, refs[ref]['ncell'].tolist())), 'reference cells per coarse class')
    Z42 = np.vstack([S[r] - S[r].mean(0) for r in REF_NAMES])
    # ---------------- Guo sections ----------------
    secs = {s: Section(out, s, w, okb, 'centred', geo) for s in SECTIONS}
    secs_plain = {s: Section(out, s, w, okb, 'plain', geo) for s in SECTIONS}
    EXP = {}
    for s, sec in secs.items():
        NB.add(f'{s}_n_cortex_spots', len(sec.cx), f'Guo {s} cortex-mask spots after QC')
        NB.add(f'{s}_median_longrange_contacts', float(np.median(np.asarray(np.load(out / f"spots_{s}_den.npy", mmap_mode="r")[:, sec.cx].sum((0, 2))) / 2)),
               f'Guo {s}: median per cortex spot of cis contacts with |i-j| >= 2 Mb (den summed over bands / 2)')
        rng = np.random.default_rng(seed + 10)
        H = sec.halves(rng)
        for ref in REF_NAMES:
            P = sec.comp(out, ref)
            st = explained_block(sec, P, S[ref], H, np.random.default_rng(seed + 20))
            EXP[(s, ref)] = st
            tag = f'{s}_{ref}'
            NB.add(f'explained_{tag}', st['explained'], f'Guo {s}, {ref}: share of the reproducible between-depth-decile '
                   'compartment variance (split-half covariance, 20 splits) removed by the composition model (one slope)')
            NB.add(f'explained_null95_{tag}', np.percentile(st['null_explained'], 95),
                   '95th percentile of the same statistic with the class labels of the reference profiles permuted (200x)')
            NB.add(f'explained_p_{tag}', (np.sum(st['null_explained'] >= st['explained']) + 1) / 201, 'permutation p')
            NB.add(f'slope_{tag}', st['slope'], 'least-squares slope of observed on predicted decile deviations (protocol scale)')
            NB.add(f'r_contrast_{tag}', st['r_contrast'], 'r over bins of the superficial (deciles 1-4) minus deep (7-9) '
                   'contrast, observed vs predicted')
            NB.add(f'r_contrast_p_{tag}', (np.sum(st['null_r_contrast'] >= st['r_contrast']) + 1) / 201, 'permutation p')
            NB.add(f'resid_left_{tag}', 1 - st['explained'], 'reproducible between-decile variance left after the model')
        NB.add(f'rel_contrast_{s}', EXP[(s, 'gage')]['rel_contrast'], f'split-half r of the observed superficial-deep '
               f'contrast in Guo {s} (ceiling for r_contrast is about sqrt(2r/(1+r)))')
        # sensitivity: plain (not distance-centred) score
        for ref in ['gage']:
            stp = explained_block(secs_plain[s], sec.comp(out, ref), Sp[ref], H, np.random.default_rng(seed + 21), nperm=50)
            NB.add(f'explained_plain_{s}_{ref}', stp['explained'], 'as explained_* but with the plain partner score '
                   '(v = e_j, P(d)-confounded); sensitivity check')
        # cell share instead of UMI share
        stc = explained_block(sec, sec.comp(out, 'gage', share='cs'), S['gage'], H, np.random.default_rng(seed + 22), nperm=50)
        NB.add(f'explained_cellshare_{s}_gage', stc['explained'], 'as explained_* with composition = cell share '
               '(UMI share / median UMI per cell of the class in the reference) instead of UMI share')
        # residual structure (GAGE)
        st = EXP[(s, 'gage')]
        vres = st['v_res'].mean(0)
        NB.add(f'resid_decile_share_{s}', (vres / vres.sum()).round(3), 'share of the reproducible residual variance '
               '(GAGE) in each depth decile (decile 0 = layer 1 / pia)')
        NB.add(f'resid_layer1_share_{s}', vres[0] / vres.sum(), 'share of the reproducible residual variance in decile 0')
        NB.add(f'resid_splithalf_r_by_decile_{s}', st['rel_resid_dec'].round(3), 'split-half r of the residual per decile')
        NB.add(f'obs_splithalf_r_by_decile_{s}', st['rel_dec'].round(3), 'split-half r of the observed deviation per decile')
        # spot level, decile projections, WM control, heatmap (GAGE; spot level also for the other references)
        for ref in REF_NAMES:
            sa = spot_axes(sec, sec.comp(out, ref), S[ref], np.random.default_rng(seed + 30))
            for ax in ('glia_neuron', 'L23IT_L6CT'):
                NB.add(f'spot_r_{ax}_{s}_{ref}', sa[ax]['r'], f'per-spot r (cortex spots), {ax} axis: Hi-C projection from '
                       "the spot's own contacts vs RNA-predicted projection")
                NB.add(f'spot_r_within_depth_{ax}_{s}_{ref}', sa[ax]['r_within'], 'same after removing depth-decile means')
                NB.add(f'spot_null_sd_{ax}_{s}_{ref}', sa[ax]['null_sd'], 'SD of r with spots permuted (500x)')
            NB.add(f'spot_pattern_r_{s}_{ref}', sa['pattern']['mean_r'], 'mean over spots of r over bins between the '
                   "spot's deviation and its composition prediction (random-partner null about 0)")
            if ref == 'gage':
                for ax in ('glia_neuron', 'L23IT_L6CT'):
                    F[f'{s}_spot_obs_{ax}'] = sa[ax]['obs'].astype(np.float32)
                    F[f'{s}_spot_pred_{ax}'] = sa[ax]['pred'].astype(np.float32)
        P = sec.comp(out, 'gage')
        dp = decile_projection(sec, P, S['gage'], np.random.default_rng(seed + 40))
        for k in ('obs', 'pred', 'obs_se', 'pred_se', 'depth_mean', 'n'):
            F[f'{s}_dec_{k}'] = dp[k]
        F[f'{s}_dec_pred_x_slope'] = dp['pred'] * EXP[(s, 'gage')]['slope']
        NB.add(f'decile_axis_slope_{s}', dp['slope_axis'], 'slope of observed on predicted decile projections on the '
               'L2/3 IT - L6 CT axis (fit on the 10 points; the figure uses the global slope slope_<sec>_gage)')
        NB.add(f'decile_axis_r_{s}', corr(dp['obs'], dp['pred']), 'r over the 10 deciles of the projections')
        for ref in REF_NAMES:
            Pall = sec.comp(out, ref, rows='wm')
            Pc = sec.comp(out, ref)
            pred = (Pall.mean(0) - Pc.mean(0)) @ S[ref]
            obs = sec.wm_pool - sec.sbar
            NB.add(f'wm_r_{s}_{ref}', corr(obs, pred), f'white-matter control, Guo {s}: r over bins of (WM pool - cortex '
                   f'pool) vs composition prediction; WM = {len(sec.wm)} spots outside the cortex with the top 7 % '
                   'oligodendrocyte-gene fraction')
            NB.add(f'wm_slope_{s}_{ref}', (obs * pred).sum() / (pred ** 2).sum(), 'least-squares slope (through 0)')
            if ref == 'gage':
                F[f'{s}_wm_obs'], F[f'{s}_wm_pred'] = obs.astype(np.float32), pred.astype(np.float32)
                NB.add(f'wm_n_{s}', len(sec.wm), 'white-matter spots')
        Sm = P.mean(0) @ S['gage']
        dom = P.argmax(1)
        rows_, labs, ns = [], [], []
        for k, t in enumerate(CLASSES):
            ix = np.where(dom == k)[0]
            if len(ix) < 60:
                continue
            d = sec.N[ix].sum(0) / sec.D[ix].sum(0) - sec.sbar
            rows_.append([corr(d, S['gage'][j] - Sm) for j in range(len(CLASSES))])
            labs.append(t)
            ns.append(len(ix))
        F[f'{s}_heat_r'] = np.array(rows_, np.float32)
        F[f'{s}_heat_rows'] = np.array(labs)
        F[f'{s}_heat_n'] = np.array(ns)
        # spot tables
        F[f'{s}_spot_id'] = sec.ids.astype(str)
        for k in ('x', 'y', 'img_x', 'img_y'):
            F[f'{s}_spot_{k}'] = sec.g[k].to_numpy()[sec.cx].astype(np.float32)
        F[f'{s}_spot_depth'] = sec.depth.astype(np.float32)
        F[f'{s}_spot_decile'] = sec.dec.astype(np.int8)
        F[f'{s}_spot_comp'] = P.astype(np.float32)
        g_all = geo[geo.section == SECTIONS[s]]
        F[f'{s}_all_spot_id'] = g_all.index.to_numpy().astype(str)
        for k in ('x', 'y', 'img_x', 'img_y'):
            F[f'{s}_all_{k}'] = g_all[k].to_numpy().astype(np.float32)
        F[f'{s}_all_cortex'] = g_all.cortex.to_numpy()
        F[f'{s}_all_qc'] = g_all.qc.to_numpy()
    F['classes'] = np.array(CLASSES)
    F['explained'] = np.array([[EXP[(s, r)]['explained'] for r in REF_NAMES] for s in SECTIONS])
    F['explained_null'] = np.array([[EXP[(s, r)]['null_explained'] for r in REF_NAMES] for s in SECTIONS], np.float32)
    F['explained_null95'] = np.percentile(F['explained_null'], 95, axis=-1)
    F['refs'] = np.array(REF_NAMES)
    F['sections'] = np.array(list(SECTIONS))
    # cross-section / cross-reference residual agreement
    for ref in REF_NAMES:
        NB.add(f'resid_contrast_r1_vs_r2_{ref}', corr(EXP[('r1', ref)]['resid_contrast'], EXP[('r2', ref)]['resid_contrast']),
               'r over bins between Guo r1 and r2 of the residual superficial-deep contrast (deciles 1-4 minus 7-9)')
    NB.add('obs_contrast_r1_vs_r2', corr(secs['r1'].delta[SUP].mean(0) - secs['r1'].delta[DEEP].mean(0),
                                         secs['r2'].delta[SUP].mean(0) - secs['r2'].delta[DEEP].mean(0)),
           'r over bins between r1 and r2 of the observed superficial-deep contrast')
    for s in SECTIONS:
        rc = {r: EXP[(s, r)]['resid_contrast'] for r in REF_NAMES}
        NB.add(f'resid_contrast_cross_reference_{s}', [corr(rc['gage'], rc['paired']), corr(rc['gage'], rc['schicar']),
                                                     corr(rc['paired'], rc['schicar'])],
               'r between references of the residual contrast (gage-paired, gage-schicar, paired-schicar)')
    # span / amplitude decomposition of the reproducible residual contrast (GAGE)
    ch_ = np.array([str(c) for c in chrom[okb]])
    rng = np.random.default_rng(seed + 50)

    def shifted(Zm):
        o = Zm.copy()
        for c in np.unique(ch_):
            ix = np.where(ch_ == c)[0]
            o[:, ix] = np.roll(Zm[:, ix], rng.integers(5, len(ix) - 5), axis=1)
        return o

    for s, sec in secs.items():
        rcA, rcB = EXP[(s, 'gage')]['resid_contrast_halves']
        amp = sec.sbar[None, :]
        M2 = np.vstack([amp, Z42])
        acc = {k: [] for k in ('tot', 'g14', 'g14n', 'a42', 'a42n', 'amp', 'amp_span')}
        Zg = S['gage'] - S['gage'].mean(0)
        for a, b in zip(rcA, rcB):
            acc['tot'].append(cov(a, b))
            acc['g14'].append(cov(proj(Zg, a), proj(Zg, b)))
            Zs = shifted(Zg)
            acc['g14n'].append(cov(proj(Zs, a), proj(Zs, b)))
            acc['a42'].append(cov(proj(Z42, a), proj(Z42, b)))
            Zs = shifted(Z42)
            acc['a42n'].append(cov(proj(Zs, a), proj(Zs, b)))
            acc['amp'].append(cov(proj(amp, a), proj(amp, b)))
            acc['amp_span'].append(cov(proj(M2, a), proj(M2, b)))
        m = {k: np.mean(v) for k, v in acc.items()}
        NB.add(f'resid_in_span_gage14_{s}', m['g14'] / m['tot'], 'share of the reproducible residual contrast (GAGE '
               'model, split halves) inside the span of the 14 GAGE class profiles')
        NB.add(f'resid_in_span_gage14_null_{s}', m['g14n'] / m['tot'], 'same with the profiles circularly shifted within chromosomes')
        NB.add(f'resid_in_span_all42_{s}', m['a42'] / m['tot'], 'share inside the span of all 42 class profiles (3 references)')
        NB.add(f'resid_in_span_all42_null_{s}', m['a42n'] / m['tot'], 'same, shifted-profile null')
        NB.add(f'resid_amplitude_share_{s}', m['amp'] / m['tot'], 'share along the mean score profile (global compartment strength)')
        NB.add(f'resid_outside_amp_span_{s}', 1 - m['amp_span'] / m['tot'], 'share outside amplitude + 42-profile span (locus-specific)')
    g1, g2 = EXP[('r1', 'gage')]['resid_contrast'], EXP[('r2', 'gage')]['resid_contrast']
    NB.add('resid_contrast_r1_vs_r2_outside_span', corr(g1 - proj(Z42, g1), g2 - proj(Z42, g2)),
           'r1 vs r2 residual contrast (GAGE) after removing the 42-profile span')
    # ---------------- Chen ----------------
    CH = {}
    for ref in REF_NAMES:
        comp = pd.read_parquet(out / f'comp_chen_{ref}.parquet')
        CH[ref] = chen_block(out, w, okb, S[ref], comp, np.random.default_rng(seed + 60))
        NB.add(f'chen_explained_{ref}', CH[ref]['explained'], f'Chen 10 um, {ref}: share of the reproducible between-layer '
               'variance (layers I-VI; split halves from 4 random quarters, 3 pairings) explained by composition of the '
               'adjacent RNA section (one slope)')
        NB.add(f'chen_r_all_{ref}', CH[ref]['r_all'], 'r over (5 layers x bins) of observed vs predicted layer deviations')
        NB.add(f'chen_p_{ref}', CH[ref]['p'], 'class-label permutation p of chen_r_all (300x)')
        NB.add(f'chen_null95_{ref}', CH[ref]['null95'], '95th percentile of the permutation null of chen_r_all')
        NB.add(f'chen_slope_{ref}', CH[ref]['slope'], 'protocol slope (observed on predicted)')
        NB.add(f'chen_r_contrast_{ref}', CH[ref]['r_contrast'], 'r of the layer II-IV minus V-VI contrast, observed vs predicted')
        NB.add(f'chen_rel_contrast_{ref}', CH[ref]['rel_contrast'], 'split-half r of the observed II-IV minus V-VI contrast')
        for L in CHEN_POOLS:
            for k in ('r', 'split_half', 'ceiling', 'n_hic', 'n_rna'):
                NB.add(f'chen_{L}_{k}_{ref}', CH[ref]['per'][L][k], f'Chen pool {L}: {k} (ceiling = sqrt(2 sh / (1 + sh)))')
    F['chen_pools'] = np.array(CHEN_POOLS)
    F['chen_r'] = np.array([[CH[r]['per'][L]['r'] for L in CHEN_POOLS] for r in REF_NAMES], np.float32)
    F['chen_split_half'] = np.array([[CH[r]['per'][L]['split_half'] for L in CHEN_POOLS] for r in REF_NAMES], np.float32)
    F['chen_ceiling'] = np.array([[CH[r]['per'][L]['ceiling'] for L in CHEN_POOLS] for r in REF_NAMES], np.float32)
    F['chen_n_hic'] = np.array([CH['gage']['per'][L]['n_hic'] for L in CHEN_POOLS])
    F['chen_n_rna'] = np.array([CH['gage']['per'][L]['n_rna'] for L in CHEN_POOLS])
    F['chen_null_r_gage'] = CH['gage']['null_r'].astype(np.float32)
    cr = CH['gage']['resid_contrast']
    okc = CH['gage']['okc']
    chen_obs_con = _chen_obs_contrast(out, w, okb)
    for s in SECTIONS:
        gr = EXP[(s, 'gage')]['resid_contrast']
        NB.add(f'resid_contrast_{s}_vs_chen', corr(gr[okc], cr[okc]), f'r over bins of the residual depth contrast, Guo {s} '
               '(deciles 1-4 minus 7-9) vs Chen (layers II-IV minus V-VI), GAGE model in both')
        NB.add(f'resid_contrast_{s}_vs_chen_outside_span', corr((gr - proj(Z42, gr))[okc], (cr[okc] - proj(Z42[:, okc], cr[okc]))),
               'same after removing the 42-profile span from both')
        NB.add(f'obs_contrast_{s}_vs_chen', corr((secs[s].delta[SUP].mean(0) - secs[s].delta[DEEP].mean(0))[okc],
                                                 chen_obs_con[okc]),
               'r over bins of the observed depth contrasts, Guo (deciles 1-4 minus 7-9) vs Chen (layers II-IV minus V-VI)')
    # ---------------- cross-fitted residual axis (per spot) ----------------
    Zc = np.full(okb.sum(), np.nan)
    Zc[okc] = zscore(cr[okc])
    for s, other in (('r1', 'r2'), ('r2', 'r1')):
        sec, st = secs[s], EXP[(s, 'gage')]
        axis = np.nan_to_num((zscore(EXP[(other, 'gage')]['resid_contrast']) + np.nan_to_num(Zc)) / 2)
        a = axis / np.sqrt((axis ** 2).sum())
        P = sec.comp(out, 'gage')
        Sbar = P.mean(0) @ S['gage']
        delta = np.where(sec.D > 0, sec.N / np.maximum(sec.D, 1e-12), sec.sbar) - sec.sbar
        Dl = P @ S['gage'] - Sbar
        b = st['slope']
        den_a = sec.D @ (a * a)
        h_res = ((delta - b * Dl) * sec.D) @ a / den_a
        h_obs = (delta * sec.D) @ a / den_a
        h_pred = (b * Dl) @ a
        wts = sec.D.sum(1)
        dec_res = np.array([np.average(h_res[ix], weights=wts[ix]) for ix in sec.pools])
        rng = np.random.default_rng(seed + 70)
        bs = np.array([[np.average(h_res[j], weights=wts[j]) for j in [rng.choice(ix, len(ix)) for ix in sec.pools]] for _ in range(200)])
        from scipy.stats import spearmanr
        NB.add(f'xfit_resid_spearman_depth_{s}', spearmanr(np.arange(NDEC), dec_res)[0], f'Guo {s}: Spearman over the 10 '
               'depth deciles of the residual projected on the residual axis learned from the OTHER Guo section + Chen')
        F[f'{s}_spot_resid_xfit'] = h_res.astype(np.float32)
        F[f'{s}_spot_obs_xfit'] = h_obs.astype(np.float32)
        F[f'{s}_spot_pred_xfit'] = h_pred.astype(np.float32)
        F[f'{s}_dec_resid_xfit'] = dec_res
        F[f'{s}_dec_resid_xfit_se'] = bs.std(0)
    F['bin_chrom'] = np.array([str(c) for c in chrom[okb]])
    F['bin_start'] = start[okb].astype(np.int64)
    # ---------------- write ----------------
    figdir.mkdir(parents=True, exist_ok=True)
    figdir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(figdir / f'{NAME}.npz', **F)
    arrays = {k: {'shape': list(np.shape(v)), 'dtype': str(np.asarray(v).dtype)} for k, v in F.items()}
    doc = {'title': 'Fig. 2 data: spatial Hi-C spot compartments as mixtures of cell-type compartments',
           'main_analysis': 'GAGE-seq reference, distance-centred linear compartment score, UMI-share composition, '
                            'Guo r1 / r2 cortex-mask spots after QC; Chen 10 um cortex as cross-protocol replication',
           'generated_by': 'spatial_composition.py', 'seed': seed, 'numbers': NB.d, 'arrays': arrays,
           'array_notes': ARRAY_NOTES}
    (figdir / f'{NAME}.json').write_text(json.dumps(doc, indent=1))
    log(f'analysis: wrote {figdir / f"{NAME}.npz"} ({(figdir / f"{NAME}.npz").stat().st_size / 1e6:.2f} MB) and {NAME}.json '
        f'({len(NB.d)} numbers)')
    return NB.d


def _chen_obs_contrast(out, w, okb):
    """Observed Chen layer II-IV minus V-VI contrast (all quarters pooled) on the analysis bins."""
    ch = dict(np.load(out / 'chen.npz', allow_pickle=True))
    regions = list(ch['regions'])
    cols = np.where(okb)[0]
    Nw = np.tensordot(w, ch['numc'], axes=(0, 0))[:, cols]
    Dw = np.tensordot(w, ch['den'], axes=(0, 0))[:, cols]

    def s_of(regs):
        gi = [regions.index(r) * 4 + q for r in regs for q in range(4)]
        N, D = Nw[gi].sum(0), Dw[gi].sum(0)
        return np.where(D > 0, N / np.where(D > 0, D, 1), np.nan)

    sb = s_of(CHEN_LAYERS)
    d = {L: s_of([L]) - sb for L in CHEN_LAYERS}
    return np.nan_to_num((d['Layer_II_III'] + d['Layer_IV']) / 2 - (d['Layer_V'] + d['Layer_VI']) / 2)


ARRAY_NOTES = {
    '{s}_spot_*': 'Guo section s (r1 / r2), cortex-mask spots after QC, in the same order: id, grid x / y (spot units, y down), '
                  'image px, relative depth (0 = pia, 1 = white matter), depth decile, composition (UMI share, GAGE, columns = '
                  'classes), per-spot Hi-C projection (obs_*) and RNA-predicted projection (pred_*) on the glia-neuron and '
                  'L2/3 IT - L6 CT axes (unscaled; pred is not multiplied by the slope), and on the cross-fitted residual '
                  'axis (resid_xfit, obs_xfit, pred_xfit = slope x prediction).  Projections are noisy per spot; smooth '
                  'over neighbours (e.g. 3 x 3) for display.',
    '{s}_all_*': 'all in-tissue spots of the section (draw the non-cortex ones grey): grid x / y, image px, cortex (mask after QC) '
                 'and qc flags.',
    '{s}_dec_*': 'depth deciles: obs / pred = projections of the pooled observed / composition-predicted deviation on the '
                 'L2/3 IT - L6 CT axis (z / z.z), bootstrap SE over spots, pred_x_slope = pred x global slope; '
                 'resid_xfit = D-weighted mean of the per-spot cross-fitted residual projection (+ bootstrap SE).',
    'explained*': 'shape (section [r1, r2], reference [gage, paired, schicar]); explained_null holds the 200 class-label '
                  'permutations.',
    '{s}_wm_obs / _pred': 'per bin (bin_chrom / bin_start): white matter pool - cortex pool, observed and composition-predicted (GAGE).',
    '{s}_heat_*': 'cortex spots pooled by RNA-dominant class (rows, n spots) vs reference class profile deviations (columns = classes): r.',
    'chen_*': 'shape (reference, pool) with pools = chen_pools; ceiling = sqrt(2 sh / (1 + sh)) from the split-half r.',
}


# ----------------------------------------------------------------------------------------------------------------
NAME = 'spatial_composition'          # the figure data: <figdir>/spatial_composition.{npz,json}


def default_figdata(out: Path) -> Path:
    """The Brief Communication's results folder of the paper repository (benchmarks/_paper.py), else <out>/figdata."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _paper import paper_root
    root = paper_root()
    return root / 'manuscripts' / 'nmeth-bc' / 'figures' / 'results' if root else out / 'figdata'


def main(argv=None):
    here = Path(__file__).resolve().parent
    default_data = str(data_dir())
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data', default=default_data, help='data directory (default: $UCHROM_DATA, else ~/.cache/uchrom)')
    ap.add_argument('--out', default=None,
                    help='cache directory for intermediate arrays (~2 GB; default <data>/spatial_composition_cache)')
    ap.add_argument('--figdata', default=None,
                    help='directory for spatial_composition.{npz,json} (default: the paper repository\'s '
                         'manuscripts/nmeth-bc/figures/results, else <out>/figdata)')
    ap.add_argument('--stages', default='e1,scores,geometry,composition,analysis')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--seed', type=int, default=0)
    a = ap.parse_args(argv)
    inp = Inputs(Path(a.data))
    out = Path(a.out) if a.out else Path(a.data) / 'spatial_composition_cache'
    out.mkdir(parents=True, exist_ok=True)
    figdir = Path(a.figdata) if a.figdata else default_figdata(out)
    stages = [s.strip() for s in a.stages.split(',') if s.strip()]
    t0 = time.time()
    for st in stages:
        t = time.time()
        log(f'--- stage {st}')
        if st == 'e1':
            stage_e1(inp, out)
        elif st == 'scores':
            stage_scores(inp, out, a.workers, a.seed)
        elif st == 'geometry':
            stage_geometry(inp, out)
        elif st == 'composition':
            stage_composition(inp, out, a.workers)
        elif st == 'analysis':
            stage_analysis(inp, out, figdir, a.seed)
        else:
            sys.exit(f'unknown stage {st!r}')
        log(f'--- stage {st} done in {time.time() - t:.0f} s')
    log(f'total {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
