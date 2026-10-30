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


def test_capitalised_chromosome_prefix(tmp_path):
    f = _files("mateo2019_orca_4DNEXJL6E1NS")
    cap = tmp_path / "core.csv"                                    # written "Chr3R" (as Liu et al. 2025 write "Chr14")
    cap.write_text(open(f["core"]).read().replace(",chr3R,", ",Chr3R,"))
    cd = read_4dn_tracing([dict(name="b", core=cap)])
    assert cd.uns["fofct_chrom_renames"] == {"Chr3R": "chr3R"}
    assert set(cd.bins["chrom"].astype(str)) == {"chr3R"}


def test_cells_numbered_per_field_of_view_in_the_core():
    f = F / "odd_liu2025_kras_cells_per_fov_4DNFIEC1D26L.csv"            # CellID 110 in FOVid 1 and in FOVid 12
    cd = read_4dn_tracing([dict(name="e", core=f)])
    assert sorted(cd.cells.index) == ["e_1-110", "e_12-110"]
    assert sorted(cd.cells["fov"]) == ["1", "12"]
    assert cd.uns["fofct_chrom_renames"] == {"Chr6": "chr6"}


def test_cells_numbered_per_field_and_run():
    f = F / "odd_liu2025_kras_runs_4DNFIU7X8FJJ.csv"         # CellID 36 of FOVid 1 in Dataset IDs 210628 and 210728
    cd = read_4dn_tracing([dict(name="e", core=f)])
    assert sorted(cd.cells.index) == ["e_210628-1-36", "e_210728-1-36"]
    assert sorted(cd.cells["run"]) == ["210628", "210728"] and set(cd.cells["fov"]) == {"1"}


def test_traces_from_core_columns():
    f = F / "odd_tastemel2025_sox2_locus_trace_ids_4DNFIH5BHP3E.csv"    # Trace_ID = locus index; cell 11, two alleles
    by_locus = read_4dn_tracing([dict(name="e", core=f)])
    assert by_locus.n_traces == len(by_locus.bins) > 2                   # as deposited: one "trace" per locus
    cd = read_4dn_tracing([dict(name="e", core=f, trace_by=("Cell_ID", "Extra_Cell_ROI_ID"))])
    assert sorted(cd.traces.index) == ["e_11_129", "e_11_CAST"] and cd.n_cells == 1
    assert cd.uns["fofct_trace_keys"] == {"e": ["Cell_ID", "Extra_Cell_ROI_ID"]}
    per = cd.spots.groupby("trace_id", observed=True)["bin_id"]
    assert (per.nunique() == per.size()).all()                           # each locus once per allele


def test_spot_tables_of_other_columns_joined():
    p = "odd_le2024_se_two_spot_tables_"            # spots 1-12 of one experiment: core, quality, nascent RNA per spot
    cd = read_4dn_tracing([dict(name="e", core=F / f"{p}core_4DNFI4YJYP5Q.csv",
                                spot_quality=[F / f"{p}spot_quality_4DNFIF8577IV.csv",
                                              F / f"{p}spot_bio_4DNFIJ5YBMVT.csv"])])
    st = cd.spot_tracks
    assert {"fitQuality", "nascentRNA_burst_intensity", "RNA_name"} <= set(st.columns)
    assert not {"Chrom", "Chrom_Start", "Chrom_End"} & set(st.columns)          # the spot's own locus, repeated
    rna = {r[0]: r for r in _rows(F / f"{p}spot_bio_4DNFIJ5YBMVT.csv")}
    assert st["RNA_name"].notna().all() and set(st["RNA_name"]) <= {r[7] for r in rna.values()}
    # cells and traces numbered per field of view, the field given in the quality table only
    fov = read_4dn_tracing([dict(name="e", core=F / f"{p}core_4DNFI4YJYP5Q.csv", fov_from=("fov",),
                                 spot_quality=[F / f"{p}spot_quality_4DNFIF8577IV.csv"], trace_by=("Trace_ID", "Chrom"))])
    assert set(fov.cells.index) == {f"e_1-{c}" for c in {r[8] for r in _rows(F / f"{p}core_4DNFI4YJYP5Q.csv")}}
    assert all(t.startswith("e_1-") and t.rsplit("_", 1)[1] in ("chr1", "chr3") for t in fov.traces.index.astype(str))
    assert fov.uns["fofct_fov_columns"] == {"e": "fov"}


def test_cell_table_joined_where_cells_are_keyed_by_field():
    p = "odd_liu2025_mop_cells_by_fov_"           # two cells; core and cell table both give FOV_ID and Cell_ID
    cd = read_4dn_tracing([dict(name="e", core=F / f"{p}core_4DNFI36ZLABD.csv",
                                cell_data=F / f"{p}cell_data_4DNFIA7FUW8Y.csv")])
    table = {r[0]: r for r in _rows(F / f"{p}cell_data_4DNFIA7FUW8Y.csv")}
    assert len(cd.cells) == 2
    for cid, row in cd.cells.iterrows():
        fov, raw = cid.split("_", 1)[1].split("-", 1)
        assert row["cluster_subclass"] == table[raw][7] and row["cell_volume_from_merlin"] == pytest.approx(float(table[raw][2]))


