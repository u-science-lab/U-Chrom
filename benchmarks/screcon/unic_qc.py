"""Uni-C GM12878 (Gao et al. 2025, GSE267873) contact QC and a phasing-yield projection, next to Dip-C GM12878
(Tan 2018) and scMicro-C GM12878 (Wu 2025) processed the same way.  Exploratory, not pre-registered.

The Uni-C raw reads (SRA SRX24523753 ...) are not public (SRA status "hup", 2026-10-04), so the contacts cannot
be phased at the read level.  What can be measured from the public ``.pairs.gz`` (positions + strands only):

``hets``      phased heterozygous SNVs of a VCF (``0|1`` / ``1|0``) -> ``.npz`` (chrom -> sorted positions).

``stats``     on a hickit-filtered ``.pairs[.gz]`` (``hickit -i`` = de-duplication ``--dup-dist`` + legs >= 1 kb,
              run by ``sherlock/unic_qc.sbatch``): contacts, cis / trans, separation histogram and P(s) slopes,
              legs per 1 kb bin (fragment-end multiplicity: WGA chimeras / near-duplicates pile up), contacts per
              particle of a diploid female genome at 100 kb .. 1 kb, the actual phased-leg fraction when the file
              has ``phase0`` / ``phase1``, and the fraction of legs whose read footprint (``--read-len`` from the
              leg position, three conventions: ``down`` = the read runs from ``pos`` in the strand direction (4DN /
              pairtools 5' end), ``up`` = the opposite, ``both`` = either) covers a phased het SNV (``--hets``).
              On a file with phases, ``phased_legs_with_het`` (fraction of the actually phased legs with a het in
              the footprint) tells which convention the file uses.

``project``   Uni-C phased-leg fraction expected from a Dip-C-like pipeline = Uni-C footprint fraction x the
              calibration (actual / footprint, same convention) of the reference datasets with phases; contacts
              with >= 1 / 2 phased ends assuming independent legs.  Default convention ``both``: in the hickit pairs
              of Dip-C and scMicro-C about half of the phased legs have their het downstream and half upstream of
              the leg position (it is not the read's 5' end), so only the symmetric footprint is comparable.

    python benchmarks/screcon/unic_qc.py hets --vcf HG001_GRCh37...vcf.gz --strip-chr --out hets_grch37.npz
    python benchmarks/screcon/unic_qc.py stats --pairs cell.dd100.pairs.gz --hets hets_grch37.npz --label unic_1 --out S.json
    python benchmarks/screcon/unic_qc.py project --unic S1.json S2.json --ref D1.json M1.json --out P.json
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import numpy as np

RESOLUTIONS = (100_000, 20_000, 10_000, 5_000, 2_000, 1_000)
SEP_EDGES = np.logspace(3, 8.5, 23)          # 1 kb .. 316 Mb, 4 bins per decade
SLOPE_WINDOWS = {"1k-10k": (1e3, 1e4), "10k-100k": (1e4, 1e5), "100k-2M": (1e5, 2e6), "2M-20M": (2e6, 2e7)}


def _open(path):
    return gzip.open(path, "rt") if str(path).endswith(".gz") else open(path)


def _norm(c):
    c = str(c)
    return c[3:] if c.lower().startswith("chr") else c


def _header(path):
    cols, sizes = None, {}
    with _open(path) as fh:
        for line in fh:
            if not line.startswith("#"):
                break
            f = line.split()
            if line.startswith("#columns:"):
                cols = f[1:]
            elif line.startswith(("#chromsize:", "#chromosome:")) and len(f) >= 3:
                sizes[_norm(f[1])] = int(f[2])
    return cols, sizes


# --------------------------------------------------------------------------- hets

def cmd_hets(args) -> None:
    import pandas as pd
    pos = {}
    n_all = n_ph = 0
    for chunk in pd.read_csv(args.vcf, sep="\t", comment="#", header=None, usecols=[0, 1, 3, 4, 9],
                             names=["c", "p", "ref", "alt", "s"], dtype={"c": str, "p": np.int64, "ref": str,
                                                                        "alt": str, "s": str}, chunksize=1_000_000):
        snv = (chunk["ref"].str.len() == 1) & (chunk["alt"].str.len() == 1)
        gt = chunk["s"].str.split(":", n=1).str[0]
        het = snv & gt.isin(["0|1", "1|0", "0/1", "1/0"])
        ph = snv & gt.isin(["0|1", "1|0"])
        n_all += int(het.sum()); n_ph += int(ph.sum())
        for c, g in chunk[ph].groupby("c"):
            pos.setdefault(_norm(c) if args.strip_chr else c, []).append(g["p"].to_numpy())
    out = {c: np.sort(np.concatenate(v)) for c, v in pos.items()}
    np.savez_compressed(args.out, **out)
    meta = {"vcf": args.vcf, "het_snv": n_all, "phased_het_snv": n_ph, "chroms": sorted(out)}
    Path(args.out + ".json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))


# --------------------------------------------------------------------------- stats

def _read_pairs(path):
    import pandas as pd
    cols, sizes = _header(path)
    if cols is None:
        cols = ["readID", "chr1", "pos1", "chr2", "pos2", "strand1", "strand2"]
    cols = ["chr1" if c == "chrom1" else "chr2" if c == "chrom2" else c for c in cols]
    use = [c for c in ("chr1", "pos1", "chr2", "pos2", "strand1", "strand2", "phase0", "phase1") if c in cols]
    df = pd.read_csv(path, sep="\t", comment="#", header=None, names=cols, usecols=use,
                     dtype={"chr1": "category", "chr2": "category", "pos1": np.int64, "pos2": np.int64,
                            "strand1": "category", "strand2": "category", "phase0": "category",
                            "phase1": "category"})
    for k in ("chr1", "chr2"):
        df[k] = df[k].astype(str).map(_norm)
    return df, sizes


def _footprint_hit(hets, chrom, pos, strand, L):
    """Per leg: het SNV in [pos, pos+L) / (pos-L, pos] by strand ('down'), the opposite ('up'), or either."""
    down = np.zeros(len(pos), bool)
    up = np.zeros(len(pos), bool)
    plus = strand == "+"
    for c in np.unique(chrom):
        h = hets.get(c)
        if h is None:
            continue
        m = np.flatnonzero(chrom == c)
        p = pos[m]
        # number of hets in [a, b] = searchsorted(b, right) - searchsorted(a, left)
        right = np.searchsorted(h, p + L - 1, "right") - np.searchsorted(h, p, "left") > 0     # [p, p+L-1]
        left = np.searchsorted(h, p, "right") - np.searchsorted(h, p - L + 1, "left") > 0      # [p-L+1, p]
        down[m] = np.where(plus[m], right, left)
        up[m] = np.where(plus[m], left, right)
    return {"down": down, "up": up, "both": down | up}


def _slope(edges, counts, lo, hi):
    mid = np.sqrt(edges[:-1] * edges[1:])
    dens = counts / np.diff(edges)
    ok = (mid >= lo) & (mid <= hi) & (dens > 0)
    if ok.sum() < 2:
        return None
    return float(np.polyfit(np.log10(mid[ok]), np.log10(dens[ok]), 1)[0])


def stats(path, hets=None, read_len=150, label=None, ploidy_x=2) -> dict:
    df, sizes = _read_pairs(path)
    c1, c2 = df["chr1"].to_numpy(), df["chr2"].to_numpy()
    p1, p2 = df["pos1"].to_numpy(), df["pos2"].to_numpy()
    main = {str(k) for k in range(1, 23)} | {"X"}
    keep = np.isin(c1, list(main)) & np.isin(c2, list(main))
    n_all = len(df)
    df = df[keep]
    c1, c2, p1, p2 = c1[keep], c2[keep], p1[keep], p2[keep]
    n = len(df)
    cis = c1 == c2
    sep = np.abs(p2 - p1)[cis]
    hist, _ = np.histogram(sep, SEP_EDGES)
    out = {"file": str(path), "label": label, "rows": int(n_all), "contacts": int(n),
           "dropped_other_chroms": int(n_all - n), "frac_cis": float(cis.mean()),
           "frac_trans": float(1 - cis.mean()),
           "cis_ge": {f"{t // 1000}kb": int((sep >= t).sum()) for t in (1000, 10_000, 100_000, 1_000_000)},
           "sep_edges": SEP_EDGES.tolist(), "sep_hist": hist.tolist(),
           "ps_slope": {k: _slope(SEP_EDGES, hist, lo, hi) for k, (lo, hi) in SLOPE_WINDOWS.items()}}
    # legs per 1 kb bin (fragment-end multiplicity)
    legs_c = np.concatenate([c1, c2])
    legs_p = np.concatenate([p1, p2])
    codes = {c: i for i, c in enumerate(sorted(main))}
    key = np.array([codes[c] for c in legs_c], np.int64) * 1_000_000 + legs_p // 1000
    _, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    per_leg = cnt[inv]
    out["legs_per_1kb_bin"] = {"occupied_bins": int(len(cnt)), "mean": float(cnt.mean()),
                               "p50": float(np.percentile(cnt, 50)), "p99": float(np.percentile(cnt, 99)),
                               "max": int(cnt.max()),
                               **{f"frac_legs_in_bins_gt{k}": float((per_leg > k).mean()) for k in (2, 4, 8, 16)}}
    # contacts per particle (diploid female: two copies of every autosome and chrX)
    glen = {c: sizes.get(c, int(max(p1[c1 == c].max(initial=0), p2[c2 == c].max(initial=0)))) for c in main}
    out["genome_bp"] = int(sum(glen.values()))
    out["contacts_per_particle"] = {}
    for r in RESOLUTIONS:
        parts = 2 * sum(int(np.ceil(v / r)) for v in glen.values())
        out["contacts_per_particle"][str(r)] = {"particles": parts, "contacts": float(n / parts)}
    # phases
    if "phase0" in df and "phase1" in df:
        ph0 = (df["phase0"].astype(str) != ".").to_numpy()
        ph1 = (df["phase1"].astype(str) != ".").to_numpy()
        out["actual"] = {"frac_legs_phased": float((ph0.sum() + ph1.sum()) / (2 * n)),
                         "frac_contacts_ge1_phased": float((ph0 | ph1).mean()),
                         "frac_contacts_both_phased": float((ph0 & ph1).mean())}
    if hets is not None and "strand1" in df:
        s = np.concatenate([df["strand1"].astype(str).to_numpy(), df["strand2"].astype(str).to_numpy()])
        hit = _footprint_hit(hets, legs_c, legs_p, s, read_len)
        out["footprint"] = {"read_len": read_len,
                            **{f"frac_legs_{k}": float(v.mean()) for k, v in hit.items()},
                            **{f"frac_contacts_ge1_{k}": float((v[:n] | v[n:]).mean()) for k, v in hit.items()},
                            **{f"frac_contacts_both_{k}": float((v[:n] & v[n:]).mean()) for k, v in hit.items()}}
        if "actual" in out:
            legs_ph = np.concatenate([ph0, ph1])
            out["footprint"]["phased_legs_with_het"] = {k: float(v[legs_ph].mean()) for k, v in hit.items()}
            out["footprint"]["calibration"] = {k: out["actual"]["frac_legs_phased"] / max(float(v.mean()), 1e-12)
                                               for k, v in hit.items()}
    return out


def cmd_stats(args) -> None:
    hets = dict(np.load(args.hets)) if args.hets else None
    out = stats(args.pairs, hets, args.read_len, args.label)
    if args.counts:
        out["pipeline_counts"] = json.loads(Path(args.counts).read_text())
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1))
    brief = {k: out[k] for k in ("label", "contacts", "frac_trans", "ps_slope")}
    brief["cpp_5kb"] = out["contacts_per_particle"]["5000"]["contacts"]
    for k in ("actual", "footprint"):
        if k in out:
            brief[k] = out[k]
    print(json.dumps(brief, default=float))


# --------------------------------------------------------------------------- projection

def cmd_project(args) -> None:
    conv = args.convention
    refs = [json.loads(Path(p).read_text()) for p in args.ref]
    unic = [json.loads(Path(p).read_text()) for p in args.unic]
    calib = {}
    for r in refs:
        fp = r["footprint"]
        calib[r["label"]] = {"convention": conv, "phased_legs_with_het": fp["phased_legs_with_het"],
                             "ratio": fp["calibration"][conv], "actual_legs": r["actual"]["frac_legs_phased"],
                             "footprint_legs": fp[f"frac_legs_{conv}"]}
    ratios = [v["ratio"] for v in calib.values()]
    rows = []
    for u in unic:
        f = u["footprint"][f"frac_legs_{conv}"]
        row = {"label": u["label"], "contacts": u["contacts"], "footprint_legs": f}
        for name, q in (("min", min(ratios)), ("max", max(ratios))):
            p = f * q
            row[f"proj_legs_{name}"] = p
            row[f"proj_ge1_{name}"] = 1 - (1 - p) ** 2
            row[f"proj_both_{name}"] = p * p
            row[f"proj_ge1_contacts_{name}"] = u["contacts"] * (1 - (1 - p) ** 2)
        rows.append(row)
    out = {"convention": conv, "calibration": calib, "unic": rows,
           "refs": {r["label"]: {"contacts": r["contacts"], **r["actual"]} for r in refs}}
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hets")
    h.add_argument("--vcf", required=True)
    h.add_argument("--strip-chr", action="store_true", help="store chromosome names without 'chr'")
    h.add_argument("--out", required=True)
    h.set_defaults(fn=cmd_hets)
    s = sub.add_parser("stats")
    s.add_argument("--pairs", required=True)
    s.add_argument("--hets")
    s.add_argument("--read-len", type=int, default=150)
    s.add_argument("--label")
    s.add_argument("--counts", help="JSON of pipeline row counts (raw, hickit stages) to attach")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_stats)
    p = sub.add_parser("project")
    p.add_argument("--unic", nargs="+", required=True)
    p.add_argument("--ref", nargs="+", required=True)
    p.add_argument("--convention", default="both", choices=["down", "up", "both"],
                   help="read footprint used for the calibration and the projection (default both: the leg "
                        "positions of hickit pairs are not the read 5' end, see the module docstring)")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_project)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
