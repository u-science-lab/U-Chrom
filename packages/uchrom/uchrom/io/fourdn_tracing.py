"""Chromatin tracing deposited in the 4DN Data Portal as FOF-CT tables, several experiments in one ``ChromData``.

A 4DN chromatin-tracing experiment is a FOF-CT *core* table (one row per spot: ``Spot_ID``, ``Trace_ID``, ``X``,
``Y``, ``Z``, ``Chrom``, ``Chrom_Start``, ``Chrom_End``, sometimes ``Cell_ID``) with optional companions keyed by
its ids: *spot quality* (``Spot_ID`` + ``Brightness``, fit widths, drift, ...), *trace data* (``Trace_ID`` + the
cell-cycle stage, field of view, ...) and *cell data* (``Cell_ID`` + RNA counts, tissue / embryo ids, or
``Trace_ID`` + ``Cell_ID`` + nuclear measurements).  A study is many such experiments (conditions, regions,
replicates); :func:`read_4dn_tracing` reads them into one object, the ids prefixed by the experiment.

Some deposits state ``XYZ_unit=micron`` for coordinates in nm (Hafner et al. 2023, Murphy & Boettiger 2024:
``X`` of ~10,000 for neighbouring loci 5 kb apart).  The unit is taken from the spacing of the traces instead:
the median distance between successive loci of a trace is 0.05-1 µm in chromatin tracing, so a median above 20
in a file that says micron means nm (and below 0.02 in one that says nm means µm).  Each such correction is
recorded in ``uns["fofct_unit_fixes"]``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Mapping, Optional

import numpy as np
import pandas as pd

__all__ = ["read_4dn_tracing"]

_TO_MICRON = {"micron": 1.0, "um": 1.0, "µm": 1.0, "micrometer": 1.0, "nm": 1e-3, "nanometer": 1e-3, "mm": 1e3}


#: the columns of the FOF-CT core table (normalised)
_CORE = {"spot_id", "trace_id", "x", "y", "z", "chrom", "chrom_start", "chrom_end", "cell_id", "extracellroiid",
         "subcellroiid"}
_IDS = {"spot_id": "Spot_ID", "trace_id": "Trace_ID", "cell_id": "Cell_ID"}


def _norm(name) -> str:
    """``Spot_ID`` / ``spotID`` / ``spot_ID`` -> ``spot_id``, ``chr_start`` -> ``chrom_start``, ``FOVid`` -> ``fov``
    (the deposits spell the columns several ways)."""
    k = re.sub(r"[\s_]", "", str(name).strip().lower())
    return {"spotid": "spot_id", "traceid": "trace_id", "cellid": "cell_id", "chromstart": "chrom_start",
            "chromend": "chrom_end", "chr": "chrom", "chrstart": "chrom_start", "chrend": "chrom_end",
            "fovid": "fov"}.get(k, k)


def _cols(df: pd.DataFrame) -> dict:
    """normalised column name (:func:`_norm`) -> the file's name"""
    return {_norm(c): c for c in df.columns}


def _declared_value(path) -> str:
    """The text of a table's ``##columns=`` line ("" without one)."""
    with open(path) as fh:
        for line in fh:
            t = line.strip().rstrip(",").strip().strip('"')
            if t.lower().startswith("##columns="):
                return t.split("=", 1)[1].strip()
            if t and not t.startswith("#"):
                break
    return ""


def _declared_columns(path) -> list:
    """The names of a table's ``##columns=(...)`` line ([] without one)."""
    v = _declared_value(path)
    if not v:
        return []
    return [x.strip() for x in (v[1:-1] if v.startswith("(") and v.endswith(")") else v).split(",")]


def _locus_columns_ok(df: pd.DataFrame) -> bool:
    c = _cols(df)
    if not {"chrom", "chrom_start", "chrom_end", "x", "y", "z"} <= set(c):
        return False
    chrom = df[c["chrom"]].dropna().astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    chrom = chrom[chrom != ""]
    if not len(chrom) or not (pd.api.types.is_numeric_dtype(df[c["chrom_start"]])
                              and pd.api.types.is_numeric_dtype(df[c["chrom_end"]])):
        return False
    # chromosome names: "chr3R", "3R", "X", or a number of one or two digits ("19": Liu et al. 2020), and loci that
    # are integer intervals — not coordinates or ids moved into the wrong columns
    named = chrom.str.fullmatch(r"(chr)?[0-9]{1,2}[A-Za-z]{0,2}|(chr)?[A-Za-z][0-9A-Za-z_]{0,7}")
    rows = df[c["chrom"]].notna()
    start, end = df.loc[rows, c["chrom_start"]].astype(float), df.loc[rows, c["chrom_end"]].astype(float)
    integer = ((start == start.round()) & (end == end.round())).mean()
    ordered = (end > start).mean()          # most loci: some deposits have a few with end <= start (Huang 2021: 2.4 %)
    return bool(named.mean() > 0.99 and integer > 0.99 and ordered > 0.9)


