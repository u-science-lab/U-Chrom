"""uchrom.io.read_4dn_tracing on real 4DN FOF-CT experiments (tests/fixtures/fourdn_tracing: cut from the deposits,
headers as deposited), checked against the files read with the csv module."""

import csv

import numpy as np
import pytest

from uchrom.io import read_4dn_tracing

from tests import FIXTURES

F = FIXTURES / "fourdn_tracing"


def _files(prefix):
    out = {}
    for p in F.glob(f"{prefix}_*.csv"):
        for kind in ("spot_quality", "trace_data", "cell_data", "core"):
            if f"_{kind}_" in p.name:
                out[kind] = p
    return out


def _rows(path):
    """The data rows of a FOF-CT file as lists of strings (header lines and a CSV header row left out)."""
    lines = [l for l in open(path) if not l.lstrip().startswith(("#", '"#')) and l.strip()]
    rows = [next(csv.reader([l])) for l in lines]
    return rows[1:] if rows and not rows[0][0].strip()[:1].isdigit() else rows


def test_hafner_units_columns_and_cells_per_field():
    f = _files("hafner2023_orca_4DNEX5IV8FMD")
    cd = read_4dn_tracing([dict(name="e", meta={"set": "4DNESQ49IXDU"}, **f)])
    # 'R' is declared but absent; X, Y, Z are in nm although the header says micron
    assert [x["fix"] for x in cd.uns["fofct_column_fixes"]] == ["dropped R"]
    assert [x["used"] for x in cd.uns["fofct_unit_fixes"]] == ["nm"]
    core = _rows(f["core"])                      # Spot_ID, Trace_ID, X, Y, Z, Chrom, Chrom_Start, Chrom_End, Cell_ID
    placed = [r for r in core if r[5]]
    assert len(cd.spots) == len(placed) and cd.uns["fofct_dropped_spots"]["e"]["no_locus"] == len(core) - len(placed)
    want = np.array([[float(r[2]), float(r[3]), float(r[4])] for r in placed]) / 1000
    assert np.allclose(cd.coords, want)
    loci = cd.spots_with_loci()
    assert loci["chrom"].astype(str).tolist() == [r[5] for r in placed]
    assert loci["start"].tolist() == [int(r[6]) for r in placed]
    # cells are numbered per field of view, 0 = no cell
    fov = {r[0]: r[1] for r in _rows(f["trace_data"])}
    want_cell = [f"e_t{r[1]}" if r[8] == "0" else f"e_{fov[r[1]]}-{r[8]}" for r in placed]
    assert cd.spots["cell_id"].astype(str).tolist() == want_cell
    # per-trace cell values (Mean_Geminin), the brightness of each spot
    cells = {r[0]: float(r[2]) for r in _rows(f["cell_data"])}         # Trace_ID -> Mean_Geminin
    tr = cd.traces
    for t, g in cells.items():
        assert tr.loc[f"e_{t}", "Mean_Geminin"] == pytest.approx(g)
    bright = {r[0]: float(r[1]) for r in _rows(f["spot_quality"])}
    assert np.allclose(cd.spot_tracks["Brightness"], [bright[r[0]] for r in placed])
    assert set(cd.cells["set"].astype(str)) == {"4DNESQ49IXDU"}


def test_mateo_cell_table_by_cell_id():
    f = _files("mateo2019_orca_4DNEXJL6E1NS")
    cd = read_4dn_tracing([dict(name="m", **f)])
    assert cd.uns["fofct_unit_fixes"] == [] and cd.uns["genome_assembly"] == "dm6"
    table = {r[0]: r for r in _rows(f["cell_data"])}                   # Cell_ID, Embryo_ID, ..., Genotype
    for cell, r in table.items():
        assert cd.cells.loc[f"m_{cell}", "Genotype"] == r[-1]
        assert cd.cells.loc[f"m_{cell}", "nascentRNA_AbdA"] == pytest.approx(float(r[2]))


def test_bintu_trace_data_and_one_cell_per_trace():
    f = _files("bintu2018_4dn_4DNEXXQVNRK6")
    cd = read_4dn_tracing([dict(name="b", **f)])
    assert cd.uns["fofct_unit_fixes"] == [] and cd.uns["genome_assembly"] == "GRCh38"
    stage = {r[0]: r[1] for r in _rows(f["trace_data"])}
    assert {t: cd.traces.loc[f"b_{t}", "Cell_Cycle_Stage"] for t in stage} == stage
    assert (cd.spots["cell_id"].astype(str) == "b_t" + cd.spots["trace_id"].astype(str).str[2:]).all()
    core = _rows(f["core"])
    assert np.allclose(cd.coords, [[float(r[2]), float(r[3]), float(r[4])] for r in core])


def test_experiments_combined_with_their_ids_apart():
    h, m = _files("hafner2023_orca_4DNEX5IV8FMD"), _files("murphy2024_orca_4DNEX7V7HE4O")
    cd = read_4dn_tracing([dict(name="h", meta={"condition": "A"}, **h), dict(name="m", meta={"condition": "B"}, **m)])
    assert [x["experiment"] for x in cd.uns["fofct_unit_fixes"]] == ["h", "m"]
    assert set(cd.traces["experiment"]) == {"h", "m"}
    assert cd.cells.groupby("experiment", observed=True)["condition"].first().to_dict() == {"h": "A", "m": "B"}
    assert {"Brightness", "Fit_Height", "Drift_Z"} <= set(cd.spot_tracks.columns)
    assert cd.spot_tracks.loc[cd.spots["trace_id"].astype(str).str.startswith("h_").to_numpy(), "Fit_Height"].isna().all()
    with pytest.raises(ValueError, match="assemblies differ"):
        read_4dn_tracing([dict(name="h", **h), dict(name="x", **_files("mateo2019_orca_4DNEXJL6E1NS"))])


