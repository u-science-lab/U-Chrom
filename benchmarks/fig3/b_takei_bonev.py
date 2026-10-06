"""Fig. 3b first look, mESC: Takei 2021 DNA seqFISH+ vs Bonev 2017 Hi-C.

Takei et al. 2021 (Nature 590:344) compared their E14 mESC 25 kb traces
(20 chromosomes x 60 loci, 4DN 4DNFIHF3JCBY) with Bonev et al. 2017 mESC
Hi-C (GSE96107) and reported Spearman -0.84 between median spatial
distance and Hi-C contact frequency (146,741 intra-chromosomal pairs,
KR-normalised Juicer maps).

The Bonev G1-sorted ES mcool on 4DN (4DNFIC21MG3U, 12.6 GB, mm10) is too
large to download, so the 20 imaged windows are read over HTTP range
requests (fsspec + h5py + cooler, 25 kb, balanced weights as stored).
Per window: median distance and contact frequency (< r nm) from the
traces (``uchrom.fea.distance``) vs Hi-C, all windows pooled.

Usage::

    python benchmarks/fig3/b_takei_bonev.py [--data $UCHROM_DATA] [--out x.json]
"""

from __future__ import annotations

from uchrom.datasets import data_dir
import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
BONEV = ("https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/"
         "2b448d99-d3fb-4bb9-a126-386ccb99a6fd/4DNFIC21MG3U.mcool")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=data_dir())
    ap.add_argument("--mcool", default=BONEV)
    ap.add_argument("--res", type=int, default=25_000)
    ap.add_argument("--radii", type=float, nargs="+", default=[0.15, 0.2, 0.3, 0.5])
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    import cooler
    import fsspec
    import h5py
    from uchrom import ChromData
    from uchrom.fea.distance import contact_frequency, mean_distance_matrix

    cd = ChromData.from_fofct(str(args.data / "4DNFIHF3JCBY.csv"))
    df = cd.to_dataframe()
    df["chrom"] = df["chrom"].astype(str)
    fh = fsspec.open(args.mcool, block_size=2 ** 20, cache_type="blockcache").open()
    clr = cooler.Cooler(h5py.File(fh, "r")[f"resolutions/{args.res}"])
    pooled = {"hic": [], "med": [], **{r: [] for r in args.radii}}
    per_chrom = {}
    for chrom, sub in df.groupby("chrom"):
        starts = np.sort(sub["start"].unique())
        lo, hi = int(starts.min()), int(starts.max()) + args.res
        H = clr.matrix(balance=True).fetch(f"{chrom}:{lo}-{hi}")
        idx = ((starts - lo) // args.res).astype(int)
        H = H[np.ix_(idx, idx)]
        med, _, _ = mean_distance_matrix(sub, reduce="median")
        iu = np.triu_indices(len(starts), 1)
        ok = np.isfinite(H[iu]) & np.isfinite(med[iu])
        pooled["hic"].append(H[iu][ok])
        pooled["med"].append(med[iu][ok])
        for r in args.radii:
            cf, _, _ = contact_frequency(sub, threshold=r)
            pooled[r].append(cf[iu][ok])
        per_chrom[chrom] = float(stats.spearmanr(med[iu][ok], H[iu][ok])[0])
    h = np.concatenate(pooled["hic"])
    m = np.concatenate(pooled["med"])
    res = {"n_pairs": int(len(h)), "spearman_median_distance_vs_hic": float(stats.spearmanr(m, h)[0]),
           "per_chrom_spearman_median": float(np.median(list(per_chrom.values()))),
           "per_chrom": per_chrom, "by_radius_um": {}}
    for r in args.radii:
        c = np.concatenate(pooled[r])
        ok = (c > 0) & (h > 0)
        res["by_radius_um"][r] = {"spearman": float(stats.spearmanr(c, h)[0]),
                                  "pearson_log": float(stats.pearsonr(np.log10(c[ok]), np.log10(h[ok]))[0])}
    print(json.dumps({k: v for k, v in res.items() if k != "per_chrom"}, indent=1))
    if args.out:
        args.out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
