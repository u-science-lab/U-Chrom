"""In-silico spatial Hi-C tissue from real single cells (PREREG §14, ``benchmarks/screcon/PREREG.md``).

Standalone (numpy / scipy / pandas) so it runs in the Sherlock ``venv-main`` without U-Chrom.

Pieces
------
* :class:`Layout` — cis bin pairs of chr1-19 (mm10) at one resolution: genome-wide bin index, the upper
  triangle of every chromosome flattened into one pair index, the separation of every pair.
* :func:`read_cell_cis` / :func:`cell_bins` — a Tan 2021 Dip-C cell's cis contacts (separation >= 1 kb,
  chr1-19, both homologs on one chain) as base-resolution bin pairs (``BASE_RES`` = 50 kb, int32).
* :func:`split_cells` — the registered TRUTH / POOL-dev / POOL-test roles of the cells (§14.2).
* :func:`build_tissue` — a grid of spots; every spot pools 1-5 (partial) cells whose types follow a
  cortical layer pattern along the x axis; each cell's contacts are drawn without replacement inside a
  tissue (disjoint between spots); the cell and type of origin of every contact are kept.
* :func:`observed_composition` — the composition the method is given: exact contact shares, or an
  RNA-like estimate (per-type RNA-content bias + Dirichlet noise).
* :func:`spot_matrix` — the spots x pairs count matrix at a resolution (scipy CSR).
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

HERE = Path(__file__).resolve().parent
CELLS_TSV = HERE.parent / "screcon" / "data" / "tan2021_adult_cortex_cells.tsv"

MM10 = {"chr1": 195471971, "chr2": 182113224, "chr3": 160039680, "chr4": 156508116, "chr5": 151834684,
        "chr6": 149736546, "chr7": 145441459, "chr8": 129401213, "chr9": 124595110, "chr10": 130694993,
        "chr11": 122082543, "chr12": 120129022, "chr13": 120421639, "chr14": 124902244, "chr15": 104043685,
        "chr16": 98207768, "chr17": 94987271, "chr18": 90702639, "chr19": 61431566}
CHROMS = list(MM10)
BASE_RES = 50_000
MIN_SEP = 1_000

# Deconvolution types (code -> Tan 2021 "structure type" label), PREREG §14.2.
TYPES = {"P": "Cortical L2–5 Pyramidal Cell", "L6": "Cortical L6 Pyramidal Cell", "I": "Interneuron",
         "O": "Mature Oligodendrocyte", "A": "Adult Astrocyte", "M": "Microglia Etc."}
TYPE_CODES = list(TYPES)
SEED_SPLIT = 20261007

# Cortical layer pattern along x in [0, 1] (0 = pia, 1 = white matter): (x_end, {type: probability}).
LAYERS = [
    (0.10, {"P": 0.10, "L6": 0.00, "I": 0.30, "O": 0.10, "A": 0.30, "M": 0.20}),   # L1
    (0.55, {"P": 0.60, "L6": 0.03, "I": 0.15, "O": 0.07, "A": 0.08, "M": 0.07}),   # L2-5
    (0.80, {"P": 0.10, "L6": 0.50, "I": 0.10, "O": 0.15, "A": 0.08, "M": 0.07}),   # L6
    (1.00, {"P": 0.02, "L6": 0.05, "I": 0.03, "O": 0.70, "A": 0.10, "M": 0.10}),   # white matter
]

# Depth regimes (PREREG §14.3): spots, cis contacts per spot (log-uniform), cells per spot.
REGIMES = {
    "low": {"n_spots": 600, "depth": (5_000, 30_000), "cells": (1, 2)},    # 10 um-like: 1 + Binom(2, .5)
    "high": {"n_spots": 150, "depth": (30_000, 150_000), "cells": (2, 3)},  # 20 um-like: 2 + Binom(3, .5)
}
PARTIAL = (0.3, 1.0)      # fraction of a cell's nucleus in the spot, uniform

# Composition given to the method (PREREG §14.3): RNA-content bias sd (log), Dirichlet concentration,
# background (share of the Dirichlet mean spread evenly over all types: RNA deconvolution leaks mass to
# absent types).  Calibration on the layer pattern: tissue.py docstring / README.
NOISE = {"exact": (0.0, np.inf, 0.0), "moderate": (0.3, 10.0, 0.1), "heavy": (0.6, 3.0, 0.2)}


# --------------------------------------------------------------------------- layout

@dataclass
class Layout:
    """cis bin pairs (upper triangle incl. the diagonal) of ``chroms`` at ``res``."""

    res: int
    chroms: list = field(default_factory=lambda: list(CHROMS))
    sizes: dict = field(default_factory=lambda: dict(MM10))

    def __post_init__(self):
        self.n = np.array([-(-self.sizes[c] // self.res) for c in self.chroms], np.int64)
        self.bin_off = np.concatenate([[0], np.cumsum(self.n)])
        npair = self.n * (self.n + 1) // 2
        self.pair_off = np.concatenate([[0], np.cumsum(npair)])
        self.n_bins = int(self.bin_off[-1])
        self.n_pairs = int(self.pair_off[-1])
        self.bin_chrom = np.repeat(np.arange(len(self.chroms)), self.n)
        self.bin_local = np.arange(self.n_bins) - self.bin_off[self.bin_chrom]
        self._pairs = None

    def _pair_arrays(self):
        """Per pair: chromosome, local i <= j (built on first use; not for the 50 kb base layout)."""
        if self._pairs is None:
            ci, ii, jj = [], [], []
            for c, n in enumerate(self.n):
                i, j = np.triu_indices(int(n))
                ci.append(np.full(len(i), c, np.int16)); ii.append(i.astype(np.int32)); jj.append(j.astype(np.int32))
            self._pairs = (np.concatenate(ci), np.concatenate(ii), np.concatenate(jj))
        return self._pairs

    @property
    def pair_chrom(self) -> np.ndarray:
        return self._pair_arrays()[0]

    @property
    def pair_i(self) -> np.ndarray:
        return self._pair_arrays()[1]

    @property
    def pair_j(self) -> np.ndarray:
        return self._pair_arrays()[2]

    @property
    def pair_sep(self) -> np.ndarray:
        _, i, j = self._pair_arrays()
        return j - i

    def bin_index(self, chrom_idx, pos) -> np.ndarray:
        return self.bin_off[chrom_idx] + np.asarray(pos) // self.res

    def pair_index(self, a, b) -> np.ndarray:
        """Pair index of global bins ``a``, ``b`` on the same chromosome (order free)."""
        a, b = np.minimum(a, b).astype(np.int64), np.maximum(a, b).astype(np.int64)
        c = self.bin_chrom[a]
        n = self.n[c]
        i, j = a - self.bin_off[c], b - self.bin_off[c]
        return self.pair_off[c] + i * n - i * (i - 1) // 2 + (j - i)

    def from_base(self, base_bins: np.ndarray, base: "Layout") -> np.ndarray:
        """Map global bins of a finer layout ``base`` (res divides self.res) onto this layout."""
        assert self.res % base.res == 0 and self.chroms == base.chroms
        c = base.bin_chrom[base_bins]
        return self.bin_off[c] + base.bin_local[base_bins] // (self.res // base.res)

    def chrom_slices(self):
        for c, name in enumerate(self.chroms):
            yield c, name, slice(int(self.pair_off[c]), int(self.pair_off[c + 1]))


# --------------------------------------------------------------------------- cells

def _open(path):
    return gzip.open(path, "rt") if str(path).endswith(".gz") else open(path)


def read_cell_cis(path, chroms=CHROMS) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """cis contacts (separation >= 1 kb) of a GEO 4-column or ``.pairs`` table: chromosome index, pos_a, pos_b.

    Homolog suffixes (``chr1(mat)``) and phases are dropped: both copies on one chain.
    """
    df = pd.read_csv(path, sep=r"\s+", comment="#", header=None, dtype=str, engine="c")
    first = df.iloc[0]
    geo = first[1].lstrip("-").isdigit() and not first[2].lstrip("-").isdigit()
    cols = [0, 1, 2, 3] if geo else [1, 2, 3, 4]
    ca = df[cols[0]].str.replace(r"\(.*\)$", "", regex=True).to_numpy()
    cb = df[cols[2]].str.replace(r"\(.*\)$", "", regex=True).to_numpy()
    pa = df[cols[1]].astype(np.int64).to_numpy()
    pb = df[cols[3]].astype(np.int64).to_numpy()
    cmap = {c: k for k, c in enumerate(chroms)}
    ia = pd.Series(ca).map(cmap).to_numpy()
    ib = pd.Series(cb).map(cmap).to_numpy()
    keep = ~pd.isna(ia) & (ia == ib) & (np.abs(pa - pb) >= MIN_SEP)
    return ia[keep].astype(np.int16), pa[keep], pb[keep]


def cell_bins(path, base: Layout | None = None) -> np.ndarray:
    """(n, 2) int32 base-resolution global bins of a cell's cis contacts (a <= b), file order."""
    base = base or Layout(BASE_RES)
    c, pa, pb = read_cell_cis(path, base.chroms)
    a = base.bin_index(c, np.minimum(pa, pb) - 1)
    b = base.bin_index(c, np.maximum(pa, pb) - 1)
    keep = (pa > 0) & (pb > 0) & (np.maximum(pa, pb) <= np.array([base.sizes[x] for x in base.chroms])[c])
    return np.stack([a[keep], b[keep]], 1).astype(np.int32)


