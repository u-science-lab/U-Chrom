"""Relate a feature to chromatin structure (or two modalities) at a stated level — the
associate-modalities skill's recipe.

    # cell level: one value per cell, confounders partialled out, within cell types
    python associate.py cell data.chromdata.zarr --x if.<MARK> --y rg [--covar nuc_volume_um3,n_spots] [--group cell_type]
    python associate.py cell data.chromdata.zarr --x atac.<GENE> --y rna.<GENE> --group cell_type
    python associate.py cell data.chromdata.zarr --x if.<MARK> --y ps_slope --chrom chr1
    # bin level: per genomic bin, the mean of a spot track vs the mean of a structural spot feature
    python associate.py bin data.chromdata.zarr --x <TRACK> --y <TRACK> --chrom <CHROM> --bin-size <BIN>
    # embedding: k-nearest-neighbour label purity of a 2-D / n-D embedding in cellm
    python associate.py purity data.chromdata.zarr --emb hic_umap,rna_umap --label cell_type --k 15
    # spatial: Moran's I spatial autocorrelation of a per-cell feature on spatial k-NN graph
    python associate.py spatial data.chromdata.zarr --feature rg [--spatial-key default] [--region fov1] [--k 10]

Per-cell values (``--x`` / ``--y`` / ``--feature``):
  a ``cells`` column (``if.<MARK>``, ``rna.<GENE>``, ``nuc_volume_um3``, …);
  ``rg`` / ``span`` — median over the cell's traces of the trace radius of gyration / end-to-end distance;
  ``rg_norm`` — the same after dividing each trace's Rg by the median Rg of its chromosome (removes
  chromosome-composition differences between cells);
  ``n_spots`` — median spots per trace;  ``track:<name>`` — mean of a per-spot track over the cell's spots;
  ``ps_slope`` / ``cis_contacts`` / ``contact_density`` — per-cell contact map statistics (embedded Zarr first,
  then ``linked_scool``);
  ``clusters:<key>:n_clusters|median_size|cis_frac`` — multi-way contact cluster statistics.
  Optional ``--chrom``, ``--start``, ``--end`` restrict tracing, contact, and cluster stats to a window.
Per-spot values for ``bin``: any ``tracks`` column, or ``dist_to_cell_center`` (distance of a spot from the
centroid of all spots of its cell).
Prints one JSON object; ``checks`` lists what the report must mention.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

MIN_N = 5
CONTACT_STATS = ("ps_slope", "cis_contacts", "contact_density")
CLUSTER_METRICS = ("n_clusters", "median_size", "cis_frac")
MAX_CONTACT_BINS = 25_000


def _cell_index(cd) -> pd.Index:
    c = cd.cells
    return c["cell_id"].astype(str) if "cell_id" in c.columns else c.index.astype(str)


def _validate_window(chrom: str | None, start: int | None, end: int | None) -> tuple[str | None, int | None, int | None]:
    if chrom is not None and (not str(chrom).strip() or str(chrom).strip() == "*"):
        raise ValueError("chrom must be non-empty and not '*'")
    if (start is not None or end is not None) and chrom is None:
        raise ValueError("chrom is required when start or end is provided")
    if start is not None and end is not None and int(end) <= int(start):
        raise ValueError(f"end ({end}) must be > start ({start})")
    return (str(chrom) if chrom is not None else None), (int(start) if start is not None else None), (
        int(end) if end is not None else None
    )


def _window_mask(df_like, chrom: str | None, start: int | None, end: int | None) -> np.ndarray:
    chrom, start, end = _validate_window(chrom, start, end)
    mask = np.ones(len(df_like), dtype=bool)
    if chrom is not None:
        mask &= df_like["chrom"].astype(str).to_numpy() == chrom
    if mask.any() and (start is not None or end is not None):
        s_arr = df_like["start"].to_numpy(np.int64)
        e_arr = df_like["end"].to_numpy(np.int64)
        lo = max(0, int(start or 0))
        hi = int(end) if end is not None else int(e_arr[mask].max())
        mask &= (e_arr > lo) & (s_arr < hi)
    return mask


def _trace_frame(cd, chrom: str | None = None, start: int | None = None, end: int | None = None) -> pd.DataFrame:
    chrom, start, end = _validate_window(chrom, start, end)
    s = cd.spots
    df = pd.DataFrame(
        {
            "trace_id": s["trace_id"].astype(str).to_numpy(),
            "chrom": s["chrom"].astype(str).to_numpy(),
            "start": s["start"].to_numpy(np.int64),
            "end": s["end"].to_numpy(np.int64),
            "cell_id": s["cell_id"].astype(str).to_numpy() if "cell_id" in s.columns else "all",
        }
    )
    df[["x", "y", "z"]] = np.asarray(cd.coords, dtype=float)
    if len(df):
        df = df[np.isfinite(df[["x", "y", "z"]].to_numpy(float)).all(axis=1)]
    if len(df) and (chrom is not None or start is not None or end is not None):
        df = df[_window_mask(df, chrom, start, end)]
    return df


def per_trace(cd, chrom: str | None = None, start: int | None = None, end: int | None = None) -> pd.DataFrame:
    """trace_id, cell_id, chrom, n_spots, rg, span (optionally windowed by ``chrom:start-end``)."""
    df = _trace_frame(cd, chrom=chrom, start=start, end=end)
    if not len(df):
        return pd.DataFrame(columns=["cell_id", "chrom", "n_spots", "rg", "span", "rg_norm"])
    xyz = df[["x", "y", "z"]].to_numpy()
    cen = df.groupby("trace_id")[["x", "y", "z"]].transform("mean").to_numpy()
    df["r2"] = ((xyz - cen) ** 2).sum(1)
    df = df.sort_values(["trace_id", "start"])
    g = df.groupby("trace_id")
    t = g.agg(cell_id=("cell_id", "first"), chrom=("chrom", "first"), n_spots=("r2", "size"), ms=("r2", "mean"))
    t["rg"] = np.sqrt(t.pop("ms"))
    first, last = g[["x", "y", "z"]].first(), g[["x", "y", "z"]].last()
    t["span"] = np.linalg.norm(first.to_numpy() - last.to_numpy(), axis=1)
    t.loc[t["n_spots"] < 2, ["rg", "span"]] = np.nan
    t["rg_norm"] = t["rg"] / t.groupby("chrom")["rg"].transform("median")
    return t


# ------------------------------------------------------------------ per-cell contacts (embedded Zarr first)
def _linked_scool_records(cd) -> dict:
    raw = (cd.uns or {}).get("linked_scool")
    if not isinstance(raw, dict):
        return {}
    if "path" in raw:
        return {"default": raw}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict) and v.get("path")}


def _pick_resolution(resolutions: list[int], chromsizes: dict[str, int], chrom: str | None, start: int | None, end: int | None) -> int:
    if chrom is not None:
        if chrom not in chromsizes:
            raise KeyError(f"chromosome {chrom!r} not in contact map (have {list(chromsizes)[:10]})")
        clen = int(chromsizes[chrom])
        lo = max(0, int(start or 0))
        hi = min(clen, int(end)) if end is not None else clen
        span = max(0, hi - lo)
    else:
        span = sum(int(v) for v in chromsizes.values())
    res_list = sorted(int(r) for r in resolutions)
    for r in res_list:
        if span / r <= MAX_CONTACT_BINS:
            return r
    return res_list[-1]


def _n_pairs_array(bin_counts: list[int]) -> np.ndarray:
    max_nc = max(bin_counts, default=0)
    arr = np.zeros(max(max_nc, 1), dtype=np.float64)
    for nc in bin_counts:
        if nc >= 2:
            arr[1:nc] += np.arange(nc - 1, 0, -1, dtype=np.float64)
    return arr


def _diag_bounds(max_nc: int, r: int, smin: float | None, smax: float | None) -> tuple[int, int]:
    k_min = max(1, int(np.ceil(smin / r))) if smin is not None else 1
    k_max = min(max_nc - 1, int(np.floor(smax / r))) if smax is not None else max_nc - 1
    return k_min, k_max


def _diag_metrics(
    k_parts: list[np.ndarray],
    c_parts: list[np.ndarray],
    cis_total: float,
    r: int,
    n_pairs_by_k: np.ndarray,
    k_min: int,
    k_max: int,
) -> tuple[float, float, float]:
    total_pairs = float(n_pairs_by_k[k_min:k_max + 1].sum()) if k_min <= k_max else 0.0
    if not k_parts:
        return np.nan, float(cis_total), (0.0 if total_pairs > 0 else np.nan)
    ks = np.concatenate(k_parts) if len(k_parts) > 1 else k_parts[0]
    cs = np.concatenate(c_parts) if len(c_parts) > 1 else c_parts[0]
    uk, inv = np.unique(ks, return_inverse=True)
    dsum = np.bincount(inv, weights=cs.astype(float))
    density = float(dsum.sum() / total_pairs) if total_pairs > 0 else np.nan
    denom = n_pairs_by_k[uk]
    ok = (dsum > 0) & (denom > 0)
    if ok.sum() < 3:
        return np.nan, float(cis_total), density
    lx = np.log10(uk[ok].astype(float) * float(r))
    ly = np.log10(dsum[ok] / denom[ok])
    dx = lx - lx.mean()
    slope = float((dx * (ly - ly.mean())).sum() / (dx * dx).sum())
    return slope, float(cis_total), density


def _embedded_contact_stat(e, stat: str, chrom: str | None, start: int | None, end: int | None, smin: float | None, smax: float | None) -> pd.Series:
    csizes = e.chromsizes()
    r = _pick_resolution(e.resolutions, csizes, chrom, start, end)
    bins_df = e.bins(r)
    b_chrom = bins_df["chrom"].astype(str).to_numpy()
    if chrom is not None:
        mask = b_chrom == chrom
        lo = max(0, int(start or 0))
        hi = min(int(csizes[chrom]), int(end)) if end is not None else int(csizes[chrom])
        in_win = np.flatnonzero(mask & (bins_df["end"].to_numpy() > lo) & (bins_df["start"].to_numpy() < hi))
        first_c = int(np.flatnonzero(mask)[0]) if mask.any() else 0
        scopes = [(chrom, int(in_win[0]) - first_c, int(in_win[-1] + 1) - first_c)] if len(in_win) else [(chrom, 0, 0)]
    else:
        scopes = [(c, 0, int((b_chrom == c).sum())) for c in e.chroms if (b_chrom == c).any()]
    n_pairs = _n_pairs_array([b1 - b0 for _, b0, b1 in scopes])
    k_min, k_max = _diag_bounds(len(n_pairs), r, smin, smax)

    order = np.arange(len(e.cells), dtype=np.int64)
    cis_acc = np.zeros(len(order), dtype=np.float64)
    k_acc: list[list[np.ndarray]] = [[] for _ in range(len(order))]
    c_acc: list[list[np.ndarray]] = [[] for _ in range(len(order))]
    if len(order):
        for cname, b0, b1 in scopes:
            part = f"cis/{cname}"
            if b1 <= b0 or part not in e.g[f"r{r}"]:
                continue
            off = e._offsets(r, part, "cell_offset")
            counts = off[order + 1] - off[order]
            pos = counts > 0
            cell_of, cnts = order[pos], counts[pos]
            ptr = 0
            for d in e.cell_pixel_blocks(part, order, r):
                s = 0
                while s < len(d):
                    nk, ci = int(cnts[ptr]), int(cell_of[ptr])
                    px = d[s:s + nk]
                    m = (px[:, 0] >= b0) & (px[:, 0] < b1) & (px[:, 1] >= px[:, 0]) & (px[:, 1] < b1)
                    if m.any():
                        pm = px[m]
                        cis_acc[ci] += float(pm[:, 2].sum())
                        kk = pm[:, 1] - pm[:, 0]
                        km = (kk >= k_min) & (kk <= k_max)
                        if km.any():
                            k_acc[ci].append(kk[km])
                            c_acc[ci].append(pm[km, 2])
                    s += nk
                    ptr += 1

    col_idx = CONTACT_STATS.index(stat)
    vals = [
        _diag_metrics(k_acc[i], c_acc[i], float(cis_acc[i]), r, n_pairs, k_min, k_max)[col_idx]
        for i in range(len(order))
    ]
    return pd.Series(vals, index=pd.Index([str(c) for c in e.cells], dtype=object), name=stat, dtype=float)


def _scool_contact_stat(path: Path, stat: str, chrom: str | None, start: int | None, end: int | None, smin: float | None, smax: float | None) -> pd.Series:
    import h5py

    col_idx = CONTACT_STATS.index(stat)
    with h5py.File(path, "r") as f:
        chroms = [x.decode() if isinstance(x, (bytes, np.bytes_)) else str(x) for x in f["chroms/name"][:]]
        b_chrom = np.asarray(f["bins/chrom"][:], dtype=np.int64)
        b_start = np.asarray(f["bins/start"][:], dtype=np.int64)
        b_end = np.asarray(f["bins/end"][:], dtype=np.int64)
        r = int(np.median(b_end - b_start))
        if chrom is not None:
            if chrom not in chroms:
                raise KeyError(f"chromosome {chrom!r} not in scool (have {chroms[:10]})")
            c_idx = chroms.index(chrom)
            c_bins = np.flatnonzero(b_chrom == c_idx)
            lo = max(0, int(start or 0))
            hi = int(b_end[c_bins].max()) if (end is None and len(c_bins)) else int(end or 0)
            in_win = c_bins[(b_end[c_bins] > lo) & (b_start[c_bins] < hi)]
            g_b0, g_b1 = (int(in_win[0]), int(in_win[-1] + 1)) if len(in_win) else (0, 0)
            n_pairs = _n_pairs_array([g_b1 - g_b0])
        else:
            n_pairs = _n_pairs_array([int((b_chrom == ci).sum()) for ci in range(len(chroms))])
        k_min, k_max = _diag_bounds(len(n_pairs), r, smin, smax)

        cids = list(f["cells"].keys())
        vals = []
        for scid in cids:
            grp = f["cells"][scid]
            px = grp["pixels"]
            if chrom is not None:
                if g_b1 <= g_b0:
                    vals.append(_diag_metrics([], [], 0.0, r, n_pairs, k_min, k_max)[col_idx])
                    continue
                boff = grp["indexes/bin1_offset"]
                p_lo, p_hi = int(boff[g_b0]), int(boff[g_b1])
                if p_hi <= p_lo:
                    vals.append(_diag_metrics([], [], 0.0, r, n_pairs, k_min, k_max)[col_idx])
                    continue
                p1 = np.asarray(px["bin1_id"][p_lo:p_hi], dtype=np.int64)
                p2 = np.asarray(px["bin2_id"][p_lo:p_hi], dtype=np.int64)
                cnt = np.asarray(px["count"][p_lo:p_hi], dtype=np.float64)
                m = (p2 >= p1) & (p2 < g_b1)
            else:
                p1 = np.asarray(px["bin1_id"][:], dtype=np.int64)
                p2 = np.asarray(px["bin2_id"][:], dtype=np.int64)
                cnt = np.asarray(px["count"][:], dtype=np.float64)
                m = (b_chrom[p1] == b_chrom[p2]) & (p2 >= p1)
            if not m.any():
                vals.append(_diag_metrics([], [], 0.0, r, n_pairs, k_min, k_max)[col_idx])
                continue
            p1, p2, cnt = p1[m], p2[m], cnt[m]
            cis_total = float(cnt.sum())
            kk = p2 - p1
            km = (kk >= k_min) & (kk <= k_max)
            vals.append(_diag_metrics([kk[km]] if km.any() else [], [cnt[km]] if km.any() else [], cis_total, r, n_pairs, k_min, k_max)[col_idx])
    return pd.Series(vals, index=pd.Index([str(c) for c in cids], dtype=object), name=stat, dtype=float)


def _contact_stat(
    cd,
    stat: str,
    *,
    cool: str | None = None,
    chrom: str | None = None,
    start: int | None = None,
    end: int | None = None,
    smin: float | None = None,
    smax: float | None = None,
) -> pd.Series:
    chrom, start, end = _validate_window(chrom, start, end)
    if smin is not None and smax is not None and float(smax) < float(smin):
        raise ValueError(f"smax ({smax}) must be >= smin ({smin})")
    src = cd._links_from() if hasattr(cd, "_links_from") else None
    maps = {}
    if src is not None:
        from chromdata.embedded import open_all

        maps = open_all(src)
    e = None
    if cool is not None and cool in maps:
        if maps[cool].kind != "per_cell":
            raise ValueError(f"contact map {cool!r} has kind {maps[cool].kind!r}; per_cell required")
        e = maps[cool]
    elif cool is None:
        per_cell_maps = {k: v for k, v in maps.items() if v.kind == "per_cell"}
        if per_cell_maps:
            if "default" in per_cell_maps:
                e = per_cell_maps["default"]
            else:
                recs = _linked_scool_records(cd)
                pick = next((k for k in recs if k in per_cell_maps), next(iter(per_cell_maps)))
                e = per_cell_maps[pick]
    if e is not None:
        return _embedded_contact_stat(e, stat, chrom, start, end, smin, smax)

    recs = _linked_scool_records(cd)
    if cool is not None:
        if cool in recs:
            rec = recs[cool]
        elif Path(cool).exists():
            rec = {"path": cool}
        else:
            raise KeyError(f"no embedded per_cell map or linked_scool record {cool!r}")
    else:
        if not recs:
            raise KeyError("no embedded per_cell map and no uns['linked_scool'] record")
        rec = recs.get("default") or next(iter(recs.values()))
    p = cd.resolve_link_path(rec["path"]) if hasattr(cd, "resolve_link_path") else Path(rec["path"])
    return _scool_contact_stat(p, stat, chrom, start, end, smin, smax)


# ------------------------------------------------------------------ multi-way cluster metrics
def _cluster_stat(cd, spec: str, chrom: str | None = None, start: int | None = None, end: int | None = None) -> pd.Series:
    chrom, start, end = _validate_window(chrom, start, end)
    parts = spec.split(":")
    if len(parts) < 3 or parts[0] != "clusters":
        raise ValueError(f"invalid cluster stat {spec!r}; expected clusters:<key>:<metric>")
    key, metric = ":".join(parts[1:-1]), parts[-1]
    if metric not in CLUSTER_METRICS:
        raise ValueError(f"unknown cluster metric {metric!r}; expected one of {CLUSTER_METRICS}")
    if key not in cd.clusters:
        raise KeyError(f"no clusters[{key!r}] in ChromData")
    t = cd.clusters[key]
    if t.kind != "per_cell" or t.cells is None:
        raise ValueError(f"clusters[{key!r}] is a bulk table (no cells)")
    if chrom is not None:
        if chrom not in t.chroms:
            return pd.Series(0.0 if metric == "n_clusters" else np.nan, index=t.cells, name=spec, dtype=float)
        lo = max(0, int(start or 0))
        hi = int(end) if end is not None else (1 << 60)
        u = t.region(chrom, lo, hi).drop_duplicates("cluster")
        if metric == "n_clusters":
            return u.groupby("cell_id", observed=True).size().reindex(t.cells, fill_value=0).astype(float).rename(spec)
        if metric == "median_size":
            return u.groupby("cell_id", observed=True)["size"].median().reindex(t.cells).astype(float).rename(spec)
        u = u.assign(_cis=(u["chrom_size"] == u["size"]).astype(float))
        return u.groupby("cell_id", observed=True)["_cis"].mean().reindex(t.cells).astype(float).rename(spec)

    co = t.cell_offsets
    if metric == "n_clusters":
        vals = np.diff(co).astype(float)
    elif metric == "median_size":
        sizes = t.sizes()
        vals = np.array(
            [float(np.median(sizes[co[i]:co[i + 1]])) if co[i + 1] > co[i] else np.nan for i in range(t.n_cells)],
            dtype=float,
        )
    else:
        off = t.member_offsets
        sizes = np.diff(off)
        c0 = np.asarray(t._members[0, :], dtype=np.int64)
        nz = sizes > 0
        is_cis = np.zeros(t.n_clusters, dtype=float)
        is_cis[nz] = (c0[off[:-1][nz]] == c0[off[1:][nz] - 1]).astype(float)
        vals = np.array(
            [float(is_cis[co[i]:co[i + 1]].mean()) if co[i + 1] > co[i] else np.nan for i in range(t.n_cells)],
            dtype=float,
        )
    return pd.Series(vals, index=t.cells, name=spec, dtype=float)


def per_cell(
    cd,
    stat: str,
    chrom: str | None = None,
    start: int | None = None,
    end: int | None = None,
    cool: str | None = None,
    smin: float | None = None,
    smax: float | None = None,
) -> pd.Series:
    """One value per cell (index = cell id) for a value spec (see module docstring)."""
    if stat in ("rg", "span", "rg_norm", "n_spots"):
        return per_trace(cd, chrom=chrom, start=start, end=end).groupby("cell_id")[stat].median().rename(stat)
    if stat in CONTACT_STATS:
        return _contact_stat(cd, stat, cool=cool, chrom=chrom, start=start, end=end, smin=smin, smax=smax)
    if stat.startswith("clusters:"):
        return _cluster_stat(cd, stat, chrom=chrom, start=start, end=end)
    if stat.startswith("track:"):
        name = stat[len("track:"):]
        s = cd.spots
        mask = _window_mask(s, chrom, start, end) if (chrom is not None or start is not None or end is not None) else slice(None)
        cid = s["cell_id"].astype(str).to_numpy()[mask]
        vals = pd.to_numeric(_spot_track(cd, name), errors="coerce")[mask]
        return pd.Series(vals).groupby(cid).mean().rename(stat)
    if cd.cells is None or stat not in cd.cells.columns:
        raise KeyError(
            f"{stat!r} is not a cells column nor one of rg, span, rg_norm, n_spots, track:<name>, "
            "ps_slope, cis_contacts, contact_density, clusters:<key>:<metric>"
        )
    return pd.Series(pd.to_numeric(cd.cells[stat], errors="coerce").to_numpy(), index=_cell_index(cd), name=stat)


def _rank_resid(y: np.ndarray, Z: np.ndarray) -> np.ndarray:
    """Residuals of rank(y) on ranks of the covariates (for a partial Spearman correlation)."""
    ry = st.rankdata(y)
    X = np.column_stack([np.ones(len(y))] + [st.rankdata(z) for z in Z.T])
    beta, *_ = np.linalg.lstsq(X, ry, rcond=None)
    return ry - X @ beta


def _corr(a, b, method):
    r = st.spearmanr(a, b) if method == "spearman" else st.pearsonr(a, b)
    return float(r.statistic), float(r.pvalue)


def cell_level(
    cd,
    x: str,
    y: str,
    covariates=("nuc_volume_um3",),
    group: str | None = "cell_type",
    method: str = "spearman",
    chrom: str | None = None,
    start: int | None = None,
    end: int | None = None,
    cool: str | None = None,
    smin: float | None = None,
    smax: float | None = None,
) -> dict:
    """Correlate two per-cell values across cells: overall, partial on covariates, and within groups."""
    chrom, start, end = _validate_window(chrom, start, end)
    cols = {
        x: per_cell(cd, x, chrom=chrom, start=start, end=end, cool=cool, smin=smin, smax=smax),
        y: per_cell(cd, y, chrom=chrom, start=start, end=end, cool=cool, smin=smin, smax=smax),
    }
    covs = [c for c in (covariates or []) if c and c not in (x, y)]
    for c in covs:
        cols[c] = per_cell(cd, c, chrom=chrom, start=start, end=end, cool=cool, smin=smin, smax=smax)
    df = pd.DataFrame(cols).dropna()
    if group and cd.cells is not None and group in cd.cells.columns:
        lab = pd.Series(cd.cells[group].astype(str).to_numpy(), index=_cell_index(cd))
        df["_group"] = lab.reindex(df.index).to_numpy()
    else:
        group = None
    n = len(df)
    res = {"level": "cell (one value per cell)", "x": x, "y": y, "method": method, "n_cells": n, "checks": []}
    if chrom is not None:
        res["window"] = {"chrom": chrom, "start": start, "end": end}
    if n < 3:
        res["checks"].append("fewer than 3 cells with both values")
        return res
    res["rho"], res["p"] = _corr(df[x], df[y], method)
    res["confounders"] = {}
    for c in covs:
        rx, _ = _corr(df[x], df[c], "spearman")
        ry, _ = _corr(df[y], df[c], "spearman")
        res["confounders"][c] = {"rho_with_x": rx, "rho_with_y": ry}
        if abs(rx) > 0.3 and abs(ry) > 0.3:
            res["checks"].append(
                f"{c} correlates with both {x} (rho {rx:.2f}) and {y} (rho {ry:.2f}): part of the "
                f"association may run through {c} — report the partial correlation"
            )
    if covs and n > len(covs) + 3:
        Z = df[covs].to_numpy(float)
        pr = st.pearsonr(_rank_resid(df[x].to_numpy(float), Z), _rank_resid(df[y].to_numpy(float), Z))
        res["partial"] = {
            "controls": covs,
            "rho": float(pr.statistic),
            "p": float(pr.pvalue),
            "method": "Spearman partial (rank residuals)",
        }
    if group:
        within = {}
        for g, d in df.groupby("_group"):
            if len(d) >= MIN_N and d[x].nunique() > 1 and d[y].nunique() > 1:
                r, p = _corr(d[x], d[y], method)
                within[g] = {"n": int(len(d)), "rho": r, "p": p}
            else:
                within[g] = {"n": int(len(d)), "rho": None, "note": f"< {MIN_N} cells or constant"}
        res["within_" + group] = within
        rhos = [v["rho"] for v in within.values() if v.get("rho") is not None]
        res["median_within_group_rho"] = float(np.median(rhos)) if rhos else None
        # pooled within-group: centre ranks inside each group, then correlate
        cx = df.groupby("_group")[x].rank(pct=True) - 0.5
        cy = df.groupby("_group")[y].rank(pct=True) - 0.5
        pw = st.pearsonr(cx, cy)
        res["pooled_within_group"] = {
            "rho": float(pw.statistic),
            "p": float(pw.pvalue),
            "method": f"Pearson of within-{group} percentile ranks",
        }
        gm = df.groupby("_group")[[x, y]].median()
        if len(gm) >= 3:
            res["between_group_medians_rho"] = _corr(gm[x], gm[y], "spearman")[0]
        if (
            abs(res["rho"]) >= 0.1
            and res["p"] < 0.05
            and abs(res["pooled_within_group"]["rho"]) < 0.5 * abs(res["rho"])
        ):
            res["checks"].append(
                f"the association is much weaker within {group} (pooled within rho "
                f"{res['pooled_within_group']['rho']:.2f} vs overall {res['rho']:.2f}): it is largely "
                f"driven by differences between {group}s"
            )
    if n < 20:
        res["checks"].append(f"only {n} cells: wide uncertainty; give the p-value and avoid strong claims")
    if cd.cells is not None and "batch" in cd.cells.columns and cd.cells["batch"].nunique() <= 1:
        res["checks"].append("one batch / field of view: no biological replicate")
    return res


def spot_values(cd, name: str) -> np.ndarray:
    if name == "dist_to_cell_center":
        df = _trace_frame(cd)
        cen = df.groupby("cell_id")[["x", "y", "z"]].transform("mean").to_numpy()
        return np.linalg.norm(df[["x", "y", "z"]].to_numpy() - cen, axis=1)
    return pd.to_numeric(_spot_track(cd, name), errors="coerce").astype(float)


def _spot_track(cd, name: str) -> np.ndarray:
    """A track as one value per spot: a spot track as is, a bin (locus) track broadcast through bin_id."""
    s_tr = getattr(cd, "spot_tracks", None)
    if s_tr is not None and name in s_tr.columns:
        return s_tr[name].to_numpy()
    b_tr = getattr(cd, "bin_tracks", None)
    if b_tr is not None and name in b_tr.columns:
        return b_tr[name].reindex(cd.spots["bin_id"].to_numpy()).to_numpy()
    raise KeyError(f"{name!r} is neither a spot track nor a bin track")


def bin_level(
    cd, x: str, y: str, chrom: str, bin_size: float = 1e6, cells=None, method: str = "spearman", min_spots: int = 10
) -> dict:
    """Per genomic bin (``bin_size`` bp on ``chrom``): mean of spot value x and of spot value y over all spots
    (optionally of ``cells``) in the bin; correlate across bins."""
    s = cd.spots
    mask = s["chrom"].astype(str).to_numpy() == str(chrom)
    if cells is not None:
        mask &= s["cell_id"].astype(str).isin([str(c) for c in cells]).to_numpy()
    xv, yv = spot_values(cd, x)[mask], spot_values(cd, y)[mask]
    mid = ((s["start"].to_numpy(np.int64) + s["end"].to_numpy(np.int64)) // 2)[mask]
    b = mid // int(bin_size)
    df = pd.DataFrame({"bin": b, "x": xv, "y": yv, "cell": s["cell_id"].astype(str).to_numpy()[mask]}).dropna()
    g = df.groupby("bin").agg(x=("x", "mean"), y=("y", "mean"), n_spots=("x", "size"), n_cells=("cell", "nunique"))
    g = g[g["n_spots"] >= min_spots]
    res = {
        "level": f"genomic bin ({int(bin_size)} bp) — per-bin means over spots of all selected cells",
        "x": x,
        "y": y,
        "chrom": chrom,
        "method": method,
        "n_bins": int(len(g)),
        "median_spots_per_bin": float(g["n_spots"].median()) if len(g) else None,
        "checks": [],
    }
    if len(g) >= 3:
        res["rho"], res["p"] = _corr(g["x"], g["y"], method)
        # spot-level for contrast only: spots are not independent (same trace, same cell)
        res["spot_level_rho_for_contrast"] = _corr(df["x"], df["y"], method)[0]
        res["checks"].append(
            "p-value across bins ignores spatial autocorrelation of neighbouring bins; treat it as descriptive"
        )
    if y == "dist_to_cell_center" or x == "dist_to_cell_center":
        res["checks"].append(
            "dist_to_cell_center: larger = more peripheral (centroid of the cell's DNA spots, not "
            "the segmented nucleus)"
        )
    return res


def knn_purity(cd, emb: str, label: str = "cell_type", k: int = 15) -> dict:
    """Mean fraction of each cell's k nearest neighbours (self excluded, Euclidean) sharing its label."""
    from sklearn.neighbors import NearestNeighbors

    X = np.asarray(cd.cellm[emb], dtype=float)
    lab = cd.cells[label].astype(str).to_numpy()
    ok = np.isfinite(X).all(1) & pd.notna(cd.cells[label]).to_numpy()
    X, lab = X[ok], lab[ok]
    idx = NearestNeighbors(n_neighbors=k + 1).fit(X).kneighbors(X, return_distance=False)[:, 1:]
    same = (lab[idx] == lab[:, None]).mean(1)
    freq = pd.Series(lab).value_counts(normalize=True)
    per = pd.Series(same).groupby(lab).mean()
    meta = (cd.uns.get("embeddings") or {}).get(emb, {})
    return {
        "embedding": emb,
        "dims": int(X.shape[1]),
        "label": label,
        "k": k,
        "n_cells": int(len(X)),
        "purity": float(same.mean()),
        "chance_purity": float((freq ** 2).sum()),
        "per_label": per.round(4).to_dict(),
        "modality": meta.get("modality"),
        "method": meta.get("method"),
    }


