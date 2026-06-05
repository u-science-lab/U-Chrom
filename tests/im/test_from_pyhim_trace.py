"""Tests for ChromData.from_pyhim_trace — reading PyHiM ECSV trace tables.

PyHiM (Devos et al. 2024) writes its chromatin tracing output as ECSV
tables.  The reader translates them into a ChromData container so the
rest of U-Chrom (browser, structure callers, embedding) can consume the
output without going through the FOF-CT CSV detour.

ECSV schema (from pyHi-M/pyHiM master, ``chromatin_trace_table.py``):

    Spot_ID, Trace_ID, x, y, z, Chrom, Chrom_Start, Chrom_End,
    ROI #, Mask_id, Barcode #, label

meta['comments'] carries ``xyz_unit=...`` and ``genome_assembly=...``.

Two scenarios:

1. ``Chrom``/``Chrom_Start``/``Chrom_End`` already populated → use as-is.
2. Those columns empty → require ``barcode_dict`` mapping each
   ``Barcode #`` to ``(chrom, start, end)``.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_from_pyhim_trace_reads_basic_fixture():
    """Read a small ECSV with Chrom columns populated; check the basics."""
    from uchrom import ChromData

    cd = ChromData.from_pyhim_trace(FIXTURES / "fixture_with_chrom.ecsv")

    # coords shape and value spot-check
    assert cd.coords.shape == (6, 3)
    np.testing.assert_allclose(cd.coords[0], [1.10, 2.10, 3.10], atol=1e-5)
    np.testing.assert_allclose(cd.coords[3], [5.10, 6.10, 7.10], atol=1e-5)

    # required spots columns are filled
    spots = cd.spots
    assert {"chrom", "start", "end", "trace_id"} <= set(spots.columns)
    assert list(spots["start"]) == [10_000_000, 20_000_000, 30_000_000,
                                     10_000_000, 20_000_000, 30_000_000]
    assert sorted(set(map(str, spots["trace_id"]))) == ["trace_A", "trace_B"]

    # spot_id carried through, dtype categorical (per ChromData convention)
    assert "spot_id" in spots.columns
    assert list(spots["spot_id"].astype(str)) == [f"s{i:03d}" for i in range(1, 7)]

    # cell_id derived from Mask_id (PyHiM convention)
    assert "cell_id" in spots.columns
    assert set(map(int, spots["cell_id"])) == {1}


def test_from_pyhim_trace_preserves_ecsv_meta():
    """xyz_unit / genome_assembly captured into cd.uns."""
    from uchrom import ChromData

    cd = ChromData.from_pyhim_trace(FIXTURES / "fixture_with_chrom.ecsv")
    assert cd.uns.get("xyz_unit") == "micron"
    assert cd.uns.get("genome_assembly") == "mm10"
    # also keep the raw header under uns['pyhim'] for traceability
    assert "pyhim" in cd.uns
    raw = cd.uns["pyhim"]
    assert isinstance(raw.get("ecsv_comments"), list)
    assert any("xyz_unit=micron" in c for c in raw["ecsv_comments"])


def test_from_pyhim_trace_applies_barcode_dict():
    """When Chrom columns are empty, barcode_dict provides the mapping."""
    from uchrom import ChromData

    barcode_dict = {
        1: ("chr1", 10_000_000, 10_050_000),
        2: ("chr1", 20_000_000, 20_050_000),
        3: ("chr1", 30_000_000, 30_050_000),
    }
    cd = ChromData.from_pyhim_trace(
        FIXTURES / "fixture_barcode_only.ecsv",
        barcode_dict=barcode_dict,
    )

    assert cd.coords.shape == (6, 3)
    assert list(cd.spots["start"]) == [10_000_000, 20_000_000, 30_000_000,
                                        10_000_000, 20_000_000, 30_000_000]
    assert list(cd.spots["end"]) == [10_050_000, 20_050_000, 30_050_000,
                                      10_050_000, 20_050_000, 30_050_000]
    assert set(map(str, cd.spots["chrom"])) == {"chr1"}


def test_from_pyhim_trace_missing_barcode_raises():
    """A barcode in the ECSV that's absent from barcode_dict fails loudly."""
    from uchrom import ChromData

    incomplete = {
        1: ("chr1", 10_000_000, 10_050_000),
        # 2 and 3 deliberately missing
    }
    with pytest.raises(KeyError, match="2"):
        ChromData.from_pyhim_trace(
            FIXTURES / "fixture_barcode_only.ecsv",
            barcode_dict=incomplete,
        )


def test_from_pyhim_trace_no_barcode_dict_when_chrom_missing_raises():
    """Empty Chrom column + no barcode_dict → actionable error."""
    from uchrom import ChromData

    with pytest.raises(ValueError, match="barcode_dict"):
        ChromData.from_pyhim_trace(FIXTURES / "fixture_barcode_only.ecsv")


def test_from_pyhim_trace_accepts_dataframe_barcode_dict():
    """Also accept a DataFrame with columns barcode, chrom, start, end."""
    from uchrom import ChromData

    bdf = pd.DataFrame({
        "barcode": [1, 2, 3],
        "chrom":   ["chr1", "chr1", "chr1"],
        "start":   [10_000_000, 20_000_000, 30_000_000],
        "end":     [10_050_000, 20_050_000, 30_050_000],
    })
    cd = ChromData.from_pyhim_trace(
        FIXTURES / "fixture_barcode_only.ecsv",
        barcode_dict=bdf,
    )
    assert list(cd.spots["start"])[:3] == [10_000_000, 20_000_000, 30_000_000]
