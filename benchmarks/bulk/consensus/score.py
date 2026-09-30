"""Score consensus structures (and baselines) against imaging median distances and the input.

Per model and imaging set (``imaging.py`` output), over locus pairs with >= --min-count imaged
distances (loci mapped to the model bin containing their midpoint; two loci in one bin are left
out):

* **distance agreement** — Spearman and Pearson (linear and log-log) between the model distance
  and the imaging MEDIAN distance: all pairs, cis, trans, cis by separation band (0-1, 1-2, 2-5,
  5-10, 10-20, 20-50, > 50 Mb), and the median over chromosomes of the per-chromosome cis Spearman;
* **scale-free RMSD** — the model's loci superposed (scale + rotation + reflection) onto the
  imaging mean-distance embedding (``imaging.py``: SMACOF of the medians), RMSD / Rg(embedding);
  genome-wide and the median of per-chromosome superpositions; distance-matrix models (HIPPS, IGM
  means) are embedded the same way first;
* **fit to the input** (coordinate models, ``--fit-input``) — Spearman between model distance and
  balanced contact frequency over observed pixels at the model resolution (cis within 200 bins,
  and trans at genome-wide resolutions), reported as -rho (higher = better fit).

Distance-matrix baselines: ``--hipps CELL:RES`` (HIPPS mean distances <r> = (f / f_nn)^-1/4 of the
same balanced input) and ``--igm NAME=population.chromdata.zarr`` (IGM population median distances,
same pooling as the imaging).

    python benchmarks/bulk/consensus/score.py --imaging IMG/su2020_genome.npz \
        --model consensus=M/imr90_250kb_s1.npz --model mds_full=B/imr90_250kb/mds_full.npz \
        --hipps imr90:250000 --fit-input imr90 --out S/su2020_genome__imr90_250kb.json
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

import _bc
from _bc import Model, hic_source, map_loci_to_bins, model_from_chromdata, model_from_npz, read_json, write_json
from imaging import embed, pair_medians

BANDS = [(0, 1), (1, 2), (2, 5), (5, 10), (10, 20), (20, 50), (50, np.inf)]


def _corr(x, y):
    if len(x) < 10:
        return {"n": int(len(x)), "spearman": np.nan, "pearson": np.nan, "pearson_log": np.nan}
    lx, ly = np.log(np.maximum(x, 1e-12)), np.log(np.maximum(y, 1e-12))
    return {"n": int(len(x)), "spearman": float(spearmanr(x, y)[0]), "pearson": float(pearsonr(x, y)[0]),
            "pearson_log": float(pearsonr(lx, ly)[0])}


def distance_metrics(Dm, Di, cnt, chrom, mid, min_count):
    L = len(chrom)
    iu = np.triu_indices(L, 1)
    dm, di, c = Dm[iu], Di[iu], cnt[iu]
    ok = np.isfinite(dm) & np.isfinite(di) & (c >= min_count) & (dm > 0)
    cis = chrom[iu[0]] == chrom[iu[1]]
    sep = np.abs(mid[iu[1]] - mid[iu[0]]) / 1e6
    out = {"all": _corr(dm[ok], di[ok]), "cis": _corr(dm[ok & cis], di[ok & cis]),
           "trans": _corr(dm[ok & ~cis], di[ok & ~cis])}
    for a, b in BANDS:
        k = ok & cis & (sep >= a) & (sep < b)
        out[f"cis_{a}-{b}Mb"] = _corr(dm[k], di[k])
    per = []
    for ch in pd.unique(chrom):
        k = ok & cis & (chrom[iu[0]] == ch)
        if k.sum() >= 10:
            per.append(spearmanr(dm[k], di[k])[0])
    out["cis_per_chrom_spearman_median"] = float(np.median(per)) if per else np.nan
    out["coverage"] = {"pairs_scored": int(ok.sum()), "pairs_imaged": int(((c >= min_count) & np.isfinite(di)).sum())}
    return out


def rmsd_metrics(Xm, emb, chrom):
    from uchrom.recon.bulk.consensus import kabsch

    ok = np.isfinite(Xm).all(1) & np.isfinite(emb).all(1)
    if ok.sum() < 4:
        return {"n": int(ok.sum()), "rmsd_over_rg": np.nan}
    E = emb[ok]
    rg = np.sqrt(((E - E.mean(0)) ** 2).sum(1).mean())
    _, r = kabsch(E, Xm[ok], reflection=True, scale=True)
    per = []
    for ch in pd.unique(chrom[ok]):
        k = chrom[ok] == ch
        if k.sum() >= 4:
            Ec = E[k]
            rgc = np.sqrt(((Ec - Ec.mean(0)) ** 2).sum(1).mean())
            per.append(kabsch(Ec, Xm[ok][k], reflection=True, scale=True)[1] / rgc)
    return {"n": int(ok.sum()), "rmsd_over_rg": float(r / rg),
            "rmsd_over_rg_per_chrom_median": float(np.median(per)) if per else np.nan}


def fit_to_input(model: Model, src: str, res: int, max_pairs: int = 2_000_000):
    """-Spearman(model distance, balanced frequency) over observed pixels of the model's chromosomes."""
    from uchrom.recon.bulk.consensus import ConsensusParams
    from uchrom.recon.bulk.consensus._contacts import CoolerSource
    from uchrom.recon.bulk.consensus._restraints import load_stage

    p = ConsensusParams()
    chroms = [c for c in pd.unique(model.bins["chrom"].astype(str))]
    src_ = CoolerSource(src)
    kind = "genome" if res >= p.trans_max_resolution or len(model.bins) <= 3000 else "cis"
    px = load_stage(src_, res, chroms, kind, 200, p)
    idx = map_loci_to_bins(px.bins, model.bins)            # same bins -> identity when aligned
    X = np.full((len(px.bins), 3), np.nan)
    X[idx >= 0] = model.coords[idx[idx >= 0]]
    i, j, b = px.i, px.j, px.b
    cis = px.chrom_code[i] == px.chrom_code[j]
    k = np.isfinite(X[i]).all(1) & np.isfinite(X[j]).all(1) & (~cis | ((j - i) <= 200))
    rng = np.random.default_rng(0)
    out = {}
    for name, m in (("cis", cis & k), ("trans", ~cis & k)):
        sel = np.flatnonzero(m)
        if len(sel) > max_pairs:
            sel = rng.choice(sel, max_pairs, replace=False)
        if len(sel) < 10:
            out[name] = {"n": int(len(sel)), "neg_spearman": np.nan}
            continue
        d = np.linalg.norm(X[i[sel]] - X[j[sel]], axis=1)
        out[name] = {"n": int(len(sel)), "neg_spearman": float(-spearmanr(d, b[sel])[0])}
    return out


