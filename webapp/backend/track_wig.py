"""WIG-format track endpoint for igv.js integration.

Endpoint: GET /api/track_wig/{name}?chrom=chr1&start=0&end=10000000
Returns: variableStep WIG text (plain text, UTF-8)

UID format: the `name` path param matches a column name in cd.tracks DataFrame.
If cd.tracks is None or the column doesn't exist, returns 404.

WIG variableStep format:
    variableStep chrom=<chrom> span=<bin_size>
    <start_bp> <value>
    <start_bp> <value>
    ...

One track per chromosome section. Values are the per-bin mean across all cells.
"""

from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

import webapp.backend.data_api as data_api

track_wig_router = APIRouter()


@track_wig_router.get("/api/tracks")
def list_tracks(session_id: Optional[str] = None) -> list:
    """Return list of available track names from cd.tracks columns."""
    session = data_api.resolve_session(session_id)
    if session is None or session.chromdata is None:
        return []
    cd = session.chromdata
    if cd.tracks is None:
        return []
    return list(cd.tracks.columns)


@track_wig_router.get("/api/track_wig/{name}")
def get_track_wig(
    name: str,
    chrom: Optional[str] = None,
    start: Optional[int] = None,
    end: Optional[int] = None,
    session_id: Optional[str] = None,
) -> PlainTextResponse:
    """Return variableStep WIG text for the named track column."""
    cd = data_api.cd_or_404(session_id)

    if cd.tracks is None or name not in cd.tracks.columns:
        raise HTTPException(status_code=404, detail={"error": f"Track '{name}' not found"})

    # Build a combined DataFrame of spots + track value
    df = cd.spots[["chrom", "start", "end"]].copy()
    df["_value"] = cd.tracks[name].values

    # Filter by chrom
    if chrom is not None:
        df = df[df["chrom"] == chrom]

    # Filter by genomic range (overlap semantics: bin overlaps [start, end))
    if start is not None:
        df = df[df["end"] > start]
    if end is not None:
        df = df[df["start"] < end]

    if df.empty:
        return PlainTextResponse(f"track type=wiggle_0 name={name}\n", media_type="text/plain")

    # Group by (chrom, start, end) and compute mean across all cells/traces
    grouped = df.groupby(["chrom", "start", "end"], observed=True)["_value"].mean().reset_index()
    grouped = grouped.sort_values(["chrom", "start"])

    lines = [f"track type=wiggle_0 name={name}"]
    for chrom_name, group in grouped.groupby("chrom", observed=True, sort=True):
        group = group.sort_values("start")
        if group.empty:
            continue
        # bin_size from the first bin
        first = group.iloc[0]
        bin_size = int(first["end"] - first["start"])
        lines.append(f"variableStep chrom={chrom_name} span={bin_size}")
        for row in group.rename(columns={"_value": "value"}).itertuples(index=False):
            wig_pos = int(row.start) + 1  # WIG is 1-based
            lines.append(f"{wig_pos} {row.value:.6g}")

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain")


@track_wig_router.get("/api/track_csv/{name}")
def get_track_csv(
    name: str,
    chrom: Optional[str] = None,
    start: Optional[int] = None,
    end: Optional[int] = None,
    session_id: Optional[str] = None,
) -> PlainTextResponse:
    """Return Gosling-compatible CSV for the named track column.

    Gosling's `data.type:'csv'` loader parses a header row plus comma-separated
    rows; it cannot parse WIG text (see get_track_wig). This endpoint emits the
    columns Gosling expects for a signal track::

        chrom,start,end,value
        chr1,0,1000,0.123
        ...

    Values are the per-bin mean across all cells/traces, matching the WIG
    endpoint's aggregation. Use with a spec data block of
    ``{"type":"csv","url":"/api/track_csv/<name>","chromosomeField":"chrom",
    "genomicFields":["start","end"]}`` and ``y:{"field":"value",...}``.
    """
    cd = data_api.cd_or_404(session_id)

    if cd.tracks is None or name not in cd.tracks.columns:
        raise HTTPException(status_code=404, detail={"error": f"Track '{name}' not found"})

    df = cd.spots[["chrom", "start", "end"]].copy()
    df["_value"] = cd.tracks[name].values

    if chrom is not None:
        df = df[df["chrom"] == chrom]
    if start is not None:
        df = df[df["end"] > start]
    if end is not None:
        df = df[df["start"] < end]

    header = "chrom,start,end,value\n"
    if df.empty:
        return PlainTextResponse(header, media_type="text/csv")

    grouped = (
        df.groupby(["chrom", "start", "end"], observed=True)["_value"]
        .mean()
        .reset_index()
        .rename(columns={"_value": "value"})
        .sort_values(["chrom", "start"])
    )

    lines = [header.rstrip("\n")]
    for row in grouped.itertuples(index=False):
        lines.append(
            f"{row.chrom},{int(row.start)},{int(row.end)},{row.value:.6g}"
        )
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/csv")