def cell_file(data: Path, name: str) -> Path:
    return Path(data) / "tan2021_cortex" / "cells" / name / f"{name}.contacts.pairs.txt.gz"


# --------------------------------------------------------------------------- split

def split_cells(cells_tsv=CELLS_TSV) -> pd.DataFrame:
    """Registered roles (PREREG §14.2): per type, cells sorted by GSM and permuted with
    ``default_rng(SEED_SPLIT + type index)``; first floor(n/2) = ``truth``, next floor((n - truth)/2) =
    ``dev``, rest = ``test``."""
    d = pd.read_csv(cells_tsv, sep="\t")
    rows = []
    for k, (code, label) in enumerate(TYPES.items()):
        sub = d[d.cell_type == label].sort_values("gsm").reset_index(drop=True)
        perm = np.random.default_rng(SEED_SPLIT + k).permutation(len(sub))
        n = len(sub)
        n_truth = n // 2
        n_dev = (n - n_truth) // 2
        for rank, idx in enumerate(perm):
            role = "truth" if rank < n_truth else ("dev" if rank < n_truth + n_dev else "test")
            r = sub.iloc[idx]
            rows.append({"gsm": r.gsm, "name": r["name"], "type": code, "role": role, "rank": rank})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- tissue

def layer_probs(x: float) -> dict:
    for x_end, probs in LAYERS:
        if x <= x_end:
            return probs
    return LAYERS[-1][1]


