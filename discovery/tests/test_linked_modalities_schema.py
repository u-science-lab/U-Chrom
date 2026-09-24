"""Discovery schema coverage for linked MuData / scool / cell-spatial records."""

import numpy as np
import pandas as pd

from uchrom_discovery.schema import build_discovery_schema


def _make_cd(coords=None):
    from uchrom import ChromData

    if coords is None:
        coords = np.zeros((4, 3), dtype=float)
    spots = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr1", "chr1"],
        "start": [0, 1_000_000, 0, 1_000_000],
        "end": [1_000_000, 2_000_000, 1_000_000, 2_000_000],
        "trace_id": ["t1", "t1", "t2", "t2"],
        "cell_id": ["cell_a", "cell_a", "cell_b", "cell_b"],
    })
    cells = pd.DataFrame(
        {"cell_type": ["L2/3 IT", "L5 IT"]},
        index=pd.Index(["cell_a", "cell_b"], name="cell_id"),
    )
    return ChromData(coords, spots, cells=cells)


def test_discovery_schema_reports_linked_mudata_and_scool(tmp_path):
    cd = _make_cd()
    cd.link_mudata(tmp_path / "schicar.h5mu", key="schicar", modalities=["rna", "spatial"])
    cd.link_scool(tmp_path / "contacts.scool", key="contacts", cell_name="RNAbarcode")

    schema = build_discovery_schema(cd)

    assert schema["linked_mudata"]["present"] is True
    assert "schicar" in schema["linked_mudata"]["records"]
    assert schema["linked_scool"]["present"] is True
    assert "contacts" in schema["linked_scool"]["records"]
    assert schema["modalities"]["mudata_multiomics"]["present"] is True
    assert schema["modalities"]["single_cell_hic_contacts"]["present"] is True


def test_cell_spatial_coordinates_align_by_cell_id_and_roundtrip(tmp_path):
    from uchrom import ChromData
    cd = _make_cd()
    cd.set_cell_spatial_coordinates(
        np.array([[20.0, 30.0], [10.0, 15.0]]),
        key="tangram_merfish",
        cell_ids=["cell_b", "cell_a"],
        source="MERFISH centroid",
        method="Tangram map_cells_to_space",
        coordinate_system="micron",
        inferred=True,
    )

    path = tmp_path / "spatial_cells.h5cd"
    cd.write(path)
    out = ChromData.read(path)

    assert out.cells.loc["cell_a", "tangram_merfish_spatial_x"] == 10.0
    assert out.cells.loc["cell_a", "tangram_merfish_spatial_y"] == 15.0
    assert out.cells.loc["cell_b", "tangram_merfish_spatial_x"] == 20.0
    assert out.describe_links()["cell_spatial"]["tangram_merfish"]["inferred"] is True

    schema = build_discovery_schema(out)
    assert schema["cell_spatial"]["present"] is True
    assert "tangram_merfish" in schema["cell_spatial"]["records"]
    assert schema["modalities"]["cell_spatial_coordinates"]["present"] is True