def spatial_autocorr(
    cd,
    feature: str,
    spatial_key: str | None = None,
    region: str | None = None,
    k: int = 10,
    permutations: int = 199,
    seed: int = 0,
    chrom: str | None = None,
    start: int | None = None,
    end: int | None = None,
    cool: str | None = None,
    smin: float | None = None,
    smax: float | None = None,
) -> dict:
    """Moran's I spatial autocorrelation of a per-cell feature on a spatial k-NN graph within a region."""
    import scipy.sparse as sps
    from scipy.spatial import cKDTree

    if spatial_key is None:
        recs = (cd.uns or {}).get("cell_spatial") or {}
        spatial_key = "default" if ("default" in recs or not recs) else next(iter(recs))
    pos = cd.cell_positions(spatial_key)
    s = per_cell(cd, feature, chrom=chrom, start=start, end=end, cool=cool, smin=smin, smax=smax)
    dims = [c for c in ("x", "y", "z") if c in pos.columns and pos[c].notna().any()]
    pos.index = pos.index.astype(str)
    s.index = s.index.astype(str)
    common = pos.index.intersection(s.index)
    xy_ok = np.isfinite(pos.loc[common, dims].to_numpy(float)).all(axis=1) if dims else np.zeros(len(common), bool)
    val_ok = np.isfinite(pd.to_numeric(s.reindex(common), errors="coerce").to_numpy(float))
    valid_ids = common[xy_ok & val_ok]

    checks: list[str] = []
    chosen_region = None
    if "region" in pos.columns:
        reg_series = pos.loc[valid_ids, "region"].astype(str)
        counts = reg_series.value_counts()
        if region is not None:
            chosen_region = str(region)
            valid_ids = valid_ids[reg_series.to_numpy() == chosen_region]
        elif len(counts):
            max_cnt = int(counts.max())
            chosen_region = sorted([str(r) for r, c in counts.items() if c == max_cnt])[0]
            if len(counts) > 1:
                checks.append(
                    f"multiple spatial regions present ({len(counts)}); computed within largest region "
                    f"{chosen_region!r} — specify region= to test another"
                )
            valid_ids = valid_ids[reg_series.to_numpy() == chosen_region]
    elif region is not None:
        raise ValueError(f"region={region!r} requested, but spatial key {spatial_key!r} has no region column")

    n = len(valid_ids)
    res = {
        "level": "spatial (per-cell Moran's I on k-NN graph)",
        "feature": feature,
        "spatial_key": spatial_key,
        "region": chosen_region,
        "k": int(k),
        "n_cells": int(n),
        "permutations": int(permutations),
        "seed": int(seed),
        "morans_i": None,
        "expected_i": None,
        "p_upper": None,
        "p_two_sided": None,
        "checks": checks,
    }
    if n < 4 or k < 1:
        checks.append(f"only {n} cells with finite positions and feature values (< 4); Moran's I not computed")
        return res

    xy = pos.loc[valid_ids, dims].to_numpy(float)
    vals = pd.to_numeric(s.reindex(valid_ids), errors="coerce").to_numpy(float)
    z = vals - vals.mean()
    zz = float(z @ z)
    if zz == 0.0 or np.allclose(z, 0.0):
        checks.append("feature is constant across cells; Moran's I is undefined")
        return res

    k_eff = min(int(k), n - 1)
    if k_eff < int(k):
        checks.append(f"k clamped from {int(k)} to {k_eff} (n_cells - 1)")
        res["k_used"] = k_eff

    _, nbrs = cKDTree(xy).query(xy, k=k_eff + 1)
    rows = np.repeat(np.arange(n), k_eff)
    cols = nbrs[:, 1:].ravel()
    adj = sps.coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n)).tocsr()
    adj = ((adj + adj.T) > 0).astype(np.float64).tocsr()
    adj.setdiag(0)
    adj.eliminate_zeros()
    deg = np.asarray(adj.sum(axis=1)).ravel()
    inv = np.divide(1.0, deg, out=np.zeros_like(deg), where=deg > 0)
    w = (sps.diags(inv) @ adj).tocsr()
    s0 = float(w.sum())
    if s0 == 0.0:
        checks.append("spatial graph has no edges; Moran's I is undefined")
        return res

    scale = n / (s0 * zz)
    obs_i = float(scale * (z @ (w @ z)))
    rng = np.random.default_rng(seed)
    n_perms = max(0, int(permutations))
    ge = 0
    le = 0
    for _ in range(n_perms):
        zp = z[rng.permutation(n)]
        ip = scale * (zp @ (w @ zp))
        if ip >= obs_i:
            ge += 1
        if ip <= obs_i:
            le += 1

    res["morans_i"] = obs_i
    res["expected_i"] = float(-1.0 / (n - 1))
    if n_perms > 0:
        p_up = float((ge + 1) / (n_perms + 1))
        p_lo = float((le + 1) / (n_perms + 1))
        res["p_upper"] = p_up
        res["p_two_sided"] = float(min(1.0, 2.0 * min(p_up, p_lo)))
    if n < 20:
        checks.append(f"only {n} cells: wide uncertainty; give the p-value and avoid strong claims")
    spatial_meta = pos.attrs.get("cell_spatial", {})
    if spatial_meta.get("status") == "inferred":
        checks.append(f"cell positions are inferred (source: {spatial_meta.get('source', 'unknown')})")
    return res