def _fix_columns(df: pd.DataFrame, path, name: str, fixes: list) -> pd.DataFrame:
    """A core table whose ``##columns`` line names one column more or one less than its rows have (Hafner et al.
    2023 declare ``X, Y, Z,R,Chrom, ...`` over rows without an R, and ``X, Y, Z, Chrom_Start, ...`` over rows with
    the chromosome): the reader labels the columns from the left and the loci come out shifted.  Drop the one name
    that makes the locus columns parse (a chromosome name, integer positions) and is not a core column, or insert
    the one missing core name that does; refuse when none or several do."""
    if _locus_columns_ok(df):
        return df
    names = _declared_columns(path)
    good = []
    if len(names) == len(df.columns) + 1:              # a name without a column
        for i in range(len(names)):
            cand = df.set_axis(names[:i] + names[i + 1:], axis=1)
            if _locus_columns_ok(cand):
                good.append((f"dropped {names[i]}", cand))
        if len(good) > 1:                # shifting X / Y / Z parses too: drop a name the core format does not have
            good = [g for g in good if _norm(g[0].split(" ", 1)[1]) not in _CORE]
    elif len(names) == len(df.columns) - 1:            # a core column left out of the names (Hafner: no Chrom)
        have = {_norm(n) for n in names}
        for miss in [n for n in ("Chrom", "Chrom_Start", "Chrom_End", "Trace_ID", "Spot_ID") if _norm(n) not in have]:
            for i in range(len(names) + 1):
                cand = df.set_axis(names[:i] + [miss] + names[i:], axis=1)
                if _locus_columns_ok(cand):
                    good.append((f"inserted {miss}", cand))
    else:
        raise ValueError(f"{name}: the locus columns of {Path(path).name} do not parse (columns {list(df.columns)})")
    if len(good) > 1:                    # an id column can pass for a numbered chromosome: prefer named ones
        def worded(cand):
            ch = cand[_cols(cand)["chrom"]].dropna().astype(str)
            return pd.to_numeric(ch, errors="coerce").isna().mean() > 0.5
        good = [g for g in good if worded(g[1])] or good
    if len(good) != 1:
        raise ValueError(f"{name}: {Path(path).name} declares {names} over {len(df.columns)} columns; "
                         f"{len(good)} relabellings make the loci parse")
    fixes.append({"experiment": name, "declared": names, "fix": good[0][0]})
    return good[0][1]


def _median_step(df: pd.DataFrame, c: dict) -> float:
    """Median distance between successive loci of the traces (file units)."""
    t = df[[c["trace_id"], c["chrom"], c["chrom_start"], c["x"], c["y"], c["z"]]].dropna()
    t = t.sort_values([c["trace_id"], c["chrom"], c["chrom_start"]], kind="stable")
    xyz = t[[c["x"], c["y"], c["z"]]].to_numpy(float)
    same = (t[c["trace_id"]].to_numpy()[1:] == t[c["trace_id"]].to_numpy()[:-1])
    d = np.linalg.norm(np.diff(xyz, axis=0), axis=1)[same]
    return float(np.median(d)) if len(d) else float("nan")


def _scale(header: Mapping[str, str], step: float, name: str, fixes: list) -> float:
    """Factor to µm of a core table, from its ``XYZ_unit`` checked against the trace spacing."""
    stated = str({k.lower(): v for k, v in header.items()}.get("xyz_unit", "micron")).strip().lower()
    if stated not in _TO_MICRON:
        raise ValueError(f"{name}: unknown XYZ_unit {stated!r}")
    scale = _TO_MICRON[stated]
    if np.isfinite(step):
        if scale == 1.0 and step > 20:
            fixes.append({"experiment": name, "stated": stated, "used": "nm", "median_step": step})
            scale = 1e-3
        elif scale == 1e-3 and step < 0.02:
            fixes.append({"experiment": name, "stated": stated, "used": "micron", "median_step": step})
            scale = 1.0
    return scale