def hipps_model(cell_res: str, loci: pd.DataFrame):
    cell, res = cell_res.split(":")
    res = int(res)
    from mds_baselines import balanced_genome
    from uchrom.recon.bulk.consensus import ConsensusParams

    chroms = [c for c in pd.unique(loci["chrom"].astype(str))]
    M, bins, valid, ch = balanced_genome(hic_source(cell), res, chroms, ConsensusParams())
    idx = map_loci_to_bins(loci, bins)
    # f_nn: mean balanced frequency of adjacent valid bins
    same = bins["chrom"].to_numpy()[1:] == bins["chrom"].to_numpy()[:-1]
    adj = np.array([M[t, t + 1] for t in np.flatnonzero(same) if valid[t] and valid[t + 1]])
    f_nn = float(adj[adj > 0].mean())
    L = len(loci)
    F = np.full((L, L), np.nan)
    ok = idx >= 0
    F[np.ix_(ok, ok)] = M[np.ix_(idx[ok], idx[ok])]
    with np.errstate(divide="ignore"):
        D = np.where(F > 0, (F / f_nn) ** -0.25, np.nan)
    same_bin = (idx[:, None] == idx[None]) & ok[:, None]
    D[same_bin] = np.nan
    return Model(f"hipps_{res // 1000}kb", dist=D, meta={"model": "hipps", "resolution": res, "alpha": 4, "f_nn": f_nn})


def igm_model(name: str, path: str, loci: pd.DataFrame):
    from population import load_any

    pop = load_any(path, loci)
    med, _, _ = pair_medians(pop.coords, pop.chrom)
    return Model(name, dist=med.astype(float), meta={"model": "igm_population_median", "path": path,
                                                     "n_structures": int(pop.n_structures)})


def load_model(spec: str) -> Model:
    name, path = spec.split("=", 1)
    if path.endswith(".zarr") or path.endswith(".cdz"):
        return model_from_chromdata(path, name)
    return model_from_npz(path, name)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--imaging", required=True)
    ap.add_argument("--model", action="append", default=[], help="name=path (.npz from run.py / baselines.py, or .chromdata.zarr)")
    ap.add_argument("--hipps", action="append", default=[], help="CELL:RES")
    ap.add_argument("--igm", action="append", default=[], help="name=population.chromdata.zarr")
    ap.add_argument("--fit-input", default=None, help="cell (Hi-C source) for the fit-to-input metric")
    ap.add_argument("--min-count", type=int, default=20)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    z = np.load(a.imaging, allow_pickle=True)
    loci = pd.DataFrame({"chrom": z["chrom"].astype(str), "start": z["start"], "end": z["end"]})
    chrom = loci["chrom"].to_numpy()
    mid = (loci["start"].to_numpy() + loci["end"].to_numpy()) / 2
    Di, cnt, emb = z["median"].astype(float), z["count"], z["embedding"].astype(float)
    img_meta = json.loads(str(z["meta"]))
    models = [load_model(s) for s in a.model]
    models += [hipps_model(s, loci) for s in a.hipps]
    models += [igm_model(*s.split("=", 1), loci) for s in a.igm]
    res = {"imaging": a.imaging, "dataset": img_meta.get("dataset"), "n_loci": len(loci),
           "imaging_meta": {k: img_meta[k] for k in ("n_structures_used", "distance_r_embedding_vs_input", "pooling")
                            if k in img_meta}, "models": {}}
    for m in models:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            Dm, Xm = m.loci_distances(loci)
            r = {"meta": {k: v for k, v in m.meta.items() if isinstance(v, (int, float, str, bool, type(None)))},
                 "distance": distance_metrics(Dm, Di, cnt, chrom, mid, a.min_count)}
            if Xm is None:
                Xm = embed(Dm)[0]
                r["rmsd_from"] = "embedded distance matrix"
            r["rmsd"] = rmsd_metrics(Xm, emb, chrom)
            if a.fit_input and m.coords is not None:
                res_m = int(np.median(m.bins["end"] - m.bins["start"]))
                r["fit_input"] = fit_to_input(m, hic_source(a.fit_input), res_m)
        res["models"][m.name] = r
        d = r["distance"]
        print(f"{m.name}: spearman all {d['all']['spearman']:.3f} cis {d['cis']['spearman']:.3f} "
              f"trans {d['trans']['spearman']:.3f}; RMSD/Rg {r['rmsd']['rmsd_over_rg']:.3f}", flush=True)
    write_json(a.out, res)


if __name__ == "__main__":
    main()