def _is_valid_cov(cd, c: str) -> bool:
    return (
        c in ("rg", "n_spots", "span", "rg_norm", *CONTACT_STATS)
        or c.startswith(("track:", "clusters:"))
        or (cd.cells is not None and c in cd.cells.columns)
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["cell", "bin", "purity", "spatial"])
    ap.add_argument("data")
    ap.add_argument("--x")
    ap.add_argument("--y")
    ap.add_argument("--feature")
    ap.add_argument("--covar", default="nuc_volume_um3")
    ap.add_argument("--group", default="cell_type")
    ap.add_argument("--method", default="spearman", choices=["spearman", "pearson"])
    ap.add_argument("--chrom")
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--cool", default=None)
    ap.add_argument("--smin", type=float, default=None)
    ap.add_argument("--smax", type=float, default=None)
    ap.add_argument("--bin-size", type=float, default=1e6)
    ap.add_argument("--emb")
    ap.add_argument("--label", default="cell_type")
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("--spatial-key", default=None)
    ap.add_argument("--region", default=None)
    ap.add_argument("--permutations", type=int, default=199)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    from chromdata import ChromData

    cd = ChromData.read(a.data, backed=True)
    if a.cmd == "cell":
        covs = [c for c in a.covar.split(",") if c and _is_valid_cov(cd, c)]
        out = cell_level(
            cd,
            a.x,
            a.y,
            covs,
            a.group or None,
            a.method,
            chrom=a.chrom,
            start=a.start,
            end=a.end,
            cool=a.cool,
            smin=a.smin,
            smax=a.smax,
        )
    elif a.cmd == "bin":
        out = bin_level(cd, a.x, a.y, a.chrom, a.bin_size, method=a.method)
    elif a.cmd == "spatial":
        feat = a.feature or a.x
        if not feat:
            ap.error("spatial requires --feature (or --x)")
        out = spatial_autocorr(
            cd,
            feat,
            spatial_key=a.spatial_key,
            region=a.region,
            k=10 if a.k is None else a.k,
            permutations=a.permutations,
            seed=a.seed,
            chrom=a.chrom,
            start=a.start,
            end=a.end,
            cool=a.cool,
            smin=a.smin,
            smax=a.smax,
        )
    else:
        out = {e: knn_purity(cd, e, a.label, 15 if a.k is None else a.k) for e in a.emb.split(",")}
    json.dump(out, sys.stdout, indent=1, default=float)
    print()


if __name__ == "__main__":
    main()
