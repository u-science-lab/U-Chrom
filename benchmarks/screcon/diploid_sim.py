"""Diploid imaging-truth simulation: homolog-resolved truth -> phased single-cell Hi-C -> score.

Subcommands
-----------
``truth``   Diploid truth cells (both homologs, copy chains ``<chrom>(0)`` / ``<chrom>(1)``, see
            ``diploid.py``)::

                python benchmarks/screcon/diploid_sim.py truth --dataset su2020_genome --n 5 --out SIM/su_gs

            * ``su2020_genome``: Su et al. 2020 IMR90 genome-scale DNA-MERFISH, 1,041 loci of
              100 kb on chr1-22 and chrX, homologs resolved by the experiment (``homolog
              number``; female: chrX two copies).  Eligible cells: detection >= 0.85 on each
              homolog (816 of 1,787); ``n`` drawn with ``--seed``.
            * ``takei2021_1mb``: Takei et al. 2021 mESC seqFISH+ 1 Mb (2,460 loci); homologs split
              by the screcon heuristic (``truth.split_homologs``; per copy detection >= 0.6,
              separation >= 1 Rg — ``benchmarks/bulk/truths.takei2021_1mb``); eligible cells:
              all 19 autosomes accepted with both copies (45 of 201); chrX single copy (male).
            Missing loci are interpolated along their copy chain for the forward model only.

``grid``    Phased reads for a (depth x rc x eps x phased fraction) grid.  Forward model as
            ``simulate.py`` (Gaussian kernel p(d) = exp(-(d / rc)^2), rc relative to the
            median consecutive-locus distance; depth = reads per Mb of the *diploid* span
            (all copy chains); a fraction eps of the reads uniform over all copy-locus pairs;
            positions uniform inside the locus) over every pair of copy loci, then every
            end of a two-copy chromosome is phased with probability ``phased`` (its true
            haplotype; wrong with probability ``--phase-err``, default 0.01), else ``.``.
            Single-copy chromosomes are never phased (hickit sets their phase itself).
            Output: hickit ``.pairs.gz`` (``phase0`` / ``phase1``) + ``.truth.npz`` (true
            haplotype of both ends and the noise flag per row) + JSON sidecar.

``score``   Models (``.npz``, copy chains) vs the truth: the haploid metrics of
            ``simulate.score_ensemble`` on the copy chains ("cis" = within one copy chain,
            "whole" = every copy-locus pair, homologs included), plus
            * ``homolog_spearman``: distances between the two copies of each chromosome;
            * ``swap_frac``: fraction of two-copy chromosomes whose copy chains fit the
              truth better swapped (after one similarity superposition of the whole
              structure) — structural phasing error;
            * ``phase``: accuracy of the most probable copy pair of the contacts with an
              unphased end (``phase_probs`` in the model ``.npz``, or hickit's imputed
              probabilities), overall and for cis < 10 Mb / cis >= 10 Mb / trans, signal
              reads only.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.distance import pdist

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bulk"))
from contacts import load_models  # noqa: E402
from diploid import Phased, copy_name, split_copy, write_phased  # noqa: E402
from metrics import superpose  # noqa: E402
from simulate import genome_span_mb, kernel, median_consecutive, score_ensemble  # noqa: E402
from truth import interpolate_missing, load_truth, save_truth  # noqa: E402


# --------------------------------------------------------------------------- truths

def diploid_truths(dataset: str, n: int = 5, seed: int = 1, data=None) -> list[dict]:
    import truths as bulk_truths
    rng = np.random.default_rng(seed)
    if dataset == "su2020_genome":
        pop = bulk_truths.load_dataset("su2020_genome", data)
        det = np.isfinite(pop.coords[..., 0]).mean(2)
        elig = np.flatnonzero(det.min(1) >= 0.85)
        rule = "detection >= 0.85 on each homolog"
        ploidy = {c: 2 for c in np.unique(pop.chrom)}
    elif dataset == "takei2021_1mb":
        pop = bulk_truths.load_dataset("takei2021_1mb", data, min_detect=0.6)
        auto = [c for c in np.unique(pop.chrom) if c not in ("chrX", "chrY")]
        acc = np.array([[np.isfinite(pop.coords[s, 1, pop.chrom == c, 0]).any() for c in auto] for s in range(pop.n_structures)])
        elig = np.flatnonzero(acc.all(1))
        rule = "all 19 autosomes accepted with both copies (per-copy detection >= 0.6, separation >= 1 Rg)"
        ploidy = {c: (1 if c in ("chrX", "chrY") else 2) for c in np.unique(pop.chrom)}
    else:
        raise ValueError(dataset)
    pick = np.sort(rng.choice(elig, size=min(n, len(elig)), replace=False))
    out = []
    for s in pick:
        rows_c, rows_s, rows_e, rows_x = [], [], [], []
        for c in [c for c in dict.fromkeys(pop.chrom)]:
            sel = pop.chrom == c
            for h in range(ploidy[c]):
                X = pop.coords[s, h, sel]
                if not np.isfinite(X[:, 0]).any():
                    continue
                rows_c.append(np.full(sel.sum(), copy_name(c, h, ploidy[c]), dtype=object))
                rows_s.append(pop.start[sel]); rows_e.append(pop.end[sel]); rows_x.append(X)
        chrom = np.concatenate(rows_c).astype(str)
        X = np.concatenate(rows_x).astype(float)
        out.append({"chrom": chrom, "start": np.concatenate(rows_s), "end": np.concatenate(rows_e), "coords": X,
                    "meta": {"dataset": dataset, "structure": int(s), "cell": pop.meta.get("cell_ids", [None] * (s + 1))[s],
                             "eligibility": rule, "n_eligible": int(len(elig)), "seed": seed, "unit": "nm",
                             "ploidy": ploidy, "homolog_assignment": pop.meta.get("homolog_assignment"),
                             "copy_chains": sorted(set(chrom.tolist()))}})
    return out


def cmd_truth(args) -> None:
    out = Path(args.out)
    for k, t in enumerate(diploid_truths(args.dataset, args.n, args.seed, args.data), 1):
        filled, measured = interpolate_missing(t["chrom"], t["start"], t["coords"])
        t["meta"].update({"n_loci": int(len(t["chrom"])), "n_measured": int(measured.sum())})
        save_truth(out / f"truth_{k}.npz", t["chrom"], t["start"], t["end"], t["coords"], measured, t["meta"])
        print(json.dumps({k2: t["meta"][k2] for k2 in ("dataset", "structure", "cell", "n_loci", "n_measured")}), flush=True)


# --------------------------------------------------------------------------- forward model

def simulate_phased(t: dict, *, reads_per_mb: float, rc_rel: float = 1.0, eps: float = 0.05, phased: float = 0.3,
                    phase_err: float = 0.01, kind: str = "gauss", seed: int = 0):
    """-> (Phased table, truth arrays dict, info)."""
    rng = np.random.default_rng(seed)
    chrom = t["chrom"]
    base = np.array([split_copy(c)[0] for c in chrom])
    hap = np.array([split_copy(c)[1] for c in chrom], np.int8)
    two = {b: (np.char.endswith(chrom[base == b].astype(str), ")")).any() for b in np.unique(base)}
    X = np.asarray(t["coords"], float)
    filled, measured = interpolate_missing(chrom, t["start"], X)
    unit = median_consecutive(chrom, np.where(measured[:, None], X, np.nan))
    rc = rc_rel * unit
    L = len(chrom)
    ia, ib = np.triu_indices(L, 1)
    d = np.linalg.norm(filled[ia] - filled[ib], axis=1)
    p = kernel(d, rc, kind)
    reads = int(round(reads_per_mb * genome_span_mb(chrom, t["start"], t["end"])))
    n_noise = int(rng.binomial(reads, eps))
    cnt = rng.multinomial(reads - n_noise, p / p.sum())
    pair = np.concatenate([np.repeat(np.arange(len(ia)), cnt), rng.integers(0, len(ia), n_noise)])
    is_noise = np.concatenate([np.zeros(int(cnt.sum()), bool), np.ones(n_noise, bool)])
    o = rng.permutation(len(pair))
    pair, is_noise = pair[o], is_noise[o]
    A, B = ia[pair], ib[pair]
    # random orientation of each read
    sw = rng.random(len(A)) < 0.5
    A, B = np.where(sw, B, A), np.where(sw, A, B)

    def draw(k):
        lo, hi = t["start"][k] + 1, t["end"][k] - 1
        return lo + (rng.random(len(k)) * (hi - lo + 1)).astype(np.int64)

    def phase(k):
        h = hap[k].copy()
        obs = np.array([two[b] for b in base[k]]) & (rng.random(len(k)) < phased)
        flip = obs & (rng.random(len(k)) < phase_err)
        h = np.where(flip, 1 - h, h)
        return np.where(obs, h, -1).astype(np.int8)

    pa, pb = draw(A), draw(B)
    ha, hb = phase(A), phase(B)
    c = Phased(base[A], pa, ha, base[B], pb, hb)
    tr = {"true_hap_a": hap[A], "true_hap_b": hap[B], "is_noise": is_noise,
          "two_a": np.array([two[x] for x in base[A]]), "two_b": np.array([two[x] for x in base[B]])}
    info = {"n_reads": int(len(A)), "n_signal": int(cnt.sum()), "n_noise": n_noise, "eps": eps, "rc_rel": rc_rel,
            "rc_nm": float(rc), "median_consecutive_nm": unit, "reads_per_mb": reads_per_mb, "phased": phased,
            "phase_err": phase_err, "kernel": kind, "seed": seed, "n_copy_loci": int(L),
            "diploid_span_mb": genome_span_mb(chrom, t["start"], t["end"]),
            "frac_ends_phased": float(((ha >= 0).sum() + (hb >= 0).sum()) / max(2 * len(A), 1)),
            "frac_inter_homolog_signal": float(np.mean((base[A] == base[B]) & (hap[A] != hap[B]) & ~is_noise))}
    return c, tr, info


def chrom_sizes(t: dict) -> dict:
    base = np.array([split_copy(c)[0] for c in t["chrom"]])
    return {b: int(t["end"][base == b].max() + 1_000_000) for b in np.unique(base)}


def grid_name(depth, rc, eps, phased, seed) -> str:
    return f"d{depth:g}_rc{rc:g}_e{eps:g}_p{phased:g}_s{seed}"


def cmd_grid(args) -> None:
    out = Path(args.out)
    for tp in sorted(Path(args.truth_dir).glob("truth_*.npz")):
        t = load_truth(tp)
        for depth, rc, eps, ph, seed in itertools.product(args.depths, args.rc_rels, args.eps, args.phased, args.seeds):
            name = f"{tp.stem}_{grid_name(depth, rc, eps, ph, seed)}"
            f = out / f"{name}.pairs.gz"
            if f.exists() and not args.overwrite:
                continue
            c, tr, info = simulate_phased(t, reads_per_mb=depth, rc_rel=rc, eps=eps, phased=ph,
                                          phase_err=args.phase_err, seed=seed)
            write_phased(f, c, chrom_sizes(t))
            np.savez_compressed(out / f"{name}.truth.npz", **tr)
            info.update({"truth": str(tp), "name": name})
            Path(str(f) + ".json").write_text(json.dumps(info, indent=1))
            print(name, info["n_reads"], round(info["frac_ends_phased"], 3), flush=True)


# --------------------------------------------------------------------------- scoring

def homolog_metrics(t: dict, chrom, pos, X) -> dict:
    """Inter-homolog distances and swapped copy chains (model 0 .. M-1, median)."""
    from simulate import map_loci
    p = map_loci(t, chrom, pos)
    use = np.flatnonzero(p >= 0)
    lc = t["chrom"][use]
    base = np.array([split_copy(c)[0] for c in lc])
    hap = np.array([split_copy(c)[1] for c in lc])
    T = t["coords"][use]
    out = {"homolog_spearman": [], "swap_frac": []}
    for m in range(len(X)):
        Y = X[m, p[use]]
        fit, *_ = superpose(T, Y, scale=True, mirror=True)
        rs, swaps, n2 = [], 0, 0
        for b in np.unique(base):
            s0 = np.flatnonzero((base == b) & (hap == 0))
            s1 = np.flatnonzero((base == b) & (hap == 1))
            if len(s0) < 5 or len(s1) < 5:
                continue
            n2 += 1
            from scipy.stats import spearmanr
            dt = np.linalg.norm(T[s0][:, None] - T[s1][None], axis=2).ravel()
            dm = np.linalg.norm(Y[s0][:, None] - Y[s1][None], axis=2).ravel()
            rs.append(spearmanr(dt, dm)[0])
            # swap check on the loci measured on both copies
            l0 = {int(t["start"][use][k]): k for k in s0}
            l1 = {int(t["start"][use][k]): k for k in s1}
            both = sorted(set(l0) & set(l1))
            if len(both) >= 5:
                a = np.array([l0[x] for x in both]); bb = np.array([l1[x] for x in both])
                keep = np.sum((fit[a] - T[a]) ** 2) + np.sum((fit[bb] - T[bb]) ** 2)
                swap = np.sum((fit[a] - T[bb]) ** 2) + np.sum((fit[bb] - T[a]) ** 2)
                swaps += swap < keep
        out["homolog_spearman"].append(float(np.median(rs)) if rs else np.nan)
        out["swap_frac"].append(swaps / n2 if n2 else np.nan)
    return {k: float(np.nanmedian(v)) for k, v in out.items()} | {"n_two_copy": n2}


def phase_metrics(table, truth_npz, probs) -> dict:
    """Accuracy of the most probable (hap_a, hap_b) of signal reads with an unphased end of a
    two-copy chromosome.  ``probs`` (n, 4) rows aligned with ``table``; NaN = not assigned."""
    from diploid import read_phased
    c = read_phased(table)
    z = np.load(truth_npz)
    ok = np.isfinite(probs).all(1) & ~z["is_noise"]
    best = np.argmax(np.nan_to_num(probs, nan=-1), 1)
    ia, ib = best >> 1, best & 1
    two_a = z["two_a"] & (c.hap_a < 0)
    two_b = z["two_b"] & (c.hap_b < 0)
    sep = np.abs(c.pos_a - c.pos_b)
    cis = c.chrom_a == c.chrom_b
    out = {}
    for name, sel in {"all": np.ones(len(c), bool), "cis_lt10mb": cis & (sep < 10_000_000),
                      "cis_ge10mb": cis & (sep >= 10_000_000), "trans": ~cis}.items():
        right = tot = 0
        for end, (unph, imp, true) in enumerate([(two_a, ia, z["true_hap_a"]), (two_b, ib, z["true_hap_b"])]):
            s = sel & ok & unph
            right += int((imp[s] == true[s]).sum()); tot += int(s.sum())
        out[f"phase_acc_{name}"] = right / tot if tot else None
        out[f"phase_n_{name}"] = tot
    out["phase_assigned_frac"] = float(np.mean(np.isfinite(probs).all(1)[~z["is_noise"]]))
    return out


def cmd_score(args) -> None:
    t = load_truth(args.truth)
    out = {"truth": str(args.truth), "table": args.table, "methods": {}}
    for path, lab in zip(args.models, args.labels or [Path(m).stem for m in args.models]):
        if not Path(path).exists():
            print(f"missing {path}")
            continue
        chrom, pos, X = load_models(path)
        r = score_ensemble(t, chrom, pos, X)
        r.update(homolog_metrics(t, chrom, pos, X))
        z = np.load(path, allow_pickle=False)
        if "phase_probs" in z.files and args.table:
            r.update(phase_metrics(args.table, args.table_truth, z["phase_probs"]))
        r["models"] = str(path)
        out["methods"][lab] = r
        mo = r["median_over_models"]
        print(json.dumps({"method": lab, "spearman_cis": round(mo["dist_spearman_cis"], 3),
                          "spearman_whole": round(mo["dist_spearman_whole"], 3),
                          "homolog_spearman": round(r["homolog_spearman"], 3), "swap_frac": round(r["swap_frac"], 3),
                          "phase_acc_all": r.get("phase_acc_all")}), flush=True)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=1, default=float))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("truth")
    s.add_argument("--dataset", required=True, choices=["su2020_genome", "takei2021_1mb"])
    s.add_argument("--data", help="input file (default: from the data directory, uchrom.datasets)")
    s.add_argument("--n", type=int, default=5)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_truth)
    g = sub.add_parser("grid")
    g.add_argument("--truth-dir", required=True)
    g.add_argument("--depths", type=float, nargs="+", default=[20, 80], help="reads per Mb of the diploid span")
    g.add_argument("--rc-rels", type=float, nargs="+", default=[0.5, 1.0])
    g.add_argument("--eps", type=float, nargs="+", default=[0.05, 0.2])
    g.add_argument("--phased", type=float, nargs="+", default=[0.2, 0.4], help="fraction of phased ends")
    g.add_argument("--phase-err", type=float, default=0.01)
    g.add_argument("--seeds", type=int, nargs="+", default=[1])
    g.add_argument("--overwrite", action="store_true")
    g.add_argument("--out", required=True)
    g.set_defaults(fn=cmd_grid)
    c = sub.add_parser("score")
    c.add_argument("--truth", required=True)
    c.add_argument("--table", help="the phased .pairs.gz the models were built from (phase accuracy)")
    c.add_argument("--table-truth", help="its .truth.npz")
    c.add_argument("--models", nargs="+", required=True)
    c.add_argument("--labels", nargs="*")
    c.add_argument("--out")
    c.set_defaults(fn=cmd_score)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
