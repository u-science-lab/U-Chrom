"""``ChromData.to_fofct`` / ``uchrom.io.write_fofct``: FOF-CT core (+ cell
and RNA) tables that ``from_fofct`` reads back exactly."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from uchrom import ChromData

DATA = Path(__file__).resolve().parents[2] / "example-data"
CORE = DATA / "4DNFIHF3JCBY.csv"
CELLS = DATA / "4DNFIFINA2U9.csv"
RNA = DATA / "4DNFIJ52NVDV.csv"


def _cd():
    rng = np.random.default_rng(0)
    n = 40
    spots = pd.DataFrame({
        "chrom": np.where(np.arange(n) < 25, "chr2", "chr10"),
        "start": (np.arange(n) % 25) * 25_000, "end": (np.arange(n) % 25) * 25_000 + 25_000,
        "trace_id": np.repeat(["t1", "t2", "t3", "t4"], 10),
        "cell_id": np.repeat(["c1", "c2"], 20),
        "spot_id": np.arange(n) + 100,
        "readout": rng.choice(["r1", "r2"], n),
        "quality": rng.random(n),
    })
    coords = rng.normal(size=(n, 3)) * 10
    coords[5] = np.nan
    cells = pd.DataFrame({"centroid_x": [1.5, 2.5], "centroid_y": [3.0, 4.0],
                          "nucleus_area_um2": [100.0, 120.0], "rna.Nanog": [3, 0],
                          "cell_type": ["A", "B"]},
                         index=pd.Index(["c1", "c2"], name="cell_id"))
    rna = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0], "z": [0.5, 0.25], "gene": ["Nanog", "Sox2"],
                        "gene_id": ["NM_1", "NM_2"], "cell_id": ["c1", "c2"], "spot_id": [1, 2],
                        "peak_intensity": [100, 200]})
    cd = ChromData(coords, spots, cells=cells, points={"rna": rna},
                   spot_tracks=pd.DataFrame({"IF": rng.normal(size=n)}),
                   uns={"genome_assembly": "mm10", "xyz_unit": "micron"})
    cd.bin_tracks = pd.DataFrame({"atac": np.arange(cd.n_bins, dtype=float)})
    return cd


def test_round_trip_through_from_fofct(tmp_path):
    cd = _cd()
    out = cd.to_fofct(tmp_path / "core.csv", cell_table=tmp_path / "cell.csv", rna_table=tmp_path / "rna.csv")
    assert set(out) == {"core", "cells", "rna"}
    lines = (tmp_path / "core.csv").read_text().splitlines()
    assert lines[0] == "##FOF-CT_version=v0.1" and lines[1] == "##Table_namespace=4dn_FOF-CT_core"
    assert "##genome_assembly=mm10" in lines and "##XYZ_unit=micron" in lines
    assert lines[4].startswith("##columns=(Spot_ID,Trace_ID,X,Y,Z,Chrom,Chrom_Start,Chrom_End,Cell_ID,")
    back = ChromData.from_fofct(tmp_path / "core.csv", cell_table=tmp_path / "cell.csv",
                                rna_table=tmp_path / "rna.csv")
    # coords, ids and loci are exact (NaN kept)
    np.testing.assert_array_equal(back.coords, cd.coords)
    a, b = cd.spots_with_loci(), back.spots_with_loci()
    for col in ("trace_id", "cell_id", "chrom"):
        assert list(a[col].astype(str)) == list(b[col].astype(str))
    for col in ("start", "end", "spot_id"):
        np.testing.assert_array_equal(a[col].to_numpy(), b[col].to_numpy())
    pd.testing.assert_frame_equal(back.bins[["chrom", "start", "end"]], cd.bins[["chrom", "start", "end"]])
    # extra columns and spot tracks come back as spot columns
    assert list(b["readout"]) == list(a["readout"])
    np.testing.assert_array_equal(b["quality"].to_numpy(), a["quality"].to_numpy())
    np.testing.assert_array_equal(b["IF"].to_numpy(), cd.spot_tracks["IF"].to_numpy())
    assert "atac" not in b.columns                          # bin tracks only on request
    # cell and RNA tables
    pd.testing.assert_frame_equal(back.cells[cd.cells.columns], cd.cells, check_dtype=False,
                                  check_index_type=False)
    pd.testing.assert_frame_equal(back.points["rna"][cd.points["rna"].columns], cd.points["rna"],
                                  check_dtype=False)
    assert back.uns["genome_assembly"] == "mm10" and back.uns["xyz_unit"] == "micron"


def test_options_and_errors(tmp_path):
    from uchrom.io import write_fofct

    cd = _cd()
    write_fofct(cd, tmp_path / "c.csv", spot_tracks=False, bin_tracks=True,
                header={"lab_name": "Test, lab", "XYZ_unit": "nm"})
    text = (tmp_path / "c.csv").read_text()
    assert '"#lab_name: Test, lab"' in text and "##XYZ_unit=nm" in text
    back = ChromData.from_fofct(tmp_path / "c.csv")
    assert "IF" not in back.spots.columns and back.uns["fofct_header"]["lab_name"] == "Test, lab"
    np.testing.assert_array_equal(back.spots["atac"].to_numpy(),
                                  cd.bin_tracks["atac"].to_numpy()[cd.spots["bin_id"].to_numpy()])
    # no spot_id: generated
    plain = ChromData(np.zeros((2, 3)), pd.DataFrame({"chrom": ["chr1", "chr1"], "start": [0, 10],
                                                      "end": [10, 20], "trace_id": [0, 0]}))
    plain.to_fofct(tmp_path / "p.csv")
    assert list(ChromData.from_fofct(tmp_path / "p.csv").spots["spot_id"]) == [0, 1]
    with pytest.raises(ValueError, match="points"):
        plain.to_fofct(tmp_path / "q.csv", rna_table=tmp_path / "r.csv")
    with pytest.raises(ValueError, match="cells"):
        plain.to_fofct(tmp_path / "q.csv", cell_table=tmp_path / "r.csv")


@pytest.mark.skipif(not CORE.exists(), reason="example-data/4DNFIHF3JCBY.csv not downloaded")
def test_takei2021_real_round_trip(tmp_path):
    cd = ChromData.from_fofct(CORE, cell_table=CELLS, rna_table=RNA)
    cd.to_fofct(tmp_path / "core.csv", cell_table=tmp_path / "cell.csv", rna_table=tmp_path / "rna.csv")
    back = ChromData.from_fofct(tmp_path / "core.csv", cell_table=tmp_path / "cell.csv",
                                rna_table=tmp_path / "rna.csv")
    pd.testing.assert_frame_equal(back.to_dataframe(), cd.to_dataframe())
    pd.testing.assert_frame_equal(back.cells, cd.cells)
    pd.testing.assert_frame_equal(back.points["rna"], cd.points["rna"])
    assert back.uns["fofct_header"] == cd.uns["fofct_header"]
    assert back.uns["fofct_companions"]["cells"]["header"] == cd.uns["fofct_companions"]["cells"]["header"]
