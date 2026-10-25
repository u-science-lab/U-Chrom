"""Link the reprocessed spatial Hi-C contact maps (Chen, Guo et al. 2026; GSA CRA016676) into the stores.

The contacts come from our cluster pipeline (apps/atlas/recipes/spatial_hic_chen2026/slurm/: raw reads
-> bwa -> pairtools -> pairs_to_cool.py), one folder per run in the archive.  Copy each run's
``<run>.pixels_1Mb.scool``, ``<run>.bulk.mcool``, ``<run>.barcode_stats.tsv`` and ``<run>.log.json``
into ``$UCHROM_DATA/spatial_hic_chen2026/contacts/`` first (over the DTN; README), then::

    python apps/atlas/recipes/link_spatial_hic_chen2026_contacts.py [RUN ...]

**Which spot is which.**  A map is named by its barcode pair ``<b1>_<b2>`` (read order); the stores
name spots ``<section>:<prefix><col>x<row>`` (and the brain stores also keep the authors' barcode
pair, ``cells.pixel``).  The grid orientation differs between sections, so every candidate —
the 8 orientations of the grid (swap the two barcodes, flip either index) and, where the store
has it, ``pixel`` read as ``b1_b2`` or ``b2_b1`` — is scored on the data:

    for every spot, the compartment of its contacts' partners along the genome (each 1-Mb bin:
    the contact-weighted mean of the bulk eigenvector E1 over the bins it touches), minus the
    mean over all spots; Pearson r with the authors' single-spot A/B scores (``ssAB``, also
    minus their mean), median over spots.

Only the right pairing makes a spot's deviations follow the authors' for that spot; any other
gives r ~ 0.  The best candidate must beat the runner-up by ``MARGIN`` (and be > 0), else the
run is not linked.

**What is linked**, per section: ``<store>_<section>.reprocessed_1Mb.scool`` (cells renamed to the
store's ids; spots outside the store dropped) and ``contacts/<run>.bulk.mcool``, as
``per_spot.<section>`` / ``bulk.<section>`` — or with ``.reprocessed`` appended when the section
already has maps (built from the authors' BEDPE).  ``uns['contacts_stats']['reprocessed'][<run>]``
records the pipeline counts, the candidate scores and the choice.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import anndata as ad
import h5py
import numpy as np
import pandas as pd

from uchrom import ChromData
from uchrom.datasets import data_dir

HERE = data_dir() / "spatial_hic_chen2026"                          # the data: stores, contacts
PIPELINE = Path(__file__).resolve().parent / "spatial_hic_chen2026" / "slurm"   # the pipeline tables
SRC = HERE / "contacts"
RUNS = ["CRR1161506", "CRR1161507", "CRR1161509", "CRR1161510", "CRR1829212", "CRR1829213", "CRR1829214",
        "CRR1829215", "CRR1829216", "CRR1829217", "CRR1829219", "CRR1829220", "CRR1831973"]   # runs.tsv rows with a store
MARGIN = 0.05
N_SPOTS = 1500          # spots scored per candidate (random, fixed seed)


def barcode_lists(n: int):
    if n == 50:
        return (pd.read_csv(PIPELINE / "barcodes_50_B.tsv", sep="\t").barcode.tolist(),
                pd.read_csv(PIPELINE / "barcodes_50_A.tsv", sep="\t").barcode.tolist())
    b = pd.read_csv(PIPELINE / "barcodes_96.tsv", sep="\t").barcode.tolist()
    return b, b


def candidates(names: pd.Series, cells: pd.DataFrame, n: int) -> dict:
    """Candidate name -> {barcode pair: store cell id}."""
    b1 = names.str.split("_").str[0]
    b2 = names.str.split("_").str[1]
    l1, l2 = barcode_lists(n)
    i1 = b1.map({b: i + 1 for i, b in enumerate(l1)})
    i2 = b2.map({b: i + 1 for i, b in enumerate(l2)})
    prefix = re.sub(r"\d+x\d+$", "", str(cells["spot"].iloc[0]))
    by_spot = pd.Series(cells.index, index=cells["spot"].astype(str))
    out = {}
    for swap in (False, True):
        for f1 in (False, True):
            for f2 in (False, True):
                x = (n + 1 - i1) if f1 else i1
                y = (n + 1 - i2) if f2 else i2
                a, b = (y, x) if swap else (x, y)
                spot = prefix + a.astype("Int64").astype(str) + "x" + b.astype("Int64").astype(str)
                ids = spot.map(by_spot)
                out[f"grid swap={int(swap)} flip1={int(f1)} flip2={int(f2)}"] = dict(zip(names[ids.notna()], ids[ids.notna()]))
    if n == 96:
        # the authors' own barcode -> grid index (their plate order, not ours: read off the
        # brain_embryo_20um store's barcode pairs and spot names; slurm/barcodes_96_authors_index.tsv)
        t = pd.read_csv(PIPELINE / "barcodes_96_authors_index.tsv", sep="\t").set_index("barcode")
        for roles, (o1, o2) in {"b1=pos1": ("index_pos1", "index_pos2"), "b1=pos2": ("index_pos2", "index_pos1")}.items():
            j1 = b1.map(t[o1]).astype("Float64")
            j2 = b2.map(t[o2]).astype("Float64")
            for swap in (False, True):
                for f1 in (False, True):
                    for f2 in (False, True):
                        x = (n + 1 - j1) if f1 else j1
                        y = (n + 1 - j2) if f2 else j2
                        a, b = (y, x) if swap else (x, y)
                        spot = prefix + a.astype("Int64").astype(str) + "x" + b.astype("Int64").astype(str)
                        ids = spot.map(by_spot)
                        out[f"authors' order {roles} swap={int(swap)} flip1={int(f1)} flip2={int(f2)}"] = dict(zip(names[ids.notna()], ids[ids.notna()]))
    if "pixel" in cells:
        by_px = pd.Series(cells.index, index=cells["pixel"].astype(str))
        for name, key in (("pixel b1_b2", names), ("pixel b2_b1", b2 + "_" + b1)):
            ids = key.map(by_px)
            out[name] = dict(zip(names[ids.notna()], ids[ids.notna()]))
    return out


def bulk_e1(mcool: Path, bins: pd.DataFrame, ref: pd.Series) -> np.ndarray:
    """E1 of the bulk map per chromosome at 1 Mb on ``bins``; sign: positive where ``ref`` (the
    authors' mean ssAB on the same bins) is high."""
    import cooler

    clr = cooler.Cooler(f"{mcool}::/resolutions/1000000")
    e1 = np.full(len(bins), np.nan)
    for chrom, idx in bins.groupby("chrom", observed=True).groups.items():
        if chrom not in clr.chromnames:
            continue
        m = clr.matrix(balance=False).fetch(chrom).astype(float)
        k = min(len(m), len(idx))
        m = m[:k, :k]
        cov = m.sum(0)
        ok = cov > np.percentile(cov[cov > 0], 5) if (cov > 0).any() else cov > 0
        if ok.sum() < 10:
            continue
        s = m[np.ix_(ok, ok)]
        s = s / np.sqrt(np.outer(s.sum(0), s.sum(0)))
        d = np.abs(np.subtract.outer(np.arange(len(s)), np.arange(len(s))))
        exp = np.array([np.nanmean(np.diagonal(s, i)) for i in range(len(s))])
        oe = np.nan_to_num(s / exp[d])
        v = np.linalg.eigh(np.nan_to_num(np.corrcoef(oe)))[1][:, -1]
        full = np.full(k, np.nan)
        full[np.flatnonzero(ok)] = v
        pos = np.asarray(idx)[:k]
        r = ref.iloc[pos].to_numpy()
        f = np.isfinite(full) & np.isfinite(r)
        if f.sum() > 5 and np.corrcoef(full[f], r[f])[0, 1] < 0:
            full = -full
        e1[pos] = full
    return e1


def partner_profile(f: h5py.File, name: str, e1: np.ndarray) -> np.ndarray:
    """Per bin: contact-weighted mean E1 of the bins its cis contacts touch."""
    g = f["cells"][name]
    b1 = g["pixels/bin1_id"][:]
    b2 = g["pixels/bin2_id"][:]
    c = g["pixels/count"][:].astype(float)
    chrom = f["bins/chrom"][:] if "bins/chrom" in f else None
    n = len(e1)
    cis = chrom[b1] == chrom[b2] if chrom is not None else np.ones(len(b1), bool)
    b1, b2, c = b1[cis], b2[cis], c[cis]
    e = np.nan_to_num(e1)
    num = np.bincount(b1, c * e[b2], n) + np.bincount(b2, c * e[b1], n)
    den = np.bincount(b1, c, n) + np.bincount(b2, c, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def score(scool: Path, mcool: Path, cand: dict, ssab: ad.AnnData, rng) -> dict:
    """Median per-spot Pearson r of residual partner profiles vs residual ssAB, per candidate."""
    with h5py.File(scool, "r") as f:
        bins = pd.DataFrame({"chrom": pd.Categorical(f["bins/chrom"][:].astype(str) if f["bins/chrom"].dtype.kind in "SO" else
                                                    np.asarray(f["chroms/name"][:]).astype(str)[f["bins/chrom"][:]]),
                             "start": f["bins/start"][:]})
    # the authors' ssAB (500 kb) onto these 1-Mb bins
    v = ssab.var
    key = v["chrom"].astype(str) + ":" + (v["start"] // 1_000_000).astype(str)
    bkey = bins["chrom"].astype(str) + ":" + (bins["start"] // 1_000_000).astype(str)
    col_of = pd.Series(np.arange(len(bins)), index=bkey.values)
    tgt = key.map(col_of).to_numpy()
    X = ssab.X if isinstance(ssab.X, np.ndarray) else ssab.X[:]
    X = np.asarray(X, float)
    agg = np.full((X.shape[0], len(bins)), np.nan)
    ok = ~np.isnan(tgt)
    cnt = np.zeros(len(bins))
    acc = np.zeros((X.shape[0], len(bins)))
    for j in np.flatnonzero(ok):
        acc[:, int(tgt[j])] += X[:, j]
        cnt[int(tgt[j])] += 1
    agg[:, cnt > 0] = acc[:, cnt > 0] / cnt[cnt > 0]
    row = pd.Series(np.arange(len(ssab)), index=ssab.obs_names)
    ref = pd.Series(np.nanmean(agg, 0))
    e1 = bulk_e1(mcool, bins, ref)
    # partner profiles of every map (once), residualised over the maps
    names = sorted({n for m in cand.values() for n in m})
    pick = rng.choice(names, min(len(names), N_SPOTS * 2), replace=False)
    with h5py.File(scool, "r") as f:
        have = set(f["cells"].keys())
        prof = {n: partner_profile(f, n, e1) for n in pick if n in have}
    P = np.array(list(prof.values()))
    P = P - np.nanmean(P, 0)
    prow = dict(zip(prof, range(len(prof))))
    S = agg - np.nanmean(agg, 0)
    out = {}
    for cname, m in cand.items():
        rs = []
        for n in pick:
            cid = m.get(n)
            if cid is None or n not in prow or cid not in row.index:
                continue
            a, b = P[prow[n]], S[row[cid]]
            f2 = np.isfinite(a) & np.isfinite(b)
            if f2.sum() > 50 and a[f2].std() > 0 and b[f2].std() > 0:
                rs.append(np.corrcoef(a[f2], b[f2])[0, 1])
            if len(rs) >= N_SPOTS:
                break
        out[cname] = (float(np.median(rs)) if rs else float("nan"), len(rs))
    return out


def same_pairing(a: dict, b: dict, frac: float = 0.9) -> bool:
    """Whether two candidate pairings (map name -> store cell id) agree on at least ``frac`` of their maps."""
    common = a.keys() & b.keys()
    return bool(common) and sum(a[k] == b[k] for k in common) >= frac * max(len(a), len(b)) * 0.99


def rename_scool(src: Path, dst: Path, rename: dict) -> int:
    tmp = dst.with_suffix(".tmp")
    shutil.copyfile(src, tmp)
    with h5py.File(tmp, "r+") as f:
        cells = f["cells"]
        for name in list(cells.keys()):
            new = rename.get(name)
            if new is None:
                del cells[name]
            elif new != name:
                cells.move(name, new)
        n = len(cells)
    tmp.replace(dst)
    return n


def main(runs: list) -> None:
    table = pd.read_csv(PIPELINE / "runs.tsv", sep="\t").set_index("run")
    rng = np.random.default_rng(0)
    by_store: dict = {}
    for run in runs:
        r = table.loc[run]
        by_store.setdefault(r["store"], []).append(run)
    for store, store_runs in by_store.items():
        path = HERE / f"{store}.chromdata.zarr"
        cd = ChromData.read(path)
        rec = (cd.uns.get("linked_bin_matrices") or {}).get("ssAB")
        ssab = ad.read_h5ad(cd.resolve_link_path(rec["path"]), backed="r")
        res500 = (ssab.var["resolution"] == 500_000).to_numpy() if "resolution" in ssab.var else np.ones(ssab.n_vars, bool)
        stats = dict(cd.uns.get("contacts_stats") or {})
        rep = dict(stats.get("reprocessed") or {})
        for run in store_runs:
            r = table.loc[run]
            sec, n = r["section"], int(r["grid"])
            scool, mcool = SRC / f"{run}.pixels_1Mb.scool", SRC / f"{run}.bulk.mcool"
            if not scool.exists() or not mcool.exists():
                print(f"{run}: {scool.name} / {mcool.name} missing (copy them from the archive first) — skipped")
                continue
            cells = cd.cells[cd.cells["section"] == sec]
            with h5py.File(scool, "r") as f:
                names = pd.Series(sorted(f["cells"].keys()))
            cand = candidates(names, cells, n)
            sub = ssab[ssab.obs_names.isin(cells.index), res500].to_memory()   # this section, 500-kb columns
            sc = score(scool, mcool, cand, sub, rng)
            ranked = sorted(sc.items(), key=lambda kv: -np.nan_to_num(kv[1][0], nan=-9))
            best, (r1, k1) = ranked[0]
            # the runner-up is the best candidate that maps the spots differently: several names describe
            # the same pairing (e.g. "authors' order" and "pixel b1_b2"), those are not competitors
            second, (r2, _) = next(((k, v) for k, v in ranked[1:] if not same_pairing(cand[best], cand[k])), ranked[1])
            print(f"{run} {sec}: " + " | ".join(f"{k} {v:.3f}" for k, (v, _) in ranked[:4]))
            info = {"section": sec, "store": store, "candidates": {k: round(v, 4) for k, (v, _) in sc.items()},
                    "chosen": best, "spots_scored": k1}
            if not (r1 > 0 and r1 - np.nan_to_num(r2) >= MARGIN):
                print(f"  {run}: no clear orientation (best {r1:.3f} vs {r2:.3f}) — not linked")
                info["chosen"] = None
                rep[run] = info
                continue
            existing = set((cd.uns.get("linked_scool") or {}).keys()) | set((cd.uns.get("linked_cool") or {}).keys())
            suffix = ".reprocessed" if f"per_spot.{sec}" in existing or f"bulk.{sec}" in existing else ""
            # the per-spot key must not clash with an earlier reprocessed run of the same section
            out = HERE / f"{store}_{sec}.{run}.reprocessed_1Mb.scool"
            n_maps = rename_scool(scool, out, cand[best])
            label_run = f"{sec} ({run}, reprocessed)"
            key = f"per_spot.{sec}{suffix}"
            if key in (cd.uns.get("linked_scool") or {}) and (cd.uns["linked_scool"][key].get("run") not in (None, run)):
                key = f"per_spot.{sec}.{run}"
            cd.link_scool(out.name, key=key, cell_name="cell id (store)", genome_assembly="mm10", bin_size=1_000_000,
                          label=f"{label_run}, per spot", run=run,
                          source="reprocessed from GSA CRA016676 (apps/atlas/recipes/spatial_hic_chen2026/slurm)")
            bkey = key.replace("per_spot.", "bulk.", 1)
            cd.link_cool(f"contacts/{mcool.name}", key=bkey, label=f"{label_run}, all spots (merged)", genome_assembly="mm10", run=run)
            pipe = json.loads((SRC / f"{run}.log.json").read_text())
            info.update({k: pipe[k] for k in ("lines", "kept", "duplicates", "low_mapq", "short_cis", "bad_barcode", "min_mapq", "min_cis_dist")})
            info.update({"spots_with_map": n_maps, "spots_in_store": int(len(cells)), "key": key, "bulk_key": bkey})
            rep[run] = info
            print(f"  linked {key} ({n_maps} of {len(cells)} spots) + {bkey}")
        stats["reprocessed"] = rep
        cd.uns["contacts_stats"] = stats
        cd.write(path)
        print("wrote", path.name)


if __name__ == "__main__":
    main(sys.argv[1:] or RUNS)
