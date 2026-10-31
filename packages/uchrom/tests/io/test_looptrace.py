"""uchrom.io.read_looptrace on the LoopTrace tables of Beckwith et al. 2025 (tests/fixtures/looptrace: rows as
published — three mitotic traces, the traces of one RPE-1 nucleus, three traces of the table without a trace
column around a gap of its row index), checked against the files read with the csv module."""

import csv
import gzip

import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData
from uchrom.io import read_looptrace

from tests import FIXTURES

MITOSIS = FIXTURES / "looptrace" / "mitofold_traces.csv.gz"
COMPARISON = FIXTURES / "looptrace" / "looptrace_comparison.csv.gz"
COMBINED = FIXTURES / "looptrace" / "looptrace_combined.csv.gz"


def _rows(path):
    with gzip.open(path, "rt", newline="") as fh:
        return list(csv.DictReader(fh))


def _index(cd):
    """Spot row of each (trace, g_pos)."""
    s = cd.spots_with_loci()
    return s, {(t, float(g)): i for i, (t, g) in enumerate(zip(s["trace_id"].astype(str), s["g_pos"]))}


def test_mitotic_traces_with_the_authors_qc():
    rows = _rows(MITOSIS)
    cd = read_looptrace(MITOSIS)
    located = [r for r in rows if r["g_pos"] != ""]
    assert len(located) < len(rows)                         # the region-detection frame has no locus
    assert cd.n_spots == len(located) and cd.uns["looptrace"]["rows_without_locus"] == len(rows) - len(located)
    assert cd.uns["genome_assembly"] == "hg38" and cd.uns["xyz_unit"] == "nm"

    s, at = _index(cd)
    size = {"Chr5_1MB": 12_000, "Chr2_full": 100_000}
    for r in located:
        i = at[("t" + r["trace_id"], float(r["g_pos"]))]
        xyz = [float(r["x"]), float(r["y"]), float(r["z"])]
        assert np.allclose(cd.layers["fit"][i], xyz)
        assert bool(s["qc_pass"].iloc[i]) == (r["QC"] == "1")
        assert np.allclose(cd.coords[i], xyz) if r["QC"] == "1" else np.isnan(cd.coords[i]).all()
        start, end = s["start"].iloc[i], s["end"].iloc[i]
        assert start <= float(r["g_pos"]) < end and end - start <= size[r["region"]]
        cell = f"{r['exp']}/{r['position'].replace('.zarr', '')}/{r['nuc_label']}"
        assert s["cell_id"].iloc[i] == cell and cd.cells.loc[cell, "phase"] == r["phase"]
    assert set(cd.traces["region"]) == set(size)
    passed = cd.spots.groupby("trace_id", observed=True)["qc_pass"].sum().reindex(cd.traces.index)
    assert (cd.traces["n_qc_pass"] == passed).all()


def test_nuclei_of_the_comparison_table():
    rows = _rows(COMPARISON)
    cd = read_looptrace(COMPARISON)
    assert cd.n_spots == len(rows) and "fit" not in (cd.layers or {}) and not np.isnan(cd.coords).any()
    s, at = _index(cd)
    for r in rows:
        i = at[("t" + r["trace_id"], float(r["g_pos"]))]
        assert np.allclose(cd.coords[i], [float(r["x"]), float(r["y"]), float(r["z"])])
        assert np.isclose(cd.spot_tracks["A"].iloc[i], float(r["A"]))
        cell = f"{r['exp']}/{r['nuc_id'].replace('.zarr', '')}"
        assert s["cell_id"].iloc[i] == cell
        assert np.isclose(cd.cells.loc[cell, "nuc_total_int"], float(r["nuc_total_int"]))
        assert s["chrom"].iloc[i] == r["chr"] and s["start"].iloc[i] <= float(r["g_pos"]) < s["end"].iloc[i]
    assert len(cd.traces) == len({r["trace_id"] for r in rows})


def test_traces_from_the_row_blocks(tmp_path):
    rows = _rows(COMBINED)
    cd = read_looptrace(COMBINED)
    n_frames = len({r["frame_name"] for r in rows})
    assert cd.n_spots == len(rows) and len(cd.traces) == len(rows) // n_frames == 3
    s = cd.spots_with_loci()
    for k, r in enumerate(sorted(rows, key=lambda r: int(r[""]))):     # k-th row of the index = frame of trace k // n
        i = int(np.flatnonzero(np.isclose(cd.coords[:, 0], float(r["x"])))[0])
        assert s["trace_id"].iloc[i] == f"{r['cell_type']}.{r['exp']}.{r['region_name']}.{k // n_frames}"
    assert cd.cells is None or len(cd.cells) == 0
    assert set(cd.traces["cell_type"]) == {"HK_dCTCF"} and set(cd.traces["region"]) == {"Chr4-B"}

    raw = pd.read_csv(COMBINED)                             # one row short: the blocks are not whole traces
    raw.drop(index=raw.iloc[:, 0].idxmin()).to_csv(tmp_path / "broken.csv", index=False)
    with pytest.raises(ValueError, match="not whole traces"):
        read_looptrace(tmp_path / "broken.csv")


def test_round_trip_and_unknown_input(tmp_path):
    cd = read_looptrace(MITOSIS)
    cd.write(tmp_path / "lt.chromdata.zarr")
    back = ChromData.read(tmp_path / "lt.chromdata.zarr", original_order=True)
    assert np.array_equal(back.coords, cd.coords, equal_nan=True)
    assert np.array_equal(back.layers["fit"], cd.layers["fit"])
    assert back.bins[["start", "end"]].equals(cd.bins[["start", "end"]])

    p = tmp_path / "x.csv"
    p.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError, match="not a LoopTrace table"):
        read_looptrace(p)
    other = pd.read_csv(COMPARISON).head(5).assign(region_name="SOX2")
    other.to_csv(tmp_path / "other.csv", index=False)
    with pytest.raises(ValueError, match="no spot size"):
        read_looptrace(tmp_path / "other.csv")