@dataclass
class Tissue:
    """Spots of one in-silico tissue; contacts as base-resolution bin pairs with their origin."""

    xy: np.ndarray            # (S, 2) grid coordinates in [0, 1]
    spot: np.ndarray          # (n,) spot of every contact
    bins: np.ndarray          # (n, 2) base bins
    cell: np.ndarray          # (n,) index into ``cells``
    cells: list               # cell names
    cell_type: np.ndarray     # (n_cells,) type index of each cell
    spot_cells: list          # per spot: list of (cell index, contacts)
    meta: dict

    @property
    def n_spots(self) -> int:
        return len(self.xy)

    def contact_type(self) -> np.ndarray:
        return self.cell_type[self.cell]

    def true_composition(self, n_types: int) -> np.ndarray:
        """(S, T) realised contact share of every type in every spot."""
        m = np.zeros((self.n_spots, n_types))
        np.add.at(m, (self.spot, self.contact_type()), 1.0)
        return m / np.maximum(m.sum(1, keepdims=True), 1)

    def cell_composition(self, n_types: int) -> np.ndarray:
        """(S, T) share of cells (each cell counted by its partial fraction) of every type in every spot."""
        m = np.zeros((self.n_spots, n_types))
        for s, lst in enumerate(self.spot_cells):
            for ci, _n, phi in lst:
                m[s, self.cell_type[ci]] += phi
        return m / np.maximum(m.sum(1, keepdims=True), 1e-12)


