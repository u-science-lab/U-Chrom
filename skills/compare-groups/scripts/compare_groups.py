"""Compare a statistic between two groups of cells — the compare-groups skill's recipe.

The unit of replication is the **cell**: per-trace (or per-spot) values are first summarised per
cell (median), and the test compares cells.  Traces of one cell are not independent; testing them
as if they were inflates n and makes almost any difference "significant".

    python compare_groups.py data.chromdata.zarr --a <cell_id>,<cell_id>,... --b field:cell_type=<TYPE> --stat rg
    python compare_groups.py data.chromdata.zarr --a field:cell_type=<TYPE> --b rest --stat rg --equalize 100
    python compare_groups.py data.chromdata.zarr --a field:cell_type=<TYPE> --b rest --stat ps_slope --chrom chr1
    python compare_groups.py data.chromdata.zarr --a <cell_id>,<cell_id>,... --b rest --scan if.     # every if.* column, BH-FDR
    # or from Python:  from compare_groups import compare, scan; compare(cd, a, b, stat="rg")

Groups: comma-separated cell ids, ``field:<column>=<value>`` / ``field:<column>!=<value>`` (cells column),
``all``, or ``rest`` (for b: every cell not in a).
Stats: ``rg`` (radius of gyration per trace), ``span`` (end-to-end distance per trace), ``n_spots`` (spots
per trace), per-cell contact stats (``ps_slope``, ``cis_contacts``, ``contact_density``), multi-way cluster
stats (``clusters:<key>:n_clusters|median_size|cis_frac``), or any numeric ``cells`` column (e.g.
``nuc_volume_um3``, ``if.<MARK>``) — then there is one value per cell.  ``chrom``/``start``/``end`` restrict
tracing or contact/cluster metrics to a genomic window.  ``equalize=k`` recomputes ``rg``/``span`` on k
randomly drawn loci per trace (traces with fewer are dropped; averaged over draws), so groups with different
detection are compared at equal loci.
``scan`` compares many cells columns at once with Benjamini–Hochberg FDR, plus categorical composition.
Prints one JSON object; ``checks`` lists everything a report must mention.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

MIN_CELLS = 5
TRACE_STATS = ("rg", "span", "n_spots")
CONTACT_STATS = ("ps_slope", "cis_contacts", "contact_density")
CLUSTER_METRICS = ("n_clusters", "median_size", "cis_frac")
MAX_CONTACT_BINS = 25_000


def _all_ids(cd) -> list:
    cells = cd.cells
    if cells is not None and len(cells):
        return list(cells.index.astype(str) if "cell_id" not in cells else cells["cell_id"].astype(str))
    if "cell_id" in cd.spots.columns:
        return list(cd.spots["cell_id"].astype(str).unique())
    return []


def resolve_group(cd, spec, other=None) -> list:
    """Cell ids of a group spec (list of ids, 'a,b,c', 'field:<col>=<value>', 'field:<col>!=<value>',
    'all', or 'rest' = every cell not in ``other``)."""
    if isinstance(spec, str) and spec in ("all", "rest"):
        excl = set(resolve_group(cd, other)) if spec == "rest" and other is not None else set()
        return list(dict.fromkeys(c for c in _all_ids(cd) if c not in excl))
    if isinstance(spec, str) and spec.startswith("field:"):
        body = spec[len("field:"):]
        neg = "!=" in body
        col, val = body.split("!=" if neg else "=", 1)
        cells = cd.cells
        ids = cells.index.astype(str) if "cell_id" not in cells else cells["cell_id"].astype(str)
        hit = cells[col].astype(str).to_numpy() == val
        return list(dict.fromkeys(str(c) for c in ids[~hit if neg else hit]))
    if isinstance(spec, str):
        spec = [s for s in spec.split(",") if s]
    return list(dict.fromkeys(str(c) for c in spec))


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


def _filter_spots_window(df: pd.DataFrame, chrom: str | None, start: int | None, end: int | None) -> pd.DataFrame:
    chrom, start, end = _validate_window(chrom, start, end)
    if chrom is not None:
        df = df[df["chrom"].astype(str) == chrom]
    if len(df) and (start is not None or end is not None):
        lo = max(0, int(start or 0))
        hi = int(end) if end is not None else int(df["end"].max())
        df = df[(df["end"] > lo) & (df["start"] < hi)]
    return df


def _equalized(df: pd.DataFrame, stat: str, k: int, draws: int, seed: int) -> pd.Series:
    """Per trace: mean over ``draws`` random subsets of k loci of Rg (or span); traces with < k loci dropped.

    Each trace draws from its own generator seeded by (seed, trace id), and loci are ordered by
    (start, x, y, z), so the result does not depend on the stored row or trace order."""
    import zlib

    out = {}
    for tid, t in df.groupby("trace_id", observed=True):
        if len(t) < k:
            continue
        rng = np.random.default_rng([seed, zlib.crc32(str(tid).encode())])
        t = t.sort_values(["start", "x", "y", "z"], kind="mergesort")
        xyz = t[["x", "y", "z"]].to_numpy()
        vals = []
        for _ in range(draws):
            idx = np.sort(rng.choice(len(t), size=k, replace=False))
            p = xyz[idx]
            if stat == "rg":
                vals.append(np.sqrt(((p - p.mean(0)) ** 2).sum(1).mean()))
            else:
                vals.append(np.linalg.norm(p[-1] - p[0]))
        out[tid] = float(np.mean(vals))
    return pd.Series(out, dtype=float)


def per_trace(
    cd,
    stat: str,
    equalize: int | None = None,
    draws: int = 20,
    seed: int = 0,
    chrom: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> pd.DataFrame:
    """One row per trace: cell_id, value (optionally restricted to ``chrom:start-end``)."""
    from uchrom.fea.distance import radius_of_gyration

    chrom, start, end = _validate_window(chrom, start, end)
    df = cd.to_dataframe()
    if len(df):
        df = df[np.isfinite(df[["x", "y", "z"]].to_numpy(float)).all(axis=1)]
    df = _filter_spots_window(df, chrom, start, end)
    if not len(df):
        return pd.DataFrame(columns=["cell_id", "value"])
    if stat in ("rg", "span") and not equalize:
        counts = df.groupby("trace_id", observed=True).size()
        df = df[df["trace_id"].isin(counts.index[counts >= 2])]
        if not len(df):
            return pd.DataFrame(columns=["cell_id", "value"])
    if equalize and stat in ("rg", "span"):
        v = _equalized(df, stat, max(2, int(equalize)), draws, seed)
    elif stat == "n_spots":
        v = df.groupby("trace_id", observed=True).size().astype(float)
    elif stat == "rg":
        v = radius_of_gyration(df)
    elif stat == "span":
        g = df.sort_values("start").groupby("trace_id", observed=True)
        v = g.apply(
            lambda t: float(np.linalg.norm(t[["x", "y", "z"]].iloc[-1].to_numpy() - t[["x", "y", "z"]].iloc[0].to_numpy())),
            include_groups=False,
        )
    else:
        raise ValueError(f"unknown per-trace stat {stat!r}")
    if not len(v):
        return pd.DataFrame(columns=["cell_id", "value"])
    cell_col = "cell_id" if "cell_id" in df.columns else "trace_id"
    cell = df.groupby("trace_id", observed=True)[cell_col].first().astype(str)
    return pd.DataFrame({"cell_id": cell.reindex(v.index).to_numpy(), "value": v.to_numpy()}).dropna()


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


def _embedded_contact_stats(e, cells: list[str], chrom: str | None, start: int | None, end: int | None, smin: float | None, smax: float | None) -> pd.DataFrame:
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

    cell_pos = {str(c): i for i, c in enumerate(e.cells)}
    req = [(str(c), cell_pos[str(c)]) for c in cells if str(c) in cell_pos]
    order = np.unique([idx for _, idx in req]).astype(np.int64)
    cis_acc = {int(ci): 0.0 for ci in order}
    k_acc: dict[int, list[np.ndarray]] = {int(ci): [] for ci in order}
    c_acc: dict[int, list[np.ndarray]] = {int(ci): [] for ci in order}

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

    rows = {
        ci: _diag_metrics(k_acc[ci], c_acc[ci], cis_acc[ci], r, n_pairs, k_min, k_max)
        for ci in order
    }
    data = [rows[idx] for _, idx in req]
    return pd.DataFrame(data, index=pd.Index([cid for cid, _ in req], dtype=object),
                        columns=list(CONTACT_STATS)) if req else pd.DataFrame(columns=list(CONTACT_STATS))


def _scool_binsize(f, b_chrom: np.ndarray, b_start: np.ndarray, b_end: np.ndarray) -> int:
    for holder in (f,):
        bs = holder.attrs.get("bin-size")
        if bs is not None and not isinstance(bs, (bool, bytes, str)) and int(bs) > 0:
            return int(bs)
    cells_grp = f.get("cells")
    if cells_grp and len(cells_grp):
        first_key = next(iter(cells_grp.keys()))
        bs = cells_grp[first_key].attrs.get("bin-size")
        if bs is not None and not isinstance(bs, (bool, bytes, str)) and int(bs) > 0:
            return int(bs)
    diffs = (b_end - b_start).astype(np.int64)
    if len(b_chrom) > 1:
        non_last = np.r_[b_chrom[:-1] == b_chrom[1:], False]
        inner = diffs[non_last & (diffs > 0)]
        if len(inner):
            return int(np.median(inner))
    pos = diffs[diffs > 0]
    return int(np.median(pos)) if len(pos) else 1


def _scool_contact_stats(path: Path, cells: list[str], chrom: str | None, start: int | None, end: int | None, smin: float | None, smax: float | None) -> pd.DataFrame:
    import h5py

    with h5py.File(path, "r") as f:
        chroms = [x.decode() if isinstance(x, (bytes, np.bytes_)) else str(x) for x in f["chroms/name"][:]]
        b_chrom = np.asarray(f["bins/chrom"][:], dtype=np.int64)
        b_start = np.asarray(f["bins/start"][:], dtype=np.int64)
        b_end = np.asarray(f["bins/end"][:], dtype=np.int64)
        r = _scool_binsize(f, b_chrom, b_start, b_end)
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
            counts_c = [int((b_chrom == ci).sum()) for ci in range(len(chroms))]
            n_pairs = _n_pairs_array(counts_c)
        k_min, k_max = _diag_bounds(len(n_pairs), r, smin, smax)

        avail = set(f["cells"].keys())
        kept, rows = [], []
        for cid in cells:
            scid = str(cid)
            if scid not in avail:
                continue
            kept.append(scid)
            grp = f["cells"][scid]
            px = grp["pixels"]
            if chrom is not None:
                if g_b1 <= g_b0:
                    rows.append(_diag_metrics([], [], 0.0, r, n_pairs, k_min, k_max))
                    continue
                boff = grp["indexes/bin1_offset"]
                p_lo, p_hi = int(boff[g_b0]), int(boff[g_b1])
                if p_hi <= p_lo:
                    rows.append(_diag_metrics([], [], 0.0, r, n_pairs, k_min, k_max))
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
                rows.append(_diag_metrics([], [], 0.0, r, n_pairs, k_min, k_max))
                continue
            p1, p2, cnt = p1[m], p2[m], cnt[m]
            cis_total = float(cnt.sum())
            kk = p2 - p1
            km = (kk >= k_min) & (kk <= k_max)
            rows.append(_diag_metrics([kk[km]] if km.any() else [], [cnt[km]] if km.any() else [], cis_total, r, n_pairs, k_min, k_max))
    return pd.DataFrame(rows, index=pd.Index(kept, dtype=object), columns=list(CONTACT_STATS)) if kept else pd.DataFrame(columns=list(CONTACT_STATS))


def _contact_stats(
    cd,
    cells: list[str],
    *,
    cool: str | None = None,
    chrom: str | None = None,
    start: int | None = None,
    end: int | None = None,
    smin: float | None = None,
    smax: float | None = None,
) -> pd.DataFrame:
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
        return _embedded_contact_stats(e, cells, chrom, start, end, smin, smax)

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
    return _scool_contact_stats(p, cells, chrom, start, end, smin, smax)


# ------------------------------------------------------------------ multi-way cluster metrics
def _parse_cluster_spec(spec: str) -> tuple[str, str]:
    parts = spec.split(":")
    if len(parts) < 3 or parts[0] != "clusters":
        raise ValueError(f"invalid cluster stat {spec!r}; expected clusters:<key>:<metric>")
    key, metric = ":".join(parts[1:-1]), parts[-1]
    if metric not in CLUSTER_METRICS:
        raise ValueError(f"unknown cluster metric {metric!r}; expected one of {CLUSTER_METRICS}")
    return key, metric


def _cluster_stats(
    cd,
    key: str,
    metric: str,
    cells: list[str],
    chrom: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> pd.Series:
    chrom, start, end = _validate_window(chrom, start, end)
    if key not in cd.clusters:
        raise KeyError(f"no clusters[{key!r}] in ChromData")
    t = cd.clusters[key]
    if t.kind != "per_cell" or t.cells is None:
        raise ValueError(f"clusters[{key!r}] is a bulk table (no cells)")
    want = [str(c) for c in cells]
    if chrom is not None:
        if chrom not in t.chroms:
            s = pd.Series(0.0 if metric == "n_clusters" else np.nan, index=t.cells, dtype=float)
            return s.reindex(want).dropna()
        lo = max(0, int(start or 0))
        hi = int(end) if end is not None else (1 << 60)
        keep_cells = [c for c in want if c in set(t.cells)]
        df = t.region(chrom, lo, hi, cells=keep_cells) if keep_cells else t.region(chrom, 0, 0)
        u = df.drop_duplicates("cluster")
        if metric == "n_clusters":
            s = u.groupby("cell_id", observed=True).size().reindex(keep_cells, fill_value=0).astype(float)
            return s.reindex(want).dropna()
        if metric == "median_size":
            s = u.groupby("cell_id", observed=True)["size"].median().astype(float)
        else:
            u = u.assign(_cis=(u["chrom_size"] == u["size"]).astype(float))
            s = u.groupby("cell_id", observed=True)["_cis"].mean().astype(float)
        return s.reindex(want).dropna()

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
    return pd.Series(vals, index=t.cells, dtype=float).reindex(want).dropna()


def per_cell(
    cd,
    stat: str,
    cells: list,
    equalize: int | None = None,
    chrom: str | None = None,
    start: int | None = None,
    end: int | None = None,
    cool: str | None = None,
    smin: float | None = None,
    smax: float | None = None,
) -> pd.Series:
    """One value per cell (median over its traces, contact stat, cluster stat, or cells column)."""
    if stat in TRACE_STATS:
        sub = cd.get_cells(cells) if "cell_id" in cd.spots.columns else cd
        t = per_trace(sub, stat, equalize, chrom=chrom, start=start, end=end)
        return t.groupby("cell_id")["value"].median()
    if stat in CONTACT_STATS:
        df = _contact_stats(cd, [str(c) for c in cells], cool=cool, chrom=chrom, start=start, end=end, smin=smin, smax=smax)
        return df[stat].dropna()
    if stat.startswith("clusters:"):
        key, metric = _parse_cluster_spec(stat)
        return _cluster_stats(cd, key, metric, [str(c) for c in cells], chrom=chrom, start=start, end=end)
    col = cd.cells
    ids = col.index.astype(str) if "cell_id" not in col else col["cell_id"].astype(str)
    s = pd.Series(pd.to_numeric(col[stat], errors="coerce").to_numpy(), index=ids)
    return s.reindex([str(c) for c in cells]).dropna()


def _raw_explicit_ids(spec) -> list[str] | None:
    if isinstance(spec, str):
        if spec in ("all", "rest") or spec.startswith("field:"):
            return None
        return [s for s in spec.split(",") if s]
    return [str(c) for c in spec]


def compare(
    cd,
    a,
    b,
    stat: str = "rg",
    confounder: str | None = "nuc_volume_um3",
    equalize: int | None = None,
    chrom: str | None = None,
    start: int | None = None,
    end: int | None = None,
    cool: str | None = None,
    smin: float | None = None,
    smax: float | None = None,
) -> dict:
    a_raw, b_raw = _raw_explicit_ids(a), _raw_explicit_ids(b)
    a_ids = resolve_group(cd, a)
    b_ids = resolve_group(cd, b, other=a_ids)
    overlap = sorted(set(a_ids) & set(b_ids))
    eq_k = max(2, int(equalize)) if (equalize and stat in ("rg", "span")) else None
    if stat in CONTACT_STATS:
        ca_df = _contact_stats(cd, a_ids, cool=cool, chrom=chrom, start=start, end=end, smin=smin, smax=smax)
        cb_df = _contact_stats(cd, b_ids, cool=cool, chrom=chrom, start=start, end=end, smin=smin, smax=smax)
        va, vb = ca_df[stat].dropna(), cb_df[stat].dropna()
    else:
        ca_df = cb_df = None
        va = per_cell(cd, stat, a_ids, eq_k, chrom=chrom, start=start, end=end)
        vb = per_cell(cd, stat, b_ids, eq_k, chrom=chrom, start=start, end=end)
    res = {
        "stat": stat,
        "unit": "cell (median over its traces)" if stat in TRACE_STATS else "cell",
        "a": {"n_cells": int(len(va)), "median": float(np.median(va)) if len(va) else None},
        "b": {"n_cells": int(len(vb)), "median": float(np.median(vb)) if len(vb) else None},
        "checks": [],
    }
    if a_raw is not None and len(a_raw) != len(a_ids):
        res["checks"].append(f"duplicate cell IDs in group 'a' collapsed ({len(a_raw)} -> {len(a_ids)})")
    if b_raw is not None and len(b_raw) != len(b_ids):
        res["checks"].append(f"duplicate cell IDs in group 'b' collapsed ({len(b_raw)} -> {len(b_ids)})")
    if chrom is not None:
        res["window"] = {"chrom": chrom, "start": start, "end": end}
    if stat in ("rg", "span"):
        res["value_unit"] = str(cd.uns.get("xyz_unit", "unknown (no uns['xyz_unit'])"))
    if stat == "span" and cd.uns.get("trace_kind") == "set":
        res["checks"].append(
            "trace_kind is 'set' (unordered spots, not a polymer path); end-to-end span is not meaningful — prefer rg"
        )
    if eq_k is not None:
        res["equalized_loci_per_trace"] = eq_k
        res["checks"].append(
            f"{stat} recomputed on {eq_k} random loci per trace (mean of 20 draws); traces "
            "with fewer loci dropped — report the equalized medians next to the raw ones"
        )
    if stat in TRACE_STATS:
        sub_a = cd.get_cells(a_ids) if "cell_id" in cd.spots.columns else cd
        sub_b = cd.get_cells(b_ids) if "cell_id" in cd.spots.columns else cd
        ta = per_trace(sub_a, stat, eq_k, chrom=chrom, start=start, end=end)
        tb = per_trace(sub_b, stat, eq_k, chrom=chrom, start=start, end=end)
        res["a"]["n_traces"], res["b"]["n_traces"] = int(len(ta)), int(len(tb))
        res["a"]["median_over_traces"] = float(ta["value"].median()) if len(ta) else None
        res["b"]["median_over_traces"] = float(tb["value"].median()) if len(tb) else None
    if overlap:
        res["checks"].append(f"groups overlap in {len(overlap)} cells; compare disjoint groups")
    if min(len(va), len(vb)) < MIN_CELLS:
        res["checks"].append(
            f"fewer than {MIN_CELLS} cells in a group (a: {len(va)}, b: {len(vb)}); "
            "report as exploratory, no p-value claims"
        )
    if len(va) >= 2 and len(vb) >= 2:
        u = st.mannwhitneyu(va, vb, alternative="two-sided")
        res["test"] = {"name": "Mann–Whitney U on per-cell values", "U": float(u.statistic), "p": float(u.pvalue)}
        # rank-biserial r = 2U/(n_a n_b) - 1: +1 when every a cell exceeds every b cell
        res["effect"] = {
            "rank_biserial": float(2 * u.statistic / (len(va) * len(vb)) - 1),
            "median_ratio": float(np.median(va) / np.median(vb)) if np.median(vb) else None,
        }
    if ca_df is not None and stat in ("ps_slope", "contact_density"):
        cis_a = ca_df["cis_contacts"].reindex(va.index).dropna()
        cis_b = cb_df["cis_contacts"].reindex(vb.index).dropna()
        ma = float(np.median(cis_a)) if len(cis_a) else None
        mb = float(np.median(cis_b)) if len(cis_b) else None
        res["a"]["median_cis_contacts"] = ma
        res["b"]["median_cis_contacts"] = mb
        res["cis_contacts"] = {"a_median": ma, "b_median": mb}
        both_v = pd.concat([va, vb])
        both_c = pd.concat([cis_a, cis_b])
        common = both_v.index.intersection(both_c.index)
        if len(common) >= 5 and both_v[common].nunique() > 1 and both_c[common].nunique() > 1:
            rho = st.spearmanr(both_v[common], both_c[common])
            res["depth_confounder"] = {"field": "cis_contacts", "spearman_rho": float(rho.statistic), "p": float(rho.pvalue)}
            if np.isfinite(rho.statistic) and abs(rho.statistic) > 0.5:
                res["checks"].append(
                    f"{stat} tracks cis_contacts (depth) across cells (rho {rho.statistic:.2f}); "
                    "the difference may reflect sequencing depth, not folding"
                )
        if (ma is not None and ma < 1000) or (mb is not None and mb < 1000):
            res["checks"].append(
                f"sparse single-cell contact maps (median cis_contacts: a={ma}, b={mb}); per-cell estimates are noisy"
            )
    if confounder and cd.cells is not None and confounder in cd.cells.columns and confounder != stat:
        both = pd.concat([va, vb])
        conf = per_cell(cd, confounder, list(both.index))
        common = both.index.intersection(conf.index)
        if len(common) >= 5 and both[common].nunique() > 1 and conf[common].nunique() > 1:
            rho = st.spearmanr(both[common], conf[common])
            res["confounder"] = {"field": confounder, "spearman_rho": float(rho.statistic), "p": float(rho.pvalue)}
            if abs(rho.statistic) > 0.5:
                res["checks"].append(
                    f"{stat} tracks {confounder} across cells (rho {rho.statistic:.2f}); "
                    "the difference may reflect nuclear size, not the group"
                )
    if stat in ("rg", "span") and not equalize:
        na = per_cell(cd, "n_spots", a_ids, chrom=chrom, start=start, end=end)
        nb = per_cell(cd, "n_spots", b_ids, chrom=chrom, start=start, end=end)
        if len(na) and len(nb):
            ma, mb = float(np.median(na)), float(np.median(nb))
            res["spots_per_trace"] = {"a_median_of_cells": ma, "b_median_of_cells": mb}
            if max(ma, mb) > 1.3 * min(ma, mb):
                res["checks"].append(
                    f"spots per trace differ (median per cell {ma:.0f} vs {mb:.0f}); {stat} depends "
                    f"on how many loci are detected — rerun with equalize=k (k ≈ the smaller "
                    "group's lower quartile of spots per trace) and report both"
                )
    if cd.cells is not None and len(cd.cells):
        c_ids = cd.cells.index.astype(str) if "cell_id" not in cd.cells else cd.cells["cell_id"].astype(str)
        sel = c_ids.isin(set(a_ids) | set(b_ids))
        for col in ("fov", "field_of_view", "region", "batch", "replicate", "sample"):
            if col in cd.cells.columns:
                vals = cd.cells.loc[sel, col]
                if vals.nunique() <= 1:
                    res["checks"].append(
                        f"all cells share one {col} ({vals.iloc[0] if len(vals) else '?'}); "
                        "no replicate — say so"
                    )
                    break
    return res


def _bh(p):
    p = np.asarray(p, float)
    n = len(p)
    o = np.argsort(p)
    q = p[o] * n / (np.arange(n) + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty(n)
    out[o] = np.clip(q, 0, 1)
    return out


def scan(cd, a, b, columns="", top: int = 10) -> dict:
    """Compare every numeric cells column (starting with ``columns``, a prefix like 'if.'; or a list) between
    groups, per cell, Mann–Whitney + rank-biserial, BH-FDR across columns; plus categorical composition."""
    a_ids = resolve_group(cd, a)
    b_ids = resolve_group(cd, b, other=a_ids)
    cells = cd.cells
    ids = cells.index.astype(str) if "cell_id" not in cells else cells["cell_id"].astype(str)
    ia, ib = ids.isin(a_ids), ids.isin(b_ids)
    if isinstance(columns, str):
        cols = [c for c in cells.columns if str(c).startswith(columns)]
    else:
        cols = list(columns)
    rows = []
    for c in cols:
        x = pd.to_numeric(cells[c], errors="coerce")
        if x.notna().sum() < 4:
            continue
        va, vb = x[ia].dropna(), x[ib].dropna()
        if len(va) < 2 or len(vb) < 2 or (va.nunique() == 1 and vb.nunique() == 1 and va.iloc[0] == vb.iloc[0]):
            continue
        u = st.mannwhitneyu(va, vb, alternative="two-sided")
        rows.append(
            {
                "field": str(c),
                "median_a": float(va.median()),
                "median_b": float(vb.median()),
                "rank_biserial": float(2 * u.statistic / (len(va) * len(vb)) - 1),
                "p": float(u.pvalue),
            }
        )
    df = pd.DataFrame(rows)
    res = {
        "unit": "cell",
        "n_a": int(ia.sum()),
        "n_b": int(ib.sum()),
        "n_fields_tested": int(len(df)),
        "correction": "Benjamini–Hochberg FDR across all fields tested",
        "checks": [],
    }
    if len(df):
        df["q"] = _bh(df["p"].to_numpy())
        # most significant first; ties (common with small n) broken by the larger effect
        df = df.iloc[np.lexsort((-df["rank_biserial"].abs().to_numpy(), df["p"].to_numpy()))].reset_index(drop=True)
        res["top"] = df.head(top).to_dict("records")
        res["n_q_below_0.05"] = int((df["q"] < 0.05).sum())
        if not (df["q"] < 0.05).any():
            res["checks"].append("no field passes FDR 0.05: report the top fields as candidates only")
    comp = {}
    for c in cells.columns:
        if (cells[c].dtype == object or str(cells[c].dtype) in ("category", "str", "string")) and 1 < cells[c].nunique() <= 30:
            ca, cb = cells.loc[ia, c].astype(str).value_counts(), cells.loc[ib, c].astype(str).value_counts()
            comp[str(c)] = {"a": ca.to_dict(), "b": cb.to_dict()}
            top_a = ca.index[0] if len(ca) else None
            if top_a is not None:
                tab = [
                    [int(ca.get(top_a, 0)), int(ca.sum() - ca.get(top_a, 0))],
                    [int(cb.get(top_a, 0)), int(cb.sum() - cb.get(top_a, 0))],
                ]
                comp[str(c)]["enrichment"] = {
                    "value": top_a,
                    "frac_a": tab[0][0] / max(1, sum(tab[0])),
                    "frac_b": tab[1][0] / max(1, sum(tab[1])),
                    "fisher_p": float(st.fisher_exact(tab)[1]),
                }
    res["composition"] = comp
    if min(ia.sum(), ib.sum()) < MIN_CELLS:
        res["checks"].append(f"fewer than {MIN_CELLS} cells in a group: exploratory")
    return res


def _json_safe(obj):
    import math

    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        val = float(obj)
        return val if math.isfinite(val) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("data")
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--stat", default="rg")
    ap.add_argument("--confounder", default="nuc_volume_um3")
    ap.add_argument("--equalize", type=int, default=None, help="recompute rg/span on k random loci per trace")
    ap.add_argument("--chrom", default=None)
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--cool", default=None, help="embedded/linked_scool contact map key")
    ap.add_argument("--smin", type=float, default=None)
    ap.add_argument("--smax", type=float, default=None)
    ap.add_argument("--scan", default=None, help="compare every cells column with this prefix ('' = all), BH-FDR")
    a = ap.parse_args()
    from chromdata import ChromData

    cd = ChromData.read(a.data, backed=True)
    out = (
        scan(cd, a.a, a.b, a.scan)
        if a.scan is not None
        else compare(
            cd,
            a.a,
            a.b,
            a.stat,
            a.confounder,
            a.equalize,
            chrom=a.chrom,
            start=a.start,
            end=a.end,
            cool=a.cool,
            smin=a.smin,
            smax=a.smax,
        )
    )
    json.dump(_json_safe(out), sys.stdout, indent=1, allow_nan=False)
    print()


if __name__ == "__main__":
    main()