def _table(path) -> pd.DataFrame:
    """A companion table with its id columns named ``Spot_ID`` / ``Trace_ID`` / ``Cell_ID``, however the file spells
    them, and the names of a malformed ``##columns`` line taken from after its ``(...)`` (Hafner et al. 2023:
    ``(Trace_ID, Cell_ID, Geminin)Trace_ID,Cell_ID,Mean_Geminin,Nuclear_Size``)."""
    from chromdata import read_fofct_table

    df, _ = read_fofct_table(path)
    v = _declared_value(path)
    if ")" in v[:-1]:
        tail = [x.strip() for x in v.rsplit(")", 1)[1].split(",")]
        if len(tail) == len(df.columns):
            df = df.set_axis(tail, axis=1)
    df = df.rename(columns={c: _IDS[_norm(c)] for c in df.columns if _norm(c) in _IDS})
    df.columns = [str(x).strip() for x in df.columns]
    if df.columns.duplicated().any():
        raise ValueError(f"{Path(path).name}: repeated column names {list(df.columns)}")
    return df


def _companion(path, key: str, name: str) -> pd.DataFrame:
    """A companion table (:func:`_table`) indexed by its ``key`` column."""
    df = _table(path)
    if key not in df.columns:
        raise ValueError(f"{name}: {Path(path).name} has no {key} column (columns {list(df.columns)})")
    return df.drop_duplicates(key).set_index(key)


def _split_reused_traces(df: pd.DataFrame, c: dict):
    """Rows repeated exactly (same trace, locus and position: Mateo et al. 2019 list some traces twice) dropped,
    and a ``Trace_ID`` that comes back in a later block of rows split into one trace per block — the ids are
    numbered per field of view in some deposits (Murphy & Boettiger 2024: the blocks of one id lie ~100 µm
    apart).  Rows of one trace repeating a locus within a block (several fits ~0.1 µm apart) are kept.  A table
    not grouped by trace (most ids in several blocks) is left as it is.  Returns the rows (``Trace_ID`` of the
    second and later blocks suffixed ``.b<k>``) and counts."""
    t = df[c["trace_id"]].astype(str)
    block = (t != t.shift()).cumsum()
    key = [c["trace_id"], c["chrom"], c["chrom_start"], c["x"], c["y"], c["z"]]
    dup = df.duplicated(key)
    df, t, block = df[~dup].reset_index(drop=True), t[~dup].reset_index(drop=True), block[~dup].reset_index(drop=True)
    rank = block.groupby(t).rank(method="dense").astype(int)
    n_ids = t.nunique()
    reused = int(t[rank > 1].nunique())
    out = {"duplicate_rows": int(dup.sum()), "split_traces": 0, "traces": n_ids}
    if reused and reused <= n_ids / 2:
        new = t.where(rank == 1, t + ".b" + rank.astype(str))
        df = df.assign(**{c["trace_id"]: new.to_numpy(dtype=object)})
        out["split_traces"] = reused
    return df, out


def _as_list(v) -> list:
    return [] if not v else list(v) if isinstance(v, (list, tuple)) else [v]


def _tidy(df: pd.DataFrame, category: bool = False) -> pd.DataFrame:
    """Text columns of tables concatenated over experiments as text: one experiment's ``Tissue_ID`` can be numbers
    and another's ``"A1"`` (Mateo et al. 2019), which a Parquet column cannot hold; repeated text values (condition,
    biosample) as categories."""
    for col in df.columns:
        if df[col].dtype == object:
            v = df[col]
            df[col] = v.where(v.isna(), v.astype(str))
            if category:
                df[col] = df[col].astype("category")
    return df


