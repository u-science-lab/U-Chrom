"""Build the Uni-C stores of the atlas (Gao et al. 2025, Nat. Commun., doi:10.1038/s41467-025-62215-w;
GEO GSE267873).

Uni-C (Uniform Chromosome Conformation Capture) sequences single cells deeply: chromatin contacts and, from the
same reads, genome-wide variants.  The deposited pairs (pairtools, deduplicated, MAPQ >= 40; GRCh37 / GRCm38 with
Ensembl chromosome names) hold every read pair; most are cis pairs closer than 1 kb (fragments read through: the
uniform coverage the variants come from).  Contacts here are cis pairs at least 1 kb apart and trans pairs; in a
single cell, contacts whose ends fall in the same pair of 1-kb bins count once (copies of one ligation junction made
by whole-genome amplification, which exact-position deduplication keeps).  Two
stores, no 3-D coordinates:

  unic2025/unic_human.chromdata.zarr   hg19: GM12878 (10 cells), COLO320-DM (6), circulating tumour cells of the
                                       pancreatic cancer PDX mouse PanT24 (7); bulk GM12878, COLO320-DM, PanT24 tumour
  unic2025/unic_mouse.chromdata.zarr   mm10: circulating tumour cells of the KPC mice KPC0402 (6) and KPC0403 (6),
                                       the monoclonal MC38 line (8); bulk MC38 (two libraries, merged)

Each store links, next to it: ``<stem>_cells_100kb.scool`` and ``<stem>_cells_1Mb.scool`` (one map per cell),
per sample the merged map of its cells (``<stem>_cells_<sample>.mcool``, 100, 200, 500 kb, 1 Mb) and of its bulk library
(``<stem>_bulk_<sample>.mcool``, 25 kb - 1 Mb), ICE-balanced from 100 kb up.  Cells: sample, kind, GSM, read
pairs, contact pairs and unique contacts, cis / trans, the fractions of cis contacts of at least 25 kb that span 25 kb - 2 Mb (``frac_near``)
and 2 - 12 Mb (``frac_mitotic``, the band mitotic chromosomes fill; Nagano et al. 2017).  Embedding: scHiCluster on
the 1 Mb maps (PCA).  The per-cell VCFs of the series are not used.

Inputs: ``python example-data/download_data.py --unic2025`` (110 GB).

Usage::

    python example-data/build_unic2025.py human [--workers 6]
    python example-data/build_unic2025.py mouse
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sc_hic_common import balance_mcool, bin_table, empty_spots, log, stream_pairs  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "unic2025"
RAW = OUT / "raw" / "GSE267873"
SOURCE = "Gao et al. 2025, Nat. Commun. (doi:10.1038/s41467-025-62215-w); GEO GSE267873"
MIN_CIS = 1000
DEDUP_BIN = 1000          # single cells: one contact per pair of 1-kb bins (amplification copies)
CELL_RES = (100_000, 1_000_000)
BULK_RES = 25_000
#: sample -> (file prefix of its cells, bulk file names, what the cells are)
STORES = {
    "human": {"assembly": "hg19", "chroms": [str(i) for i in range(1, 23)] + ["X", "Y"], "samples": {
        "GM12878": ("GM12878", ["GM12878-BULK"], "GM12878 lymphoblastoid cell line"),
        "COLO320DM": ("COLO320DM", ["COLO320DM-BULK"], "COLO320-DM colorectal cancer cell line (ecDNA)"),
        "PanT24": ("PanT24", ["PanT24-Tumor"], "circulating tumour cell, pancreatic cancer PDX mouse PanT24"),
    }},
    "mouse": {"assembly": "mm10", "chroms": [str(i) for i in range(1, 20)] + ["X", "Y"], "samples": {
        "KPC0402": ("KPC0402", [], "circulating tumour cell, KPC mouse 0402 (spontaneous pancreatic cancer)"),
        "KPC0403": ("KPC0403", [], "circulating tumour cell, KPC mouse 0403 (spontaneous pancreatic cancer)"),
        "MC38": ("MC38-Uni-C", ["MC38-BULK-1", "MC38-BULK-2"], "MC38 colon adenocarcinoma, monoclonal line"),
    }},
}


def header_sizes(path: Path, chroms) -> dict:
    """``chr<name>`` -> length from a pairs header (``#chromsize: 1 249250621``), the given chromosomes in order."""
    sizes = {}
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if not line.startswith("#"):
                break
            parts = line.split()
            if parts[0] == "#chromsize:" and len(parts) >= 3:
                sizes[parts[1]] = int(parts[2])
    return {f"chr{c}": sizes[c] for c in chroms if c in sizes}


def _offsets(sizes: dict, res: int):
    n = np.array([-(-v // res) for v in sizes.values()], dtype=np.int64)
    return np.r_[0, np.cumsum(n)[:-1]], int(n.sum())


def _reduce(parts):
    """Sum the counts of equal keys over (keys, counts) blocks."""
    if not parts:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    k = np.concatenate([p[0] for p in parts])
    c = np.concatenate([p[1] for p in parts])
    order = np.argsort(k, kind="stable")
    k, c = k[order], c[order]
    first = np.r_[True, k[1:] != k[:-1]]
    idx = np.flatnonzero(first)
    return k[idx], np.add.reduceat(c, idx)


def bin_file(args):
    """One pairs file -> its statistics and (keys, counts) of its contacts at each resolution.

    ``collapse`` (single cells): contacts whose two ends fall in the same pair of 1-kb bins are one contact.
    Whole-genome amplification copies a ligation junction many times with different read ends, which
    pairtools' exact-position deduplication keeps (in these cells 80-90 % of the contact pairs); scHi-C pipelines
    (hickit, Dip-C) merge them the same way.  Bulk libraries are binned as deposited."""
    path, sizes, resolutions, collapse = args
    index = {c: i for i, c in enumerate(sizes)}
    offs = {r: _offsets(sizes, r) for r in resolutions}
    off1k, n1k = _offsets(sizes, DEDUP_BIN)
    acc = {r: [] for r in resolutions}
    ukeys: list = []
    st = dict(n_pairs=0, n_cis_short=0, n_contact_pairs=0, n_cis=0, n_trans=0, n_other_chrom=0,
              n_cis_25k=0, n_near=0, n_mitotic=0)
    for df in stream_pairs(path, {"chr1": 1, "pos1": 2, "chr2": 3, "pos2": 4}):
        st["n_pairs"] += len(df)
        code = {}
        for col in ("chr1", "chr2"):
            cats = df[col].cat.categories
            table = np.array([index.get("chr" + str(c), -1) for c in cats], dtype=np.int64)
            cc = df[col].cat.codes.to_numpy()
            code[col] = np.where(cc >= 0, table[np.maximum(cc, 0)], -1)
        c1, c2 = code["chr1"], code["chr2"]
        p1, p2 = df["pos1"].to_numpy(np.int64), df["pos2"].to_numpy(np.int64)
        ok = (c1 >= 0) & (c2 >= 0)
        st["n_other_chrom"] += int((~ok).sum())
        cis = ok & (c1 == c2)
        short = cis & (np.abs(p2 - p1) < MIN_CIS)
        st["n_cis_short"] += int(short.sum())
        keep = ok & ~short
        st["n_contact_pairs"] += int(keep.sum())
        c1, c2, p1, p2 = c1[keep], c2[keep], p1[keep], p2[keep]
        if collapse:
            g1, g2 = off1k[c1] + p1 // DEDUP_BIN, off1k[c2] + p2 // DEDUP_BIN
            ukeys.append(np.unique(np.minimum(g1, g2) * n1k + np.maximum(g1, g2)))
            if len(ukeys) >= 8:
                ukeys = [np.unique(np.concatenate(ukeys))]
            continue
        _count(st, c1, p1, c2, p2)
        for r in resolutions:
            off, nb = offs[r]
            g1, g2 = off[c1] + p1 // r, off[c2] + p2 // r
            u, n = np.unique(np.minimum(g1, g2) * nb + np.maximum(g1, g2), return_counts=True)
            acc[r].append((u, n.astype(np.int64)))
        if len(acc[resolutions[0]]) >= 8:                      # keep the blocks few
            for r in resolutions:
                acc[r] = [_reduce(acc[r])]
    if collapse:
        k = np.unique(np.concatenate(ukeys)) if ukeys else np.zeros(0, np.int64)
        lo, hi = k // n1k, k % n1k
        c1 = np.searchsorted(off1k, lo, side="right") - 1
        c2 = np.searchsorted(off1k, hi, side="right") - 1
        p1 = (lo - off1k[c1]) * DEDUP_BIN + DEDUP_BIN // 2         # bin centres
        p2 = (hi - off1k[c2]) * DEDUP_BIN + DEDUP_BIN // 2
        _count(st, c1, p1, c2, p2)
        out = {}
        for r in resolutions:
            off, nb = offs[r]
            g1, g2 = off[c1] + p1 // r, off[c2] + p2 // r
            u, n = np.unique(np.minimum(g1, g2) * nb + np.maximum(g1, g2), return_counts=True)
            out[r] = (u, n.astype(np.int64))
        return str(path), st, out
    return str(path), st, {r: _reduce(acc[r]) for r in resolutions}


def _count(st, c1, p1, c2, p2) -> None:
    """Contact statistics: cis / trans, and the cis contacts of at least 25 kb by separation."""
    cis = c1 == c2
    d = np.abs(p2 - p1)
    st["n_cis"] += int(cis.sum())
    st["n_trans"] += int((~cis).sum())
    far = cis & (d >= 25_000)
    st["n_cis_25k"] += int(far.sum())
    st["n_near"] += int((far & (d < 2_000_000)).sum())
    st["n_mitotic"] += int((cis & (d >= 2_000_000) & (d < 12_000_000)).sum())


def pixels(keys: np.ndarray, counts: np.ndarray, nb: int) -> pd.DataFrame:
    return pd.DataFrame({"bin1_id": keys // nb, "bin2_id": keys % nb, "count": counts.astype(np.int64)})


def write_mcool(path: Path, sizes: dict, base: int, keys, counts, resolutions) -> Path:
    import cooler

    _, nb = _offsets(sizes, base)
    tmp = path.with_suffix(".base.cool")
    cooler.create_cooler(str(tmp), bin_table(sizes, base), pixels(keys, counts, nb), ordered=True)
    if path.exists():
        path.unlink()
    cooler.zoomify_cooler(str(tmp), str(path), sorted(resolutions), chunksize=10_000_000)
    tmp.unlink()
    balance_mcool(path, min_res=100_000)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("species", choices=sorted(STORES))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--test", type=int, default=0, help="only the first N cells of each sample, no bulk")
    args = ap.parse_args()

    import cooler

    from uchrom import ChromData
    from uchrom.emb import embed_cells, scool_cell_features

    spec = STORES[args.species]
    stem = OUT / f"unic_{args.species}{'_test' if args.test else ''}"
    jobs, rows = [], []
    for sample, (prefix, bulks, what) in spec["samples"].items():
        files = sorted(RAW.glob(f"GSM*_{prefix}-Cell*.pairs.gz"),
                       key=lambda p: int(re.search(r"-Cell(\d+)\.pairs", p.name).group(1)))
        if args.test:
            files = files[:args.test]
        for f in files:
            n = int(re.search(r"-Cell(\d+)\.pairs", f.name).group(1))
            rows.append({"cell_id": f"{sample}_Cell{n}", "sample": sample, "kind": what, "gsm": f.name.split("_")[0],
                         "file": str(f)})
            jobs.append(("cell", f"{sample}_Cell{n}", f))
        if not args.test:
            for b in bulks:
                hit = sorted(RAW.glob(f"GSM*_{b}.pairs.gz"))
                if not hit:
                    raise SystemExit(f"{b}: no pairs file under {RAW}")
                jobs.append(("bulk", sample, hit[0]))
    if not rows:
        raise SystemExit(f"no cells under {RAW}: python example-data/download_data.py --unic2025")
    sizes = header_sizes(Path(rows[0]["file"]), spec["chroms"])
    log(f"{args.species}: {len(rows)} cells, {sum(j[0] == 'bulk' for j in jobs)} bulk libraries, "
        f"{len(sizes)} chromosomes ({spec['assembly']})")

    cells = pd.DataFrame(rows).set_index("cell_id")
    cell_px = {r: {} for r in CELL_RES}
    bulk_px = {}
    stats = {}
    tasks = [(f, sizes, CELL_RES if kind == "cell" else (BULK_RES,), kind == "cell") for kind, _, f in jobs]
    who = {str(f): (kind, name) for kind, name, f in jobs}
    with Pool(args.workers) as pool:
        for path, st, px in pool.imap_unordered(bin_file, tasks):
            kind, name = who[path]
            if kind == "cell":
                stats[name] = st
                for r in CELL_RES:
                    cell_px[r][name] = px[r]
            else:
                bulk_px.setdefault(name, []).append(px[BULK_RES])
                stats[f"bulk:{name}:{Path(path).name}"] = st
            log(f"  {Path(path).name}: {st['n_pairs']:,} pairs, {st['n_contact_pairs']:,} contact pairs, "
                f"{st['n_cis'] + st['n_trans']:,} contacts{' (unique)' if kind == 'cell' else ''} "
                f"({st['n_trans'] / max(1, st['n_cis'] + st['n_trans']):.1%} trans)")

    st = pd.DataFrame({k: v for k, v in stats.items() if not k.startswith("bulk:")}).T.reindex(cells.index)
    cells["n_pairs"] = st["n_pairs"].astype(np.int64)
    cells["n_contact_pairs"] = st["n_contact_pairs"].astype(np.int64)      # before merging amplification copies
    cells["n_contacts"] = (st["n_cis"] + st["n_trans"]).astype(np.int64)    # unique (1-kb bin pairs)
    cells["n_cis"] = st["n_cis"].astype(np.int64)
    cells["n_trans"] = st["n_trans"].astype(np.int64)
    cells["n_cis_short"] = st["n_cis_short"].astype(np.int64)
    cells["frac_trans"] = cells["n_trans"] / cells["n_contacts"].clip(lower=1)
    cells["frac_near"] = st["n_near"] / st["n_cis_25k"].clip(lower=1)
    cells["frac_mitotic"] = st["n_mitotic"] / st["n_cis_25k"].clip(lower=1)
    cells = cells.drop(columns=["file"])
    for k, v in stats.items():
        if k.startswith("bulk:"):
            log(f"{k}: {v['n_pairs']:,} pairs, {v['n_cis'] + v['n_trans']:,} contacts")

    # per-cell maps
    names = sorted(cells.index)
    scools = {}
    for r in CELL_RES:
        _, nb = _offsets(sizes, r)
        tag = f"{r // 1000}kb" if r < 1_000_000 else f"{r // 1_000_000}Mb"
        path = stem.with_name(f"{stem.name}_cells_{tag}.scool")
        if path.exists():
            path.unlink()
        cooler.create_scool(str(path), bin_table(sizes, r),
                            {n: pixels(*cell_px[r][n], nb) for n in names}, ordered=True)
        scools[r] = path
        log(f"wrote {path.name}")
    # per sample: its cells merged, its bulk library
    merged = {}
    for sample in spec["samples"]:
        mine = cells.index[cells["sample"] == sample]
        if len(mine):
            k, c = _reduce([cell_px[CELL_RES[0]][n] for n in mine])
            merged[f"cells_{sample}"] = write_mcool(stem.with_name(f"{stem.name}_cells_{sample}.mcool"), sizes,
                                                    CELL_RES[0], k, c, (100_000, 200_000, 500_000, 1_000_000))
        if sample in bulk_px:
            k, c = _reduce(bulk_px[sample])
            merged[f"bulk_{sample}"] = write_mcool(stem.with_name(f"{stem.name}_bulk_{sample}.mcool"), sizes,
                                                   BULK_RES, k, c, (25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000))
        log(f"{sample}: merged maps written")

    cd = ChromData(np.zeros((0, 3)), empty_spots(), cells=cells,
                   uns={"genome_assembly": spec["assembly"], "source": SOURCE,
                        "coordinate_status": "no 3-D coordinates: contacts only",
                        "contacts_filter": (f"cis pairs closer than {MIN_CIS} bp dropped (read-through fragments); per cell, "
                                           f"contacts in one pair of {DEDUP_BIN // 1000}-kb bins counted once (amplification copies)")})
    feats, _, _ = scool_cell_features(str(scools[1_000_000]), names, chroms=[c for c in sizes if c != "chrY"])
    order = pd.Index(names).get_indexer(cd.cells.index)
    embed_cells(cd, source="hic", matrix=feats[order], normalization="none", methods=("pca",),
                n_pcs=min(10, len(names) - 1),
                features="scHiCluster (convolution + random walk + binarise) of the per-cell 1 Mb maps")
    for sample in spec["samples"]:
        if f"bulk_{sample}" in merged:
            cd.link_cool(merged[f"bulk_{sample}"].name, key=f"bulk_{sample}", label=f"{sample} bulk")
    for sample in spec["samples"]:
        if f"cells_{sample}" in merged:
            cd.link_cool(merged[f"cells_{sample}"].name, key=f"cells_{sample}", label=f"{sample} cells (merged)")
    cd.link_scool(scools[CELL_RES[0]].name, key="per_cell", label="Per cell, 100 kb", cell_name="cell_id",
                  genome_assembly=spec["assembly"], bin_size=CELL_RES[0])
    cd.link_scool(scools[1_000_000].name, key="per_cell_1mb", label="Per cell, 1 Mb", cell_name="cell_id",
                  genome_assembly=spec["assembly"], bin_size=1_000_000)
    out = stem.with_name(stem.name + ".chromdata.zarr")
    cd.write(out)
    log(f"wrote {out}: {cd}")


if __name__ == "__main__":
    main()
