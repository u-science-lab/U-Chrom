"""The single-cell Hi-C data of SnapHiC (Yu et al. 2021, Nat Methods 18:1056) as ``ChromData``.

``nagano2017_dip_serum``: the mouse ES cells SnapHiC called loops from — Nagano et al. 2017 (Nature 547:61;
GEO GSE94489) diploid F1-hybrid ES cells grown in serum, batches 1CDS1 and 1CDS2 (1,175 cells; SnapHiC kept
"the top 742 cells with > 150,000 contacts").  The Tanay lab's fend-pair tables (``adj``: ``fend1 fend2
count``, mm9 GATC fragment ends) are placed on mm9 with ``GATC.fends``, lifted to mm10 with the UCSC chain
and binned at 10 kb (SnapHiC's resolution) into one ``.scool`` linked as ``per_cell``; one contact per fend
pair (the count column, duplicate reads, is dropped), both homologs summed.  ``cells``: the GEO feature
table's columns (batch, cell-cycle group, QC) plus the contacts of the maps and ``snaphic_top742``: the 742
cells with the most contacts in these maps — SnapHiC counted contacts from its own alignment of the reads
(BWA-MEM to mm10), which are not public, so its cell list is matched by rank, not reproduced.
"""

from __future__ import annotations

import gzip
import io
import os
import shutil
import tarfile
from collections.abc import Mapping
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from ._loaders import Loader, register

#: bin size of the per-cell maps: SnapHiC calls loops at 10 kb
RESOLUTION = 10_000
#: cells SnapHiC kept (the deepest of the 1,175)
N_SNAPHIC = 742

#: mm10 chromosome sizes (UCSC), chr1-19 and X (the cells are male: chrY has few contacts and is left out)
MM10 = {"chr1": 195471971, "chr2": 182113224, "chr3": 160039680, "chr4": 156508116, "chr5": 151834684,
        "chr6": 149736546, "chr7": 145441459, "chr8": 129401213, "chr9": 124595110, "chr10": 130694993,
        "chr11": 122082543, "chr12": 120129022, "chr13": 120421639, "chr14": 124902244, "chr15": 104043685,
        "chr16": 98207768, "chr17": 94987271, "chr18": 90702639, "chr19": 61431566, "chrX": 171031299}

#: files of the fetch() dataset ``nagano2017_dip_serum`` (relative to the data directory)
TARBALLS = ("nagano2017_dip/schic_hyb_1CDS1_adj_files.tar.gz", "nagano2017_dip/schic_hyb_1CDS2_adj_files.tar.gz")
FEATURES = "nagano2017_dip/GSE94489_serum_diploids_features_table.txt.gz"
FENDS = "nagano2017_hap/GATC.fends"
CHAIN = "nagano2017_hap/mm9ToMm10.over.chain.gz"


