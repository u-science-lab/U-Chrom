"""Deep low-phasing diploid development (PREREG §10): derived contact tables for diagnostics and for
prototyping candidate fixes before they go into the engine.

``derive`` writes a hickit ``.pairs`` (phases only; hickit's ``phase_prob`` columns dropped) from a phased
table with any of:

* ``--downsample N``     N random rows (``--seed``)
* ``--min-cis-sep BP``   drop cis contacts closer than BP
* ``--commit TAU``       hard phasing with EMber's 2-D neighbourhood prior (``uchrom_nucdyn.neighbour_phase_prior``,
                         same-homolog rule within 10 Mb): a contact with an unphased end whose most probable
                         copy pair has probability >= TAU gets those haplotypes; ``--rest drop`` removes the
                         other ambiguous contacts (hickit ``-S``), ``--rest keep`` keeps them unphased
* ``--iso-nei K --iso-radius R``  keep a contact only if >= K other contacts of the same chromosome pair have
                         both ends within R (Chebyshev; hickit ``-r R -c K``)

Prints a JSON line with the counts.

    python benchmarks/screcon/deep_diploid.py derive --contacts cell.pairs.gz --commit 0.75 --rest drop --out X.pairs.gz
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diploid import Phased, read_phased, write_phased  # noqa: E402


def isolated_mask(c: Phased, k: int, radius: int) -> np.ndarray:
    """True for contacts with >= k other contacts of the same chromosome pair within ``radius`` at both ends."""
    keep = np.zeros(len(c), bool)
    key = np.char.add(np.char.add(c.chrom_a.astype(str), "|"), c.chrom_b.astype(str))
    for g in np.unique(key):
        idx = np.flatnonzero(key == g)
        pa, pb = c.pos_a[idx], c.pos_b[idx]
        o = np.argsort(pa, kind="stable")
        pa, pb, idx = pa[o], pb[o], idx[o]
        lo = np.searchsorted(pa, pa - radius, "left")
        hi = np.searchsorted(pa, pa + radius, "right")
        for i in range(len(idx)):
            n = int((np.abs(pb[lo[i]:hi[i]] - pb[i]) <= radius).sum()) - 1
            keep[idx[i]] = n >= k
    return keep


def cmd_derive(args) -> None:
    c = read_phased(args.contacts)
    n0 = len(c)
    rng = np.random.default_rng(args.seed)
    keep = np.ones(len(c), bool)
    if args.downsample and args.downsample < len(c):
        sel = np.zeros(len(c), bool)
        sel[rng.choice(len(c), args.downsample, replace=False)] = True
        keep &= sel
    if args.min_cis_sep:
        keep &= ~((c.chrom_a == c.chrom_b) & (np.abs(c.pos_b - c.pos_a) < args.min_cis_sep))
    c = c.subset(keep)
    stats = {"input": n0, "after_subset": len(c)}
    if args.iso_nei:
        m = isolated_mask(c, args.iso_nei, args.iso_radius)
        c = c.subset(m)
        stats["after_isolation"] = len(c)
    if args.commit:
        import uchrom_nucdyn as un
        pr = un.neighbour_phase_prior(c.chrom_a, c.pos_a, c.chrom_b, c.pos_b, c.hap_a, c.hap_b, ploidy="auto")
        amb = (c.hap_a < 0) | (c.hap_b < 0)
        best = pr.argmax(1)
        ok = amb & (pr.max(1) >= args.commit)
        ha, hb = c.hap_a.copy(), c.hap_b.copy()
        ha[ok], hb[ok] = (best[ok] >> 1).astype(np.int8), (best[ok] & 1).astype(np.int8)
        c = Phased(c.chrom_a, c.pos_a, ha, c.chrom_b, c.pos_b, hb, c.header, None)
        stats.update({"ambiguous": int(amb.sum()), "committed": int(ok.sum())})
        if args.rest == "drop":
            c = c.subset(~amb | ok)
            stats["after_drop"] = len(c)
    write_phased(args.out, c)
    stats["written"] = len(c)
    print(json.dumps(stats), flush=True)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("derive")
    d.add_argument("--contacts", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--seed", type=int, default=1)
    d.add_argument("--downsample", type=int, default=0)
    d.add_argument("--min-cis-sep", type=int, default=0)
    d.add_argument("--commit", type=float, default=0.0)
    d.add_argument("--rest", choices=["keep", "drop"], default="drop")
    d.add_argument("--iso-nei", type=int, default=0)
    d.add_argument("--iso-radius", type=int, default=10_000_000)
    d.set_defaults(fn=cmd_derive)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
