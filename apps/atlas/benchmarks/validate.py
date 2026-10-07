"""Checks of the atlas datasets, recomputed from the stores, for the paper (Brief Communication Fig. 2c, Supp. Fig. 6).

For every dataset of ``apps/atlas/datasets.json`` (stores under ``$UCHROM_DATA/``):

* **size**: kind of data, species, cells or spots, contacts per cell / spot (median: the ``cells`` column of the
  build, else the ``sum`` of every cell's map in the linked per-cell ``.scool``), traced or modelled loci per cell;
* **published counts**: reprocessed contacts per cell against the counts the authors deposited (HiRES,
  dscHi-C, Droplet / Paired Hi-C): exact share, median ratio, largest relative difference;
* **embedding agreement**: share of the 15 nearest neighbours of a cell with its cell type, per embedding, and the
  chance level (sum of squared type frequencies);
* **cells vs bulk** (Uni-C): stratum-adjusted correlation of the ICE-balanced merged-cell and bulk maps (500 kb,
  diagonals 1-20, autosomes), every sample against every bulk library;
* **spatial**: the checks of ``benchmarks/spatial_hicrna_validation.py`` and
  ``benchmarks/spatial_hic_chen2026_reprocessed.py`` (their result files, cited, not recomputed).

Writes ``<u-chrom-paper>/manuscripts/nmeth-bc/figures/results/atlas.json`` (``benchmarks/_paper.py``).

    python apps/atlas/benchmarks/validate.py [--only ID ...]
"""

from __future__ import annotations

from uchrom.datasets import data_dir
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                                   # the repository
for _pkg in ("uchrom", "chromdata", "uchrom-browser"):   # this checkout's packages, not installed copies
    sys.path.insert(0, str(ROOT / "packages" / _pkg))
sys.path.insert(0, str(ROOT / "benchmarks"))
from _paper import paper_root  # noqa: E402

DATA = data_dir()
CONFIG = HERE.parent / "datasets.json"
CONTACT_COLUMNS = ("n_contacts", "n_contacts_hic")
PUBLISHED = {            # dataset -> (reprocessed column, published columns summed)
    "hires_brain": ("n_contacts", ["n_contacts_published"]),
    "hires_embryo": ("n_contacts", ["n_contacts_published"]),
    "dschic_aging_cortex": ("n_contacts", ["n_contacts_published"]),
    "droplet_hic_mouse_cortex": ("n_contacts", ["n_cis_1kb_published", "n_trans_published"]),
    "paired_hic_mouse_cortex": ("n_contacts", ["n_cis_1kb_published", "n_trans_published"]),
}
LABELS = ("cell_type", "sample")
K = 15


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def scool_sums(store: Path, cd) -> np.ndarray:
    """Contacts of every cell / spot of the store's per-cell maps (the coolers' ``sum``)."""
    import cooler

    out = []
    for rec in (cd.uns.get("linked_scool") or {}).values():
        path = Path(rec["path"]) if Path(rec["path"]).is_absolute() else store.parent / rec["path"]
        if not path.exists():
            continue
        for name in cooler.fileops.list_scool_cells(str(path)):
            out.append(int(cooler.Cooler(f"{path}::{name}").info.get("sum", 0)))
    return np.asarray(out, dtype=np.int64)


def knn_agreement(x: np.ndarray, labels: np.ndarray, k: int = K) -> float:
    from sklearn.neighbors import NearestNeighbors

    ok = np.isfinite(x).all(1)
    x, labels = x[ok], labels[ok]
    k = min(k, len(x) - 1)
    nn = NearestNeighbors(n_neighbors=k + 1).fit(x).kneighbors(x, return_distance=False)[:, 1:]
    return float((labels[nn] == labels[:, None]).mean())


def chance(labels: np.ndarray) -> float:
    _, n = np.unique(labels, return_counts=True)
    return float(((n / n.sum()) ** 2).sum())


def scc(a, b) -> float:
    """Stratum-adjusted correlation without smoothing: per-diagonal Pearson, weighted by n and the coefficients
    of variation (HiCRep's weights)."""
    num = den = 0.0
    for ch in a:
        for x, y in zip(a[ch], b[ch]):
            ok = np.isfinite(x) & np.isfinite(y)
            x, y = x[ok], y[ok]
            if len(x) < 10 or x.std() == 0 or y.std() == 0 or x.mean() <= 0 or y.mean() <= 0:
                continue
            w = len(x) * x.std() / x.mean() * y.std() / y.mean()
            num += w * np.corrcoef(x, y)[0, 1]
            den += w
    return num / den if den else float("nan")


def diagonals(path: str, res: int = 500_000, maxd: int = 20):
    import cooler

    clr = cooler.Cooler(f"{path}::resolutions/{res}")
    out = {}
    for ch in clr.chromnames:
        if ch in ("chrX", "chrY", "chrM"):
            continue
        m = clr.matrix(balance=True).fetch(ch)
        out[ch] = [np.diagonal(m, d) for d in range(1, maxd + 1)]
    return out


def cells_vs_bulk(store: Path, cd) -> dict:
    """Uni-C: every sample's merged cells against every bulk library."""
    recs = cd.uns.get("linked_cool") or {}
    path = {k: str(store.parent / r["path"]) for k, r in recs.items()}
    cells = {k[len("cells_"):]: p for k, p in path.items() if k.startswith("cells_")}
    bulks = {k[len("bulk_"):]: p for k, p in path.items() if k.startswith("bulk_")}
    d = {k: diagonals(p) for k, p in {**{f"c:{s}": p for s, p in cells.items()}, **{f"b:{s}": p for s, p in bulks.items()}}.items()}
    return {"resolution": 500_000, "diagonals": [1, 20], "balanced": True,
            "scc": {s: {b: round(scc(d[f"c:{s}"], d[f"b:{b}"]), 4) for b in bulks} for s in cells}}


