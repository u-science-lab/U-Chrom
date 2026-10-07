"""Datasets built from their sources rather than downloaded whole.

``slice_hic``: Rao et al. 2014 in situ Hi-C (GEO GSE63525) sliced into small coolers.  The GEO ``.hic``
files are 9-51 GB; ``hicstraw`` reads one over HTTP range requests, so only the intra-chromosomal
blocks needed are fetched (observed, raw counts; the MAPQ > 0 "combined" maps, as used by Bintu et al.
2018).  Coordinates stay in hg19 with a ``chr`` prefix; nothing is normalised (``cooler balance`` if a
method needs it).  Needs ``hic-straw`` (u-chrom[hic]) and ``cooler``.

``seqfish_fov_head``: the first cells of one field of view of Takei et al. 2025 (DNA seqFISH+ multi-omics,
Zenodo 7693825).  A field of view is one ~2 GB CSV inside a ~2.8 GB tarball; the tarball is streamed and
closed after the first rows, the last (possibly cut) cell is dropped, and the locus map and the cell
clustering (GitHub) are downloaded next to it.
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


def seqfish_fov_head(tarball: str, member: str, rows: int, sidecars: list, out: Path) -> Path:
    import tarfile
    import urllib.request

    from ._fetch import download

    out.parent.mkdir(parents=True, exist_ok=True)
    for name, url in sidecars:
        download(url, out.parent / name, name)
    if out.exists():
        return out
    print(f"[pull] first {rows:,} rows of {member} streamed out of {tarball}", flush=True)
    with urllib.request.urlopen(tarball) as resp, tarfile.open(fileobj=resp, mode="r|gz") as tar:
        for m in tar:
            if m.name != member:
                continue
            fh = tar.extractfile(m)
            buf, n_lines = bytearray(), 0
            while n_lines <= rows:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                buf += chunk
                n_lines += chunk.count(b"\n")
            df = pd.read_csv(__import__("io").BytesIO(b"\n".join(bytes(buf).split(b"\n")[: rows + 1])))
            df = df[df["cellID"] != df["cellID"].iloc[-1]]       # the last cell may be cut off
            tmp = out.with_suffix(out.suffix + ".part")
            df.to_csv(tmp, index=False)
            tmp.rename(out)
            print(f"wrote {out} ({len(df):,} spots, {df['cellID'].nunique()} cells)")
            return out
    raise FileNotFoundError(f"{member} not found in {tarball}")
