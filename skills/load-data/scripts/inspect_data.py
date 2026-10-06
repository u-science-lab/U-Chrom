"""Inspect a U-Chrom dataset and run the QC a report needs — the load-data skill's recipe.

    python inspect_data.py data.chromdata.zarr                 # JSON summary + QC checks
    python inspect_data.py data.chromdata.zarr --group cell_type
    # or from Python:  from inspect_data import summarize; s = summarize(cd)

What it reports (every block is skipped when the data has no such part):

* counts — cells (cells table and cells with spots), traces, spots, chromosomes
* units / assembly / coordinate status from ``uns``
* ``cells`` columns grouped by prefix (``if.`` IF antibody channels, ``rna.``, ``atac.``, …) and the
  categorical columns with their value counts
* ``tracks`` (per-spot signals), ``traces`` columns, ``cellm`` embeddings with their ``uns['embeddings']`` recipe
* linked contact maps (``uns['linked_cool']`` / ``uns['linked_scool']``): file, resolutions, number of cells
* tracing QC: traces per (cell, chromosome) — ploidy —, duplicate loci within a trace, spots per trace
  (per cell, then per group), locus spacing and detection rate per chromosome, and the distance between
  consecutive detected loci (with units)

``checks`` lists what must be handled or mentioned before analysis.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


def _cell_ids(cells: pd.DataFrame) -> pd.Index:
    return cells["cell_id"].astype(str) if "cell_id" in cells.columns else cells.index.astype(str)


def _prefix_groups(cols) -> dict:
    groups: dict[str, list] = {}
    for c in cols:
        c = str(c)
        key = c.split(".", 1)[0] + "." if "." in c else "(no prefix)"
        groups.setdefault(key, []).append(c)
    return groups


def _jsonable(v):
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, np.generic):
        return v.item()
    return v


def linked_maps(cd) -> dict:
    """Linked .cool / .mcool / .scool files: path, existence, resolutions, cell count."""
    out = {}
    try:
        import cooler
    except ImportError:  # pragma: no cover
        cooler = None
    for family in ("linked_cool", "linked_scool"):
        for key, rec in (cd.uns.get(family) or {}).items():
            rec = dict(rec)
            info = {"family": family, "key": key, "format": rec.get("format"), "label": rec.get("label"),
                    "path": rec.get("path")}
            p = cd.resolve_link_path(rec["path"]) if rec.get("path") else None
            info["exists"] = bool(p and p.exists())
            if cooler is not None and info["exists"]:
                try:
                    if str(p).endswith(".mcool"):
                        info["resolutions"] = [int(u.rsplit("/", 1)[1]) for u in cooler.fileops.list_coolers(str(p))]
                        info["uri_example"] = f"{p}::/resolutions/{info['resolutions'][0]}"
                    elif family == "linked_scool" or str(p).endswith(".scool"):
                        cells = cooler.fileops.list_scool_cells(str(p))
                        info["n_cells"] = len(cells)
                        info["resolutions"] = [int(cooler.Cooler(f"{p}::{cells[0]}").binsize)] if cells else []
                    else:
                        c = cooler.Cooler(str(p))
                        info["resolutions"] = [int(c.binsize)]
                        info["total_contacts"] = int(c.info.get("sum", 0))
                except Exception as e:  # noqa: BLE001 — report, don't fail the summary
                    info["error"] = repr(e)
            elif rec.get("bin_size"):
                info["resolutions"] = [int(rec["bin_size"])]
            out[f"{family}:{key}"] = info
    return out


def tracing_qc(cd, group: str | None = "cell_type") -> dict:
    """Ploidy, duplicate loci, spots per trace, locus spacing, consecutive distances."""
    s = cd.spots
    qc: dict = {}
    if len(s) == 0:
        return qc
    df = pd.DataFrame({"chrom": s["chrom"].astype(str).to_numpy(), "start": s["start"].to_numpy(np.int64),
                       "trace_id": s["trace_id"].astype(str).to_numpy()})
    has_cell = "cell_id" in s.columns
    df["cell_id"] = s["cell_id"].astype(str).to_numpy() if has_cell else "all"
    xyz = np.asarray(cd.coords, dtype=float)

    # --- traces per (cell, chromosome): ploidy -------------------------------------------------
    tpc = df.drop_duplicates("trace_id").groupby(["cell_id", "chrom"]).size()
    n_cells_sp, n_chroms = df["cell_id"].nunique(), df["chrom"].nunique()
    dist = Counter(tpc.to_numpy().tolist())
    qc["traces_per_cell_chrom"] = {
        "distribution": {int(k): int(v) for k, v in sorted(dist.items())},
        "n_cell_chrom_with_traces": int(len(tpc)),
        "n_cell_chrom_without_traces": int(n_cells_sp * n_chroms - len(tpc)),
        "frac_gt2_of_nonempty": float((tpc > 2).mean()),
        "frac_gt2_of_all_cell_chrom": float((tpc > 2).sum() / (n_cells_sp * n_chroms)),
        "mean_nonempty": float(tpc.mean()),
    }
    # --- duplicate loci within a trace ------------------------------------------------------------
    dup = df.groupby(["trace_id", "chrom", "start"]).size()
    qc["duplicate_loci"] = {"n_trace_locus_with_gt1_spot": int((dup > 1).sum()),
                            "n_extra_spots": int((dup - 1).clip(lower=0).sum()),
                            "frac_traces_affected": float((dup > 1).groupby(level=0).any().mean())}
    # --- spots per trace: per cell (median over its traces), then per group ------------------------
    spt = df.groupby("trace_id").agg(n=("start", "size"), cell_id=("cell_id", "first"), chrom=("chrom", "first"))
    per_cell = spt.groupby("cell_id")["n"].median()
    qc["spots_per_trace"] = {"median_over_traces": float(spt["n"].median()),
                             "median_of_per_cell_medians": float(per_cell.median()),
                             "min": int(spt["n"].min()), "max": int(spt["n"].max())}
    if group and cd.cells is not None and group in cd.cells.columns:
        lab = pd.Series(cd.cells[group].astype(str).to_numpy(), index=_cell_ids(cd.cells))
        g = per_cell.groupby(lab.reindex(per_cell.index).to_numpy())
        qc["spots_per_trace"]["by_" + group] = {
            k: {"n_cells": int(len(v)), "median_of_per_cell_medians": float(v.median())} for k, v in g}
    # --- loci per chromosome: spacing and detection rate --------------------------------------------
    loci = df.drop_duplicates(["chrom", "start"]).groupby("chrom")["start"]
    spacing = loci.apply(lambda x: float(np.median(np.diff(np.sort(x.to_numpy())))) if len(x) > 1 else np.nan)
    n_loci = loci.size()
    det = spt.assign(n_loci=spt["chrom"].map(n_loci)).eval("n / n_loci").groupby(spt["chrom"]).median()
    qc["loci_per_chrom"] = {c: {"n_loci": int(n_loci[c]), "median_spacing_bp": spacing[c],
                                "median_detected_frac_per_trace": float(det[c])} for c in n_loci.index}
    # --- consecutive detected loci within a trace ---------------------------------------------------
    order = np.lexsort((df["start"].to_numpy(), df["trace_id"].to_numpy()))
    t = df["trace_id"].to_numpy()[order]
    same = t[1:] == t[:-1]
    d3 = np.linalg.norm(np.diff(xyz[order], axis=0), axis=1)[same]
    gap = np.diff(df["start"].to_numpy()[order])[same]
    ok = gap > 0                                         # skip duplicate loci
    chrom_o = df["chrom"].to_numpy()[order][1:][same][ok]
    cons = pd.DataFrame({"chrom": chrom_o, "d": d3[ok], "gap": gap[ok]})
    qc["consecutive_loci"] = {
        "unit": cd.uns.get("xyz_unit", "unknown"),
        "median_distance": float(cons["d"].median()) if len(cons) else None,
        "median_genomic_gap_bp": float(cons["gap"].median()) if len(cons) else None,
        "per_chrom_median_distance": cons.groupby("chrom")["d"].median().round(4).to_dict()}
    return qc


def summarize(cd, path=None, group: str | None = "cell_type") -> dict:
    s: dict = {"path": str(path) if path else None, "repr": repr(cd).splitlines()[0]}
    cells = cd.cells if cd.cells is not None else pd.DataFrame()
    s["counts"] = {"n_cells_table": int(len(cells)), "n_cells_with_spots": int(cd.spots["cell_id"].nunique())
                   if "cell_id" in cd.spots.columns else None,
                   "n_traces": int(cd.n_traces), "n_spots": int(cd.n_spots), "chroms": list(map(str, cd.chroms))}
    s["uns"] = {k: _jsonable(cd.uns.get(k)) for k in ("genome_assembly", "xyz_unit", "coordinate_status", "source",
                                                      "spot_semantics", "allele_col") if k in cd.uns}
    s["cells"] = {"n_columns": int(cells.shape[1]),
                  "by_prefix": {k: {"n": len(v), "first": v[:5]} for k, v in _prefix_groups(cells.columns).items()}}
    cats = {}
    for c in cells.columns:
        if (cells[c].dtype == object or str(cells[c].dtype) in ("category", "str", "string")) and cells[c].nunique() <= 50:
            cats[c] = {str(k): int(v) for k, v in cells[c].astype(str).value_counts().items()}
    s["cells"]["categorical"] = cats
    s["spots_columns"] = [str(c) for c in cd.spots.columns]
    for attr, note in (("spot_tracks", "per-spot values (cd.spot_tracks), aligned row-for-row with spots"),
                       ("bin_tracks", "per-locus values (cd.bin_tracks), one row per bin")):
        t = getattr(cd, attr, None)
        if t is not None and len(t.columns):
            s[attr] = {"n": int(t.shape[1]), "columns": [str(c) for c in t.columns], "note": note}
    if cd.traces is not None and len(cd.traces.columns):
        s["traces_columns"] = [str(c) for c in cd.traces.columns]
    emb = cd.uns.get("embeddings") or {}
    s["cellm"] = {k: {"shape": list(np.shape(v)),
                      **{f: _jsonable(emb.get(k, {}).get(f)) for f in ("label", "modality", "method", "input")
                         if f in emb.get(k, {})}} for k, v in (cd.cellm or {}).items()}
    for name in ("layers", "points", "results"):
        d = getattr(cd, name, None) or {}
        if d:
            s[name] = list(map(str, d.keys()))
    s["linked"] = linked_maps(cd)
    s["qc"] = tracing_qc(cd, group)
    s["checks"] = checks(cd, s)
    return s


def checks(cd, s) -> list[str]:
    out = []
    unit = cd.uns.get("xyz_unit")
    if cd.n_spots and not unit:
        out.append("no xyz_unit in uns: state that distances are in unknown units")
    elif unit and "model" in str(unit).lower():
        out.append(f"coordinates are in {unit}: not a physical length, do not convert to µm/nm")
    if cd.n_spots == 0:
        out.append("no 3-D coordinates (" + str(cd.uns.get("coordinate_status", "no spots"))
                   + "): structure comes from the linked contact maps, not from coords")
    qc = s.get("qc", {})
    tp = qc.get("traces_per_cell_chrom")
    if tp and tp["frac_gt2_of_nonempty"] > 0:
        out.append(f"{tp['frac_gt2_of_nonempty']:.1%} of (cell, chrom) pairs with traces have >2 traces "
                   "(diploid expects ≤2, ≤4 in G2): over-split alleles, doublets or replicated DNA. Before comparing "
                   "cells, summarise per cell (median over its traces) and/or keep cells with ≤2 traces per chrom; "
                   f"{tp['n_cell_chrom_without_traces']} (cell, chrom) pairs have no trace — say which denominator you use")
    du = qc.get("duplicate_loci")
    if du and du["n_trace_locus_with_gt1_spot"]:
        out.append(f"{du['n_trace_locus_with_gt1_spot']} (trace, locus) pairs have >1 spot: average them (or keep "
                   "the brighter) before distance matrices / TAD calling")
    sp = qc.get("spots_per_trace", {})
    by = {k: v for k, v in sp.items() if k.startswith("by_")}
    for k, v in by.items():
        meds = [x["median_of_per_cell_medians"] for x in v.values() if x["n_cells"] >= 3]
        if len(meds) >= 2 and max(meds) > 1.5 * min(meds):
            out.append(f"spots per trace differ >1.5x between {k[3:]} groups: Rg and span grow with the number and "
                       "genomic spread of detected loci — compare at equal loci (subsample) or adjust")
    lp = qc.get("loci_per_chrom", {})
    if lp and np.nanmedian([v["median_detected_frac_per_trace"] for v in lp.values()]) < 0.5:
        out.append("traces detect a minority of the loci on their chromosome (sparse traces): bin to a coarser "
                   "resolution before distance maps / TAD calling (see call-structures)")
    if "batch" in cd.cells.columns if cd.cells is not None else False:
        if cd.cells["batch"].nunique() <= 1:
            out.append("one batch / field of view: no biological replicate")
    for k, v in s.get("linked", {}).items():
        if not v["exists"]:
            out.append(f"linked file {v['path']} ({k}) is missing")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("data")
    ap.add_argument("--group", default="cell_type", help="cells column to break spots per trace down by")
    a = ap.parse_args()
    from chromdata import ChromData
    cd = ChromData.read(a.data)
    json.dump(_jsonable(summarize(cd, a.data, a.group)), sys.stdout, indent=1, default=str)
    print()


if __name__ == "__main__":
    main()
