"""Genomic coordinates of the 1,151 genome-wide DNA-MERFISH targets of Cheng et al. 2026 (Science 393:eadw4243),
derived from the authors' probe sequences.

The deposit (Zenodo 19959235) and the supplement give no coordinates for these targets: Data S1 lists the 460,400
primary probes as ``<id>_Target<n>_Seq_<k>_Code<50-bit code>`` with their 140-nt sequences (20-nt forward primer,
20-nt readout, 40-nt genome-targeting region, two 20-nt readouts, 20-nt reverse primer; Data S4 / S6).  This script
takes each probe's targeting region (nt 41-80), finds its exact matches on the primary hg38 chromosomes (both strands;
32-mer index of the genome, then the whole 40 nt compared), and summarises every target by the probes that match once:
chromosome (their majority), start / end (the first / last matching probe, the probe length included), the median
position and how many probes agree; ``chrom_id`` (1-22, X = 23) and ``locus`` (1-based genomic order within the
chromosome) index the traces of the authors' ``.mat`` files.  Output (default):
``packages/uchrom/uchrom/datasets/cheng2026_targets_hg38.tsv``, read by the ``cheng2026_*`` loaders.

Result (2026-11-17): 460,317 of the 460,400 probes match hg38 exactly once, 83 nowhere, none several times; every
probe of a target lies within its locus (17-100 kb) and on one chromosome; the targets per chromosome (107 on chr1
... 23 on X) equal the trace lengths of the .mat files.

Usage (needs ~40 GB of memory and the hg38 FASTA; about 30 min)::

    python apps/atlas/recipes/cheng2026_mina/map_probes.py DATA_S1.xlsx hg38.fa.gz [OUT.tsv]
"""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CHROMS = [f"chr{c}" for c in [*range(1, 23), "X", "Y"]]
K = 32
_CODE = np.full(256, 4, np.uint8)
for i, b in enumerate(b"ACGT"):
    _CODE[b] = i
    _CODE[b + 32] = i                      # lower case (soft-masked repeats)


def probes(xlsx: Path) -> pd.DataFrame:
    sheets = pd.read_excel(xlsx, sheet_name=None, dtype=str)
    df = pd.concat([d.assign(subpool=name) for name, d in sheets.items()], ignore_index=True)
    parts = df["Name"].str.extract(r"_Target(\d+)_Seq_(\d+)_Code([01]+)$")
    if parts.isna().any().any() or not (df["Sequence"].str.len() == 140).all():
        raise ValueError("unexpected probe names or lengths in Data S1")
    return pd.DataFrame({"target": parts[0].astype(int), "seq_id": parts[1].astype(int), "code": parts[2],
                         "subpool": df["subpool"], "region": df["Sequence"].str[40:80].str.upper()})


def kmer(seq: str) -> int:
    v = 0
    for ch in seq[:K]:
        v = (v << 2) | int(_CODE[ord(ch)])
    return v


def revcomp(s: str) -> str:
    return s.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def read_fasta(path: Path):
    name, chunks = None, []
    with gzip.open(path, "rt") if str(path).endswith(".gz") else open(path) as fh:
        for line in fh:
            if line.startswith(">"):
                if name in CHROMS:
                    yield name, "".join(chunks)
                name, chunks = line[1:].split()[0], []
            elif name in CHROMS:
                chunks.append(line.rstrip())
    if name in CHROMS:
        yield name, "".join(chunks)


def scan(seq: str, query: np.ndarray):
    """Positions (0-based) where the 32-mer of the chromosome is in ``query`` (sorted uint64), and the code."""
    b = _CODE[np.frombuffer(seq.encode(), np.uint8)]
    n = len(b) - K + 1
    bad = np.r_[0, np.cumsum(b == 4)]
    ok = (bad[K:] - bad[:-K])[:n] == 0
    code = np.zeros(n, np.uint64)
    bb = np.minimum(b, 3).astype(np.uint64)
    for j in range(K):
        code <<= np.uint64(2)
        code |= bb[j:j + n]
    i = np.searchsorted(query, code)
    i[i == len(query)] = 0
    hit = ok & (query[i] == code)
    pos = np.flatnonzero(hit)
    return pos, code[pos]


def main() -> None:
    xlsx, fasta = Path(sys.argv[1]), Path(sys.argv[2])
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else (Path(__file__).resolve().parents[4] / "packages" / "uchrom" /
                                                        "uchrom" / "datasets" / "cheng2026_targets_hg38.tsv")
    p = probes(xlsx)
    fwd = p["region"].to_numpy()
    rc = np.array([revcomp(s) for s in fwd], dtype=object)
    keys = {}
    for i, (f, r) in enumerate(zip(fwd, rc)):
        keys.setdefault(kmer(f), []).append((i, "+", f))
        keys.setdefault(kmer(r), []).append((i, "-", r))
    query = np.array(sorted(keys), dtype=np.uint64)
    hits = []
    for chrom, seq in read_fasta(fasta):
        pos, code = scan(seq, query)
        up = seq.upper()
        for x, c in zip(pos.tolist(), code.tolist()):
            for i, strand, full in keys[c]:
                if up[x:x + 40] == full:
                    hits.append((i, chrom, x, strand))
        print(chrom, len(seq), len(pos), "32-mer hits", file=sys.stderr, flush=True)
    h = pd.DataFrame(hits, columns=["probe", "chrom", "pos", "strand"])
    nhit = h.groupby("probe").size().reindex(range(len(p)), fill_value=0)
    p["n_hits"] = nhit.to_numpy()
    uniq = h[h["probe"].map(nhit) == 1].copy()
    uniq["target"] = p["target"].to_numpy()[uniq["probe"]]
    rows = []
    for t, g in uniq.groupby("target"):
        chrom = g["chrom"].mode().iloc[0]
        on = g[g["chrom"] == chrom]
        mid = float(on["pos"].median())
        near = on[(on["pos"] - mid).abs() <= 250_000]          # the probes of one locus (designed: central 100 kb)
        rows.append({"target": t, "chrom": chrom, "start": int(near["pos"].min()), "end": int(near["pos"].max()) + 40,
                     "median": int(mid), "n_probes": int((p["target"] == t).sum()), "n_unique": len(g),
                     "n_in_locus": len(near), "n_other_chrom": int((g["chrom"] != chrom).sum())})
    t = pd.DataFrame(rows)
    meta = p.groupby("target").agg(subpool=("subpool", "first"), code=("code", "first"),
                                   n_no_hit=("n_hits", lambda s: int((s == 0).sum())),
                                   n_multi=("n_hits", lambda s: int((s > 1).sum())))
    t = t.merge(meta, left_on="target", right_index=True, how="right")
    # the traces of the .mat files index loci by chromosome (1-22, X = 23) and genomic order within it
    t["chrom_id"] = t["chrom"].map({c: i + 1 for i, c in enumerate(CHROMS[:23])})
    t = t.sort_values(["chrom_id", "start"])
    t["locus"] = t.groupby("chrom_id").cumcount() + 1
    cols = ["chrom_id", "locus", "target", "chrom", "start", "end", "median", "n_probes", "n_unique", "n_in_locus",
            "n_other_chrom", "n_no_hit", "n_multi", "subpool", "code"]
    t[cols].to_csv(out, sep="\t", index=False)
    print(f"{len(p):,} probes, {int((nhit == 1).sum()):,} with one exact match, {int((nhit == 0).sum()):,} with none, "
          f"{int((nhit > 1).sum()):,} with several; {t['chrom'].notna().sum()} of {len(t)} targets placed -> {out}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