@pytest.mark.parametrize("file, fix", [
    ("odd_hafner2023_orca_no_chrom_name_4DNFILD6TDR6.csv", "inserted Chrom"),    # ##columns without Chrom
    ("odd_hafner2023_orca_header_row_4DNFI9FOT17E.csv", None),                   # header row with 'readout'
    ("odd_murphy2024_orca_chr_names_4DNFIKCHMBEC.csv", None),                    # spot_ID, chr, chr_start, ...
])
def test_core_tables_as_deposited(file, fix):
    cd = read_4dn_tracing([dict(name="e", core=F / file)])
    assert [x["fix"] for x in cd.uns["fofct_column_fixes"]] == ([fix] if fix else [])
    rows = _rows(F / file)
    loci = cd.spots_with_loci()
    dropped = cd.uns["fofct_dropped_spots"]["e"]
    assert len(loci) + dropped["no_locus"] + dropped["no_coordinates"] == len(rows) and len(loci) > 40
    assert set(loci["chrom"].astype(str)) <= {"chr3", "chr6"}
    assert (loci["end"] > loci["start"]).all()
    assert cd.uns["fofct_unit_fixes"][0]["used"] == "nm"       # all three say micron over nm values


def test_cell_table_with_a_malformed_column_line():
    from uchrom.io.fourdn_tracing import _companion

    t = _companion(F / "odd_hafner2023_orca_cell_columns_4DNFIP9SXUQC.csv", "Trace_ID", "e")
    assert list(t.columns) == ["Cell_ID", "Mean_Geminin", "Nuclear_Size"]
    first = _rows(F / "odd_hafner2023_orca_cell_columns_4DNFIP9SXUQC.csv")[0]
    assert t.loc[int(first[0]), "Mean_Geminin"] == pytest.approx(float(first[2]))


def test_chromosome_names_made_alike(tmp_path):
    f = _files("mateo2019_orca_4DNEXJL6E1NS")
    bare = tmp_path / "core.csv"                                   # the same experiment written with "3R"
    bare.write_text(open(f["core"]).read().replace(",chr3R,", ",3R,"))
    cd = read_4dn_tracing([dict(name="a", core=f["core"]), dict(name="b", core=bare)])
    assert cd.uns["fofct_chrom_renames"] == {"3R": "chr3R"}
    assert set(cd.bins["chrom"].astype(str)) == {"chr3R"}
    assert len(cd.bins) == len(read_4dn_tracing([dict(name="a", core=f["core"])]).bins)


def test_reused_trace_ids_split_and_duplicate_rows_dropped(tmp_path):
    f = F / "odd_murphy2024_orca_reused_trace_ids_4DNFIYZDTHMG.csv"
    rows = _rows(f)                                   # one id in two blocks with another trace between them
    ids = [r[1] for r in rows]
    reused = ids[0]
    cd = read_4dn_tracing([dict(name="m", core=f)])
    assert cd.uns["fofct_trace_splits"]["m"]["split_traces"] == 1
    traces = set(cd.spots["trace_id"].astype(str))
    assert {f"m_{reused}", f"m_{reused}.b2"} <= traces
    n1 = next(k for k in range(len(ids)) if ids[k] != reused)          # rows of the first block
    n2 = len(ids) - max(k for k in range(len(ids)) if ids[k] != reused) - 1   # rows of the last block
    t = cd.spots["trace_id"].astype(str).to_numpy()
    assert (t == f"m_{reused}").sum() == n1 and (t == f"m_{reused}.b2").sum() == n2
    # the same rows written twice: the copy dropped
    twice = tmp_path / "twice.csv"
    text = open(f).read()
    data = [l for l in text.splitlines(True) if l.strip() and not l.lstrip('"').startswith("#")]
    twice.write_text(text + "".join(data[:5]))
    cd2 = read_4dn_tracing([dict(name="m", core=twice)])
    assert cd2.uns["fofct_dropped_spots"]["m"]["duplicate_rows"] == 5 and len(cd2.spots) == len(cd.spots)


def test_locus_shifts():
    f = _files("bintu2018_4dn_4DNEXXQVNRK6")
    plain = read_4dn_tracing([dict(name="b", core=f["core"])]).spots_with_loci()
    lo = int(plain["start"].min())
    cd = read_4dn_tracing([dict(name="b", core=f["core"], locus_shifts=[("chr21", lo, lo + 60_000, 1000)])])
    moved = cd.spots_with_loci()
    shifted = (plain["start"] <= lo + 60_000).to_numpy()
    assert (moved["start"].to_numpy()[shifted] == plain["start"].to_numpy()[shifted] + 1000).all()
    assert (moved["start"].to_numpy()[~shifted] == plain["start"].to_numpy()[~shifted]).all()
    assert cd.uns["fofct_locus_shifts"]["b"][0]["spots"] == int(shifted.sum())
