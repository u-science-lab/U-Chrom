"""FOF-CT core + companion tables (cell data, RNA spots) and ``cd.points``."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from chromdata import ChromData
from tests import DATA_DIR, FIXTURES

CELL_TABLE = FIXTURES / "4DNFIFINA2U9.csv"   # Takei 2021 cell data
RNA_TABLE = FIXTURES / "4DNFIJ52NVDV.csv"    # Takei 2021 nascent RNA spots
CORE = DATA_DIR / "4DNFIHF3JCBY.csv"         # Takei 2021 25-kb core table (python -m uchrom.datasets fetch takei)


def _write_core(path, cell_ids):
    """Minimal FOF-CT core table in the 4DN style (quoted, comma-padded headers)."""
    lines = [
        "##FOF-CT_version=v0.1,,,,,,,,,",
        "##XYZ_unit=micron,,,,,,,,,",
        '"#additional_tables: 4dn_FOF-CT_quality, 4dn_FOF-CT_rna, 4dn_FOF-CT_cell",,,,,,,,,',
        "##columns=(Spot_ID,Trace_ID,X,Y,Z,Chrom,Chrom_Start,Chrom_End,Cell_ID,Extra_Cell_ROI_ID)",
    ]
    sid = 1
    for c in cell_ids:
        for i in range(3):
            lines.append(f"{sid},{c}_t,{i}.0,1.0,2.0,chr1,{i * 25000},{(i + 1) * 25000},{c},0")
            sid += 1
    path.write_text("\n".join(lines) + "\n")


def test_core_table_parsing(tmp_path):
    core = tmp_path / "core.csv"
    _write_core(core, ["0_1", "0_2"])
    cd = ChromData.from_fofct(core)
    assert cd.n_spots == 6 and cd.n_traces == 2 and cd.n_cells == 2
    assert cd.uns["xyz_unit"] == "micron"
    assert cd.uns["fofct_header"]["additional_tables"].startswith("4dn_FOF-CT_quality")
    assert list(cd.spots["start"]) == [0, 25000, 50000] * 2
    assert cd.points == {} and len(cd.cells) == 0


def test_companion_tables_real_takei(tmp_path):
    from chromdata.cdata import _read_fofct_table

    ids = _read_fofct_table(CELL_TABLE)[0]["Cell_ID"].astype(str).tolist()
    assert len(ids) == 201
    core = tmp_path / "core.csv"
    _write_core(core, ids)
    cd = ChromData.from_fofct(core, cell_table=CELL_TABLE, rna_table=RNA_TABLE)

    # cells: 201 cells, morphology renamed, 45 genes prefixed
    assert len(cd.cells) == 201 and cd.cells.index.name == "cell_id"
    for col in ("centroid_x", "centroid_y", "nucleus_area_um2", "cytoplasm_area_um2", "keep1"):
        assert col in cd.cells.columns
    genes = [c for c in cd.cells.columns if c.startswith("rna.")]
    assert len(genes) == 45 and "rna.Nanog" in genes
    row = cd.cells.loc["0_2"]
    assert row["rna.Zfp42"] == 95 and row["rna.Mcm2"] == 10 and row["rna.Mki67"] == 1
    assert row["nucleus_area_um2"] == pytest.approx(158.668204)

    # RNA spots: nascent RNA in the same micron frame, linked to cells
    rna = cd.points["rna"]
    assert len(rna) == 3335 and rna["gene"].nunique() == 23
    assert list(rna.columns[:7]) == ["x", "y", "z", "gene", "gene_id", "cell_id", "spot_id"]
    assert rna.loc[0, "gene_id"] == "NM_001363480"  # trailing comma stripped
    assert set(rna["cell_id"]) <= set(ids)
    assert cd.uns["fofct_companions"]["rna"]["source"] == "4DNFIJ52NVDV.csv"

    # round trip and subsetting keep points with their cells
    path = tmp_path / "multi.chromdata.zarr"
    cd.write(path)
    back = ChromData.read(path)
    assert len(back.points["rna"]) == 3335
    assert back.cells.loc["0_2", "rna.Zfp42"] == 95
    one = back.get_cell("0_2")
    assert len(one.points["rna"]) == (rna["cell_id"] == "0_2").sum() > 0
    assert set(one.points["rna"]["cell_id"]) == {"0_2"} and len(one.cells) == 1


def test_warns_on_unmatched_cells(tmp_path):
    core = tmp_path / "core.csv"
    _write_core(core, ["0_1", "zz_1"])
    with pytest.warns(UserWarning, match="cell table"):
        ChromData.from_fofct(core, cell_table=CELL_TABLE)


def test_points_validation_and_copy():
    spots = pd.DataFrame({"chrom": ["chr1"] * 2, "start": [0, 10], "end": [10, 20],
                          "trace_id": ["t", "t"], "cell_id": ["c1", "c1"]})
    with pytest.raises(ValueError, match="coordinate"):
        ChromData(np.zeros((2, 3)), spots, points={"rna": pd.DataFrame({"x": [0.0]})})
    pts = pd.DataFrame({"x": [0.0, 1.0], "y": [0.0, 1.0], "z": [0.0, 1.0], "cell_id": ["c1", "c2"]})
    cd = ChromData(np.zeros((2, 3)), spots, points={"rna": pts})
    cp = cd.copy()
    cp.points["rna"].loc[0, "x"] = 9.0
    assert cd.points["rna"].loc[0, "x"] == 0.0
    assert len(cd[np.array([0])].points["rna"]) == 1  # c2 has no spots left
    assert "points:  {'rna': 2}" in repr(cd)


@pytest.mark.skipif(not CORE.exists(), reason="Takei 2021 core table not downloaded")
def test_full_takei_dataset_matches_companions():
    cd = ChromData.from_fofct(CORE, cell_table=CELL_TABLE, rna_table=RNA_TABLE)
    assert cd.n_spots == 316995 and cd.n_cells == 201
    assert set(cd.cells.index) == {str(c) for c in cd.spots["cell_id"].unique()}
    assert set(cd.points["rna"]["cell_id"]) <= set(cd.cells.index)
