"""Real bulk Hi-C -> IGM probability matrices (design.md section 7(c)).

Subcommands
-----------
``preprocess``  raw Hi-C (``.mcool`` path or URL - HTTP range reads of one level -, ``.cool``,
                ``.hic`` through hicstraw) -> ``preprocess.preprocess_igm`` -> probability matrix
                ``.npz`` (``ProbabilityMatrix.save``)::

                    # IMR90, whole genome, IGM SI protocol (20 kb from the 10 kb level, 200 kb coarse)
                    python benchmarks/bulk/real_inputs.py preprocess --source $DATA/rao2014_imr90/4DNFIR1JDZH7.mcool \\
                        --fine 20000 --coarse 200000 --target 24 --out IMR90_igm_200kb.npz --fine-out IMR90_20kb.npz
                    # the same fine matrix mapped onto 3 Mb bins centred on the Su 2020 loci
                    python benchmarks/bulk/real_inputs.py preprocess --source ... --coarse-bins SIM/su_genome/truth.npz:centered:3000000 ...

                ``--fine-in`` reuses a saved fine matrix (``--fine-out``) instead of re-reading.
``su_crosscheck``  the authors' Rao 2014 matrix around the Su 2020 genome-scale loci
                (``Hi-C_contacts_genome-scale.tsv``: reads summed into 500 kb bins centred on the
                1,041 loci) vs the same sums from a GRCh38 IMR90 cooler (two 250 kb bins per locus,
                raw counts): Pearson / Spearman over cis and trans pairs::

                    python benchmarks/bulk/real_inputs.py su_crosscheck --source <4DNFIR1JDZH7.mcool> --out su_xcheck.json
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import RAO_IMR90_4DN, example_data, jdump, load_preprocess  # noqa: E402


def default_chroms(source: str, include_y: bool = False) -> list[str] | None:
    return None if include_y else "auto"


def cmd_preprocess(args) -> None:
    pp = load_preprocess()
    t0 = time.time()
    if args.fine_in:
        z = np.load(args.fine_in, allow_pickle=False)
        m = sp.coo_matrix((z["count"], (z["i"], z["j"])), shape=(int(z["n"]),) * 2).tocsr()
        bins = pd.DataFrame({"chrom": z["bins_chrom"].astype(str), "start": z["bins_start"], "end": z["bins_end"]})
    else:
        chroms = args.chroms
        m, bins, _ = pp.load_contacts(args.source, args.fine, chroms)
        if not args.chroms:                        # default: drop chrY / chrM / unplaced
            keep = ~bins.chrom.str.contains(r"^(?:chr)?(?:Y|M|MT)$|_|EBV", regex=True).to_numpy()
            idx = np.flatnonzero(keep)
            m = m[idx][:, idx]
            bins = bins.iloc[idx].reset_index(drop=True)
        print(f"read {args.source}: {len(bins)} bins, {m.nnz:,} pixels, {m.sum():,.0f} contacts, {time.time() - t0:.0f} s",
              flush=True)
        if args.fine_out:
            c = m.tocoo()
            np.savez_compressed(args.fine_out, i=c.row, j=c.col, count=c.data, n=len(bins),
                                bins_chrom=bins.chrom.to_numpy().astype(str), bins_start=bins.start.to_numpy(),
                                bins_end=bins.end.to_numpy(), source=str(args.source))
    coarse_bins = None
    if args.coarse_bins:
        from forward import model_bins
        from population import Population
        path, spec = args.coarse_bins.split(":", 1)
        coarse_bins = model_bins(Population.load(path), spec)
    P = pp.IGMPreprocessParams(fine_resolution=args.fine, coarse_resolution=args.coarse, target_contacts=args.target,
                               min_coverage=args.min_coverage, balance=args.balance, inter_max=args.inter_max)
    res = pp.preprocess_igm(m, bins, params=P, coarse_bins=coarse_bins, verbose=True)
    res.provenance["input"] = {"source": str(args.source or args.fine_in), "coarse_bins": args.coarse_bins}
    res.save(args.out)
    Path(str(args.out) + ".json").write_text(jdump(res.provenance))
    print(jdump({k: v for k, v in res.provenance.items() if k != "rounds"}), flush=True)


def read_su_hic(path) -> tuple[pd.DataFrame, np.ndarray]:
    df = pd.read_csv(path, sep="\t", index_col=0)
    g = pd.Series(df.columns).str.extract(r"^(chr[^:]+):(\d+)-(\d+)$")
    loci = pd.DataFrame({"chrom": g[0], "start": g[1].astype(np.int64), "end": g[2].astype(np.int64)})
    return loci, df.to_numpy(float)


def cmd_su_crosscheck(args) -> None:
    import cooler
    loci, H = read_su_hic(args.su_hic or example_data() / "su2020_imr90/Hi-C_contacts_genome-scale.tsv")
    mid = (loci.start + loci.end) // 2
    lo, hi = mid - 250_000, mid + 250_000
    src = args.source
    if src.startswith("http"):
        import fsspec
        import h5py
        clr = cooler.Cooler(h5py.File(fsspec.open(src, block_size=2 ** 22, cache_type="blockcache").open(), "r")
                            [f"resolutions/{args.res}"])
    else:
        clr = cooler.Cooler(f"{src}::/resolutions/{args.res}" if src.endswith(".mcool") else src)
    bins = clr.bins()[["chrom", "start", "end"]][:]
    # fine bins of each locus window
    groups = []
    for c, s, e in zip(loci.chrom, lo, hi):
        sub = bins[(bins.chrom == c) & (bins.start >= s) & (bins.end <= e)]
        groups.append(sub.index.to_numpy())
    allb = np.concatenate(groups)
    owner = np.concatenate([np.full(len(g), k) for k, g in enumerate(groups)])
    L = len(loci)
    M = np.zeros((L, L))
    sel = clr.matrix(balance=False, sparse=True)
    # rows of all locus windows, all columns; aggregate to the loci
    for k0 in range(0, len(allb), 200):
        rows = allb[k0:k0 + 200]
        for r_, o_ in zip(rows, owner[k0:k0 + 200]):
            v = sel[r_:r_ + 1, :].tocsr()
            cols = v.indices
            keep = np.isin(cols, allb)
            if not keep.any():
                continue
            pos = np.searchsorted(allb, cols[keep]) if np.all(np.diff(allb) > 0) else None
            own = owner[pos] if pos is not None else np.array([owner[np.flatnonzero(allb == c)[0]] for c in cols[keep]])
            np.add.at(M[o_], own, v.data[keep])
    iu = np.triu_indices(L, 1)
    cis = (loci.chrom.to_numpy()[:, None] == loci.chrom.to_numpy()[None])[iu]
    from scipy import stats
    out = {"source": src, "res": args.res, "n_loci": L}
    for name, s in (("all", np.ones(len(cis), bool)), ("cis", cis), ("trans", ~cis)):
        a, b = M[iu][s], H[iu][s]
        ok = (a > 0) & (b > 0)
        out[name] = {"n": int(s.sum()), "pearson": float(np.corrcoef(a, b)[0, 1]), "spearman": float(stats.spearmanr(a, b)[0]),
                     "pearson_log_nonzero": float(np.corrcoef(np.log(a[ok]), np.log(b[ok]))[0, 1]) if ok.sum() > 2 else None,
                     "sum_ratio": float(a.sum() / b.sum())}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(jdump(out))
    print(jdump(out), flush=True)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preprocess")
    p.add_argument("--source", help=".mcool / .cool / .hic path or URL")
    p.add_argument("--fine-in", help="saved fine matrix (--fine-out of an earlier run)")
    p.add_argument("--chroms", nargs="*")
    p.add_argument("--fine", type=int, default=20_000)
    p.add_argument("--coarse", type=int, default=200_000)
    p.add_argument("--coarse-bins", help="TRUTH.npz:SPEC (forward.model_bins spec, e.g. centered:3000000)")
    p.add_argument("--target", type=float, default=24.0)
    p.add_argument("--min-coverage", type=float, default=0.03)
    p.add_argument("--balance", default="kr", choices=["kr", "ice", "none"])
    p.add_argument("--inter-max", type=float, default=0.2)
    p.add_argument("--fine-out")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_preprocess)
    x = sub.add_parser("su_crosscheck")
    x.add_argument("--source", default=RAO_IMR90_4DN)
    x.add_argument("--res", type=int, default=250_000)
    x.add_argument("--su-hic")
    x.add_argument("--out", required=True)
    x.set_defaults(fn=cmd_su_crosscheck)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