def read_4dn_tracing(experiments: Iterable[Mapping], *, genome_assembly: Optional[str] = None):
    """Read 4DN FOF-CT chromatin-tracing experiments into one ``ChromData`` (coordinates in µm).

    Parameters
    ----------
    experiments : iterable of mappings
        One per experiment: ``name`` (prefix of its ids), ``core`` (the core table, or a list of them — their
        trace ids prefixed ``c<k>-``, ``traces["core_file"]`` naming the table) and optionally ``spot_quality`` /
        ``spot_bio`` (one or several tables keyed by ``Spot_ID``), ``trace_data``, ``cell_data`` (companion
        tables), ``meta`` (a mapping of values given
        to each of its cells, e.g. the experiment set, condition and biosample) and ``locus_shifts`` (``(chrom,
        start_from, start_to, offset)``: loci whose start lies in the range moved by ``offset`` bp — a correction
        the caller knows from the authors, recorded in ``uns["fofct_locus_shifts"]``).
    genome_assembly : str, optional
        Recorded in ``uns``; default: the ``genome_assembly`` of the core tables' headers (they must agree).

    Returns
    -------
    ChromData
        ``spots``: one per detected spot (rows without coordinates or without a locus — an empty ``Chrom``, as
        the unassigned spots of Hafner et al. 2023 — left out, counted in ``uns["fofct_dropped_spots"]``), ``trace_id = "<name>_<Trace_ID>"``,
        ``cell_id = "<name>_<Cell_ID>"`` where the experiment gives cells (in the core, or in a cell table keyed
        by trace), ``"<name>_<FOV>-<Cell_ID>"`` where its spots (core column ``FOVid`` / ``FOV``) or traces have a
        field of view (the authors number cells per field; ``"<name>_<run>-<FOV>-<Cell_ID>"`` where the core also
        has the imaging run, ``Dataset ID``, fields being numbered per run), else — and for ``Cell_ID`` 0, a trace in no cell — ``"<name>_t<Trace_ID>"`` (one cell per
        trace); ``spot_tracks``: the spot-quality columns; ``traces``: ``experiment``, the trace-data columns and
        per-trace cell values; ``cells``: ``experiment``, the ``meta`` values and the cell-data columns.
        ``uns``: ``genome_assembly``, ``xyz_unit`` (``micron``), ``fofct_headers`` (per experiment),
        ``fofct_unit_fixes``, ``fofct_dropped_spots`` (also exact duplicate rows), ``fofct_trace_splits`` (ids reused
        for several traces: :func:`_split_reused_traces`), ``fofct_column_fixes`` (core tables whose declared columns
        were one too many or one too few: :func:`_fix_columns`), ``fofct_chrom_renames`` (chromosome names
        given the UCSC ``chr`` prefix: ``3R`` -> ``chr3R``, ``19`` -> ``chr19``, ``Chr14`` -> ``chr14``).
    """
    from chromdata import ChromData, read_fofct_table

    coords, spots, spot_tracks, traces, cells = [], [], [], [], []
    headers, fixes, assemblies, dropped, column_fixes, trace_splits, shifts = {}, [], set(), {}, [], {}, {}
    for exp in experiments:
        name = str(exp["name"])
        cores = list(exp["core"]) if isinstance(exp["core"], (list, tuple)) else [exp["core"]]
        parts = []
        dropped[name] = {"no_coordinates": 0, "no_locus": 0, "duplicate_rows": 0}
        for k, core in enumerate(cores):          # an experiment may have several core tables (Takei 2021: 1 Mb, 25 kb)
            label = name if len(cores) == 1 else f"{name}:{Path(core).stem}"
            df, header = read_fofct_table(core)
            headers.setdefault(name, header)
            df = _fix_columns(df, core, label, column_fixes)
            c = _cols(df)
            need = ["spot_id", "trace_id", "x", "y", "z", "chrom", "chrom_start", "chrom_end"]
            missing = [x for x in need if x not in c]
            if missing:
                raise ValueError(f"{label}: core table without {missing} (columns {list(df.columns)})")
            hdr = {x.lower(): v for x, v in header.items()}
            if "genome_assembly" in hdr:
                assemblies.add(hdr["genome_assembly"].strip())
            scale = _scale(header, _median_step(df, c), label, fixes)
            placed = df[c["chrom"]].notna() & (df[c["chrom"]].astype(str).str.strip() != "")
            has_xyz = df[[c["x"], c["y"], c["z"]]].notna().all(axis=1)
            dropped[name]["no_coordinates"] += int((~has_xyz).sum())
            dropped[name]["no_locus"] += int((~placed).sum())
            df = df[has_xyz & placed].reset_index(drop=True)
            df, split = _split_reused_traces(df, c)
            dropped[name]["duplicate_rows"] += split.pop("duplicate_rows")
            if split["split_traces"]:
                trace_splits[label] = split
            std = pd.DataFrame({"spot_id": df[c["spot_id"]].astype(str).str.replace(r"\.0$", "", regex=True),
                                "trace_id": df[c["trace_id"]].astype(str).to_numpy(dtype=object),
                                "x": df[c["x"]].to_numpy(float) * scale, "y": df[c["y"]].to_numpy(float) * scale,
                                "z": df[c["z"]].to_numpy(float) * scale,
                                "chrom": df[c["chrom"]].to_numpy(), "chrom_start": df[c["chrom_start"]].to_numpy(),
                                "chrom_end": df[c["chrom_end"]].to_numpy()})
            if "cell_id" in c:
                std["cell_id"] = df[c["cell_id"]].to_numpy()
                if "fov" in c:                    # the field of view of each spot (Liu et al. 2025)
                    std["fov"] = df[c["fov"]].astype(str).str.replace(r"\.0$", "", regex=True).to_numpy(dtype=object)
                    run = df[c["datasetid"]].fillna("").astype(str).str.replace(r"\.0$|[\x00-\x1f\"]", "",
                                                                                regex=True) \
                        if "datasetid" in c else None                   # an empty "" reads as a control character
                    if run is not None and (run != "").any():    # and its imaging run, fields numbered per run
                        std["run"] = run.to_numpy(dtype=object)
            if len(cores) > 1:                    # trace ids are the core's own: c<k>- keeps two cores' traces apart
                std["trace_id"] = f"c{k + 1}-" + std["trace_id"].astype(str)
                std["core_file"] = Path(core).stem
            parts.append(std)
        df = pd.concat(parts, ignore_index=True)
        c = {x: x for x in df.columns}

        trace = df[c["trace_id"]].astype(str).to_numpy(dtype=object)
        tr = pd.DataFrame(index=pd.Index(pd.unique(trace), name="Trace_ID"))
        if exp.get("trace_data"):
            td = _companion(exp["trace_data"], "Trace_ID", name)
            td.index = td.index.astype(str)
            tr = tr.join(td)
        # the authors' cell of each trace: in the core, or in a cell table keyed by trace (Hafner et al. 2023);
        # numbered per field of view where the spots or traces have one (a cell id spans several fields otherwise),
        # 0 = none
        per_trace_cells = None
        cell_raw = None
        if exp.get("cell_data"):
            cdf = _table(exp["cell_data"])
            if "Cell_ID" not in cdf.columns:
                raise ValueError(f"{name}: {Path(exp['cell_data']).name} has no Cell_ID column")
            if "Trace_ID" in cdf.columns:
                per_trace_cells = cdf.drop_duplicates("Trace_ID").set_index(cdf.drop_duplicates("Trace_ID")["Trace_ID"].astype(str))
                tr = tr.join(per_trace_cells.drop(columns=["Trace_ID", "Cell_ID"]))
                cell_raw = per_trace_cells["Cell_ID"].astype(str).reindex(trace).to_numpy(dtype=object)
        if "cell_id" in c:
            cell_raw = df[c["cell_id"]].astype(str).to_numpy(dtype=object)
        if cell_raw is not None:
            raw = pd.Series(cell_raw, dtype=object).fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
            none = raw.isin(["", "0", "-1", "nan", "None"]).to_numpy()
            fov = (df["fov"].astype(str).to_numpy(dtype=object) if "fov" in df.columns
                   else tr["FOV"].astype(str).reindex(trace).to_numpy(dtype=object) if "FOV" in tr.columns else None)
            if fov is not None and "run" in df.columns:
                fov = np.char.add(np.char.add(df["run"].to_numpy().astype(str), "-"), fov.astype(str)).astype(object)
            if fov is not None:
                key = np.char.add(np.char.add(fov.astype(str), "-"), raw.to_numpy().astype(str)).astype(object)
            else:
                key = raw.to_numpy(dtype=object)
            cell = np.where(none, np.char.add("t", trace.astype(str)).astype(object), key)
        else:
            cell = np.char.add("t", trace.astype(str)).astype(object)               # one cell per trace
        trace_id = np.char.add(f"{name}_", trace.astype(str)).astype(object)
        cell_id = np.char.add(f"{name}_", cell.astype(str)).astype(object)

        coords.append(df[["x", "y", "z"]].to_numpy(float))
        loci = pd.DataFrame({"chrom": df[c["chrom"]].astype(str).to_numpy(dtype=object),
                             "start": df[c["chrom_start"]].to_numpy(np.int64),
                             "end": df[c["chrom_end"]].to_numpy(np.int64),
                             "trace_id": trace_id, "cell_id": cell_id})
        for chrom_, lo, hi, offset in exp.get("locus_shifts") or ():     # loci the deposit placed wrongly
            m = ((loci["chrom"] == chrom_) & (loci["start"] >= lo) & (loci["start"] <= hi)).to_numpy()
            loci.loc[m, ["start", "end"]] += int(offset)
            if m.any():
                shifts.setdefault(name, []).append({"chrom": chrom_, "start_from": int(lo), "start_to": int(hi),
                                                    "offset": int(offset), "spots": int(m.sum())})
        spots.append(loci)
        st = pd.DataFrame(index=pd.RangeIndex(len(df)))
        spot_files = [f for k in ("spot_quality", "spot_bio") for f in _as_list(exp.get(k))]
        if spot_files:                            # spot quality / spot biological data, keyed by Spot_ID
            q = pd.concat([_companion(f, "Spot_ID", name).drop(columns=["Trace_ID", "Cell_ID"], errors="ignore")
                           for f in spot_files])
            q.index = pd.Index(q.index.astype(str)).str.replace(r"\.0$", "", regex=True)
            if q.index.duplicated().any():
                raise ValueError(f"{name}: a Spot_ID is in several spot tables")
            q = q.reindex(df["spot_id"].to_numpy())
            for col in q.columns:
                num = pd.to_numeric(q[col], errors="coerce")
                st[col] = (num.to_numpy(float) if num.notna().sum() >= q[col].notna().sum()
                           else q[col].astype(object).to_numpy())
        spot_tracks.append(st)

        if "core_file" in df.columns:
            tr["core_file"] = df.drop_duplicates("trace_id").set_index("trace_id")["core_file"].reindex(tr.index).to_numpy()
        tr.index = np.char.add(f"{name}_", tr.index.to_numpy().astype(str)).astype(object)
        tr.index.name = "trace_id"
        tr.insert(0, "experiment", name)
        traces.append(tr)

        first = pd.DataFrame({"cell_id": cell_id, "trace_id": trace_id}).drop_duplicates("cell_id")
        ce = pd.DataFrame(index=pd.Index(first["cell_id"].to_numpy(), name="cell_id"))
        ce["experiment"] = name
        for col in ("run", "fov"):
            if col in df.columns:
                ce[col] = pd.Series(df[col].to_numpy(), index=cell_id).groupby(level=0).first().reindex(ce.index).to_numpy()
        for k, v in dict(exp.get("meta") or {}).items():
            ce[k] = v
        if per_trace_cells is not None:            # per-cell values given per trace: those of the cell's first trace
            vals = tr.reindex(first["trace_id"].to_numpy())[[x for x in per_trace_cells.columns
                                                              if x not in ("Trace_ID", "Cell_ID")]]
            vals.index = ce.index
            ce = ce.join(vals)
        elif exp.get("cell_data"):                 # a cell table keyed by the core's Cell_ID (Mateo et al. 2019)
            cv = cdf.drop_duplicates("Cell_ID")
            cv = cv.set_index(cv["Cell_ID"].astype(str).str.replace(r"\.0$", "", regex=True)).drop(columns="Cell_ID")
            raw_first = pd.Series(cell, index=cell_id).groupby(level=0).first()
            vals = cv.reindex(raw_first.reindex(ce.index).to_numpy())
            vals.index = ce.index
            ce = ce.join(vals)
        cells.append(ce)

    if not coords:
        raise ValueError("read_4dn_tracing: no experiments")
    if genome_assembly is None:
        if len(assemblies) > 1:
            raise ValueError(f"the experiments' genome assemblies differ: {sorted(assemblies)}")
        genome_assembly = next(iter(assemblies), "unknown")
    cells_df, traces_df = _tidy(pd.concat(cells), category=True), _tidy(pd.concat(traces))
    spots_df = pd.concat(spots, ignore_index=True)
    # UCSC chromosome names: one experiment writes "3R", another "chr3R" (Mateo et al. 2019); Liu et al. 2020 "19",
    # Liu et al. 2025 "Chr14"
    chrom = spots_df["chrom"].astype(str).str.replace(r"\.0$", "", regex=True)
    names = {c: "chr" + re.sub(r"^chr", "", c, flags=re.IGNORECASE) for c in chrom.unique()}
    renamed = {c: u for c, u in sorted(names.items()) if c != u}
    spots_df["chrom"] = chrom.map(names)
    return ChromData(coords=np.concatenate(coords), spots=spots_df,
                     spot_tracks=pd.concat(spot_tracks, ignore_index=True), traces=traces_df, cells=cells_df,
                     uns={"genome_assembly": genome_assembly, "xyz_unit": "micron", "fofct_headers": headers,
                          "fofct_unit_fixes": fixes, "fofct_dropped_spots": dropped,
                          "fofct_column_fixes": column_fixes, "fofct_chrom_renames": renamed,
                          "fofct_trace_splits": trace_splits, "fofct_locus_shifts": shifts})