def test_rna_spot_tables_as_points():
    from tests import FIXTURES
    core = F / "odd_takei2021_mesc_two_cells_core_4DNFIHF3JCBY.csv"      # rows of cell 0_1
    rna_file = FIXTURES / "4DNFIJ52NVDV.csv"                              # the experiment's RNA spots, all cells
    cd = read_4dn_tracing([dict(name="e", core=core, rna_spot=rna_file)])
    rna = cd.points["rna"]
    rows = _rows(rna_file)
    assert len(rna) == len(rows) and {"x", "y", "z", "gene", "gene_id", "cell_id", "experiment"} <= set(rna.columns)
    assert rna["x"].to_numpy() == pytest.approx([float(r[1]) for r in rows])            # micron, as the core
    mine = [r[6] == "0_1" for r in rows]
    assert (rna["cell_id"][mine] == "e_0_1").all() and rna["cell_id"][[not m for m in mine]].isna().all()
    assert not rna["gene_id"].str.endswith(",").any()


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


def test_numbered_chromosomes_and_spot_tables_with_trace_ids():
    # Liu et al. 2020: chromosome "19", a spot table that repeats Trace_ID, a cell table keyed by the core's Cell_ID
    core, bio = F / "odd_liu2020_mina_core.csv", F / "odd_liu2020_mina_spot_bio.csv"
    cd = read_4dn_tracing([dict(name="l", core=core, spot_bio=bio, cell_data=F / "odd_liu2020_mina_cell_data.csv")])
    assert set(cd.bins["chrom"].astype(str)) == {"chr19"} and cd.uns["fofct_chrom_renames"] == {"19": "chr19"}
    assert cd.uns["fofct_column_fixes"] == []
    lamina = {r[0]: float(r[2]) for r in _rows(bio)}            # Spot_ID, Trace_ID, Distance_To_Lamina, ...
    rows = _rows(core)
    assert np.allclose(cd.spot_tracks["Distance_To_Lamina"], [lamina[r[0]] for r in rows])
    assert "Trace_ID" not in cd.spot_tracks.columns
    sizes = {r[0]: float(r[1]) for r in _rows(F / "odd_liu2020_mina_cell_data.csv")}
    assert {c.split("_", 1)[1]: v for c, v in cd.cells["Cell_Size"].items()} == sizes


def test_several_core_tables_of_one_experiment():
    # Takei et al. 2021 brain: a 1-Mb and a 25-kb core table, spot ids numbered on across them, one quality table each
    cores = [F / "odd_takei2021_core_1.csv", F / "odd_takei2021_core_2.csv"]
    quality = [F / "odd_takei2021_quality_4DNFI6KFNKF7.csv", F / "odd_takei2021_quality_4DNFIL9IEKFL.csv"]
    cd = read_4dn_tracing([dict(name="t", core=cores, spot_quality=quality, cell_data=F / "odd_takei2021_cell_data.csv")])
    n = [len(_rows(c)) for c in cores]
    assert len(cd.spots) == sum(n)
    t = cd.spots["trace_id"].astype(str)
    assert t.str.startswith("t_c1-").sum() == n[0] and t.str.startswith("t_c2-").sum() == n[1]
    assert set(cd.traces["core_file"]) == {"odd_takei2021_core_1", "odd_takei2021_core_2"}
    label = {r[0].removesuffix(".0"): float(r[1]) for q in quality for r in _rows(q)}
    ids = [r[0] for c in cores for r in _rows(c)]
    assert np.allclose(cd.spot_tracks["labelID"], [label[i] for i in ids])
    assert cd.cells.loc["t_0_6", "cluster label"] == 9


def test_single_hash_columns_line():
    from chromdata import read_fofct_table

    table, _ = read_fofct_table(F / "odd_huang2021_trace_data_single_hash.csv")
    assert list(table.columns) == ["Trace_ID", "Allele", "Sox2_Present", "GFP_Present", "mCherry_Present"]


def test_field_of_view_positions_of_crop_local_traces():
    # Hafner 2023 keeps each trace's place in its field of view (LocusX / LocusY, pixels) in the trace table
    from uchrom.datasets._load_tracing import _fov_positions

    f = _files("hafner2023_orca_4DNEX5IV8FMD")
    cd = read_4dn_tracing([dict(name="e", **f)])
    _fov_positions(cd, "traces", "LocusX", "LocusY")
    pos = cd.cell_positions("fov")
    rec = cd.uns["cell_spatial"]["fov"]
    assert rec["unit"] == "px" and rec["frame"] == "fov" and rec["in_coords_frame"] is False
    rows = {r[0]: (r[1], float(r[2]), float(r[3])) for r in _rows(f["trace_data"])}     # Trace_ID, FOV, LocusX, LocusY
    one = [t for t, c in zip(cd.spots["trace_id"].astype(str), cd.spots["cell_id"].astype(str)) if c == f"e_t{t[2:]}"]
    t = one[0][2:]
    assert pos.loc[f"e_t{t}", "x"] == pytest.approx(rows[t][1]) and pos.loc[f"e_t{t}", "y"] == pytest.approx(rows[t][2])
    assert cd.cells.loc[f"e_t{t}", "fov_region"] == f"e/FOV {int(float(rows[t][0]))}"