def dataset(d: dict, cat: dict) -> dict:
    from uchrom import ChromData

    store = DATA / d["store"]
    cd = ChromData.read(str(store), backed=True)
    c = cd.cells
    info = cat.get(d["id"], {})
    study = d.get("study")
    out = {"id": d["id"], "study": study, "name": d.get("name"), "organism": d.get("organism"),
           "assembly": d.get("assembly"), "category": info.get("category"), "modalities": info.get("modalities"),
           "n_cells": int(cd.n_cells), "n_spots": int(cd.n_spots), "size_mb": info.get("size_mb"),
           "contact_maps": info.get("contact_maps"),
           "unit": "spot" if (cd.uns or {}).get("cell_spatial") and info.get("category") == "Spatial" else "cell"}
    col = next((k for k in CONTACT_COLUMNS if k in c.columns), None)
    if col is not None:
        v = c[col].to_numpy(dtype=float)
        out["contacts_per_unit"] = {"median": float(np.median(v)), "q25": float(np.percentile(v, 25)),
                                    "q75": float(np.percentile(v, 75)), "source": f"cells.{col}"}
    else:
        s = scool_sums(store, cd)
        if len(s):
            out["contacts_per_unit"] = {"median": float(np.median(s)), "q25": float(np.percentile(s, 25)),
                                        "q75": float(np.percentile(s, 75)), "n": int(len(s)),
                                        "source": "linked per-cell .scool, cooler sum"}
    if cd.n_spots and cd.n_cells:
        if cd.n_spots > 5e7:                        # whole-genome structures: every cell has every bin per copy
            out["loci_per_cell"] = {"mean": cd.n_spots / cd.n_cells, "source": "n_spots / n_cells"}
        else:
            per = pd.Series(np.asarray(cd.spots["cell_id"])).value_counts()
            out["loci_per_cell"] = {"median": float(per.median()), "mean": float(per.mean()), "source": "spots per cell"}
    if d["id"] in PUBLISHED:
        mine, theirs = PUBLISHED[d["id"]]
        a = c[mine].to_numpy(dtype=float)
        b = c[theirs].to_numpy(dtype=float).sum(1)
        ok = np.isfinite(a) & np.isfinite(b) & (b > 0)
        a, b = a[ok], b[ok]
        rel = (a - b) / b
        out["published_counts"] = {"n": int(ok.sum()), "exact": float((a == b).mean()),
                                   "within_0.1pct": float((np.abs(rel) <= 1e-3).mean()),
                                   "median_ratio": float(np.median(a / b)), "max_abs_rel": float(np.abs(rel).max()),
                                   "reprocessed": mine, "published": "+".join(theirs)}
    label = next((k for k in LABELS if k in c.columns and c[k].nunique() > 1), None)
    if label and cd.cellm and cd.n_cells >= 20:
        has = c[label].notna().to_numpy()                       # cells without a label (unannotated spots) are left out
        lab = np.array([str(v) for v in c[label][has]], dtype=object)
        emb = {}
        for key, m in cd.cellm.items():
            m = np.asarray(m, dtype=float)
            if m.ndim == 2 and m.shape[0] == len(has) and "." not in key:
                emb[key] = round(knn_agreement(m[has], lab, K if label == "cell_type" else 3), 4)
        if emb:
            out["embedding_agreement"] = {"label": label, "k": K if label == "cell_type" else 3, "n": int(has.sum()),
                                          "n_labels": int(len(np.unique(lab))), "chance": round(chance(lab), 4),
                                          "agreement": emb}
    if d["id"].startswith("unic_"):
        out["cells_vs_bulk"] = cells_vs_bulk(store, cd)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--catalog", type=Path, help="catalog.json of the atlas (categories, modalities, sizes)")
    args = ap.parse_args()
    cfg = json.loads(CONFIG.read_text())
    studies = {s["id"]: s for s in cfg.get("studies", [])}
    cat = {}
    if args.catalog:
        c = json.loads(args.catalog.read_text())
        cat = {d["id"]: {**d, "category": studies.get(d.get("study"), {}).get("category")} for d in c["datasets"]}
    else:
        from chromdata.catalog import describe_store
        for d in cfg["datasets"]:
            if not args.only or d["id"] in args.only:
                cat[d["id"]] = {**describe_store(DATA / d["store"]), "category": studies.get(d.get("study"), {}).get("category")}
    root = paper_root()
    if root is None:
        raise SystemExit("u-chrom-paper not found (set UCHROM_PAPER)")
    out_path = root / "manuscripts" / "nmeth-bc" / "figures" / "results" / "atlas.json"
    old = json.loads(out_path.read_text()) if out_path.exists() else {}
    rows = {r["id"]: r for r in old.get("datasets", [])}
    for d in cfg["datasets"]:
        if args.only and d["id"] not in args.only:
            continue
        t = time.time()
        rows[d["id"]] = dataset(d, cat)
        log(f"{d['id']}: {time.time() - t:.0f} s")
    order = [d["id"] for d in cfg["datasets"]]
    spatial = {}
    for name in ("spatial_hicrna_validation.json", "spatial_hic_chen2026_reprocessed.json"):
        p = ROOT / "benchmarks" / "results" / name
        if p.exists():
            spatial[name] = json.loads(p.read_text())
    try:
        git = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        git = ""
    payload = {"generated": time.strftime("%Y-%m-%d %H:%M"), "uchrom_git": git, "script": "apps/atlas/benchmarks/validate.py",
               "datasets": [rows[i] for i in order if i in rows], "spatial_checks": spatial}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1))
    log(f"wrote {out_path}")


if __name__ == "__main__":
    main()
