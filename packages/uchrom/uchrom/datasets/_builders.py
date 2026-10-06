"""Datasets built from their sources rather than downloaded whole.

``slice_hic``: Rao et al. 2014 in situ Hi-C (GEO GSE63525) sliced into small coolers.  The GEO ``.hic``
files are 9-51 GB; ``hicstraw`` reads one over HTTP range requests, so only the intra-chromosomal
blocks needed are fetched (observed, raw counts; the MAPQ > 0 "combined" maps, as used by Bintu et al.
2018).  Coordinates stay in hg19 with a ``chr`` prefix; nothing is normalised (``cooler balance`` if a
method needs it).  Needs ``hic-straw`` (u-chrom[hic]) and ``cooler``.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

GEO = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE63nnn/GSE63525/suppl"
HIC = {
    # MAPQ > 0 combined maps (GEO sizes: IMR90 13 GB, K562 ~ see catalog, GM12878 51 GB)
    "IMR90": f"{GEO}/GSE63525_IMR90_combined.hic",
    "K562": f"{GEO}/GSE63525_K562_combined.hic",
    "GM12878": f"{GEO}/GSE63525_GM12878_insitu_primary+replicate_combined.hic",
}


def slice_hic(cell: str, chroms: list[str], res: int, out: Path) -> Path:
    import cooler
    import hicstraw

    t0 = time.time()
    hic = hicstraw.HiCFile(HIC[cell])
    assert hic.getGenomeID() == "hg19", hic.getGenomeID()
    if res not in hic.getResolutions():
        raise ValueError(f"{res} bp not in {hic.getResolutions()}")
    sizes = {c.name: c.length for c in hic.getChromosomes()}
    bins, pixels, offset = [], [], 0
    for c in chroms:
        n = int(np.ceil(sizes[c] / res))
        starts = np.arange(n) * res
        bins.append(pd.DataFrame({"chrom": f"chr{c}", "start": starts,
                                  "end": np.minimum(starts + res, sizes[c])}))
        zd = hic.getMatrixZoomData(c, c, "observed", "NONE", "BP", res)
        # row blocks of 10 Mb (all columns to the right) keep memory small
        step = 10_000_000
        for s in range(0, sizes[c], step):
            recs = zd.getRecords(s, min(s + step, sizes[c]) - 1, s, sizes[c])
            if not recs:
                continue
            b1 = np.fromiter((r.binX for r in recs), np.int64, len(recs)) // res
            b2 = np.fromiter((r.binY for r in recs), np.int64, len(recs)) // res
            v = np.fromiter((r.counts for r in recs), np.float64, len(recs))
            lo, hi = np.minimum(b1, b2), np.maximum(b1, b2)
            keep = (lo * res >= s) & (lo * res < s + step)   # each pixel once
            pixels.append(pd.DataFrame({"bin1_id": lo[keep] + offset,
                                        "bin2_id": hi[keep] + offset,
                                        "count": np.rint(v[keep]).astype(np.int64)}))
        offset += n
        print(f"  {cell} chr{c} @ {res}: {sum(len(p) for p in pixels):,} pixels so far "
              f"({time.time() - t0:.0f} s)")
    px = (pd.concat(pixels).groupby(["bin1_id", "bin2_id"], as_index=False)["count"].sum()
          .sort_values(["bin1_id", "bin2_id"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    cooler.create_cooler(str(out), pd.concat(bins, ignore_index=True), px, ordered=True,
                         assembly="hg19",
                         metadata={"source": HIC[cell], "normalization": "none (observed)",
                                   "citation": "Rao et al. 2014 Cell 159:1665, GEO GSE63525"})
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {px['count'].sum():,} contacts, "
          f"{time.time() - t0:.0f} s)")
    return out