def build_tissue(pool: dict, regime: str, seed: int, *, types=TYPE_CODES, n_spots: int | None = None) -> Tissue:
    """One tissue of ``regime`` from ``pool`` = {cell name: (type code, (n, 2) base bins)}.

    Every cell's contacts are permuted once (seeded) and consumed in that order, so a cell's contacts
    are split between the spots it is used in.  A cell that runs out is replaced by another cell of its
    type with enough contacts left; when no cell of the type has enough left, the type's cells are
    re-permuted and reused (counted in ``meta['reused_contacts']``).
    """
    cfg = REGIMES[regime]
    rng = np.random.default_rng(seed)
    n_spots = n_spots or cfg["n_spots"]
    names = sorted(pool)
    tindex = {t: k for k, t in enumerate(types)}
    cell_type = np.array([tindex[pool[n][0]] for n in names])
    by_type = {k: [i for i in range(len(names)) if cell_type[i] == k] for k in range(len(types))}
    order = [rng.permutation(len(pool[n][1])) for n in names]
    ptr = np.zeros(len(names), np.int64)
    side = int(np.ceil(np.sqrt(n_spots)))
    xy = np.array([((k % side + 0.5) / side, (k // side + 0.5) / side) for k in range(n_spots)])
    lo, hi = cfg["depth"]
    n0, nb = cfg["cells"]
    spot_l, bins_l, cell_l, spot_cells = [], [], [], []
    reused = 0
    for s in range(n_spots):
        probs = layer_probs(xy[s, 0])
        p = np.array([probs[t] for t in types], float)
        p /= p.sum()
        n_cells = n0 + rng.binomial(nb, 0.5)
        depth = int(round(np.exp(rng.uniform(np.log(lo), np.log(hi)))))
        tps = rng.choice(len(types), size=n_cells, p=p)
        phi = rng.uniform(*PARTIAL, size=n_cells)
        share = rng.multinomial(depth, phi / phi.sum())
        used, lst = set(), []
        for t, want, f in zip(tps, share, phi):
            cand = [i for i in by_type[t] if i not in used]
            if not cand:
                cand = list(by_type[t])
            ok = [i for i in cand if len(order[i]) - ptr[i] >= want]
            if ok:
                ci = ok[rng.integers(len(ok))]
            else:   # every cell of the type exhausted for this draw: reuse
                ci = cand[rng.integers(len(cand))]
                order[ci] = rng.permutation(len(order[ci]))
                ptr[ci] = 0
                reused += int(want)
                want = min(int(want), len(order[ci]))
            idx = order[ci][ptr[ci]:ptr[ci] + want]
            ptr[ci] += want
            used.add(ci)
            spot_l.append(np.full(len(idx), s, np.int32))
            bins_l.append(pool[names[ci]][1][idx])
            cell_l.append(np.full(len(idx), ci, np.int32))
            lst.append((ci, int(len(idx)), float(f)))
        spot_cells.append(lst)
    meta = {"regime": regime, "seed": int(seed), "n_spots": int(n_spots), "reused_contacts": int(reused),
            "types": list(types)}
    tissue = Tissue(xy, np.concatenate(spot_l), np.concatenate(bins_l), np.concatenate(cell_l), names,
                    cell_type, spot_cells, meta)
    meta["n_contacts"] = int(len(tissue.spot))
    return tissue


def save_tissue(path, t: Tissue) -> None:
    sc = np.array([(s, ci, n, f) for s, lst in enumerate(t.spot_cells) for ci, n, f in lst], float)
    np.savez_compressed(path, xy=t.xy, spot=t.spot, bins=t.bins, cell=t.cell, cells=np.array(t.cells),
                        cell_type=t.cell_type, spot_cells=sc, meta=np.array(repr(t.meta)))


def load_tissue(path) -> Tissue:
    z = np.load(path, allow_pickle=False)
    sc = z["spot_cells"]
    spot_cells = [[] for _ in range(len(z["xy"]))]
    for s, ci, n, f in sc:
        spot_cells[int(s)].append((int(ci), int(n), float(f)))
    import ast
    return Tissue(z["xy"], z["spot"], z["bins"], z["cell"], list(z["cells"]), z["cell_type"], spot_cells,
                  ast.literal_eval(str(z["meta"])))


# --------------------------------------------------------------------------- compositions

def observed_composition(true_share: np.ndarray, level: str, seed: int) -> tuple[np.ndarray, dict]:
    """Composition handed to the method: exact, or RNA-like (``NOISE[level]``).

    RNA-like = true contact share x a per-type RNA-content factor exp(N(0, sd)) (fixed per tissue),
    renormalised, then Dirichlet(concentration x ((1 - background) share + background / T)).  Returns (S, T) and calibration numbers
    (mean absolute error, Pearson r of the flattened shares vs the truth).
    """
    sd, conc, bg = NOISE[level]
    rng = np.random.default_rng(seed)
    w = true_share.copy()
    bias = np.exp(rng.normal(0, sd, size=w.shape[1])) if sd > 0 else np.ones(w.shape[1])
    w = w * bias
    w /= w.sum(1, keepdims=True)
    if np.isfinite(conc):
        T = w.shape[1]
        w = np.vstack([rng.dirichlet(np.maximum(conc * ((1 - bg) * row + bg / T), 1e-3)) for row in w])
    cal = {"level": level, "bias": bias.tolist(), "mae": float(np.abs(w - true_share).mean()),
           "r": float(np.corrcoef(w.ravel(), true_share.ravel())[0, 1]),
           "dominant_agree": float(np.mean(w.argmax(1) == true_share.argmax(1)))}
    return w, cal


def permuted_composition(comp: np.ndarray, seed: int) -> np.ndarray:
    """Random-composition control: the rows of ``comp`` permuted across spots."""
    return comp[np.random.default_rng(seed).permutation(len(comp))]


# --------------------------------------------------------------------------- matrices

def spot_matrix(spot, bins, n_spots: int, layout: Layout, base: Layout | None = None) -> sp.csr_matrix:
    """(S, n_pairs) contact counts of ``layout``."""
    base = base or Layout(BASE_RES)
    a = layout.from_base(bins[:, 0], base)
    b = layout.from_base(bins[:, 1], base)
    p = layout.pair_index(a, b)
    m = sp.coo_matrix((np.ones(len(p), np.float64), (np.asarray(spot), p)), shape=(n_spots, layout.n_pairs))
    return m.tocsr()


def pair_counts(bins, layout: Layout, base: Layout | None = None, weights=None) -> np.ndarray:
    """(n_pairs,) counts of a contact list (pseudo-bulk)."""
    base = base or Layout(BASE_RES)
    p = layout.pair_index(layout.from_base(bins[:, 0], base), layout.from_base(bins[:, 1], base))
    return np.bincount(p, weights=weights, minlength=layout.n_pairs).astype(np.float64)
