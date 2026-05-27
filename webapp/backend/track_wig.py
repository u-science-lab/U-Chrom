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


@track_wig_router.get("/api/track_wig/{name}")
def get_track_wig(
    name: str,
    chrom: Optional[str] = None,
    start: Optional[int] = None,
    end: Optional[int] = None,
) -> PlainTextResponse:
    """Return variableStep WIG text for the named track column."""
    if data_api.current_session is None or data_api.current_session.chromdata is None:
        raise HTTPException(status_code=404, detail={"error": "No data loaded"})

    cd = data_api.current_session.chromdata

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