class _Chain:
    """A UCSC chain file: single positions mapped through the ungapped blocks (a position in a gap or in no
    block is unmapped; where chains overlap, the block starting last at or before the position is used)."""

    def __init__(self, path: Path):
        blocks: Dict[str, list] = {}
        with gzip.open(path, "rt") as fh:
            t = q = 0
            tname = qname = qstrand = None
            qsize = 0
            for line in fh:
                f = line.split()
                if not f:
                    continue
                if f[0] == "chain":
                    tname, t, qname, qsize, qstrand, q = f[2], int(f[5]), f[7], int(f[8]), f[9], int(f[10])
                    continue
                size = int(f[0])
                blocks.setdefault(tname, []).append((t, size, qname, q, qstrand == "-", qsize))
                if len(f) == 3:
                    t += size + int(f[1])
                    q += size + int(f[2])
        self.blocks = {}
        for c, b in blocks.items():
            b.sort(key=lambda x: x[0])
            self.blocks[c] = tuple(np.array([x[k] for x in b], dtype=object if k == 2 else None) for k in range(6))

    def map(self, chrom: np.ndarray, pos: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """0-based positions -> (chromosome, 0-based position; -1 = unmapped)."""
        out_c = np.full(len(pos), "", dtype=object)
        out_p = np.full(len(pos), -1, np.int64)
        for c in np.unique(chrom):
            if c not in self.blocks:
                continue
            ts, size, qn, qs, neg, qsize = self.blocks[c]
            sel = np.flatnonzero(chrom == c)
            k = np.searchsorted(ts, pos[sel], side="right") - 1
            ok = k >= 0
            kk = np.where(ok, k, 0)
            off = pos[sel] - ts[kk]
            ok &= (off >= 0) & (off < size[kk])
            qpos = qs[kk].astype(np.int64) + off
            qpos = np.where(neg[kk].astype(bool), qsize[kk].astype(np.int64) - 1 - qpos, qpos)
            out_c[sel[ok]] = qn[kk[ok]]
            out_p[sel[ok]] = qpos[ok]
        return out_c, out_p


def _fends(path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``GATC.fends`` (``fend chr coord``): sorted fend ids, their chromosome (``chrN``) and coordinate."""
    df = pd.read_csv(path, sep="\t", usecols=["fend", "chr", "coord"], dtype={"chr": str})
    order = np.argsort(df["fend"].to_numpy(np.int64), kind="stable")
    chrom = df["chr"].astype(str).to_numpy()[order]
    chrom = np.where(np.char.startswith(chrom.astype(str), "chr"), chrom, np.char.add("chr", chrom.astype(str)))
    return df["fend"].to_numpy(np.int64)[order], chrom.astype(object), df["coord"].to_numpy(np.int64)[order]


def _cell_pixels(adj: pd.DataFrame, fends, chain: _Chain, offset: Dict[str, int], width: int):
    """One cell's fend pairs -> 10 kb genome-wide pixels (upper triangle) and counts."""
    fid, fchr, fpos = fends
    stats = {"n_fend_pairs": int(len(adj))}
    ends = []
    for col in ("fend1", "fend2"):
        f = adj[col].to_numpy(np.int64)
        k = np.clip(np.searchsorted(fid, f), 0, len(fid) - 1)
        ok = fid[k] == f
        c, p = chain.map(fchr[k], fpos[k])
        ends.append((ok & (p >= 0), c, p))
    (ok1, c1, p1), (ok2, c2, p2) = ends
    off = pd.Series(offset)
    g1 = pd.Series(c1).map(off).to_numpy()
    g2 = pd.Series(c2).map(off).to_numpy()
    sizes = pd.Series(MM10)
    s1 = pd.Series(c1).map(sizes).to_numpy()
    s2 = pd.Series(c2).map(sizes).to_numpy()
    ok = ok1 & ok2 & ~pd.isna(g1) & ~pd.isna(g2)
    ok[ok] &= (p1[ok] < s1[ok].astype(np.int64)) & (p2[ok] < s2[ok].astype(np.int64))
    stats["n_unmapped"] = int((~ok).sum())
    b1 = g1[ok].astype(np.int64) + p1[ok] // RESOLUTION
    b2 = g2[ok].astype(np.int64) + p2[ok] // RESOLUTION
    lo, hi = np.minimum(b1, b2), np.maximum(b1, b2)
    key, cnt = np.unique(lo * width + hi, return_counts=True)
    cis = (c1[ok] == c2[ok])
    stats.update({"n_contacts": int(ok.sum()), "n_cis": int(cis.sum()), "n_trans": int((~cis).sum())})
    return (key // width).astype(np.int32), (key % width).astype(np.int32), cnt.astype(np.int32), stats


def build_nagano2017_dip_serum(root: Path, out: Path):
    """Nagano et al. 2017 diploid serum ES cells (1,175) at 10 kb on mm10, the data of SnapHiC (module
    docstring)."""
    import cooler
    from chromdata import ChromData

    from . import fetch
    from ..io.pairs_maps import genome_bins

    fetch("nagano2017_dip_serum", root=root)
    feats = pd.read_csv(root / FEATURES, sep="\t")
    feats = feats.set_index(pd.Index(feats["cell_nm"].astype(str), name="cell_id"))
    keep_cols = ["batch_name", "cond", "group", "passed_qc", "total_contacts", "f_trans", "repli_score"]
    cells = feats[[c for c in keep_cols if c in feats.columns]].copy()
    fends = _fends(root / FENDS)
    chain = _Chain(root / CHAIN)
    nb = {c: -(-s // RESOLUTION) for c, s in MM10.items()}
    offset = dict(zip(nb, np.r_[0, np.cumsum(list(nb.values()))[:-1]].astype(np.int64).tolist()))
    width = int(sum(nb.values()))

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.parent / f".nagano2017_dip_pixels.{os.getpid()}"
    tmp.mkdir(exist_ok=True)
    rows = {}
    try:
        for tb in TARBALLS:                                  # one sequential pass over each tarball
            with tarfile.open(root / tb, "r|gz") as tf:
                for member in tf:
                    if not member.isfile() or not member.name.endswith("/adj"):
                        continue
                    cell = member.name.split("/")[0].replace(".", "_")
                    if cell not in cells.index:
                        continue
                    adj = pd.read_csv(io.BytesIO(tf.extractfile(member).read()), sep="\t")
                    b1, b2, c, st = _cell_pixels(adj, fends, chain, offset, width)
                    np.savez(tmp / f"{cell}.npz", b1=b1, b2=b2, c=c)
                    rows[cell] = st
        missing = sorted(set(cells.index) - set(rows))
        if missing:
            raise ValueError(f"{len(missing)} cells of the feature table have no adj file, e.g. {missing[:3]}")

        class _Lazy(Mapping):                                # one cell in memory at a time
            def __getitem__(self, cell):
                z = np.load(tmp / f"{cell}.npz")
                return pd.DataFrame({"bin1_id": z["b1"], "bin2_id": z["b2"], "count": z["c"]})

            def __iter__(self):
                return iter(cells.index)

            def __len__(self):
                return len(cells.index)

        lazy = _Lazy()
        scool = out.parent / f"nagano2017_dip_serum_{RESOLUTION // 1000}kb.scool"
        part = scool.with_name(f".{scool.name}.{os.getpid()}.part")
        cooler.create_scool(str(part), genome_bins(MM10, RESOLUTION), lazy, ordered=True, assembly="mm10",
                            metadata={"source": "Nagano et al. 2017 GSE94489 diploid serum (schic2 fend pairs, "
                                                "mm9 -> mm10)"}, dtypes={"count": np.int32})
        os.replace(part, scool)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    stats = pd.DataFrame.from_dict(rows, orient="index")
    cells = cells.join(stats)
    cells["frac_cis"] = cells["n_cis"] / cells["n_contacts"]
    top = cells["n_contacts"].rank(ascending=False, method="first") <= N_SNAPHIC
    cells["snaphic_top742"] = top.to_numpy()
    cells["cell_type"] = "mESC"
    no_spots = pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                             [("chrom", str), ("start", np.int64), ("end", np.int64), ("trace_id", str),
                              ("cell_id", str)]})
    uns = {"genome_assembly": "mm10",
           "source": "Nagano et al. 2017, Nature 547:61 (GEO GSE94489): diploid F1-hybrid mESC in serum, batches "
                     "1CDS1 / 1CDS2; Tanay lab fend pairs (mm9) lifted to mm10, 10 kb; the cells of SnapHiC "
                     "(Yu et al. 2021, Nat Methods 18:1056)",
           "haplotypes": "ignored: each fend pair counted once (the per-cell map sums both homologs)"}
    cd = ChromData(np.zeros((0, 3)), no_spots, cells=cells, uns=uns)
    cd.link_scool(scool.name, key="per_cell", cell_name="cell_id", genome_assembly="mm10", bin_size=RESOLUTION,
                  label="Per cell (10 kb, homologs summed)")
    return cd


register(Loader(
    name="nagano2017_dip_serum", build=build_nagano2017_dip_serum,
    store="nagano2017_dip_serum/nagano2017_dip_serum.chromdata.zarr", sources=("nagano2017_dip_serum",),
    description="Nagano 2017 diploid serum mESC (SnapHiC's data): 1,175 cells, 10 kb maps per cell (linked "
                ".scool), mm10; snaphic_top742"))
