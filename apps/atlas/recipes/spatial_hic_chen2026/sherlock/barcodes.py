"""Spot barcodes of spatial Hi-C read pairs -> barcode-tagged genomic reads, in chunks for mapping.

--layout chen (Chen, Guo et al. 2026 spatial Hi-C; the default):

Read 1 is  bcB(8) | linker 1 (30) | bcA(8) | linker 2 (30) | Tn5 ME (19) | genomic ... ;  read 2 is genomic.
The authors cut this with umi_tools regex (linker 1 e<=1, linker 2 + ME s<=2,i<=1,d<=1); on 1e9-read runs a
regex per read is too slow, so here: the ME is searched near its expected position (74-80, tolerating
indels upstream), barcode A is the 8 bases 30 bp before it, barcode B the first 8 bases, and linker 1 must
match exactly on one of its halves.  Pairs pass when read 1 keeps >= --min-len genomic bases.  Barcodes are
appended to the read names ("<name>_<bcB>_<bcA>", as in the authors' BEDPE); whitelisting is left to the
contact step (it allows one mismatch there).

    pigz -dc R1.fq.gz | ...   (both files are read through pigz)
--layout atachic (spatial ATAC-Hi-C, GSE307620; the authors' bcsplit.py / 00.filter-linker.sh):
read 2 is  primer (22) | bc2 (8) | linker 2 (30) | bc1 (8) | linker 1 (30) | ... | genomic from base 117;
read 1 is genomic.  Pairs need both linkers (linker 2 in read 2's first 72 bases, linker 1 in its first
110; exact match of one half of each); the spot barcode is bc2 + bc1 (16 bases, as the tissue positions
list), appended to the names as "<name>_<barcode16>".

    python barcodes.py R1.fq.gz R2.fq.gz OUTDIR [--layout chen|atachic] [--chunk 60000000] [--max-pairs 0]
    (several R1 R2 pairs may be given: --pairs R1a R2a R1b R2b …, e.g. two sequencing runs of a library)

Writes OUTDIR/chunk_<k>_R1.fq.gz / _R2.fq.gz (pigz) and OUTDIR/barcodes_stats.json.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

L1 = "GTGGCCGATGTTTCGCATCGGCGTACGACT"
L2 = "ATCCACGTGCTTGAGAGGCCAGAGCATTCG"                          # atachic: linker after the first barcode
L1A, L1B = L1[:15], L1[15:]
ME = "AGATGTGTATAAGAGACAG"
ME_POS = 76                     # 8 + 30 + 8 + 30


def reader(path: str, threads: int):
    p = subprocess.Popen(["pigz", "-dc", "-p", str(threads), path], stdout=subprocess.PIPE, bufsize=1 << 22)
    return p, p.stdout


def writer(path: Path, threads: int):
    f = open(path, "wb")
    p = subprocess.Popen(["pigz", "-c", "-p", str(threads), "-3"], stdin=subprocess.PIPE, stdout=f, bufsize=1 << 22)
    return p, f


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("r1")
    ap.add_argument("r2")
    ap.add_argument("out")
    ap.add_argument("--layout", choices=("chen", "atachic"), default="chen")
    ap.add_argument("--more", nargs="*", default=[], help="further R1 R2 pairs (runs of the same library)")
    ap.add_argument("--chunk", type=int, default=60_000_000, help="read pairs per output chunk")
    ap.add_argument("--max-pairs", type=int, default=0, help="stop after this many input pairs (tests)")
    ap.add_argument("--min-len", type=int, default=20, help="genomic bases read 1 must keep")
    ap.add_argument("--threads", type=int, default=4, help="pigz threads per stream")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    inputs = [(a.r1, a.r2)] + list(zip(a.more[::2], a.more[1::2]))
    st = dict(pairs=0, kept=0, no_me=0, no_linker1=0, no_linker2=0, short=0, me_shift={}, inputs=[x for p in inputs for x in p])
    shift = {}
    k, in_chunk, w = 0, 0, None
    t0 = time.time()

    def open_chunk(k):
        return writer(out / f"chunk_{k:03d}_R1.fq.gz", a.threads), writer(out / f"chunk_{k:03d}_R2.fq.gz", a.threads)

    def close_chunk(w):
        for (p, f) in w:
            p.stdin.close()
            p.wait()
            f.close()

    l1a, l1b, l2a, l2b = L1A.encode(), L1B.encode(), L2[:15].encode(), L2[15:].encode()
    p1 = p2 = None
    try:
        for r1_path, r2_path in inputs:
            p1, f1 = reader(r1_path, a.threads)
            p2, f2 = reader(r2_path, a.threads)
            while True:
                h1 = f1.readline()
                if not h1:
                    break
                s1 = f1.readline(); f1.readline(); q1 = f1.readline()
                h2 = f2.readline(); s2 = f2.readline(); f2.readline(); q2 = f2.readline()
                st["pairs"] += 1
                if a.max_pairs and st["pairs"] > a.max_pairs:
                    st["pairs"] -= 1
                    break
                if a.layout == "chen":
                    j = s1.find(b"AGATGTGTATAAGAGACAG", ME_POS - 3, ME_POS + 22)
                    if j < 0:
                        st["no_me"] += 1
                        continue
                    if l1a not in s1[6:26] and l1b not in s1[20:42]:
                        st["no_linker1"] += 1
                        continue
                    g = j + 19
                    if len(s1) - 1 - g < a.min_len:              # (s1 ends with "\n")
                        st["short"] += 1
                        continue
                    d = j - ME_POS
                    shift[d] = shift.get(d, 0) + 1
                    tag = b"_" + s1[:8] + b"_" + s1[j - 38:j - 30]
                    rec1 = s1[g:] + b"+\n" + q1[g:]
                    rec2 = s2 + b"+\n" + q2
                else:                                            # atachic: barcodes on read 2
                    if l2a not in s2[:72] and l2b not in s2[:72]:
                        st["no_linker2"] += 1
                        continue
                    if l1a not in s2[:110] and l1b not in s2[:110]:
                        st["no_linker1"] += 1
                        continue
                    if len(s2) - 1 - 117 < a.min_len:
                        st["short"] += 1
                        continue
                    tag = b"_" + s2[22:30] + s2[60:68]
                    rec1 = s1 + b"+\n" + q1                     # read 1: genomic
                    rec2 = s2[117:] + b"+\n" + q2[117:]         # read 2: genomic part
                name1 = h1.split(None, 1)[0] + tag + b"\n"
                name2 = h2.split(None, 1)[0] + tag + b"\n"
                if w is None or in_chunk >= a.chunk:
                    if w is not None:
                        close_chunk(w)
                        k += 1
                    w, in_chunk = open_chunk(k), 0
                w[0][0].stdin.write(name1 + rec1)
                w[1][0].stdin.write(name2 + rec2)
                in_chunk += 1
                st["kept"] += 1
                if st["pairs"] % 20_000_000 == 0:
                    print(f"{st['pairs']:,} pairs, {st['kept']:,} kept, {time.time() - t0:.0f} s", flush=True)
            for p in (p1, p2):
                p.kill()
            if a.max_pairs and st["pairs"] >= a.max_pairs:
                break
    finally:
        if w is not None:
            close_chunk(w)
        for p in (p1, p2):
            if p is not None:
                p.kill()
    st["me_shift"] = {str(d): n for d, n in sorted(shift.items())}
    st["chunks"] = k + 1 if st["kept"] else 0
    st["seconds"] = round(time.time() - t0)
    (out / "barcodes_stats.json").write_text(json.dumps(st, indent=1))
    print(json.dumps({x: v for x, v in st.items() if x != "me_shift"}), flush=True)


if __name__ == "__main__":
    main()
