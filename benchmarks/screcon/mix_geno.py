"""Genotype-assisted few-cell deconvolution (PREREG §12.2): GM12878 + PBMC Dip-C (Tan 2018).

Subcommands
-----------
``cells``   the cells, their hickit re-processing GSM and SRA runs (NCBI E-utilities / SRA run info)::

                python benchmarks/screcon/mix_geno.py cells --out benchmarks/screcon/data/tan2018_dipc_sra.tsv

``split``   development / held-back / genotyping roles (registered rule)::

                python benchmarks/screcon/mix_geno.py split --cells data/tan2018_dipc_sra.tsv --out MIX/geno/split.tsv

``sites``   donor-distinguishing sites -> hickit VCF (haplotype 0 = GM12878 allele, 1 = PBMC allele)::

                python benchmarks/screcon/mix_geno.py sites --giab-vcf HG001.vcf.gz --giab-bed HG001.bed \\
                    --pbmc-calls pbmc_calls.vcf.gz --pbmc-homref pbmc_at_gm_homalt.vcf.gz --out donor_sites.vcf

``label``   donor label of every contact of an authors' table, from the re-aligned contacts::

                python benchmarks/screcon/mix_geno.py label --table cell.pairs.gz --realigned cell.donor.pairs.gz --out cell.donor.npy

``pools``   the registered pools of a set (GP, GGP, GGPP); phased pools (authors' tables) + donor labels::

                python benchmarks/screcon/mix_geno.py pools --split ... --tables DIR --labels DIR --set dev --out MIX/geno/pools

``prior``   the genotype prior of a pool (``--params``: delta, radius, max_nei, pseudo, iters)::

                python benchmarks/screcon/mix_geno.py prior --pool POOL.txt.gz --out POOL.prior.npy
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
GM_CELLS = [1, 2, 3, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 17]
PB_CELLS = list(range(1, 19))
COMPOSITIONS = {"GP": "GP", "GGP": "GGP", "GGPP": "GGPP"}
N_POOLS = {"dev": 6, "test": 8}


def _get(url: str) -> str:
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read().decode()
        except Exception:
            time.sleep(2 + 3 * attempt)
    raise RuntimeError(url)


def cmd_cells(args) -> None:
    rows = []
    for donor, cells, base in (("GM12878", GM_CELLS, 3314358), ("PBMC", PB_CELLS, 3314375)):
        for n in cells:
            gsm = f"GSM{base + n}"
            soft = _get(f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gsm}&targ=self&form=text&view=brief")
            title = re.search(r"!Sample_title = (.*)", soft).group(1).strip()
            srx = re.findall(r"sra\?term=(SRX\d+)", soft)
            runs = []
            for x in srx:
                info = _get(f"https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/runinfo?acc={x}").strip().splitlines()
                hdr = info[0].split(",")
                for line in info[1:]:
                    f = dict(zip(hdr, line.split(",")))
                    runs.append((f["Run"], int(f["spots"]), float(f["size_MB"])))
            supp = re.findall(r"!Sample_supplementary_file_\d+ = (\S+)", soft)
            rows.append({"donor": donor, "cell": n, "gsm_hickit": gsm, "title": title, "srx": ",".join(srx),
                         "srr": ",".join(r[0] for r in runs), "spots": sum(r[1] for r in runs),
                         "size_mb": round(sum(r[2] for r in runs)), "tables": ",".join(supp)})
            print(donor, n, gsm, title, rows[-1]["srr"], flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.out, sep="\t", index=False)


def split_table(cells: pd.DataFrame) -> pd.DataFrame:
    out = []
    gm = sorted(cells[cells.donor == "GM12878"].cell)
    perm = np.random.default_rng(20261007).permutation(len(gm))
    for q, i in enumerate(perm):
        out.append(("GM12878", gm[i], "dev" if q < 6 else "test"))
    pb = sorted(cells[cells.donor == "PBMC"].cell)
    perm = np.random.default_rng(20261008).permutation(len(pb))
    for q, i in enumerate(perm):
        out.append(("PBMC", pb[i], "genotype" if q < 6 else ("dev" if q < 12 else "test")))
    s = pd.DataFrame(out, columns=["donor", "cell", "role"])
    return s.merge(cells, on=["donor", "cell"])


def cmd_split(args) -> None:
    s = split_table(pd.read_csv(args.cells, sep="\t"))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    s.to_csv(args.out, sep="\t", index=False)
    print(s.groupby(["donor", "role"]).cell.apply(list))


# --------------------------------------------------------------------------- sites

def _vcf_rows(path):
    with gzip.open(path, "rt") if str(path).endswith(".gz") else open(path) as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            yield line.rstrip("\n").split("\t")


def _gt(fields, sample_col=9):
    fmt = fields[8].split(":")
    val = fields[sample_col].split(":")
    d = dict(zip(fmt, val))
    return d


def _ad_sum(fields) -> list:
    """Allelic depths summed over every sample column (the pooled genotyping cells)."""
    fmt = fields[8].split(":")
    if "AD" not in fmt:
        return []
    k = fmt.index("AD")
    tot = None
    for col in fields[9:]:
        v = col.split(":")
        if len(v) <= k or v[k] in (".", ""):
            continue
        ad = [int(x) if x != "." else 0 for x in v[k].split(",")]
        tot = ad if tot is None else [a + b for a, b in zip(tot, ad)]
    return tot or []


def read_bed(path):
    bed = {}
    with (gzip.open(path, "rt") if str(path).endswith(".gz") else open(path)) as fh:
        for line in fh:
            if line.startswith(("#", "track", "browser")):
                continue
            c, s, e = line.split()[:3]
            bed.setdefault(c, []).append((int(s), int(e)))
    return {c: (np.array([x[0] for x in sorted(v)]), np.array([x[1] for x in sorted(v)])) for c, v in bed.items()}


def in_bed(bed, chrom, pos0) -> bool:
    if chrom not in bed:
        return False
    s, e = bed[chrom]
    k = np.searchsorted(s, pos0, side="right") - 1
    return k >= 0 and pos0 < e[k]


def cmd_sites(args) -> None:
    """Hom-different biallelic SNVs (see PREREG §12.2) -> VCF for hickit sam2seg -v."""
    bed = read_bed(args.giab_bed)
    gm = {}                                   # (chrom, pos) -> (ref, alt, gt) of GIAB SNVs
    for f in _vcf_rows(args.giab_vcf):
        ref, alt = f[3], f[4]
        if len(ref) != 1 or len(alt) != 1:
            continue
        gt = _gt(f)["GT"].replace("|", "/")
        gm[(f[0], int(f[1]))] = (ref, alt, gt)
    out = []
    # (a) GIAB hom-alt where PBMC is hom-REF (>= min_dp reads, all REF): genotyped at the GIAB sites
    n_a = 0
    for f in _vcf_rows(args.pbmc_homref):
        key = (f[0], int(f[1]))
        g = gm.get(key)
        if g is None or g[2] != "1/1":
            continue
        ad = _ad_sum(f)
        if len(ad) >= 1 and ad[0] >= args.min_dp and sum(ad[1:]) == 0:
            out.append((f[0], int(f[1]), g[0], g[1], "1|0"))      # hap0 (GM) = ALT, hap1 (PBMC) = REF
            n_a += 1
    # (b) GIAB hom-REF (in the high-confidence regions, not in the VCF) where PBMC is called hom-ALT
    n_b = 0
    for f in _vcf_rows(args.pbmc_calls):
        ref, alt = f[3], f[4]
        if len(ref) != 1 or len(alt) != 1 or "," in alt or float(f[5] if f[5] != "." else 0) < args.min_qual:
            continue
        key = (f[0], int(f[1]))
        if key in gm or not in_bed(bed, f[0], int(f[1]) - 1):
            continue
        ad = _ad_sum(f)
        if len(ad) == 2 and ad[0] == 0 and ad[1] >= args.min_dp:
            out.append((f[0], int(f[1]), ref, alt, "0|1"))         # hap0 (GM) = REF, hap1 (PBMC) = ALT
            n_b += 1
    order = {str(c): i for i, c in enumerate(list(range(1, 23)) + ["X", "Y"])}
    out.sort(key=lambda x: (order.get(x[0], 99), x[1]))
    with open(args.out, "w") as fh:
        fh.write("##fileformat=VCFv4.2\n##source=mix_geno.py sites (hap0 = GM12878 allele, hap1 = PBMC allele)\n")
        fh.write('##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n')
        fh.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tdonors\n")
        for c, p, r, a, gt in out:
            fh.write(f"{c}\t{p}\t.\t{r}\t{a}\t.\tPASS\t.\tGT\t{gt}\n")
    print(json.dumps({"gm_homalt_pbmc_homref": n_a, "gm_homref_pbmc_homalt": n_b, "total": len(out)}))


# --------------------------------------------------------------------------- labels

def read_hickit_pairs(path) -> pd.DataFrame:
    cols = None
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith("#columns:"):
                cols = line.split()[1:]
            if not line.startswith("#"):
                break
    df = pd.read_csv(path, sep="\t", comment="#", header=None, names=cols, dtype=str, usecols=range(len(cols)))
    df["pos1"] = df["pos1"].astype(np.int64)
    df["pos2"] = df["pos2"].astype(np.int64)
    return df


def contact_labels(table: pd.DataFrame, realigned: pd.DataFrame) -> np.ndarray:
    """Donor (0 = GM12878, 1 = PBMC, -1 = none) of every row of ``table``: the re-aligned contact with the
    same ends and strands whose phased ends agree."""
    r = realigned.copy()
    ph = r[["phase0", "phase1"]].replace(".", "-1").astype(int).to_numpy()
    lab = np.where((ph[:, 0] >= 0) & (ph[:, 1] >= 0), np.where(ph[:, 0] == ph[:, 1], ph[:, 0], -2), ph.max(1))
    r["donor"] = lab
    r = r[r.donor >= 0]
    key = ["chr1", "pos1", "chr2", "pos2", "strand1", "strand2"]
    r = r.drop_duplicates(key)
    m = table[key].merge(r[key + ["donor"]], on=key, how="left")
    return m["donor"].fillna(-1).astype(int).to_numpy()


def cmd_label(args) -> None:
    t = read_hickit_pairs(args.table)
    r = read_hickit_pairs(args.realigned)
    lab = contact_labels(t, r)
    np.save(args.out, lab)
    v, cnt = np.unique(lab, return_counts=True)
    print(json.dumps({"rows": int(len(lab)), "realigned_rows": int(len(r)), "labels": dict(zip(map(int, v), map(int, cnt)))}))


# --------------------------------------------------------------------------- pools / prior

def pool_cells(split: pd.DataFrame, comp: str, ci: int, p: int, set_name: str):
    rng = np.random.default_rng((80_000 if set_name == "dev" else 90_000) + 100 * ci + p)
    out = []
    for d, n in (("GM12878", comp.count("G")), ("PBMC", comp.count("P"))):
        cand = sorted(split[(split.role == set_name) & (split.donor == d)].cell)
        pick = rng.choice(len(cand), size=n, replace=False)
        out += [(d, cand[q]) for q in sorted(pick)]
    return out


def cmd_pools(args) -> None:
    from mix_type import write_geo
    s = pd.read_csv(args.split, sep="\t")
    out = Path(args.out) / args.set
    out.mkdir(parents=True, exist_ok=True)
    cache = {}
    for ci, comp in enumerate(COMPOSITIONS):
        for p in range(1, N_POOLS[args.set] + 1):
            cells = pool_cells(s, comp, ci, p, args.set)
            name = f"{comp}_p{p}"
            if (out / f"{name}.pairs.gz").exists() and not args.overwrite:
                continue
            parts, labs = [], []
            for j, (d, n) in enumerate(cells):
                tag = f"{'gm12878' if d == 'GM12878' else 'pbmc'}_{n:02d}"
                if tag not in cache:
                    t = read_hickit_pairs(Path(args.tables) / f"{tag}.pairs.gz")
                    auto = [str(i) for i in range(1, 23)]
                    keep = t.chr1.isin(auto) & t.chr2.isin(auto)          # autosomes (donor sexes differ)
                    lab = np.load(Path(args.labels) / f"{tag}.donor.npy")
                    cache[tag] = (t[keep].reset_index(drop=True), lab[keep.to_numpy()])
                t, lab = cache[tag]
                parts.append(t)
                labs.append(lab)
                _write_pairs(out / f"{name}_cell{j}.pairs.gz", t)
                write_geo(out / f"{name}_cell{j}.txt.gz", t.rename(columns={"chr1": "chrom1", "chr2": "chrom2"}))
            df = pd.concat(parts, ignore_index=True)
            cell = np.concatenate([np.full(len(x), j, np.int16) for j, x in enumerate(parts)])
            lab = np.concatenate(labs)
            order = np.random.default_rng(7 * p + 13 * ci).permutation(len(df))
            df = df.iloc[order].reset_index(drop=True)
            _write_pairs(out / f"{name}.pairs.gz", df)
            write_geo(out / f"{name}.txt.gz", df.rename(columns={"chr1": "chrom1", "chr2": "chrom2"}))
            np.savez_compressed(out / f"{name}.origin.npz", cell=cell[order], cells=np.array([f"{d}:{n}" for d, n in cells]),
                                donor_label=lab[order], n_reads=np.array([len(x) for x in parts]))
            (out / f"{name}.json").write_text(json.dumps({
                "name": name, "k": len(cells), "pool": p, "composition": comp, "set": args.set, "dataset": "tan2018_dipc",
                "cells": [f"{d}:{n}" for d, n in cells], "donors": [0 if d == "GM12878" else 1 for d, _ in cells]}, indent=1))
            print(name, len(df), flush=True)


def _write_pairs(path, df) -> None:
    with gzip.open(path, "wt") as fh:
        fh.write("## pairs format v1.0\n#columns: readID chr1 pos1 chr2 pos2 strand1 strand2 phase0 phase1\n")
        for q, r in enumerate(zip(df.chr1, df.pos1, df.chr2, df.pos2, df.strand1, df.strand2, df.phase0, df.phase1)):
            fh.write("r%d\t%s\t%d\t%s\t%d\t%s\t%s\t%s\t%s\n" % ((q,) + r))


def genotype_prior(pool: str, params: dict) -> np.ndarray:
    """Donor labels -> per-contact prior over the pool's cells, spread to unlabelled contacts by 2-D
    neighbours (hickit-style imputation)."""
    import uchrom_recon as un
    from contacts import read_contacts
    meta = json.loads(Path(pool[:-7] + ".json").read_text())
    donors = np.array(meta["donors"])
    k = len(donors)
    lab = np.load(pool[:-7] + ".origin.npz")["donor_label"].astype(int)
    delta = float(params.get("delta", 0.02))
    c = read_contacts(pool)
    # donor probability per contact (2 donors), labelled fixed, unlabelled from neighbours
    q = np.full((len(lab), 2), 0.5)
    q[lab == 0] = [1 - delta, delta]
    q[lab == 1] = [delta, 1 - delta]
    if int(params.get("iters", 20)) > 0:
        off, nb, w = un.mix_neighbours(c.chrom_a.astype(str), c.pos_a, c.chrom_b.astype(str), c.pos_b,
                                       radius=int(params.get("radius", 10_000_000)), max_nei=int(params.get("max_nei", 50)))
        pseudo = float(params.get("pseudo", 0.4))
        free = lab < 0
        rows = np.repeat(np.arange(len(lab)), np.diff(off))
        for _ in range(int(params.get("iters", 20))):
            v = np.full((len(lab), 2), pseudo / 2)
            np.add.at(v, rows, w[:, None] * q[nb])
            newq = v / v.sum(1, keepdims=True)
            q[free] = newq[free]
    P = np.zeros((len(lab), k))
    for d in (0, 1):
        sel = donors == d
        if sel.any():
            P[:, sel] = q[:, [d]] / sel.sum()
    P[:, ~np.isin(donors, [0, 1])] = 0
    P /= P.sum(1, keepdims=True)
    return P


def cmd_prior(args) -> None:
    P = genotype_prior(args.pool, json.loads(args.params))
    np.save(args.out, P)
    if args.score:
        o = np.load(args.pool[:-7] + ".origin.npz")
        meta = json.loads(Path(args.pool[:-7] + ".json").read_text())
        donors = np.array(meta["donors"])
        cell = o["cell"].astype(int)
        lab = o["donor_label"].astype(int)
        dtrue = donors[cell]
        pd_ = (P[:, donors == 1].sum(1) > 0.5).astype(int)
        print(f"{Path(args.pool).name}: labelled {np.mean(lab >= 0):.3f}, label accuracy {np.mean(lab[lab >= 0] == dtrue[lab >= 0]):.3f}, "
              f"donor accuracy after spreading {np.mean(pd_ == dtrue):.3f}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("cells")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_cells)
    s = sub.add_parser("split")
    s.add_argument("--cells", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_split)
    s = sub.add_parser("sites")
    s.add_argument("--giab-vcf", required=True)
    s.add_argument("--giab-bed", required=True)
    s.add_argument("--pbmc-calls", required=True)
    s.add_argument("--pbmc-homref", required=True)
    s.add_argument("--min-dp", type=int, default=4)
    s.add_argument("--min-qual", type=float, default=30)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_sites)
    s = sub.add_parser("label")
    s.add_argument("--table", required=True)
    s.add_argument("--realigned", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_label)
    s = sub.add_parser("pools")
    s.add_argument("--split", required=True)
    s.add_argument("--tables", required=True)
    s.add_argument("--labels", required=True)
    s.add_argument("--set", required=True, choices=["dev", "test"])
    s.add_argument("--overwrite", action="store_true")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_pools)
    s = sub.add_parser("prior")
    s.add_argument("--pool", required=True)
    s.add_argument("--params", default="{}")
    s.add_argument("--score", action="store_true", help="DEVELOPMENT ONLY: label coverage / accuracy")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_prior)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
